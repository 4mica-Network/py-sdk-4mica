from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional

from eth_utils import to_bytes, to_checksum_address

# web3 pulls in websockets.legacy when importing its websocket provider classes.
# We only use the HTTP provider, so silence that third-party deprecation warning
# during import until web3 switches to the new asyncio websockets API.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        module="websockets\\.legacy",
    )
    try:
        from web3 import AsyncHTTPProvider, AsyncWeb3
    except ImportError:  # pragma: no cover - unexpected layout
        from web3 import AsyncWeb3

        AsyncHTTPProvider = None  # type: ignore

# Fallback imports for older web3 layouts.
if AsyncHTTPProvider is None:  # type: ignore[truthy-bool]
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=DeprecationWarning,
            module="websockets\\.legacy",
        )
        try:  # pragma: no cover - compatibility path
            from web3.providers.rpc.async_rpc import AsyncHTTPProvider  # type: ignore
        except ImportError:
            from web3.providers.async_rpc import AsyncHTTPProvider  # type: ignore

try:
    # Web3>=6.x had async_geth_poa_middleware under geth_poa; removed in 7.x.
    from web3.middleware.geth_poa import async_geth_poa_middleware
except ImportError:  # pragma: no cover - compatibility path or removed
    try:
        from web3.middleware import async_geth_poa_middleware  # type: ignore
    except ImportError:
        async_geth_poa_middleware = None  # type: ignore

from .errors import (
    ApproveErc20Error,
    CancelWithdrawalError,
    ContractError,
    DepositError,
    FinalizeWithdrawalError,
    GetUserError,
    PayTabError,
    RemunerateError,
    RequestWithdrawalError,
    TabPaymentStatusError,
)
from .utils import load_abi, normalize_address, parse_u256


class ContractGateway:
    """Thin async wrapper around the Core4Mica smart contract."""

    def __init__(
        self,
        eth_rpc_url: str,
        private_key: str,
        contract_address: str,
        chain_id: int,
    ) -> None:
        self.w3 = AsyncWeb3(AsyncHTTPProvider(eth_rpc_url))
        # Support PoA chains used in tests/anvil when middleware is available.
        if async_geth_poa_middleware:
            self.w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)
        self.account = self.w3.eth.account.from_key(private_key)
        self.chain_id = chain_id
        self.contract_address = normalize_address(contract_address)
        self.contract = self.w3.eth.contract(
            address=self.contract_address,
            abi=load_abi("core4mica.json"),
        )
        self._erc20_cache: Dict[str, Any] = {}

    def _fn(self, signature: str):
        """Fetch a contract function by explicit signature (handles overloads)."""
        getter = getattr(self.contract, "get_function_by_signature", None)
        if getter:
            return getter(signature)
        return self.contract.functions[signature]

    async def _build_and_send(self, txn: Dict[str, Any]) -> Dict[str, Any]:
        """Sign, broadcast, and wait for receipt."""
        try:
            signed = self.account.sign_transaction(txn)
            tx_hash = await self.w3.eth.send_raw_transaction(signed.rawTransaction)
            receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash)
            return dict(receipt)
        except Exception as exc:
            raise ContractError(str(exc)) from exc

    async def _prepare_tx(self, func, value: int = 0) -> Dict[str, Any]:
        nonce = await self.w3.eth.get_transaction_count(self.account.address)
        base = {
            "from": self.account.address,
            "nonce": nonce,
            "chainId": self.chain_id,
            "value": value,
        }
        try:
            gas_estimate = await func.estimate_gas(base)
            base["gas"] = int(gas_estimate * 1.2)
        except Exception:
            base["gas"] = 300_000
        try:
            base["gasPrice"] = await self.w3.eth.gas_price
        except Exception:
            pass
        return base

    async def _build_tx(self, func, tx: Dict[str, Any]) -> Dict[str, Any]:
        built = func.build_transaction(tx)
        if hasattr(built, "__await__"):
            built = await built
        return built

    def _erc20(self, token_address: str):
        checksum = normalize_address(token_address)
        if checksum not in self._erc20_cache:
            abi = load_abi("erc20.json")
            self._erc20_cache[checksum] = self.w3.eth.contract(
                address=checksum, abi=abi
            )
        return self._erc20_cache[checksum]

    async def approve_erc20(self, token_address: str, amount: int) -> Dict[str, Any]:
        try:
            contract = self._erc20(token_address)
            func = contract.functions.approve(
                self.contract_address, parse_u256(amount)
            )
            tx = await self._prepare_tx(func)
            built = await self._build_tx(func, tx)
            return await self._build_and_send(built)
        except Exception as exc:
            raise ApproveErc20Error(str(exc)) from exc

    async def deposit(
        self, amount: int, erc20_token: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            if erc20_token:
                token = normalize_address(erc20_token)
                func = self.contract.functions.depositStablecoin(
                    token, parse_u256(amount)
                )
                tx = await self._prepare_tx(func)
                built = await self._build_tx(func, tx)
            else:
                func = self.contract.functions.deposit()
                tx = await self._prepare_tx(func, value=parse_u256(amount))
                built = await self._build_tx(func, tx)
            return await self._build_and_send(built)
        except Exception as exc:
            raise DepositError(str(exc)) from exc

    async def get_user_assets(self) -> List[Dict[str, Any]]:
        try:
            result = await self.contract.functions.getUserAllAssets(
                self.account.address
            ).call()
        except Exception as exc:
            raise GetUserError(str(exc)) from exc

        assets: List[Dict[str, Any]] = []
        for asset in result:
            assets.append(
                {
                    "asset": asset[0],
                    "collateral": parse_u256(asset[1]),
                    "withdrawal_request_timestamp": int(asset[2]),
                    "withdrawal_request_amount": parse_u256(asset[3]),
                }
            )
        return assets

    async def get_payment_status(self, tab_id: int) -> Dict[str, Any]:
        try:
            paid, remunerated, asset = await self.contract.functions.getPaymentStatus(
                parse_u256(tab_id)
            ).call()
        except Exception as exc:
            raise TabPaymentStatusError(str(exc)) from exc
        return {
            "paid": parse_u256(paid),
            "remunerated": bool(remunerated),
            "asset": to_checksum_address(asset),
        }

    async def pay_tab_eth(
        self, tab_id: int, req_id: int, amount: int, recipient: str
    ) -> Dict[str, Any]:
        try:
            data = f"tab_id:{hex(int(tab_id))};req_id:{hex(int(req_id))}".encode()
            tx = {
                "to": normalize_address(recipient),
                "from": self.account.address,
                "value": parse_u256(amount),
                "data": data,
                "nonce": await self.w3.eth.get_transaction_count(
                    self.account.address
                ),
                "chainId": self.chain_id,
                "gas": 120_000,
            }
            try:
                tx["gasPrice"] = await self.w3.eth.gas_price
            except Exception:
                pass
            return await self._build_and_send(tx)
        except Exception as exc:
            raise PayTabError(str(exc)) from exc

    async def pay_tab_erc20(
        self, tab_id: int, amount: int, erc20_token: str, recipient: str
    ) -> Dict[str, Any]:
        try:
            func = self.contract.functions.payTabInERC20Token(
                parse_u256(tab_id),
                normalize_address(erc20_token),
                parse_u256(amount),
                normalize_address(recipient),
            )
            tx = await self._prepare_tx(func)
            built = await self._build_tx(func, tx)
            return await self._build_and_send(built)
        except Exception as exc:
            raise PayTabError(str(exc)) from exc

    async def request_withdrawal(
        self, amount: int, erc20_token: Optional[str]
    ) -> Dict[str, Any]:
        try:
            if erc20_token:
                func = self._fn("requestWithdrawal(address,uint256)")(
                    normalize_address(erc20_token),
                    parse_u256(amount),
                )
            else:
                func = self._fn("requestWithdrawal(uint256)")(parse_u256(amount))
            tx = await self._prepare_tx(func)
            built = await self._build_tx(func, tx)
            return await self._build_and_send(built)
        except Exception as exc:
            raise RequestWithdrawalError(str(exc)) from exc

    async def cancel_withdrawal(self, erc20_token: Optional[str]) -> Dict[str, Any]:
        try:
            if erc20_token:
                func = self._fn("cancelWithdrawal(address)")(
                    normalize_address(erc20_token)
                )
            else:
                func = self._fn("cancelWithdrawal()")()
            tx = await self._prepare_tx(func)
            built = await self._build_tx(func, tx)
            return await self._build_and_send(built)
        except Exception as exc:
            raise CancelWithdrawalError(str(exc)) from exc

    async def finalize_withdrawal(self, erc20_token: Optional[str]) -> Dict[str, Any]:
        try:
            if erc20_token:
                func = self._fn("finalizeWithdrawal(address)")(
                    normalize_address(erc20_token)
                )
            else:
                func = self._fn("finalizeWithdrawal()")()
            tx = await self._prepare_tx(func)
            built = await self._build_tx(func, tx)
            return await self._build_and_send(built)
        except Exception as exc:
            raise FinalizeWithdrawalError(str(exc)) from exc

    async def remunerate(
        self, claims_blob: bytes, signature_words: List[bytes]
    ) -> Dict[str, Any]:
        try:
            sig_struct = [
                to_bytes(hexstr=word)
                if not isinstance(word, (bytes, bytearray))
                else word
                for word in signature_words
            ]
            func = self.contract.functions.remunerate(claims_blob, sig_struct)
            try:
                await func.call()
            except Exception as exc:
                raise RemunerateError(str(exc)) from exc
            tx = await self._prepare_tx(func)
            built = await self._build_tx(func, tx)
            return await self._build_and_send(built)
        except Exception as exc:
            if isinstance(exc, RemunerateError):
                raise
            raise RemunerateError(str(exc)) from exc
