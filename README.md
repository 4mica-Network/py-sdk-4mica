# 4Mica Python SDK

## Installation

```bash
pip install 'sdk-4mica[bls]'
```

## Auth (SIWE)

Core `/core/*` endpoints require bearer auth. Enable SIWE auth with your wallet key:

```python
from fourmica_sdk import Client, ConfigBuilder

cfg = (
    ConfigBuilder()
    .from_env()
    .wallet_private_key(PRIVATE_KEY)
    .enable_auth()
    .build()
)
client = await Client.new(cfg)
await client.login()
```

If you already have a bearer token, set it directly:

```python
cfg = (
    ConfigBuilder()
    .from_env()
    .wallet_private_key(PRIVATE_KEY)
    .bearer_token(BEARER_TOKEN)
    .build()
)
client = await Client.new(cfg)
```

Auth environment variables:

- `4MICA_BEARER_TOKEN`
- `4MICA_AUTH_URL` (defaults to `4MICA_RPC_URL`)
- `4MICA_AUTH_REFRESH_MARGIN_SECS` (default: `60`)

## Registration (users & agents): deposit collateral

In 4Mica, a wallet is considered "registered" once it has deposited collateral into the
4Mica vault. The core service watches the chain events and register users once they deposit. Any wallet that will be **debited by guarantees** (payers or agent
wallets acting on behalf of payers) must deposit first. The deposit can be ETH or an ERC-20.

Sample registration deposit:

```python
import asyncio
import os

from fourmica_sdk import Client, ConfigBuilder

PRIVATE_KEY = os.environ["PRIVATE_KEY"]
USDC_ADDRESS = os.environ.get("USDC_ADDRESS")  # optional ERC20


async def main() -> None:
    client = await Client.new(
        ConfigBuilder().from_env().wallet_private_key(PRIVATE_KEY).build()
    )
    try:
        # ETH deposit (registers the wallet once the event is indexed)
        await client.user.deposit(1_000_000_000_000_000_000)  # 1 ETH

        # ERC-20 deposit (approve first)
        if USDC_ADDRESS:
            await client.user.approve_erc20(USDC_ADDRESS, 100_000_000)  # 100 USDC (6 decimals)
            await client.user.deposit(100_000_000, USDC_ADDRESS)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
```

Notes:
- Latency of registration is same as the latency of the underlying chain. 

## Recipient registration (alpha)

Recipients do **not** need to register in the current alpha. There is no on-chain or API
registration step for recipient addresses. A recipient only needs a wallet key to:
- create tabs (the SDK enforces that the signer address matches `recipient_address`), and
- request/verify guarantees for its own address.

## Quick start (direct SDK)

This direct flow talks to 4mica core and shows the four core actions: deposit, open a tab, request a guarantee, and settle (remunerate) it on-chain. The payer and recipient roles are separate in production, so the SDK uses different keys. The snippets below are copied from the runnable scripts in `examples/recipient_quickstart.py` and `examples/payer_quickstart.py`.

Key requirements:

- Payer flow uses the private key of the user `PAYER_KEY` and `RECIPIENT_ADDRESS`.

Four-step direct flow:

1. Deposit collateral (payer). For ETH, call `payer_client.user.deposit(amount)`. For ERC20,
   call `payer_client.user.approve_erc20(token, amount)` first, then
   `payer_client.user.deposit(amount, token)`. ‍‍`token` is the contract address of the USDC/USDT. 
2. Get `tab_id` and `req_id` (recipient). Call `recipient_client.recipient.create_tab(...)` which hits
   core `/core/payment-tabs` (core may reuse an active tab). The core response includes
   `next_req_id`; with the SDK, compute it by calling
   `latest = await recipient_client.recipient.get_latest_guarantee(tab_id)` and using
   `req_id = 0 if latest is None else latest.req_id + 1`.
3. Sign the guarantee (payer). Build `PaymentGuaranteeRequestClaims` with `tab_id`, `req_id`,
   amount, timestamp, and asset, then call
   `signature = await payer_client.user.sign_payment(claims, SigningScheme.EIP712)`.
4. Settle (recipient). Call `cert = await recipient_client.issue_payment_guarantee(...)` with
   the claims + payer signature, then `await recipient_client.remunerate(cert)` to settle on
   chain.

```bash
pip install 'sdk-4mica[bls]'
```

### Recipient (resource server) quick start

Recipient is the service provider that accepts a payer's credit. Each recipient can open a tab with a user, a configurable line of credit that enables instant, trustless fair exchange between payer and merchant.
Run this script first to open a tab, compute the next `REQ_ID`, and print the tab's asset address plus the amount the payer should sign.

```bash
export RECIPIENT_KEY=0x..
export USER_ADDRESS=0x.. # payer address
export AMOUNT_WEI=100000000000000000
```

```python
import asyncio
import os

from eth_account import Account
from fourmica_sdk import Client, ConfigBuilder

RECIPIENT_KEY = os.environ["RECIPIENT_KEY"]
USER_ADDRESS = os.environ["USER_ADDRESS"]
AMOUNT_WEI = int(os.getenv("AMOUNT_WEI", "100000000000000000"), 0)


async def main() -> None:
    recipient_cfg = ConfigBuilder().from_env().wallet_private_key(RECIPIENT_KEY).build()
    recipient_client = await Client.new(recipient_cfg)
    try:
        recipient_address = Account.from_key(RECIPIENT_KEY).address

        tab_id = await recipient_client.recipient.create_tab(
            user_address=USER_ADDRESS,
            recipient_address=recipient_address,
            erc20_token=None,
            ttl=None,
        )
        latest = await recipient_client.recipient.get_latest_guarantee(tab_id)
        req_id = latest.req_id + 1 if latest else 0
        tab = await recipient_client.recipient.get_tab(tab_id)
        asset_address = tab.asset_address if tab else None

        print("TAB_ID=", tab_id)
        print("REQ_ID=", req_id)
        print("AMOUNT_WEI=", AMOUNT_WEI)
        print("ASSET_ADDRESS=", asset_address)
    finally:
        await recipient_client.aclose()
if __name__ == "__main__":
    asyncio.run(main())
```

### Payer (client) quick start

Run this after you have a `TAB_ID` and `REQ_ID` from the recipient. It signs the guarantee and
optionally issues a certificate if you also pass `RECIPIENT_KEY`.

```bash
export PAYER_KEY=0x..
export RECIPIENT_ADDRESS=0x..
export TAB_ID=<tab_id>
export REQ_ID=<req_id>
export AMOUNT_WEI=100000000000000000
export ASSET_ADDRESS=0x0000000000000000000000000000000000000000
export RECIPIENT_KEY=0x.. # optional
```

```python
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
```

## Concepts

- Tabs are per `(user, recipient, asset)` credit ledgers. Core reuses an existing tab if it is still valid; otherwise it creates a new tab id using a SHA-256 hash of user, recipient, ttl, and a random UUID (treat `tab_id` as opaque).
- Tab lifecycle: tabs start `Pending`; the first valid guarantee opens the tab and sets `start_timestamp` to the claim timestamp. Guarantees must be within `[start_timestamp, start_timestamp + ttl]` and are rejected if the tab is closed or expired.
- Request ids: `req_id` is per-tab and strictly sequential. The first guarantee uses `req_id = 0`; each new guarantee must be `last_req_id + 1`. The facilitator returns `nextReqId` in `/tabs`.
- Guarantee request claims (v1) are the signed payload: `{ user_address, recipient_address, tab_id, req_id, amount, asset_address, timestamp }`. `asset_address` is the zero address for ETH if omitted. `timestamp` is seconds since epoch and is validated by core.
- Guarantee certificates are BLS signatures over `PaymentGuaranteeClaims` (core adds `domain`, `total_amount` which is the running sum for the tab, and `version`). The SDK models this as `BLSCert { claims, signature }`, where `claims` is ABI-encoded hex.

## Facilitator (x402)

The facilitator wraps the credit flow for x402 resource servers. Clients never call it directly; resource servers do. The canonical implementation and runnable examples live in `https://github.com/4mica-Network/x402-4mica`:
- `https://github.com/4mica-Network/x402-4mica/blob/main/examples/server/mock_paid_api.py` shows `/tab`, `/verify`, and `/settle` from a FastAPI resource server.
- `https://github.com/4mica-Network/x402-4mica/blob/main/examples/python_client/client.py` shows a client signing `X-PAYMENT` headers with the Python SDK.
- `https://github.com/4mica-Network/x402-4mica/blob/main/README.md` documents the full HTTP schema.

Endpoint shapes:

```text
POST /tabs
{ "userAddress": "...", "recipientAddress": "...", "erc20Token": null, "ttlSeconds": 3600 }

POST /verify
POST /settle
{ "x402Version": 1, "paymentHeader": "<base64 X-PAYMENT>", "paymentRequirements": { ... } }
```

### Quick integration (resource servers)

Use the facilitator (for example `https://x402.4mica.xyz/`) to open tabs and settle signed guarantees:

- Advertise `scheme = "4mica-credit"` and a supported `network` in your `402 Payment Required` responses. Embed your POST tab endpoint in `paymentRequirements.extra.tabEndpoint`, alongside `payTo` / `asset` / `maxAmountRequired`.
- Implement the tab endpoint to accept `{ userAddress, paymentRequirements }`, call the facilitator’s `POST /tabs` with `{ userAddress, recipientAddress = payTo, erc20Token = asset, ttlSeconds? }`, and return the tab response (at least `tabId`, `userAddress`, and the latest `nextReqId`/`reqId`). Cache tabs per `(user, recipient, asset)` to avoid extra calls; the facilitator will also reuse them.
- When a retried request arrives with `X-PAYMENT`, base64-decode it and send `{ x402Version, paymentHeader, paymentRequirements }` to `/verify` (optional preflight) and `/settle` (to obtain the certificate).

### Quick integration (clients)

Install the SDK and sign the `X-PAYMENT` header with `X402Flow` (same flow as the TypeScript and Rust SDKs in `~/x402-4mica`):

```bash
pip install sdk-4mica
```

```python
import asyncio
from fourmica_sdk import (
    Client,
    ConfigBuilder,
    PaymentRequirementsV1,
    X402Flow,
)

payer_key = "0x..."    # wallet private key
user_address = "0x..." # address to embed in the claims

async def main():
    cfg = ConfigBuilder().wallet_private_key(payer_key).rpc_url("https://api.4mica.xyz/").build()
    client = await Client.new(cfg)
    flow = X402Flow.from_client(client)

    # Fetch the recipient's paymentRequirements (must include extra.tabEndpoint)
    req_raw = fetch_requirements_somehow()[0]
    requirements = PaymentRequirementsV1.from_raw(req_raw)

    payment = await flow.sign_payment(requirements, user_address)
    headers = {"X-PAYMENT": payment.header}  # base64 string to send with the retry

    # Optional: settle immediately if the recipient delegates settlement to you
    settlement = await flow.settle_payment(payment, requirements, facilitator_url="https://x402.4mica.xyz/")
    print("Settlement:", settlement.settlement)

    await client.aclose()

asyncio.run(main())
```

### V2 payments

To sign x402 v2 payments, build `X402PaymentRequired` and `PaymentRequirementsV2` and call `sign_payment_v2`:

```python
from fourmica_sdk import X402PaymentRequired, PaymentRequirementsV2, X402ResourceInfo

accepted = PaymentRequirementsV2.from_raw(accepted_raw)
payment_required = X402PaymentRequired(
    x402_version=2,
    resource=X402ResourceInfo.from_raw(resource_raw),
    accepts=[accepted],
)

payment = await flow.sign_payment_v2(payment_required, accepted, user_address)
```

## X-PAYMENT header schema

`X-PAYMENT` is a base64-encoded JSON envelope:

```json
{
  "x402Version": 1,
  "scheme": "4mica-credit",
  "network": "polygon-amoy",
  "payload": {
    "claims": {
      "user_address": "<0x-prefixed checksum string>",
      "recipient_address": "<0x-prefixed checksum string>",
      "tab_id": "<decimal or 0x value>",
      "req_id": "<decimal or 0x value>",
      "amount": "<decimal or 0x value>",
      "asset_address": "<0x-prefixed checksum string>",
      "timestamp": 1716500000,
      "version": "v1"
    },
    "signature": "<0x-prefixed wallet signature>",
    "scheme": "eip712"
  }
}
```

Facilitators enforce that `scheme` / `network` match `/supported`, `payTo` matches
`recipient_address` in the claims, and `asset` / `maxAmountRequired` equal the signed `amount`.

## End-to-end credit flow (x402)

1. Resource sends `402 Payment Required` with `(scheme, network)` and a tab endpoint.
2. Client calls the tab endpoint with `{ userAddress, erc20Token?, ttlSeconds? }`; the recipient calls `/tabs` and returns tab metadata.
3. Client signs a guarantee with the SDK and wraps it into `X-PAYMENT`.
4. Client retries the protected call with `X-PAYMENT: <base64>`.
5. Recipient optionally calls `/verify` with `{ x402Version, paymentHeader, paymentRequirements }`.
6. Recipient calls `/settle` to obtain the certificate, then relays repayment details to the payer.

## Configuration

- `wallet_private_key` (**required**)
- `rpc_url` (defaults to `https://api.4mica.xyz/`)
- `ethereum_http_rpc_url` and `contract_address` are auto-fetched from the facilitator unless provided.

Environment variables mirror the Rust SDK:

```
4MICA_WALLET_PRIVATE_KEY
4MICA_RPC_URL
4MICA_ETHEREUM_HTTP_RPC_URL
4MICA_CONTRACT_ADDRESS
```

## Notes

- All methods are `async`; use `asyncio.run` or your event loop of choice.
- Remuneration requires `py-ecc` (`pip install 'sdk-4mica[bls]'`) to expand BLS signatures into the on-chain format.
- Numeric values accept `int` or hex/decimal strings and are serialized to `0x`-prefixed hex when sent to the facilitator.
