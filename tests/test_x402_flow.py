import base64
import json

import pytest

from fourmica_sdk.errors import X402Error
from fourmica_sdk.models import PaymentSignature, SigningScheme
from fourmica_sdk.x402 import (
    PaymentRequirements,
    TabResponse,
    X402Flow,
)


class StubSigner:
    async def sign_payment(self, claims, scheme: SigningScheme) -> PaymentSignature:
        return PaymentSignature(signature="deadbeef", scheme=scheme)


class StubX402Flow(X402Flow):
    async def _request_tab(
        self, payment_requirements: PaymentRequirements, user_address: str
    ) -> TabResponse:
        return TabResponse(tab_id="2", user_address=user_address)


@pytest.mark.asyncio
async def test_sign_payment_rejects_invalid_scheme():
    flow = StubX402Flow(StubSigner())
    requirements = PaymentRequirements(
        scheme="http+pay",
        network="testnet",
        max_amount_required="1",
        pay_to="0x0000000000000000000000000000000000000003",
        asset="0x0000000000000000000000000000000000000000",
        extra={"tabEndpoint": "https://example.com"},
    )
    with pytest.raises(X402Error):
        await flow.sign_payment(
            requirements, "0x0000000000000000000000000000000000000001"
        )


@pytest.mark.asyncio
async def test_sign_payment_builds_header_and_payload():
    flow = StubX402Flow(StubSigner())
    requirements = PaymentRequirements(
        scheme="4mica+pay",
        network="testnet",
        max_amount_required="5",
        pay_to="0x0000000000000000000000000000000000000003",
        asset="0x0000000000000000000000000000000000000000",
        extra={"tabEndpoint": "https://example.com"},
    )
    user_address = "0x0000000000000000000000000000000000000001"
    signed = await flow.sign_payment(requirements, user_address)

    decoded_header = base64.b64decode(signed.header).decode()
    envelope = json.loads(decoded_header)

    assert envelope["scheme"] == "4mica+pay"
    assert envelope["payload"]["claims"]["tab_id"] == hex(2)
    assert signed.claims.tab_id == 2
    assert signed.claims.amount == 5


def test_build_claims_rejects_user_mismatch():
    flow = StubX402Flow(StubSigner())
    requirements = PaymentRequirements(
        scheme="4mica+pay",
        network="testnet",
        max_amount_required="5",
        pay_to="0x0000000000000000000000000000000000000003",
        asset="0x0000000000000000000000000000000000000000",
        extra={"tabEndpoint": "https://example.com"},
    )
    tab = TabResponse(
        tab_id="3", user_address="0x00000000000000000000000000000000000000aa"
    )
    with pytest.raises(X402Error):
        flow._build_claims(
            requirements, tab, "0x00000000000000000000000000000000000000bb"
        )
