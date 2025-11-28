from __future__ import annotations

import base64
from dataclasses import dataclass
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

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "PaymentRequirements":
        def pick(keys, default=None):
            for key in keys:
                if key in raw and raw[key] is not None:
                    return raw[key]
            return default

        amount = pick(["maxAmountRequired", "max_amount_required"])
        pay_to = pick(["payTo", "pay_to"])
        asset = pick(["asset", "assetAddress", "asset_address"])
        scheme = pick(["scheme"])
        network = pick(["network"])
        if not all([amount, pay_to, asset, scheme, network]):
            missing = [
                k
                for k, v in [
                    ("scheme", scheme),
                    ("network", network),
                    ("maxAmountRequired", amount),
                    ("payTo", pay_to),
                    ("asset", asset),
                ]
                if not v
            ]
            raise X402Error(
                f"payment requirements missing fields: {', '.join(missing)}"
            )

        return cls(
            scheme=scheme,
            network=network,
            max_amount_required=str(amount),
            pay_to=pay_to,
            asset=asset,
            extra=pick(["extra"], default={}) or {},
            resource=pick(["resource"]),
            description=pick(["description"]),
            mime_type=pick(["mimeType", "mime_type"]),
            output_schema=pick(["outputSchema", "output_schema"]),
            max_timeout_seconds=pick(["maxTimeoutSeconds", "max_timeout_seconds"]),
        )

    def to_payload(self) -> Dict[str, Any]:
        extra_payload = dict(self.extra or {})
        if "tab_endpoint" in extra_payload and "tabEndpoint" not in extra_payload:
            extra_payload["tabEndpoint"] = extra_payload.pop("tab_endpoint")

        payload = {
            "scheme": self.scheme,
            "network": self.network,
            "maxAmountRequired": self.max_amount_required,
            "payTo": self.pay_to,
            "asset": self.asset,
            "extra": extra_payload,
        }
        if self.resource is not None:
            payload["resource"] = self.resource
        if self.description is not None:
            payload["description"] = self.description
        if self.mime_type is not None:
            payload["mimeType"] = self.mime_type
        if self.output_schema is not None:
            payload["outputSchema"] = self.output_schema
        if self.max_timeout_seconds is not None:
            payload["maxTimeoutSeconds"] = self.max_timeout_seconds
        return payload


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

    def to_payload(self) -> Dict[str, Any]:
        return {
            "x402Version": self.x402_version,
            "scheme": self.scheme,
            "network": self.network,
            "payload": self.payload,
        }


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
        payload = envelope.to_payload()
        # Backwards-compatibility: facilitators require x402Version at the top level.
        payload.setdefault("x402Version", envelope.x402_version)
        header_bytes = base64.b64encode(self._json_dumps(payload).encode()).decode()
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
                "x402Version": 1,
                "paymentHeader": payment.header,
                "paymentRequirements": payment_requirements.to_payload(),
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
            "userAddress": user_address,
            "paymentRequirements": payment_requirements.to_payload(),
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
