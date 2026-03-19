from types import SimpleNamespace

import pytest
from eth_abi import encode as abi_encode

from fourmica_sdk.client import RecipientClient
from fourmica_sdk.errors import VerificationError
from fourmica_sdk.guarantee import decode_guarantee_claims, encode_guarantee_claims
from fourmica_sdk.models import (
    BLSCert,
    PaymentGuaranteeClaims,
    PaymentGuaranteeValidationPolicyV2,
)


def test_encode_decode_guarantee_round_trip():
    claims = PaymentGuaranteeClaims(
        domain=b"\x00" * 32,
        user_address="0x0000000000000000000000000000000000000001",
        recipient_address="0x0000000000000000000000000000000000000002",
        tab_id=1,
        req_id=2,
        amount=3,
        total_amount=4,
        asset_address="0x0000000000000000000000000000000000000000",
        timestamp=1234,
        version=1,
    )
    encoded = encode_guarantee_claims(claims)
    decoded = decode_guarantee_claims(encoded)
    assert decoded.tab_id == claims.tab_id
    assert decoded.req_id == claims.req_id
    assert decoded.amount == claims.amount
    assert decoded.total_amount == claims.total_amount


def test_encode_guarantee_v1_rejects_validation_policy():
    claims = PaymentGuaranteeClaims(
        domain=b"\x00" * 32,
        user_address="0x0000000000000000000000000000000000000001",
        recipient_address="0x0000000000000000000000000000000000000002",
        tab_id=1,
        req_id=2,
        amount=3,
        total_amount=4,
        asset_address="0x0000000000000000000000000000000000000000",
        timestamp=1234,
        version=1,
        validation_policy=PaymentGuaranteeValidationPolicyV2(
            validation_registry_address="0x0000000000000000000000000000000000000011",
            validation_request_hash="0x" + "ab" * 32,
            validation_chain_id=1,
            validator_address="0x0000000000000000000000000000000000000022",
            validator_agent_id=7,
            min_validation_score=80,
            validation_subject_hash="0x" + "cd" * 32,
            required_validation_tag="hard-finality",
        ),
    )

    with pytest.raises(VerificationError, match="must not carry validation_policy"):
        encode_guarantee_claims(claims)


def test_encode_decode_guarantee_v2_round_trip():
    claims = PaymentGuaranteeClaims(
        domain=b"\x00" * 32,
        user_address="0x0000000000000000000000000000000000000001",
        recipient_address="0x0000000000000000000000000000000000000002",
        tab_id=1,
        req_id=2,
        amount=3,
        total_amount=4,
        asset_address="0x0000000000000000000000000000000000000000",
        timestamp=1234,
        version=2,
        validation_policy=PaymentGuaranteeValidationPolicyV2(
            validation_registry_address="0x0000000000000000000000000000000000000011",
            validation_request_hash="0x" + "ab" * 32,
            validation_chain_id=1,
            validator_address="0x0000000000000000000000000000000000000022",
            validator_agent_id=7,
            min_validation_score=80,
            validation_subject_hash="0x" + "cd" * 32,
            required_validation_tag="hard-finality",
        ),
    )
    encoded = encode_guarantee_claims(claims)
    decoded = decode_guarantee_claims(encoded)
    assert decoded.version == 2
    assert decoded.validation_policy is not None
    assert (
        decoded.validation_policy.validation_request_hash
        == claims.validation_policy.validation_request_hash
    )
    assert (
        decoded.validation_policy.validation_subject_hash
        == claims.validation_policy.validation_subject_hash
    )
    assert (
        decoded.validation_policy.required_validation_tag
        == claims.validation_policy.required_validation_tag
    )


def test_encode_guarantee_v2_requires_validation_policy():
    claims = PaymentGuaranteeClaims(
        domain=b"\x00" * 32,
        user_address="0x0000000000000000000000000000000000000001",
        recipient_address="0x0000000000000000000000000000000000000002",
        tab_id=1,
        req_id=2,
        amount=3,
        total_amount=4,
        asset_address="0x0000000000000000000000000000000000000000",
        timestamp=1234,
        version=2,
    )

    with pytest.raises(VerificationError, match="require validation_policy"):
        encode_guarantee_claims(claims)


def test_decode_guarantee_rejects_unsupported_envelope_version():
    encoded = abi_encode(["uint64", "bytes"], [3, b""])

    with pytest.raises(VerificationError, match="unsupported guarantee claims version"):
        decode_guarantee_claims(encoded)


def test_verify_guarantee_rejects_domain_mismatch():
    pytest.importorskip("py_ecc")
    from py_ecc.bls import G2Basic

    good_domain = b"\x01" * 32
    wrong_domain = b"\x02" * 32
    claims = PaymentGuaranteeClaims(
        domain=wrong_domain,
        user_address="0x0000000000000000000000000000000000000001",
        recipient_address="0x0000000000000000000000000000000000000002",
        tab_id=1,
        req_id=1,
        amount=1,
        total_amount=1,
        asset_address="0x0000000000000000000000000000000000000000",
        timestamp=1234,
        version=1,
    )
    claims_bytes = encode_guarantee_claims(claims)
    sk = 1
    pk = G2Basic.SkToPk(sk)
    signature = G2Basic.Sign(sk, claims_bytes)
    cert = BLSCert(
        claims="0x" + claims_bytes.hex(),
        signature="0x" + signature.hex(),
    )

    fake_client = SimpleNamespace(
        guarantee_domain=good_domain,
        guarantee_domains={1: good_domain},
        gateway=SimpleNamespace(
            account=SimpleNamespace(
                address="0x0000000000000000000000000000000000000002"
            )
        ),
        rpc=None,
        params=SimpleNamespace(public_key=pk),
    )
    recipient = RecipientClient(fake_client)  # type: ignore[arg-type]

    with pytest.raises(VerificationError, match="guarantee domain mismatch"):
        recipient.verify_payment_guarantee(cert)


def test_verify_v2_guarantee_uses_version_specific_domain():
    pytest.importorskip("py_ecc")
    from py_ecc.bls import G2Basic

    v2_domain = b"\x03" * 32
    claims = PaymentGuaranteeClaims(
        domain=v2_domain,
        user_address="0x0000000000000000000000000000000000000001",
        recipient_address="0x0000000000000000000000000000000000000002",
        tab_id=1,
        req_id=1,
        amount=1,
        total_amount=1,
        asset_address="0x0000000000000000000000000000000000000000",
        timestamp=1234,
        version=2,
        validation_policy=PaymentGuaranteeValidationPolicyV2(
            validation_registry_address="0x0000000000000000000000000000000000000011",
            validation_request_hash="0x" + "ab" * 32,
            validation_chain_id=1,
            validator_address="0x0000000000000000000000000000000000000022",
            validator_agent_id=7,
            min_validation_score=80,
            validation_subject_hash="0x" + "cd" * 32,
            required_validation_tag="hard-finality",
        ),
    )
    claims_bytes = encode_guarantee_claims(claims)
    sk = 1
    pk = G2Basic.SkToPk(sk)
    signature = G2Basic.Sign(sk, claims_bytes)
    cert = BLSCert(
        claims="0x" + claims_bytes.hex(),
        signature="0x" + signature.hex(),
    )

    fake_client = SimpleNamespace(
        guarantee_domain=b"\x01" * 32,
        guarantee_domains={1: b"\x01" * 32, 2: v2_domain},
        gateway=SimpleNamespace(
            account=SimpleNamespace(
                address="0x0000000000000000000000000000000000000002"
            )
        ),
        rpc=None,
        params=SimpleNamespace(public_key=pk),
    )
    recipient = RecipientClient(fake_client)  # type: ignore[arg-type]

    decoded = recipient.verify_payment_guarantee(cert)
    assert decoded.version == 2
