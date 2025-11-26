from __future__ import annotations

from typing import Union

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import remove_0x_prefix

from .errors import VerificationError
from .models import PaymentGuaranteeClaims
from .utils import parse_u256

_CLAIMS_TYPES = [
    "bytes32",  # domain
    "uint256",  # tab_id
    "uint256",  # req_id
    "address",  # client
    "address",  # recipient
    "uint256",  # amount
    "uint256",  # total_amount
    "address",  # asset
    "uint64",  # timestamp
    "uint64",  # version
]


def _ensure_domain_bytes(domain: Union[str, bytes]) -> bytes:
    if isinstance(domain, bytes):
        if len(domain) != 32:
            raise VerificationError("domain separator must be 32 bytes")
        return domain
    domain_hex = remove_0x_prefix(str(domain))
    data = bytes.fromhex(domain_hex)
    if len(data) != 32:
        raise VerificationError("domain separator must be 32 bytes")
    return data


def encode_guarantee_claims(claims: PaymentGuaranteeClaims) -> bytes:
    if claims.version != 1:
        raise VerificationError(
            f"unsupported guarantee claims version: {claims.version}"
        )

    domain = _ensure_domain_bytes(claims.domain)
    encoded_claims = abi_encode(
        _CLAIMS_TYPES,
        [
            domain,
            parse_u256(claims.tab_id),
            parse_u256(claims.req_id),
            claims.user_address,
            claims.recipient_address,
            parse_u256(claims.amount),
            parse_u256(claims.total_amount),
            claims.asset_address,
            int(claims.timestamp),
            int(claims.version),
        ],
    )

    return abi_encode(["uint64", "bytes"], [int(claims.version), encoded_claims])


def decode_guarantee_claims(data: Union[str, bytes]) -> PaymentGuaranteeClaims:
    raw_bytes = (
        bytes.fromhex(remove_0x_prefix(data)) if isinstance(data, str) else bytes(data)
    )
    version, encoded = abi_decode(["uint64", "bytes"], raw_bytes)

    if version != 1:
        raise VerificationError(f"unsupported guarantee claims version: {version}")

    (
        domain,
        tab_id,
        req_id,
        client,
        recipient,
        amount,
        total_amount,
        asset,
        timestamp,
        claims_version,
    ) = abi_decode(_CLAIMS_TYPES, encoded)

    return PaymentGuaranteeClaims(
        domain=domain,
        user_address=client,
        recipient_address=recipient,
        tab_id=parse_u256(tab_id),
        req_id=parse_u256(req_id),
        amount=parse_u256(amount),
        total_amount=parse_u256(total_amount),
        asset_address=asset,
        timestamp=int(timestamp),
        version=int(claims_version),
    )
