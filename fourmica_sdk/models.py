from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from .utils import normalize_address, parse_u256


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
    amount: int
    timestamp: int
    asset_address: str

    @classmethod
    def new(
        cls,
        user_address: str,
        recipient_address: str,
        tab_id: int,
        amount: int,
        timestamp: int,
        erc20_token: Optional[str],
    ) -> "PaymentGuaranteeRequestClaims":
        asset = erc20_token or "0x0000000000000000000000000000000000000000"
        return cls(
            user_address=normalize_address(user_address),
            recipient_address=normalize_address(recipient_address),
            tab_id=parse_u256(tab_id),
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
            tab_id=parse_u256(raw["tab_id"]),
            user_address=raw["user_address"],
            recipient_address=raw["recipient_address"],
            asset_address=raw["asset_address"],
            start_timestamp=int(raw["start_timestamp"]),
            ttl_seconds=int(raw["ttl_seconds"]),
            status=raw["status"],
            settlement_status=raw["settlement_status"],
            created_at=int(raw["created_at"]),
            updated_at=int(raw["updated_at"]),
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
            tab_id=parse_u256(raw["tab_id"]),
            req_id=parse_u256(raw["req_id"]),
            from_address=raw["from_address"],
            to_address=raw["to_address"],
            asset_address=raw["asset_address"],
            amount=parse_u256(raw["amount"]),
            timestamp=int(raw.get("start_timestamp") or raw.get("timestamp") or 0),
            certificate=raw.get("certificate"),
        )


@dataclass
class PendingRemunerationInfo:
    tab: TabInfo
    latest_guarantee: Optional[GuaranteeInfo]

    @classmethod
    def from_rpc(cls, raw: Dict[str, Any]) -> "PendingRemunerationInfo":
        return cls(
            tab=TabInfo.from_rpc(raw["tab"]),
            latest_guarantee=GuaranteeInfo.from_rpc(raw["latest_guarantee"])
            if raw.get("latest_guarantee")
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
            id=raw["id"],
            user_address=raw["user_address"],
            asset_address=raw["asset_address"],
            amount=parse_u256(raw["amount"]),
            event_type=raw["event_type"],
            tab_id=parse_u256(raw["tab_id"]) if raw.get("tab_id") is not None else None,
            req_id=parse_u256(raw["req_id"]) if raw.get("req_id") is not None else None,
            tx_id=raw.get("tx_id"),
            created_at=int(raw["created_at"]),
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
            user_address=raw["user_address"],
            asset_address=raw["asset_address"],
            total=parse_u256(raw["total"]),
            locked=parse_u256(raw["locked"]),
            version=int(raw["version"]),
            updated_at=int(raw["updated_at"]),
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
            user_address=raw["user_address"],
            recipient_address=raw["recipient_address"],
            tx_hash=raw["tx_hash"],
            amount=parse_u256(raw["amount"]),
            verified=bool(raw["verified"]),
            finalized=bool(raw["finalized"]),
            failed=bool(raw["failed"]),
            created_at=int(raw["created_at"]),
        )
