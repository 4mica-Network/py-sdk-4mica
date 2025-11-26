import builtins

import pytest

from fourmica_sdk.bls_utils import signature_to_words
from fourmica_sdk.errors import VerificationError


def test_signature_to_words_prompts_for_optional_dependency(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("py_ecc"):
            raise ImportError("force-missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(VerificationError, match="sdk-4mica\\[bls\\]"):
        signature_to_words("0x" + "00" * 96)
