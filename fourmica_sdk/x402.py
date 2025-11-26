from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol

import httpx

from .errors import X402Error
from .models import (
    PaymentGuaranteeRequestClaims,
    PaymentSignature,
    SigningScheme,
)
from .utils import normalize_address, parse_u256

if TYPE_CHECKING:
    from .client import Client


@dataclass
class PaymentRequirements:
    scheme: str
    network: str
    max_amount_required: str
    pay_to: str
    asset: str
    extra: Dict[str, Any]
    resource: Optional[str] = None
    description: Optional[str] = None
    mime_type: Optional[str] = None
    output_schema: Optional[Any] = None
    max_timeout_seconds: Optional[int] = None

    def to_payload(self) -> Dict[str, Any]:
        # Use asdict for clarity instead of relying on __dict__.
        return asdict(self)


@dataclass
class PaymentRequirementsExtra:
    tab_endpoint: Optional[str]

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "PaymentRequirementsExtra":
        raw = raw or {}
        return cls(tab_endpoint=raw.get("tabEndpoint") or raw.get("tab_endpoint"))


@dataclass
class TabResponse:
    tab_id: str
    user_address: str


@dataclass
class X402PaymentEnvelope:
    x402_version: int
    scheme: str
    network: str
    payload: Dict[str, Any]


@dataclass
class X402SignedPayment:
    header: str
    claims: PaymentGuaranteeRequestClaims
    signature: PaymentSignature


@dataclass
class X402SettledPayment:
    payment: X402SignedPayment
    settlement: Any


class FlowSigner(Protocol):
    async def sign_payment(
        self, claims: PaymentGuaranteeRequestClaims, scheme: SigningScheme
    ) -> PaymentSignature: ...


class X402Flow:
    def __init__(
        self, signer: FlowSigner, client: Optional[httpx.AsyncClient] = None
    ) -> None:
        self.signer = signer
        self.http = client or httpx.AsyncClient()

    @classmethod
    def from_client(cls, client: "Client") -> "X402Flow":  # type: ignore[name-defined]
        return cls(client.user)  # Client.user implements sign_payment

    async def sign_payment(
        self, payment_requirements: PaymentRequirements, user_address: str
    ) -> X402SignedPayment:
        self._validate_scheme(payment_requirements.scheme)
        tab = await self._request_tab(payment_requirements, user_address)
        claims = self._build_claims(payment_requirements, tab, user_address)
        signature = await self.signer.sign_payment(claims, SigningScheme.EIP712)

        envelope = self._build_envelope(payment_requirements, claims, signature)
        header_bytes = base64.b64encode(self._json_dumps(envelope).encode()).decode()
        return X402SignedPayment(
            header=header_bytes, claims=claims, signature=signature
        )

    async def settle_payment(
        self,
        payment: X402SignedPayment,
        payment_requirements: PaymentRequirements,
        facilitator_url: str,
    ) -> X402SettledPayment:
        url = facilitator_url.rstrip("/") + "/settle"
        response = await self.http.post(
            url,
            json={
                "x402_version": 1,
                "payment_header": payment.header,
                "payment_requirements": payment_requirements.to_payload(),
            },
        )
        data = await response.aread()
        if not response.is_success:
            raise X402Error(
                f"settlement failed with status {response.status_code}: {data.decode()}"
            )
        settlement = response.json()
        return X402SettledPayment(payment=payment, settlement=settlement)

    async def _request_tab(
        self, payment_requirements: PaymentRequirements, user_address: str
    ) -> TabResponse:
        extra = PaymentRequirementsExtra.from_raw(payment_requirements.extra)
        if not extra.tab_endpoint:
            raise X402Error("missing tabEndpoint in paymentRequirements.extra")
        payload = {
            "user_address": user_address,
            "payment_requirements": payment_requirements.to_payload(),
        }
        response = await self.http.post(extra.tab_endpoint, json=payload)
        if not response.is_success:
            raise X402Error(
                f"tab resolution failed: {response.status_code} {response.text}"
            )
        body = response.json()
        return TabResponse(
            tab_id=body.get("tabId") or body.get("tab_id"),
            user_address=body.get("userAddress") or body.get("user_address"),
        )

    def _build_claims(
        self, requirements: PaymentRequirements, tab: TabResponse, user_address: str
    ) -> PaymentGuaranteeRequestClaims:
        tab_id = parse_u256(tab.tab_id)
        amount = parse_u256(requirements.max_amount_required)
        if tab.user_address.lower() != user_address.lower():
            raise X402Error(
                f"user mismatch in paymentRequirements: found {tab.user_address}, expected {user_address}"
            )
        import time

        return PaymentGuaranteeRequestClaims.new(
            user_address,
            normalize_address(requirements.pay_to),
            tab_id,
            amount,
            int(time.time()),
            requirements.asset,
        )

    @staticmethod
    def _validate_scheme(scheme: str) -> None:
        if "4mica" not in scheme.lower():
            raise X402Error(f"invalid scheme: {scheme}")

    @staticmethod
    def _build_envelope(
        payment_requirements: PaymentRequirements,
        claims: PaymentGuaranteeRequestClaims,
        signature: PaymentSignature,
    ) -> X402PaymentEnvelope:
        payload = {
            "claims": {
                "version": "v1",
                "user_address": claims.user_address,
                "recipient_address": claims.recipient_address,
                "tab_id": hex(int(claims.tab_id)),
                "amount": hex(int(claims.amount)),
                "asset_address": claims.asset_address,
                "timestamp": int(claims.timestamp),
            },
            "signature": signature.signature,
            "scheme": signature.scheme.value,
        }
        return X402PaymentEnvelope(
            x402_version=1,
            scheme=payment_requirements.scheme,
            network=payment_requirements.network,
            payload=payload,
        )

    @staticmethod
    def _json_dumps(obj: Any) -> str:
        import json

        def default(o: Any):
            if hasattr(o, "value"):
                return getattr(o, "value")
            if hasattr(o, "__dict__"):
                return o.__dict__
            return str(o)

        return json.dumps(obj, default=default)
