from fourmica_sdk.guarantee import decode_guarantee_claims, encode_guarantee_claims
from fourmica_sdk.models import PaymentGuaranteeClaims


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
