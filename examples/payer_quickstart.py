import asyncio
import json
import os
import time

from eth_account import Account
from fourmica_sdk import (
    AssetBalanceInfo,
    Client,
    ConfigBuilder,
    PaymentGuaranteeRequestClaims,
    SigningScheme,
)

PAYER_KEY = os.environ["PAYER_KEY"]
RECIPIENT_ADDRESS = os.environ["RECIPIENT_ADDRESS"]
TAB_ID = int(os.environ["TAB_ID"], 0)
REQ_ID = int(os.environ["REQ_ID"], 0)
DEFAULT_ASSET_ADDRESS = "0x0000000000000000000000000000000000000000"
REQUESTED_AMOUNT_WEI = int(os.getenv("AMOUNT_WEI", "100000000000000000"), 0)
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS") or DEFAULT_ASSET_ADDRESS
RECIPIENT_KEY = os.getenv("RECIPIENT_KEY")


async def main() -> None:
    payer_cfg = ConfigBuilder().from_env().wallet_private_key(PAYER_KEY).build()
    payer_client = await Client.new(payer_cfg)
    recipient_client = None
    try:
        user_address = Account.from_key(PAYER_KEY).address
        amount_wei = REQUESTED_AMOUNT_WEI

        balance_raw = await payer_client.rpc.get_user_asset_balance(
            user_address, ASSET_ADDRESS
        )
        if balance_raw:
            balance = AssetBalanceInfo.from_rpc(balance_raw)
            available = max(balance.total - balance.locked, 0)
            print("COLLATERAL_TOTAL=", balance.total)
            print("COLLATERAL_LOCKED=", balance.locked)
            print("COLLATERAL_AVAILABLE=", available)
            if available <= 0:
                raise SystemExit("No available collateral for this asset.")
            if amount_wei > available:
                amount_wei = available
            if amount_wei <= 0:
                raise SystemExit("Requested amount exceeds available collateral.")
        else:
            print("COLLATERAL_TOTAL= <unknown>")
            print("COLLATERAL_LOCKED= <unknown>")
            print("COLLATERAL_AVAILABLE= <unknown>")
        print("AMOUNT_WEI=", amount_wei)

        claims = PaymentGuaranteeRequestClaims.new(
            user_address=user_address,
            recipient_address=RECIPIENT_ADDRESS,
            tab_id=TAB_ID,
            req_id=REQ_ID,
            amount=amount_wei,
            timestamp=int(time.time()),
            erc20_token=ASSET_ADDRESS,
        )
        signature = await payer_client.user.sign_payment(claims, SigningScheme.EIP712)

        print("PAYER_SIGNATURE=", signature.signature)
        print(
            "CLAIMS_JSON=",
            json.dumps(
                {
                    "user_address": claims.user_address,
                    "recipient_address": claims.recipient_address,
                    "tab_id": claims.tab_id,
                    "req_id": claims.req_id,
                    "amount": claims.amount,
                    "asset_address": claims.asset_address,
                    "timestamp": claims.timestamp,
                }
            ),
        )
        if RECIPIENT_KEY:
            recipient_cfg = (
                ConfigBuilder().from_env().wallet_private_key(RECIPIENT_KEY).build()
            )
            recipient_client = await Client.new(recipient_cfg)
            cert = await recipient_client.recipient.issue_payment_guarantee(
                claims, signature.signature, SigningScheme.EIP712
            )
            print("CERT_CLAIMS=", cert.claims)
            print("CERT_SIGNATURE=", cert.signature)
    finally:
        if recipient_client is not None:
            await recipient_client.aclose()
        await payer_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
