from types import SimpleNamespace

import pytest

from fourmica_sdk.client import RecipientClient
from fourmica_sdk.errors import VerificationError
from fourmica_sdk.guarantee import decode_guarantee_claims, encode_guarantee_claims
from fourmica_sdk.models import BLSCert, PaymentGuaranteeClaims


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


def test_verify_guarantee_rejects_domain_mismatch():
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
    cert = BLSCert(
        claims="0x" + encode_guarantee_claims(claims).hex(),
        signature="0x" + "aa" * 96,
    )

    fake_client = SimpleNamespace(
        guarantee_domain=good_domain,
        gateway=SimpleNamespace(
            account=SimpleNamespace(
                address="0x0000000000000000000000000000000000000002"
            )
        ),
        rpc=None,
    )
    recipient = RecipientClient(fake_client)  # type: ignore[arg-type]

    with pytest.raises(VerificationError):
        recipient.verify_payment_guarantee(cert)
