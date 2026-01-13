import httpx
import pytest

from fourmica_sdk.errors import RpcError
from fourmica_sdk.rpc import RpcProxy


def _proxy_with_transport(handler) -> RpcProxy:
    transport = httpx.MockTransport(handler)
    proxy = RpcProxy("http://example.com")
    proxy._client = httpx.AsyncClient(
        transport=transport, base_url="http://example.com"
    )
    return proxy


@pytest.mark.asyncio
async def test_rpc_proxy_get_public_params_round_trip():
    params = {
        "public_key": [1, 2, 3],
        "contract_address": "0x1234567890abcdef1234567890abcdef12345678",
        "ethereum_http_rpc_url": "http://localhost:8545",
        "eip712_name": "4mica",
        "eip712_version": "1",
        "chain_id": 1337,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/core/public-params"
        return httpx.Response(200, json=params)

    proxy = _proxy_with_transport(handler)
    try:
        got = await proxy.get_public_params()
        assert got.chain_id == 1337
        assert got.contract_address == params["contract_address"]
        assert got.ethereum_http_rpc_url == params["ethereum_http_rpc_url"]
    finally:
        await proxy.aclose()


@pytest.mark.asyncio
async def test_rpc_proxy_surfaces_api_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "settlement_status=unknown" in str(request.url)
        payload = {"error": "invalid settlement status: unknown"}
        return httpx.Response(400, json=payload)

    proxy = _proxy_with_transport(handler)
    try:
        with pytest.raises(RpcError) as err:
            await proxy.list_recipient_tabs("0xdeadbeef", ["unknown"])
        assert "invalid settlement status" in str(err.value)
    finally:
        await proxy.aclose()


@pytest.mark.asyncio
async def test_rpc_proxy_returns_decode_error_on_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    proxy = _proxy_with_transport(handler)
    try:
        with pytest.raises(RpcError):
            await proxy.get_public_params()
    finally:
        await proxy.aclose()
