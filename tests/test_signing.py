import pytest
from eth_account import Account

from fourmica_sdk.errors import SigningError
from fourmica_sdk.models import (
    PaymentGuaranteeRequestClaims,
    PaymentGuaranteeRequestClaimsV2,
    SigningScheme,
)
from fourmica_sdk.signing import CorePublicParameters, PaymentSigner
from fourmica_sdk.validation import (
    compute_validation_request_hash,
    compute_validation_subject_hash,
)


def build_params() -> CorePublicParameters:
    return CorePublicParameters(
        public_key=b"",
        contract_address="0x0000000000000000000000000000000000000000",
        ethereum_http_rpc_url="https://example.com",
        eip712_name="4Mica",
        eip712_version="1",
        chain_id=1,
    )


def build_v2_claims(user_address: str) -> PaymentGuaranteeRequestClaimsV2:
    base = PaymentGuaranteeRequestClaims.new(
        user_address,
        "0x0000000000000000000000000000000000000002",
        tab_id=42,
        req_id=2,
        amount=123,
        timestamp=999,
        erc20_token=None,
    )
    subject_hash = compute_validation_subject_hash(base)
    partial = PaymentGuaranteeRequestClaimsV2.new(
        user_address=base.user_address,
        recipient_address=base.recipient_address,
        tab_id=base.tab_id,
        req_id=base.req_id,
        amount=base.amount,
        timestamp=base.timestamp,
        erc20_token=base.asset_address,
        validation_registry_address="0x0000000000000000000000000000000000000011",
        validation_request_hash="0x" + "00" * 32,
        validation_chain_id=1,
        validator_address="0x0000000000000000000000000000000000000022",
        validator_agent_id=7,
        min_validation_score=80,
        validation_subject_hash=subject_hash,
        required_validation_tag="hard-finality",
    )
    return PaymentGuaranteeRequestClaimsV2.new(
        user_address=partial.user_address,
        recipient_address=partial.recipient_address,
        tab_id=partial.tab_id,
        req_id=partial.req_id,
        amount=partial.amount,
        timestamp=partial.timestamp,
        erc20_token=partial.asset_address,
        validation_registry_address=partial.validation_registry_address,
        validation_request_hash=compute_validation_request_hash(partial),
        validation_chain_id=partial.validation_chain_id,
        validator_address=partial.validator_address,
        validator_agent_id=partial.validator_agent_id,
        min_validation_score=partial.min_validation_score,
        validation_subject_hash=partial.validation_subject_hash,
        required_validation_tag=partial.required_validation_tag,
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


@pytest.mark.asyncio
async def test_sign_request_eip191_produces_signature():
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

    signature = await signer.sign_request(build_params(), claims, SigningScheme.EIP191)
    assert signature.scheme == SigningScheme.EIP191
    assert signature.signature.startswith("0x")
    assert len(signature.signature) == 132


@pytest.mark.asyncio
async def test_sign_request_v2_eip712_produces_signature():
    private_key = "0x59c6995e998f97a5a0044976f7be35d5ad91c0cfa55b5cfb20b07a1c60f4c5bc"
    account = Account.from_key(private_key)
    signer = PaymentSigner(private_key)
    claims = build_v2_claims(account.address)

    signature = await signer.sign_request(build_params(), claims, SigningScheme.EIP712)
    assert signature.scheme == SigningScheme.EIP712
    assert signature.signature.startswith("0x")
    assert len(signature.signature) == 132


@pytest.mark.asyncio
async def test_sign_request_v2_eip191_produces_signature():
    private_key = "0x59c6995e998f97a5a0044976f7be35d5ad91c0cfa55b5cfb20b07a1c60f4c5bc"
    account = Account.from_key(private_key)
    signer = PaymentSigner(private_key)
    claims = build_v2_claims(account.address)

    signature = await signer.sign_request(build_params(), claims, SigningScheme.EIP191)
    assert signature.scheme == SigningScheme.EIP191
    assert signature.signature.startswith("0x")
    assert len(signature.signature) == 132
