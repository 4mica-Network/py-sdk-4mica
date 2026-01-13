from __future__ import annotations

import httpx
from typing import Any, Dict, List, Optional

from .errors import RpcError
from .signing import CorePublicParameters

ADMIN_API_KEY_HEADER = "x-api-key"


def _serialize_tab_id(tab_id: int) -> str:
    return hex(int(tab_id))


class RpcProxy:
    """HTTP client for the core facilitator API."""

    def __init__(self, endpoint: str) -> None:
        base = endpoint if endpoint.endswith("/") else f"{endpoint}/"
        self._client = httpx.AsyncClient(base_url=base, timeout=20.0)
        self._admin_api_key: Optional[str] = None

    def with_admin_api_key(self, admin_api_key: str) -> "RpcProxy":
        self._admin_api_key = admin_api_key
        return self

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "RpcProxy":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    def _headers(self, admin: bool = False) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if admin and self._admin_api_key:
            headers[ADMIN_API_KEY_HEADER] = self._admin_api_key
        return headers

    async def _decode(self, response: httpx.Response) -> Any:
        try:
            payload = response.json()
        except Exception as exc:
            if response.is_success:
                raise RpcError(
                    f"invalid JSON response from {response.request.url}: {exc}"
                ) from exc
            payload = response.text
        if response.is_success:
            return payload

        message = "unknown error"
        if isinstance(payload, dict):
            message = payload.get("error") or payload.get("message") or str(payload)
        elif isinstance(payload, str) and payload.strip():
            message = payload.strip()
        raise RpcError(
            f"{response.status_code}: {message}", status_code=response.status_code
        )

    async def _get(self, path: str, admin: bool = False) -> Any:
        resp = await self._client.get(path, headers=self._headers(admin))
        return await self._decode(resp)

    async def _post(self, path: str, body: Any, admin: bool = False) -> Any:
        resp = await self._client.post(path, json=body, headers=self._headers(admin))
        return await self._decode(resp)

    async def get_public_params(self) -> CorePublicParameters:
        data = await self._get("/core/public-params")
        return CorePublicParameters.from_rpc(data)

    async def issue_guarantee(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post("/core/guarantees", body)

    async def create_payment_tab(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post("/core/payment-tabs", body)

    async def list_settled_tabs(self, recipient_address: str) -> List[Dict[str, Any]]:
        return await self._get(f"/core/recipients/{recipient_address}/settled-tabs")

    async def list_pending_remunerations(
        self, recipient_address: str
    ) -> List[Dict[str, Any]]:
        return await self._get(
            f"/core/recipients/{recipient_address}/pending-remunerations"
        )

    async def get_tab(self, tab_id: int) -> Optional[Dict[str, Any]]:
        return await self._get(f"/core/tabs/{_serialize_tab_id(tab_id)}")

    async def list_recipient_tabs(
        self, recipient_address: str, settlement_statuses: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        query = ""
        if settlement_statuses:
            query = "".join(
                [f"&settlement_status={s}" for s in settlement_statuses]
            )
            query = f"?{query.lstrip('&')}"
        return await self._get(f"/core/recipients/{recipient_address}/tabs{query}")

    async def get_tab_guarantees(self, tab_id: int) -> List[Dict[str, Any]]:
        return await self._get(f"/core/tabs/{_serialize_tab_id(tab_id)}/guarantees")

    async def get_latest_guarantee(self, tab_id: int) -> Optional[Dict[str, Any]]:
        return await self._get(
            f"/core/tabs/{_serialize_tab_id(tab_id)}/guarantees/latest"
        )

    async def get_guarantee(self, tab_id: int, req_id: int) -> Optional[Dict[str, Any]]:
        return await self._get(
            f"/core/tabs/{_serialize_tab_id(tab_id)}/guarantees/{req_id}"
        )

    async def list_recipient_payments(
        self, recipient_address: str
    ) -> List[Dict[str, Any]]:
        return await self._get(f"/core/recipients/{recipient_address}/payments")

    async def get_collateral_events_for_tab(self, tab_id: int) -> List[Dict[str, Any]]:
        return await self._get(
            f"/core/tabs/{_serialize_tab_id(tab_id)}/collateral-events"
        )

    async def get_user_asset_balance(
        self, user_address: str, asset_address: str
    ) -> Optional[Dict[str, Any]]:
        return await self._get(f"/core/users/{user_address}/assets/{asset_address}")

    async def update_user_suspension(
        self, user_address: str, suspended: bool
    ) -> Dict[str, Any]:
        body = {"suspended": suspended}
        return await self._post(
            f"/core/users/{user_address}/suspension", body, admin=True
        )

    async def create_admin_api_key(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post("/core/admin/api-keys", body, admin=True)

    async def list_admin_api_keys(self) -> List[Dict[str, Any]]:
        return await self._get("/core/admin/api-keys", admin=True)

    async def revoke_admin_api_key(self, key_id: str) -> Dict[str, Any]:
        return await self._post(
            f"/core/admin/api-keys/{key_id}/revoke", {}, admin=True
        )
