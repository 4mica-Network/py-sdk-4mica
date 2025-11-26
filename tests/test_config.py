import pytest

from fourmica_sdk.config import ConfigBuilder
from fourmica_sdk.errors import ConfigError


def test_config_builder_reads_from_env(monkeypatch):
    monkeypatch.setenv("4MICA_RPC_URL", "https://example.com")
    monkeypatch.setenv("4MICA_WALLET_PRIVATE_KEY", "11" * 32)
    cfg = ConfigBuilder().from_env().build()
    assert cfg.rpc_url == "https://example.com"
    assert cfg.wallet_private_key.startswith("0x11")


def test_config_builder_requires_private_key(monkeypatch):
    monkeypatch.delenv("4MICA_WALLET_PRIVATE_KEY", raising=False)
    builder = ConfigBuilder().from_env()
    with pytest.raises(ConfigError):
        builder.build()


def test_config_builder_rejects_invalid_private_key():
    builder = ConfigBuilder().wallet_private_key("0x1234")
    with pytest.raises(ConfigError):
        builder.build()
