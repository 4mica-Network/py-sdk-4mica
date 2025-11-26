class FourMicaError(Exception):
    """Base error for the Python 4Mica SDK."""


class ConfigError(FourMicaError):
    """Raised when configuration values are missing or invalid."""


class RpcError(FourMicaError):
    """Raised when an RPC call to the core service fails."""


class ClientInitializationError(FourMicaError):
    """Raised when the client cannot be initialized (chain mismatch, bad keys, etc.)."""


class SigningError(FourMicaError):
    """Raised when payment signing fails."""


class ContractError(FourMicaError):
    """Raised when an on-chain call or transaction fails."""


class VerificationError(FourMicaError):
    """Raised when BLS or guarantee verification fails."""


class X402Error(FourMicaError):
    """Raised for X402 flow issues (invalid scheme, settlement errors, etc.)."""
