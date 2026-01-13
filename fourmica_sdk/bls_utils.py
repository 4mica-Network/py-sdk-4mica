from __future__ import annotations

from typing import List

from .errors import VerificationError

_BLS_DEPENDENCY_MESSAGE = (
    "py-ecc is required to decode BLS signatures; "
    "install sdk-4mica[bls] to enable remuneration."
)


def _load_bls_modules():
    try:
        from py_ecc.bls import G2Basic, G2ProofOfPossession as bls_pop
        from py_ecc.optimized_bls12_381 import normalize
    except ImportError as exc:
        raise VerificationError(_BLS_DEPENDENCY_MESSAGE) from exc
    return G2Basic, bls_pop, normalize


def _split_fp(value: int) -> (bytes, bytes):
    be48 = int(value).to_bytes(48, "big")
    hi = b"\x00" * 16 + be48[:16]
    lo = be48[16:]
    return hi, lo


def signature_to_words(signature_hex: str) -> List[bytes]:
    """Expand a compressed G2 signature into the tuple expected by the contract.

    Requires the optional ``py-ecc`` dependency. A ``VerificationError`` is raised
    if py-ecc is missing or the signature cannot be decoded.
    """
    _, bls_pop, normalize = _load_bls_modules()

    try:
        sig_bytes = bytes.fromhex(signature_hex.removeprefix("0x"))
        point = bls_pop.SignatureToG2(sig_bytes)
        # Normalize to affine coordinates (x, y)
        x, y = normalize(point)[:2]
        x0, x1 = x.coeffs
        y0, y1 = y.coeffs
    except Exception as exc:
        raise VerificationError(f"invalid BLS signature: {exc}") from exc

    words = []
    for coord in (x0, x1, y0, y1):
        hi, lo = _split_fp(int(coord))
        words.extend([hi, lo])
    return words


def verify_bls_signature(
    public_key: bytes, message: bytes, signature_hex: str
) -> bool:
    """Verify a BLS signature against the provided public key and message."""
    if len(public_key) != 48:
        raise VerificationError(
            f"invalid operator public key length: expected 48 bytes, got {len(public_key)}"
        )

    G2Basic, _, _ = _load_bls_modules()
    try:
        sig_bytes = bytes.fromhex(signature_hex.removeprefix("0x"))
    except ValueError as exc:
        raise VerificationError("invalid BLS signature encoding") from exc

    try:
        return G2Basic.Verify(public_key, message, sig_bytes)
    except Exception as exc:
        raise VerificationError(f"invalid BLS signature: {exc}") from exc
