# 4Mica Python SDK

An asyncio-first Python port of the Rust SDK for interacting with the 4Mica payment network. It mirrors the Rust SDK surface: user (payer) flows, recipient flows, X402 helpers, and strongly-typed request/response models.

## Installation

```bash
pip install .           # from this repo
# Optional: remuneration requires BLS decoding
pip install 'sdk-4mica[bls]'
```

## Quick start

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

### X402 helper

```python
from fourmica_sdk import X402Flow, PaymentRequirements

flow = X402Flow.from_client(client)
payment = await flow.sign_payment(payment_requirements, user_address="0xUser")
resp = await flow.settle_payment(payment, payment_requirements, facilitator_url="https://api.4mica.xyz/core/")
```

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
4MICA_ADMIN_API_KEY
```

## Notes

- All methods are `async`; use `asyncio.run` or your event loop of choice.
- Remuneration requires `py-ecc` (`pip install 'sdk-4mica[bls]'`) to expand BLS signatures into the on-chain format.
- Numeric values accept `int` or hex/decimal strings and are serialized to `0x`-prefixed hex when sent to the facilitator.
