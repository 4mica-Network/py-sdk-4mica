import pytest
from eth_account import Account

from fourmica_sdk.errors import SigningError
from fourmica_sdk.models import PaymentGuaranteeRequestClaims, SigningScheme
from fourmica_sdk.signing import CorePublicParameters, PaymentSigner


def build_params() -> CorePublicParameters:
    return CorePublicParameters(
        public_key=b"",
        contract_address="0x0000000000000000000000000000000000000000",
        ethereum_http_rpc_url="https://example.com",
        eip712_name="4Mica",
        eip712_version="1",
        chain_id=1,
    )


@pytest.mark.asyncio
async def test_sign_request_rejects_address_mismatch():
    signer = PaymentSigner("11" * 32)
    claims = PaymentGuaranteeRequestClaims.new(
        "0x0000000000000000000000000000000000000011",
        "0x0000000000000000000000000000000000000002",
        tab_id=1,
        req_id=1,
        amount=5,
        timestamp=1234,
        erc20_token=None,
    )
    with pytest.raises(SigningError):
        await signer.sign_request(build_params(), claims, SigningScheme.EIP712)


@pytest.mark.asyncio
async def test_sign_request_eip712_produces_signature():
    private_key = "0x59c6995e998f97a5a0044976f7be35d5ad91c0cfa55b5cfb20b07a1c60f4c5bc"
    account = Account.from_key(private_key)
    signer = PaymentSigner(private_key)
    claims = PaymentGuaranteeRequestClaims.new(
        account.address,
        "0x0000000000000000000000000000000000000002",
        tab_id=42,
        req_id=7,
        amount=123,
        timestamp=999,
        erc20_token=None,
    )

    signature = await signer.sign_request(build_params(), claims, SigningScheme.EIP712)
    assert signature.scheme == SigningScheme.EIP712
    # 65-byte signature expressed as 0x-prefixed hex (132 chars).
    assert signature.signature.startswith("0x")
    assert len(signature.signature) == 132
