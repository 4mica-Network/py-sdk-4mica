# 4Mica Python SDK

Asyncio-first bindings for the 4mica credit flow used by x402. This mirrors the Rust SDK surface (payer, recipient, X402 helpers, strongly typed request/response models) and now matches the docs in `~/x402-4mica`.

## Installation

```bash
pip install .           # from this repo
# Optional: remuneration requires BLS decoding
pip install 'sdk-4mica[bls]'
```

## Quick integration (resource servers)

Use the facilitator (for example `https://x402.4mica.xyz/`) to open tabs and settle signed guarantees:

- Advertise `scheme = "4mica-credit"` and a supported `network` in your `402 Payment Required` responses. Embed your POST tab endpoint in `paymentRequirements.extra.tabEndpoint`, alongside `payTo` / `asset` / `maxAmountRequired`.
- Implement the tab endpoint to accept `{ userAddress, paymentRequirements }`, call the facilitator’s `POST /tabs` with `{ userAddress, recipientAddress = payTo, erc20Token = asset, ttlSeconds? }`, and return the tab response (at least `tabId`, `userAddress`, and the latest `nextReqId`/`reqId`). Cache tabs per `(user, recipient, asset)` to avoid extra calls; the facilitator will also reuse them.
- When a retried request arrives with `X-PAYMENT`, base64-decode it and send `{ x402Version, paymentHeader, paymentRequirements }` to `/verify` (optional preflight) and `/settle` (to obtain the certificate).

## Quick integration (clients)

Install the SDK and sign the `X-PAYMENT` header with `X402Flow` (same flow as the TypeScript and Rust SDKs in `~/x402-4mica`):

```bash
pip install sdk-4mica
```

```python
import asyncio
from fourmica_sdk import Client, ConfigBuilder, PaymentRequirements, X402Flow

payer_key = "0x..."    # wallet private key
user_address = "0x..." # address to embed in the claims

async def main():
    cfg = ConfigBuilder().wallet_private_key(payer_key).rpc_url("https://api.4mica.xyz/").build()
    client = await Client.new(cfg)
    flow = X402Flow.from_client(client)

    # Fetch the recipient's paymentRequirements (must include extra.tabEndpoint)
    req_raw = fetch_requirements_somehow()[0]
    requirements = PaymentRequirements.from_raw(req_raw)

    payment = await flow.sign_payment(requirements, user_address)
    headers = {"X-PAYMENT": payment.header}  # base64 string to send with the retry

    # Optional: settle immediately if the recipient delegates settlement to you
    settlement = await flow.settle_payment(payment, requirements, facilitator_url="https://x402.4mica.xyz/")
    print("Settlement:", settlement.settlement)

    await client.aclose()

asyncio.run(main())
```

## SDK quick start (direct 4mica calls)

```python
import asyncio
from fourmica_sdk import (
    Client, ConfigBuilder, PaymentGuaranteeRequestClaims, SigningScheme
)

async def main():
    cfg = ConfigBuilder().from_env().wallet_private_key("0x...").build()
    client = await Client.new(cfg)

    # Deposit 1 ETH
    await client.user.deposit(10**18)

    # Create a tab as the recipient
    tab_id = await client.recipient.create_tab(
        user_address="0xUser",
        recipient_address=client.recipient._recipient_address,  # or set explicitly
        erc20_token=None,
        ttl=3600,
    )

    # Sign a payment as the user
    claims = PaymentGuaranteeRequestClaims.new(
        "0xUser",
        client.recipient._recipient_address,
        tab_id,
        0,  # req_id for the first request
        10**17,
        timestamp=int(__import__("time").time()),
        erc20_token=None,
    )
    sig = await client.user.sign_payment(claims, SigningScheme.EIP712)

    # Issue a guarantee as the recipient
    cert = await client.recipient.issue_payment_guarantee(claims, sig.signature, sig.scheme)
    print("Guarantee:", cert)

    await client.aclose()

asyncio.run(main())
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
