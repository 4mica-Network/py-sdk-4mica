from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from .utils import normalize_address, parse_u256


def _get_any(raw: Dict[str, Any], *keys: str) -> Any:
    """Return the first present key (even if falsy) to handle snake/camel responses."""
    for key in keys:
        if key in raw:
            return raw[key]
    return None


class SigningScheme(str, Enum):
    EIP712 = "eip712"
    EIP191 = "eip191"


@dataclass
class PaymentSignature:
    signature: str
    scheme: SigningScheme


@dataclass
class PaymentGuaranteeRequestClaims:
    user_address: str
    recipient_address: str
    tab_id: int
    req_id: int
    amount: int
    timestamp: int
    asset_address: str

    @classmethod
    def new(
        cls,
        user_address: str,
        recipient_address: str,
        tab_id: int,
        req_id: int,
        amount: int,
        timestamp: int,
        erc20_token: Optional[str],
    ) -> "PaymentGuaranteeRequestClaims":
        asset = erc20_token or "0x0000000000000000000000000000000000000000"
        return cls(
            user_address=normalize_address(user_address),
            recipient_address=normalize_address(recipient_address),
            tab_id=parse_u256(tab_id),
            req_id=parse_u256(req_id),
            amount=parse_u256(amount),
            timestamp=int(timestamp),
            asset_address=normalize_address(asset),
        )


@dataclass
class PaymentGuaranteeClaims:
    domain: bytes
    user_address: str
    recipient_address: str
    tab_id: int
    req_id: int
    amount: int
    total_amount: int
    asset_address: str
    timestamp: int
    version: int


@dataclass
class BLSCert:
    claims: str  # hex of abi-encoded guarantee claims (with version prefix)
    signature: str  # hex of compressed G2 signature (96 bytes)


@dataclass
class TabPaymentStatus:
    paid: int
    remunerated: bool
    asset: str


@dataclass
class UserInfo:
    asset: str
    collateral: int
    withdrawal_request_amount: int
    withdrawal_request_timestamp: int


@dataclass
class TabInfo:
    tab_id: int
    user_address: str
    recipient_address: str
    asset_address: str
    start_timestamp: int
    ttl_seconds: int
    status: str
    settlement_status: str
    created_at: int
    updated_at: int

    @classmethod
    def from_rpc(cls, raw: Dict[str, Any]) -> "TabInfo":
        return cls(
            tab_id=parse_u256(_get_any(raw, "tab_id", "tabId")),
            user_address=_get_any(raw, "user_address", "userAddress"),
            recipient_address=_get_any(raw, "recipient_address", "recipientAddress"),
            asset_address=_get_any(raw, "asset_address", "assetAddress"),
            start_timestamp=int(_get_any(raw, "start_timestamp", "startTimestamp")),
            ttl_seconds=int(_get_any(raw, "ttl_seconds", "ttlSeconds")),
            status=_get_any(raw, "status"),
            settlement_status=_get_any(raw, "settlement_status", "settlementStatus"),
            created_at=int(_get_any(raw, "created_at", "createdAt")),
            updated_at=int(_get_any(raw, "updated_at", "updatedAt")),
        )


@dataclass
class GuaranteeInfo:
    tab_id: int
    req_id: int
    from_address: str
    to_address: str
    asset_address: str
    amount: int
    timestamp: int
    certificate: Optional[str]

    @classmethod
    def from_rpc(cls, raw: Dict[str, Any]) -> "GuaranteeInfo":
        return cls(
            tab_id=parse_u256(_get_any(raw, "tab_id", "tabId")),
            req_id=parse_u256(_get_any(raw, "req_id", "reqId")),
            from_address=_get_any(raw, "from_address", "fromAddress"),
            to_address=_get_any(raw, "to_address", "toAddress"),
            asset_address=_get_any(raw, "asset_address", "assetAddress"),
            amount=parse_u256(_get_any(raw, "amount")),
            timestamp=int(
                _get_any(raw, "start_timestamp", "startTimestamp", "timestamp") or 0
            ),
            certificate=_get_any(raw, "certificate"),
        )


@dataclass
class PendingRemunerationInfo:
    tab: TabInfo
    latest_guarantee: Optional[GuaranteeInfo]

    @classmethod
    def from_rpc(cls, raw: Dict[str, Any]) -> "PendingRemunerationInfo":
        return cls(
            tab=TabInfo.from_rpc(_get_any(raw, "tab")),
            latest_guarantee=GuaranteeInfo.from_rpc(
                _get_any(raw, "latest_guarantee", "latestGuarantee")
            )
            if _get_any(raw, "latest_guarantee", "latestGuarantee")
            else None,
        )


@dataclass
class CollateralEventInfo:
    id: str
    user_address: str
    asset_address: str
    amount: int
    event_type: str
    tab_id: Optional[int]
    req_id: Optional[int]
    tx_id: Optional[str]
    created_at: int

    @classmethod
    def from_rpc(cls, raw: Dict[str, Any]) -> "CollateralEventInfo":
        return cls(
            id=_get_any(raw, "id"),
            user_address=_get_any(raw, "user_address", "userAddress"),
            asset_address=_get_any(raw, "asset_address", "assetAddress"),
            amount=parse_u256(_get_any(raw, "amount")),
            event_type=_get_any(raw, "event_type", "eventType"),
            tab_id=parse_u256(_get_any(raw, "tab_id", "tabId"))
            if _get_any(raw, "tab_id", "tabId") is not None
            else None,
            req_id=parse_u256(_get_any(raw, "req_id", "reqId"))
            if _get_any(raw, "req_id", "reqId") is not None
            else None,
            tx_id=_get_any(raw, "tx_id", "txId"),
            created_at=int(_get_any(raw, "created_at", "createdAt")),
        )


@dataclass
class AssetBalanceInfo:
    user_address: str
    asset_address: str
    total: int
    locked: int
    version: int
    updated_at: int

    @classmethod
    def from_rpc(cls, raw: Dict[str, Any]) -> "AssetBalanceInfo":
        return cls(
            user_address=_get_any(raw, "user_address", "userAddress"),
            asset_address=_get_any(raw, "asset_address", "assetAddress"),
            total=parse_u256(_get_any(raw, "total")),
            locked=parse_u256(_get_any(raw, "locked")),
            version=int(_get_any(raw, "version")),
            updated_at=int(_get_any(raw, "updated_at", "updatedAt")),
        )


@dataclass
class RecipientPaymentInfo:
    user_address: str
    recipient_address: str
    tx_hash: str
    amount: int
    verified: bool
    finalized: bool
    failed: bool
    created_at: int

    @classmethod
    def from_rpc(cls, raw: Dict[str, Any]) -> "RecipientPaymentInfo":
        return cls(
            user_address=_get_any(raw, "user_address", "userAddress"),
            recipient_address=_get_any(raw, "recipient_address", "recipientAddress"),
            tx_hash=_get_any(raw, "tx_hash", "txHash"),
            amount=parse_u256(_get_any(raw, "amount")),
            verified=bool(_get_any(raw, "verified")),
            finalized=bool(_get_any(raw, "finalized")),
            failed=bool(_get_any(raw, "failed")),
            created_at=int(_get_any(raw, "created_at", "createdAt")),
        )
