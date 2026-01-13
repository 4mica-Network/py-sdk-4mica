# Changelog

## 0.3.0 - Unreleased

### Breaking
- `PaymentGuaranteeRequestClaims` now requires `req_id`; signing payloads include `req_id` for EIP-712/EIP-191.
- X402 payment envelopes include `req_id`; tab responses should return `nextReqId`/`reqId` to populate it.

### Changed
- `RpcProxy.list_recipient_tabs` now uses `settlement_status` query params.
- `RpcError` exposes `status_code` for HTTP failures.
- `ContractGateway` uses explicit overload signatures for withdrawal calls.
