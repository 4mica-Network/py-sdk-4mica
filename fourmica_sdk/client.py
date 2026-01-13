from __future__ import annotations

from typing import List, Optional, Type

from .bls_utils import signature_to_words, verify_bls_signature
from .config import Config
from .contract import ContractGateway
from .errors import (
    ClientInitializationError,
    CreateTabError,
    IssuePaymentGuaranteeError,
    RecipientQueryError,
    RemunerateError,
    RpcError,
    SigningError,
    VerifyGuaranteeError,
    VerificationError,
)
from .guarantee import decode_guarantee_claims
from .models import (
    AssetBalanceInfo,
    BLSCert,
    CollateralEventInfo,
    GuaranteeInfo,
    PaymentGuaranteeClaims,
    PaymentGuaranteeRequestClaims,
    PaymentSignature,
    PendingRemunerationInfo,
    RecipientPaymentInfo,
    SigningScheme,
    TabInfo,
    TabPaymentStatus,
    UserInfo,
)
from .rpc import RpcProxy
from .signing import CorePublicParameters, PaymentSigner
from .utils import ValidationError, normalize_address, parse_u256, serialize_u256


def _tab_status_from_rpc(status: dict) -> TabPaymentStatus:
    """Convert a payment status payload from the gateway into the public model."""
    paid = status.get("paid") if "paid" in status else status.get("paidAmount")
    remunerated = (
        status.get("remunerated") if "remunerated" in status else status.get("paidOut")
    )
    asset = status.get("asset") if "asset" in status else status.get("assetAddress")
    return TabPaymentStatus(
        paid=parse_u256(paid),
        remunerated=bool(remunerated),
        asset=asset,
    )


class Client:
    """Entry point that bundles both user and recipient flows."""

    def __init__(
        self,
        cfg: Config,
        rpc: RpcProxy,
        params: CorePublicParameters,
        gateway: ContractGateway,
        guarantee_domain: bytes,
        signer: PaymentSigner,
    ) -> None:
        self.cfg = cfg
        self.rpc = rpc
        self.params = params
        self.gateway = gateway
        self.guarantee_domain = guarantee_domain
        self._signer = signer
        self.user = UserClient(self)
        self.recipient = RecipientClient(self)

    @classmethod
    async def new(cls, cfg: Config) -> "Client":
        rpc = RpcProxy(cfg.rpc_url)
        params = await rpc.get_public_params()
        cls._validate_operator_public_key(params.public_key)
        gateway = cls._build_gateway(cfg, params)
        await cls._validate_chain_id(gateway, params.chain_id)
        guarantee_domain = await cls._fetch_guarantee_domain(gateway)
        signer = PaymentSigner(cfg.wallet_private_key)
        return cls(cfg, rpc, params, gateway, guarantee_domain, signer)

    @staticmethod
    def _build_gateway(cfg: Config, params: CorePublicParameters) -> ContractGateway:
        eth_rpc_url = cfg.ethereum_http_rpc_url or params.ethereum_http_rpc_url
        contract_address = cfg.contract_address or params.contract_address
        return ContractGateway(
            eth_rpc_url,
            cfg.wallet_private_key,
            contract_address,
            params.chain_id,
        )

    @staticmethod
    async def _validate_chain_id(
        gateway: ContractGateway, expected_chain_id: int
    ) -> None:
        try:
            chain_id = await gateway.w3.eth.chain_id
            if int(chain_id) != int(expected_chain_id):
                raise ClientInitializationError(
                    f"chain id mismatch between core ({expected_chain_id}) and provider ({chain_id})"
                )
        except Exception as exc:
            raise ClientInitializationError(str(exc)) from exc

    @staticmethod
    async def _fetch_guarantee_domain(gateway: ContractGateway) -> bytes:
        try:
            return await gateway.contract.functions.guaranteeDomainSeparator().call()
        except Exception as exc:
            raise ClientInitializationError(
                f"failed to fetch guarantee domain: {exc}"
            ) from exc

    @staticmethod
    def _validate_operator_public_key(public_key: bytes) -> None:
        if len(public_key) != 48:
            raise ClientInitializationError(
                "invalid operator public key length: "
                f"expected 48 bytes, got {len(public_key)}"
            )

    async def aclose(self) -> None:
        await self.rpc.aclose()

    async def __aenter__(self) -> "Client":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()


class UserClient:
    def __init__(self, client: Client) -> None:
        self.client = client

    @property
    def guarantee_domain(self) -> bytes:
        return self.client.guarantee_domain

    async def approve_erc20(self, token: str, amount: int) -> dict:
        return await self.client.gateway.approve_erc20(token, amount)

    async def deposit(self, amount: int, erc20_token: Optional[str] = None) -> dict:
        return await self.client.gateway.deposit(amount, erc20_token)

    async def get_user(self) -> List[UserInfo]:
        assets = await self.client.gateway.get_user_assets()
        return [
            UserInfo(
                asset=a["asset"],
                collateral=parse_u256(a["collateral"]),
                withdrawal_request_amount=parse_u256(a["withdrawal_request_amount"]),
                withdrawal_request_timestamp=int(a["withdrawal_request_timestamp"]),
            )
            for a in assets
        ]

    async def get_tab_payment_status(self, tab_id: int) -> TabPaymentStatus:
        status = await self.client.gateway.get_payment_status(tab_id)
        return _tab_status_from_rpc(status)

    async def sign_payment(
        self,
        claims: PaymentGuaranteeRequestClaims,
        scheme: SigningScheme = SigningScheme.EIP712,
    ) -> PaymentSignature:
        try:
            params = await self.client.rpc.get_public_params()
        except RpcError as exc:
            raise SigningError(str(exc)) from exc
        return await self.client._signer.sign_request(params, claims, scheme)

    async def pay_tab(
        self,
        tab_id: int,
        req_id: int,
        amount: int,
        recipient_address: str,
        erc20_token: Optional[str] = None,
    ) -> dict:
        if erc20_token:
            return await self.client.gateway.pay_tab_erc20(
                tab_id, amount, erc20_token, recipient_address
            )
        return await self.client.gateway.pay_tab_eth(
            tab_id, req_id, amount, recipient_address
        )

    async def request_withdrawal(
        self, amount: int, erc20_token: Optional[str] = None
    ) -> dict:
        return await self.client.gateway.request_withdrawal(amount, erc20_token)

    async def cancel_withdrawal(self, erc20_token: Optional[str] = None) -> dict:
        return await self.client.gateway.cancel_withdrawal(erc20_token)

    async def finalize_withdrawal(self, erc20_token: Optional[str] = None) -> dict:
        return await self.client.gateway.finalize_withdrawal(erc20_token)


class RecipientClient:
    def __init__(self, client: Client) -> None:
        self.client = client

    @property
    def _recipient_address(self) -> str:
        return normalize_address(self.client.gateway.account.address)

    @property
    def guarantee_domain(self) -> bytes:
        return self.client.guarantee_domain

    def _check_signer(self, expected: str, error_cls: Type[Exception]) -> None:
        try:
            expected_address = normalize_address(expected)
        except ValidationError as exc:
            raise error_cls(f"invalid recipient address: {exc}") from exc
        if expected_address != self._recipient_address:
            raise error_cls("signer address does not match recipient address")

    async def create_tab(
        self,
        user_address: str,
        recipient_address: str,
        erc20_token: Optional[str],
        ttl: Optional[int],
    ) -> int:
        self._check_signer(recipient_address, CreateTabError)
        body = {
            "user_address": user_address,
            "recipient_address": recipient_address,
            "erc20_token": erc20_token,
            "ttl": ttl,
        }
        try:
            result = await self.client.rpc.create_payment_tab(body)
        except RpcError as exc:
            raise CreateTabError(str(exc), status_code=exc.status_code) from exc
        return parse_u256(result["id"])

    async def get_tab_payment_status(self, tab_id: int) -> TabPaymentStatus:
        status = await self.client.gateway.get_payment_status(tab_id)
        return _tab_status_from_rpc(status)

    async def issue_payment_guarantee(
        self,
        claims: PaymentGuaranteeRequestClaims,
        signature: str,
        scheme: SigningScheme,
    ) -> BLSCert:
        self._check_signer(claims.recipient_address, IssuePaymentGuaranteeError)
        payload = {
            "claims": {
                "version": "v1",
                "user_address": claims.user_address,
                "recipient_address": claims.recipient_address,
                "tab_id": serialize_u256(claims.tab_id),
                "req_id": serialize_u256(claims.req_id),
                "amount": serialize_u256(claims.amount),
                "asset_address": claims.asset_address,
                "timestamp": int(claims.timestamp),
            },
            "signature": signature,
            "scheme": scheme.value,
        }
        try:
            cert = await self.client.rpc.issue_guarantee(payload)
        except RpcError as exc:
            raise IssuePaymentGuaranteeError(
                str(exc), status_code=exc.status_code
            ) from exc
        return BLSCert(claims=cert["claims"], signature=cert["signature"])

    def verify_payment_guarantee(self, cert: BLSCert) -> PaymentGuaranteeClaims:
        try:
            claims_bytes = bytes.fromhex(cert.claims.removeprefix("0x"))
        except ValueError as exc:
            raise VerifyGuaranteeError(
                "invalid BLS certificate claims encoding"
            ) from exc

        public_key = getattr(self.client, "params", None)
        if public_key is None or not hasattr(public_key, "public_key"):
            raise VerifyGuaranteeError(
                "missing operator public key for verification"
            )
        operator_public_key = bytes(public_key.public_key)

        if not verify_bls_signature(operator_public_key, claims_bytes, cert.signature):
            raise VerifyGuaranteeError("certificate signature mismatch")

        claims = decode_guarantee_claims(claims_bytes)
        if claims.domain != self.guarantee_domain:
            raise VerifyGuaranteeError("guarantee domain mismatch")
        return claims

    async def remunerate(self, cert: BLSCert) -> dict:
        try:
            self.verify_payment_guarantee(cert)
        except VerifyGuaranteeError as exc:
            raise RemunerateError(str(exc)) from exc
        try:
            sig_words = signature_to_words(cert.signature)
            claims_bytes = bytes.fromhex(cert.claims.removeprefix("0x"))
        except VerificationError as exc:
            raise RemunerateError(str(exc)) from exc
        return await self.client.gateway.remunerate(claims_bytes, sig_words)

    async def list_settled_tabs(self) -> List[TabInfo]:
        try:
            tabs = await self.client.rpc.list_settled_tabs(self._recipient_address)
        except RpcError as exc:
            raise RecipientQueryError(str(exc), status_code=exc.status_code) from exc
        return [TabInfo.from_rpc(tab) for tab in tabs]

    async def list_pending_remunerations(self) -> List[PendingRemunerationInfo]:
        try:
            items = await self.client.rpc.list_pending_remunerations(
                self._recipient_address
            )
        except RpcError as exc:
            raise RecipientQueryError(str(exc), status_code=exc.status_code) from exc
        return [PendingRemunerationInfo.from_rpc(item) for item in items]

    async def get_tab(self, tab_id: int) -> Optional[TabInfo]:
        try:
            result = await self.client.rpc.get_tab(tab_id)
        except RpcError as exc:
            raise RecipientQueryError(str(exc), status_code=exc.status_code) from exc
        return TabInfo.from_rpc(result) if result else None

    async def list_recipient_tabs(
        self, settlement_statuses: Optional[List[str]] = None
    ) -> List[TabInfo]:
        try:
            tabs = await self.client.rpc.list_recipient_tabs(
                self._recipient_address, settlement_statuses
            )
        except RpcError as exc:
            raise RecipientQueryError(str(exc), status_code=exc.status_code) from exc
        return [TabInfo.from_rpc(tab) for tab in tabs]

    async def get_tab_guarantees(self, tab_id: int) -> List[GuaranteeInfo]:
        try:
            guarantees = await self.client.rpc.get_tab_guarantees(tab_id)
        except RpcError as exc:
            raise RecipientQueryError(str(exc), status_code=exc.status_code) from exc
        return [GuaranteeInfo.from_rpc(g) for g in guarantees]

    async def get_latest_guarantee(self, tab_id: int) -> Optional[GuaranteeInfo]:
        try:
            result = await self.client.rpc.get_latest_guarantee(tab_id)
        except RpcError as exc:
            raise RecipientQueryError(str(exc), status_code=exc.status_code) from exc
        return GuaranteeInfo.from_rpc(result) if result else None

    async def get_guarantee(self, tab_id: int, req_id: int) -> Optional[GuaranteeInfo]:
        try:
            result = await self.client.rpc.get_guarantee(tab_id, req_id)
        except RpcError as exc:
            raise RecipientQueryError(str(exc), status_code=exc.status_code) from exc
        return GuaranteeInfo.from_rpc(result) if result else None

    async def list_recipient_payments(self) -> List[RecipientPaymentInfo]:
        try:
            payments = await self.client.rpc.list_recipient_payments(
                self._recipient_address
            )
        except RpcError as exc:
            raise RecipientQueryError(str(exc), status_code=exc.status_code) from exc
        return [RecipientPaymentInfo.from_rpc(p) for p in payments]

    async def get_collateral_events_for_tab(
        self, tab_id: int
    ) -> List[CollateralEventInfo]:
        try:
            events = await self.client.rpc.get_collateral_events_for_tab(tab_id)
        except RpcError as exc:
            raise RecipientQueryError(str(exc), status_code=exc.status_code) from exc
        return [CollateralEventInfo.from_rpc(ev) for ev in events]

    async def get_user_asset_balance(
        self, user_address: str, asset_address: str
    ) -> Optional[AssetBalanceInfo]:
        try:
            balance = await self.client.rpc.get_user_asset_balance(
                user_address, asset_address
            )
        except RpcError as exc:
            raise RecipientQueryError(str(exc), status_code=exc.status_code) from exc
        return AssetBalanceInfo.from_rpc(balance) if balance else None
