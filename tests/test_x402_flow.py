import base64
import json

import httpx

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
        return TabResponse(tab_id="2", user_address=user_address, next_req_id="0x1")


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

    assert envelope["x402Version"] == 1
    assert envelope["scheme"] == "4mica+pay"
    assert envelope["payload"]["claims"]["tab_id"] == hex(2)
    assert envelope["payload"]["claims"]["req_id"] == hex(1)
    assert signed.claims.tab_id == 2
    assert signed.claims.amount == 5
    assert signed.claims.req_id == 1


def test_payment_requirements_from_raw_handles_casing_and_required_fields():
    raw = {
        "scheme": "4mica-credit",
        "network": "polygon-amoy",
        "maxAmountRequired": "0x1",
        "payTo": "0xabc",
        "asset": "0xdef",
        "extra": {"tabEndpoint": "http://tab"},
        "mimeType": "application/json",
        "maxTimeoutSeconds": 300,
    }
    req = PaymentRequirements.from_raw(raw)
    assert req.scheme == "4mica-credit"
    assert req.network == "polygon-amoy"
    assert req.max_amount_required == "0x1"
    assert req.pay_to == "0xabc"
    assert req.asset == "0xdef"
    assert req.mime_type == "application/json"
    assert req.max_timeout_seconds == 300


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
        tab_id="3",
        user_address="0x00000000000000000000000000000000000000aa",
    )
    with pytest.raises(X402Error):
        flow._build_claims(
            requirements, tab, "0x00000000000000000000000000000000000000bb"
        )


class RecordingSigner:
    async def sign_payment(self, claims, scheme: SigningScheme) -> PaymentSignature:
        return PaymentSignature(signature="0xsig", scheme=scheme)


@pytest.mark.asyncio
async def test_x402_flow_settles_payment_through_facilitator():
    user_address = "0x0000000000000000000000000000000000000009"
    tab_endpoint = "http://facilitator.test/tab"
    facilitator_url = "http://facilitator.test"
    requirements = PaymentRequirements(
        scheme="4mica+pay",
        network="testnet",
        max_amount_required="5",
        pay_to="0x00000000000000000000000000000000000000ff",
        asset="0x0000000000000000000000000000000000000000",
        extra={"tabEndpoint": tab_endpoint},
    )

    def handler(request):
        if request.url.path == "/tab":
            assert request.method == "POST"
            body = json.loads(request.content.decode())
            assert body["userAddress"] == user_address
            return httpx.Response(
                200,
                json={
                    "tabId": "0x1234",
                    "userAddress": user_address,
                    "nextReqId": "0x1",
                },
            )
        if request.url.path == "/settle":
            payload = json.loads(request.content.decode())
            assert payload["paymentRequirements"]["payTo"] == requirements.pay_to
            return httpx.Response(
                200,
                json={"settled": True, "networkId": requirements.network},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    flow = X402Flow(RecordingSigner(), httpx.AsyncClient(transport=transport))

    try:
        payment = await flow.sign_payment(requirements, user_address)
        assert payment.claims.tab_id == 0x1234

        settled = await flow.settle_payment(payment, requirements, facilitator_url)
        assert settled.settlement["settled"] is True
        assert settled.settlement["networkId"] == requirements.network
        assert settled.payment.claims.recipient_address == requirements.pay_to
    finally:
        await flow.http.aclose()
