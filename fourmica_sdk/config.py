from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Union

from .errors import ConfigError
from .utils import (
    ValidationError,
    normalize_address,
    normalize_private_key,
    validate_url,
)


@dataclass
class AuthConfig:
    auth_url: str
    refresh_margin_secs: int = 60


@dataclass
class Config:
    rpc_url: str
    wallet_private_key: str
    ethereum_http_rpc_url: Optional[str] = None
    contract_address: Optional[str] = None
    bearer_token: Optional[str] = None
    auth: Optional[AuthConfig] = None


class ConfigBuilder:
    def __init__(self) -> None:
        self._rpc_url: Optional[str] = "https://api.4mica.xyz/"
        self._wallet_private_key: Optional[str] = None
        self._ethereum_http_rpc_url: Optional[str] = None
        self._contract_address: Optional[str] = None
        self._bearer_token: Optional[str] = None
        self._auth_enabled: bool = False
        self._auth_url: Optional[str] = None
        self._auth_refresh_margin_secs: Optional[Union[int, str]] = 60

    def rpc_url(self, value: str) -> "ConfigBuilder":
        self._rpc_url = value
        return self

    def wallet_private_key(self, value: str) -> "ConfigBuilder":
        self._wallet_private_key = value
        return self

    def ethereum_http_rpc_url(self, value: str) -> "ConfigBuilder":
        self._ethereum_http_rpc_url = value
        return self

    def contract_address(self, value: str) -> "ConfigBuilder":
        self._contract_address = value
        return self

    def bearer_token(self, value: str) -> "ConfigBuilder":
        self._bearer_token = value
        return self

    def enable_auth(self) -> "ConfigBuilder":
        self._auth_enabled = True
        return self

    def auth_url(self, value: str) -> "ConfigBuilder":
        self._auth_url = value
        return self

    def auth_refresh_margin_secs(self, value: int) -> "ConfigBuilder":
        self._auth_refresh_margin_secs = value
        return self

    def from_env(self) -> "ConfigBuilder":
        env = os.environ
        if "4MICA_RPC_URL" in env:
            self._rpc_url = env["4MICA_RPC_URL"]
        if "4MICA_WALLET_PRIVATE_KEY" in env:
            self._wallet_private_key = env["4MICA_WALLET_PRIVATE_KEY"]
        if "4MICA_ETHEREUM_HTTP_RPC_URL" in env:
            self._ethereum_http_rpc_url = env["4MICA_ETHEREUM_HTTP_RPC_URL"]
        if "4MICA_CONTRACT_ADDRESS" in env:
            self._contract_address = env["4MICA_CONTRACT_ADDRESS"]
        if "4MICA_BEARER_TOKEN" in env:
            self._bearer_token = env["4MICA_BEARER_TOKEN"]
        if "4MICA_AUTH_URL" in env:
            self._auth_url = env["4MICA_AUTH_URL"]
            self._auth_enabled = True
        if "4MICA_AUTH_REFRESH_MARGIN_SECS" in env:
            self._auth_refresh_margin_secs = env["4MICA_AUTH_REFRESH_MARGIN_SECS"]
            self._auth_enabled = True
        return self

    def _parse_refresh_margin(self) -> int:
        value = self._auth_refresh_margin_secs
        if value is None:
            return 60
        if isinstance(value, int):
            margin = value
        else:
            try:
                margin = int(str(value).strip())
            except (TypeError, ValueError) as exc:
                raise ConfigError("invalid auth_refresh_margin_secs") from exc
        if margin < 0:
            raise ConfigError("auth_refresh_margin_secs cannot be negative")
        return margin

    def build(self) -> Config:
        if not self._wallet_private_key:
            raise ConfigError("missing wallet_private_key")
        if not self._rpc_url:
            raise ConfigError("missing rpc_url")

        try:
            rpc_url = validate_url(self._rpc_url)
            wallet_private_key = normalize_private_key(self._wallet_private_key)
            ethereum_http_rpc_url = (
                validate_url(self._ethereum_http_rpc_url)
                if self._ethereum_http_rpc_url
                else None
            )
            contract_address = (
                normalize_address(self._contract_address)
                if self._contract_address
                else None
            )
            auth_config = None
            if self._auth_enabled:
                auth_url_raw = self._auth_url or self._rpc_url
                auth_config = AuthConfig(
                    auth_url=validate_url(auth_url_raw),
                    refresh_margin_secs=self._parse_refresh_margin(),
                )
        except ValidationError as exc:
            raise ConfigError(str(exc)) from exc

        return Config(
            rpc_url=rpc_url,
            wallet_private_key=wallet_private_key,
            ethereum_http_rpc_url=ethereum_http_rpc_url,
            contract_address=contract_address,
            bearer_token=self._bearer_token,
            auth=auth_config,
        )
