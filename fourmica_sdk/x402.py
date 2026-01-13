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
from .utils import ValidationError, normalize_address, parse_u256, validate_url

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

        amount = pick(["maxAmountRequired"])
        pay_to = pick(["payTo"])
        asset = pick(["asset"])
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
            mime_type=pick(["mimeType"]),
            output_schema=pick(["outputSchema"]),
            max_timeout_seconds=pick(["maxTimeoutSeconds"]),
        )

    def to_payload(self) -> Dict[str, Any]:
        payload = {
            "scheme": self.scheme,
            "network": self.network,
            "maxAmountRequired": self.max_amount_required,
            "payTo": self.pay_to,
            "asset": self.asset,
            "extra": dict(self.extra or {}),
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
        if not isinstance(raw, dict):
            raise X402Error("invalid paymentRequirements.extra")
        tab_endpoint = raw.get("tabEndpoint")
        if tab_endpoint is None:
            return cls(tab_endpoint=None)
        try:
            tab_endpoint = validate_url(str(tab_endpoint))
        except ValidationError as exc:
            raise X402Error(f"invalid tabEndpoint: {exc}") from exc
        return cls(tab_endpoint=tab_endpoint)


@dataclass
class TabResponse:
    tab_id: str
    user_address: str
    next_req_id: Optional[str] = None


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
        try:
            signature = await self.signer.sign_payment(claims, SigningScheme.EIP712)
        except Exception as exc:
            raise X402Error(f"failed to sign payment: {exc}") from exc

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
        from urllib.parse import urljoin

        try:
            base_url = validate_url(facilitator_url)
        except ValidationError as exc:
            raise X402Error(f"invalid facilitator url: {exc}") from exc
        url = urljoin(base_url, "settle")
        try:
            response = await self.http.post(
                url,
                json={
                    "x402Version": 1,
                    "paymentHeader": payment.header,
                    "paymentRequirements": payment_requirements.to_payload(),
                },
            )
        except httpx.HTTPError as exc:
            raise X402Error(str(exc)) from exc
        try:
            settlement = response.json()
        except Exception as exc:
            raise X402Error(
                f"settlement response invalid JSON: {exc}"
            ) from exc
        if not response.is_success:
            raise X402Error(
                f"settlement failed with status {response.status_code}: {settlement}"
            )
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
        try:
            response = await self.http.post(extra.tab_endpoint, json=payload)
        except httpx.HTTPError as exc:
            raise X402Error(str(exc)) from exc
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise X402Error(str(exc)) from exc
        try:
            body = response.json()
        except Exception as exc:
            raise X402Error(f"tab response invalid JSON: {exc}") from exc
        return TabResponse(
            tab_id=body.get("tabId"),
            user_address=body.get("userAddress"),
            next_req_id=body.get("nextReqId") or body.get("reqId"),
        )

    def _build_claims(
        self, requirements: PaymentRequirements, tab: TabResponse, user_address: str
    ) -> PaymentGuaranteeRequestClaims:
        tab_id = self._parse_u256(tab.tab_id)
        req_id = self._parse_u256(tab.next_req_id) if tab.next_req_id else 0
        amount = self._parse_u256(requirements.max_amount_required)
        if tab.user_address.lower() != user_address.lower():
            raise X402Error(
                f"user mismatch in paymentRequirements: found {tab.user_address}, expected {user_address}"
            )
        import time

        try:
            return PaymentGuaranteeRequestClaims.new(
                user_address,
                normalize_address(requirements.pay_to),
                tab_id,
                req_id,
                amount,
                int(time.time()),
                requirements.asset,
            )
        except ValidationError as exc:
            raise X402Error(str(exc)) from exc

    @staticmethod
    def _validate_scheme(scheme: str) -> None:
        if "4mica" not in scheme.lower():
            raise X402Error(f"invalid scheme: {scheme}")

    @staticmethod
    def _parse_u256(raw: Optional[str]) -> int:
        try:
            return parse_u256(raw or "0")
        except ValidationError as exc:
            raise X402Error(f"invalid number for field {raw}: {exc}") from exc

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
                "req_id": hex(int(claims.req_id)),
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
