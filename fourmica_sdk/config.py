from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .errors import ConfigError
from .utils import (
    ValidationError,
    normalize_address,
    normalize_private_key,
    validate_url,
)


@dataclass
class Config:
    rpc_url: str
    wallet_private_key: str
    ethereum_http_rpc_url: Optional[str] = None
    contract_address: Optional[str] = None


class ConfigBuilder:
    def __init__(self) -> None:
        self._rpc_url: Optional[str] = "https://api.4mica.xyz/"
        self._wallet_private_key: Optional[str] = None
        self._ethereum_http_rpc_url: Optional[str] = None
        self._contract_address: Optional[str] = None

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
        return self

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
        except ValidationError as exc:
            raise ConfigError(str(exc)) from exc

        return Config(
            rpc_url=rpc_url,
            wallet_private_key=wallet_private_key,
            ethereum_http_rpc_url=ethereum_http_rpc_url,
            contract_address=contract_address,
        )
