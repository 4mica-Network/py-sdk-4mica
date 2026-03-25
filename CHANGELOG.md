# Changelog

## 1.0.0 - Unreleased

### Changed
- Default `pytest` selection now excludes integration tests (`-m "not integration"`).
- X402 V2 flow no longer requires `paymentRequirements.extra.validationChainId`.
  The SDK derives `validation_chain_id` from the CAIP-2 network (`eip155:<chainId>`).
- When `extra.validationChainId` is provided, it is validated against the derived network chain id.

## 0.3.0

### Breaking
- `PaymentGuaranteeRequestClaims` now requires `req_id`; signing payloads include `req_id` for EIP-712/EIP-191.
- X402 payment envelopes include `req_id`; tab responses should return `nextReqId`/`reqId` to populate it.

### Changed
- `RpcProxy.list_recipient_tabs` now uses `settlement_status` query params.
- `RpcError` exposes `status_code` for HTTP failures.
- `ContractGateway` uses explicit overload signatures for withdrawal calls.
