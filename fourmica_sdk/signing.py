from __future__ import annotations

import asyncio

from eth_abi import encode as abi_encode
from eth_account import Account
from eth_account.messages import encode_defunct, encode_typed_data

from .errors import SigningError
from .models import PaymentGuaranteeRequestClaims, PaymentSignature, SigningScheme
from .utils import ValidationError, normalize_address


def _build_typed_message(
    params: "CorePublicParameters", claims: PaymentGuaranteeRequestClaims
):
    """Mirror the Solidity struct hashing used in the Rust SDK."""
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
            ],
            "SolGuaranteeRequestClaimsV1": [
                {"name": "user", "type": "address"},
                {"name": "recipient", "type": "address"},
                {"name": "tabId", "type": "uint256"},
                {"name": "amount", "type": "uint256"},
                {"name": "asset", "type": "address"},
                {"name": "timestamp", "type": "uint64"},
            ],
        },
        "primaryType": "SolGuaranteeRequestClaimsV1",
        "domain": {
            "name": params.eip712_name,
            "version": params.eip712_version,
            "chainId": params.chain_id,
        },
        "message": {
            "user": claims.user_address,
            "recipient": claims.recipient_address,
            "tabId": int(claims.tab_id),
            "amount": int(claims.amount),
            "asset": claims.asset_address,
            "timestamp": int(claims.timestamp),
        },
    }


def _encode_eip191(claims: PaymentGuaranteeRequestClaims) -> bytes:
    payload = abi_encode(
        ["address", "address", "uint256", "uint256", "address", "uint64"],
        [
            claims.user_address,
            claims.recipient_address,
            int(claims.tab_id),
            int(claims.amount),
            claims.asset_address,
            int(claims.timestamp),
        ],
    )
    return payload


class CorePublicParameters:
    """Network parameters returned by the facilitator."""

    def __init__(
        self,
        public_key: bytes,
        contract_address: str,
        ethereum_http_rpc_url: str,
        eip712_name: str,
        eip712_version: str,
        chain_id: int,
    ) -> None:
        self.public_key = public_key
        self.contract_address = contract_address
        self.ethereum_http_rpc_url = ethereum_http_rpc_url
        self.eip712_name = eip712_name
        self.eip712_version = eip712_version
        self.chain_id = chain_id

    @classmethod
    def from_rpc(cls, payload: dict) -> "CorePublicParameters":
        pk = (
            payload.get("public_key")
            if "public_key" in payload
            else payload.get("publicKey")
        )
        if isinstance(pk, str):
            pk_bytes = bytes.fromhex(pk.removeprefix("0x"))
        else:
            pk_bytes = bytes(pk or [])

        return cls(
            public_key=pk_bytes,
            contract_address=payload.get("contract_address")
            or payload.get("contractAddress"),
            ethereum_http_rpc_url=payload.get("ethereum_http_rpc_url")
            or payload.get("ethereumHttpRpcUrl"),
            eip712_name=payload.get("eip712_name", payload.get("eip712Name", "4Mica")),
            eip712_version=payload.get(
                "eip712_version", payload.get("eip712Version", "1")
            ),
            chain_id=int(payload.get("chain_id") or payload.get("chainId")),
        )


class PaymentSigner:
    """Signs payment guarantee requests using EIP-712 or EIP-191."""

    def __init__(self, private_key: str) -> None:
        self.account = Account.from_key(private_key)

    async def sign_request(
        self,
        params: CorePublicParameters,
        claims: PaymentGuaranteeRequestClaims,
        scheme: SigningScheme = SigningScheme.EIP712,
    ) -> PaymentSignature:
        if normalize_address(self.account.address) != normalize_address(
            claims.user_address
        ):
            raise SigningError(
                f"address mismatch: signer {self.account.address} "
                f"!= claims.user_address {claims.user_address}"
            )

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self._sign_sync(params, claims, scheme)
        )

    def _sign_sync(
        self,
        params: CorePublicParameters,
        claims: PaymentGuaranteeRequestClaims,
        scheme: SigningScheme,
    ) -> PaymentSignature:
        try:
            if scheme == SigningScheme.EIP712:
                message = encode_typed_data(
                    full_message=_build_typed_message(params, claims)
                )
                signed = self.account.sign_message(message)
            elif scheme == SigningScheme.EIP191:
                payload = _encode_eip191(claims)
                message = encode_defunct(primitive=payload)
                signed = self.account.sign_message(message)
            else:
                raise SigningError(f"unsupported signing scheme: {scheme}")
        except (ValueError, ValidationError) as exc:
            raise SigningError(str(exc)) from exc

        return PaymentSignature(signature=signed.signature.hex(), scheme=scheme)
