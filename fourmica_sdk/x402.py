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
class PaymentRequirementsV1:
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
    def from_raw(cls, raw: Dict[str, Any]) -> "PaymentRequirementsV1":
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
class PaymentRequirementsV2:
    scheme: str
    network: str
    asset: str
    amount: str
    pay_to: str
    extra: Dict[str, Any]
    max_timeout_seconds: Optional[int] = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "PaymentRequirementsV2":
        def pick(keys, default=None):
            for key in keys:
                if key in raw and raw[key] is not None:
                    return raw[key]
            return default

        amount = pick(["amount"])
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
                    ("amount", amount),
                    ("payTo", pay_to),
                    ("asset", asset),
                ]
                if not v
            ]
            raise X402Error(
                f"payment requirements missing fields: {', '.join(missing)}"
            )

        max_timeout_seconds = pick(["maxTimeoutSeconds"])
        if max_timeout_seconds is not None:
            max_timeout_seconds = int(max_timeout_seconds)

        return cls(
            scheme=scheme,
            network=network,
            asset=asset,
            amount=str(amount),
            pay_to=pay_to,
            extra=pick(["extra"], default={}) or {},
            max_timeout_seconds=max_timeout_seconds,
        )

    def to_payload(self) -> Dict[str, Any]:
        payload = {
            "scheme": self.scheme,
            "network": self.network,
            "asset": self.asset,
            "amount": self.amount,
            "payTo": self.pay_to,
            "extra": dict(self.extra or {}),
        }
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
class X402ResourceInfo:
    url: str
    description: str
    mime_type: str

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "X402ResourceInfo":
        if not isinstance(raw, dict):
            raise X402Error("invalid resource info")
        url = raw.get("url")
        description = raw.get("description")
        mime_type = raw.get("mimeType")
        if not all([url, description, mime_type]):
            raise X402Error("resource info missing fields")
        return cls(url=str(url), description=str(description), mime_type=str(mime_type))

    def to_payload(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass
class X402PaymentRequired:
    x402_version: int
    resource: X402ResourceInfo
    accepts: list[PaymentRequirementsV2]
    error: Optional[str] = None
    extensions: Optional[Dict[str, Any]] = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "X402PaymentRequired":
        if not isinstance(raw, dict):
            raise X402Error("invalid payment required payload")
        x402_version = raw.get("x402Version")
        if x402_version is None:
            raise X402Error("missing x402Version")
        resource = X402ResourceInfo.from_raw(raw.get("resource") or {})
        accepts_raw = raw.get("accepts") or []
        accepts = [PaymentRequirementsV2.from_raw(a) for a in accepts_raw]
        return cls(
            x402_version=int(x402_version),
            resource=resource,
            accepts=accepts,
            error=raw.get("error"),
            extensions=raw.get("extensions"),
        )


@dataclass
class X402PaymentEnvelopeV1:
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
class X402PaymentEnvelopeV2:
    x402_version: int
    accepted: PaymentRequirementsV2
    payload: Dict[str, Any]
    resource: X402ResourceInfo

    def to_payload(self) -> Dict[str, Any]:
        return {
            "x402Version": self.x402_version,
            "accepted": self.accepted.to_payload(),
            "payload": self.payload,
            "resource": self.resource.to_payload(),
        }


@dataclass
class X402SignedPayment:
    header: str
    payload: Dict[str, Any]
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
        self, payment_requirements: PaymentRequirementsV1, user_address: str
    ) -> X402SignedPayment:
        self._validate_scheme(payment_requirements.scheme)
        tab = await self._request_tab(1, payment_requirements, user_address)
        claims = self._build_claims(payment_requirements, tab, user_address)
        try:
            signature = await self.signer.sign_payment(claims, SigningScheme.EIP712)
        except Exception as exc:
            raise X402Error(f"failed to sign payment: {exc}") from exc

        payment_payload = self._build_payment_payload(claims, signature)
        envelope = self._build_envelope_v1(payment_requirements, payment_payload)
        envelope_payload = envelope.to_payload()
        # Backwards-compatibility: facilitators require x402Version at the top level.
        envelope_payload.setdefault("x402Version", envelope.x402_version)
        header_bytes = base64.b64encode(
            self._json_dumps(envelope_payload).encode()
        ).decode()
        return X402SignedPayment(
            header=header_bytes, payload=payment_payload, signature=signature
        )

    async def sign_payment_v2(
        self,
        payment_required: X402PaymentRequired,
        accepted: PaymentRequirementsV2,
        user_address: str,
    ) -> X402SignedPayment:
        self._validate_scheme(accepted.scheme)
        tab = await self._request_tab(2, accepted, user_address, payment_required.resource)
        claims = self._build_claims(accepted, tab, user_address)
        try:
            signature = await self.signer.sign_payment(claims, SigningScheme.EIP712)
        except Exception as exc:
            raise X402Error(f"failed to sign payment: {exc}") from exc

        payment_payload = self._build_payment_payload(claims, signature)
        envelope = self._build_envelope_v2(accepted, payment_required.resource, payment_payload)
        envelope_payload = envelope.to_payload()
        envelope_payload.setdefault("x402Version", envelope.x402_version)
        header_bytes = base64.b64encode(
            self._json_dumps(envelope_payload).encode()
        ).decode()
        return X402SignedPayment(
            header=header_bytes, payload=payment_payload, signature=signature
        )

    async def settle_payment(
        self,
        payment: X402SignedPayment,
        payment_requirements: PaymentRequirementsV1,
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
            raise X402Error(f"settlement response invalid JSON: {exc}") from exc
        if not response.is_success:
            raise X402Error(
                f"settlement failed with status {response.status_code}: {settlement}"
            )
        return X402SettledPayment(payment=payment, settlement=settlement)

    async def _request_tab(
        self,
        x402_version: int,
        payment_requirements: PaymentRequirementsV1 | PaymentRequirementsV2,
        user_address: str,
        resource: X402ResourceInfo | None = None,
    ) -> TabResponse:
        extra = PaymentRequirementsExtra.from_raw(payment_requirements.extra)
        if not extra.tab_endpoint:
            raise X402Error("missing tabEndpoint in paymentRequirements.extra")
        payload = {
            "x402Version": x402_version,
            "userAddress": user_address,
            "paymentRequirements": payment_requirements.to_payload(),
        }
        if resource is not None:
            payload["resource"] = resource.to_payload()
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
        def pick(keys, default=None):
            for key in keys:
                if key in body and body[key] is not None:
                    return body[key]
            return default

        return TabResponse(
            tab_id=pick(["tabId", "tab_id"]),
            user_address=pick(["userAddress", "user_address"]),
            next_req_id=pick(["nextReqId", "next_req_id", "reqId", "req_id"]),
        )

    def _build_claims(
        self,
        requirements: PaymentRequirementsV1 | PaymentRequirementsV2,
        tab: TabResponse,
        user_address: str,
    ) -> PaymentGuaranteeRequestClaims:
        tab_id = self._parse_u256(tab.tab_id)
        req_id = self._parse_u256(tab.next_req_id) if tab.next_req_id else 0
        amount_raw = (
            requirements.max_amount_required
            if isinstance(requirements, PaymentRequirementsV1)
            else requirements.amount
        )
        amount = self._parse_u256(amount_raw)
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
    def _build_payment_payload(
        claims: PaymentGuaranteeRequestClaims, signature: PaymentSignature
    ) -> Dict[str, Any]:
        return {
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

    @staticmethod
    def _build_envelope_v1(
        payment_requirements: PaymentRequirementsV1,
        payment_payload: Dict[str, Any],
    ) -> X402PaymentEnvelopeV1:
        return X402PaymentEnvelopeV1(
            x402_version=1,
            scheme=payment_requirements.scheme,
            network=payment_requirements.network,
            payload=payment_payload,
        )

    @staticmethod
    def _build_envelope_v2(
        accepted: PaymentRequirementsV2,
        resource: X402ResourceInfo,
        payment_payload: Dict[str, Any],
    ) -> X402PaymentEnvelopeV2:
        return X402PaymentEnvelopeV2(
            x402_version=2,
            accepted=accepted,
            payload=payment_payload,
            resource=resource,
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


# Backwards-compatible alias for older code
PaymentRequirements = PaymentRequirementsV1
