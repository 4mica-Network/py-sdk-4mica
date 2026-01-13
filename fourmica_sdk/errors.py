from typing import Optional


class FourMicaError(Exception):
    """Base error for the Python 4Mica SDK."""


class ConfigError(FourMicaError):
    """Raised when configuration values are missing or invalid."""


class RpcError(FourMicaError):
    """Raised when an RPC call to the core service fails."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ClientInitializationError(FourMicaError):
    """Raised when the client cannot be initialized (chain mismatch, bad keys, etc.)."""


class SigningError(FourMicaError):
    """Raised when payment signing fails."""


class ContractError(FourMicaError):
    """Raised when an on-chain call or transaction fails."""


class ApproveErc20Error(ContractError):
    """Raised when ERC20 approvals fail."""


class DepositError(ContractError):
    """Raised when collateral deposits fail."""


class RequestWithdrawalError(ContractError):
    """Raised when withdrawal requests fail."""


class CancelWithdrawalError(ContractError):
    """Raised when withdrawal cancellations fail."""


class FinalizeWithdrawalError(ContractError):
    """Raised when withdrawal finalization fails."""


class PayTabError(ContractError):
    """Raised when tab payments fail."""


class GetUserError(ContractError):
    """Raised when fetching user collateral fails."""


class TabPaymentStatusError(ContractError):
    """Raised when fetching tab payment status fails."""


class RemunerateError(ContractError):
    """Raised when remunerating a guarantee fails."""


class VerificationError(FourMicaError):
    """Raised when BLS or guarantee verification fails."""


class VerifyGuaranteeError(VerificationError):
    """Raised when a guarantee verification fails."""


class X402Error(FourMicaError):
    """Raised for X402 flow issues (invalid scheme, settlement errors, etc.)."""


class CreateTabError(RpcError):
    """Raised when creating payment tabs fails."""


class IssuePaymentGuaranteeError(RpcError):
    """Raised when issuing payment guarantees fails."""


class RecipientQueryError(RpcError):
    """Raised when recipient queries fail."""
