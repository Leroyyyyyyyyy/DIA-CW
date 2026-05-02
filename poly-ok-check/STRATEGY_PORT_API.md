# Strategy Port API (poly-ok-check)

This document lists which HTTP endpoints return which data for strategy code.
The service runs locally and wraps Polymarket CLOB data into stable JSON.

## 1) Start Service

```powershell
cd C:\Polyquant\poly-ok-check

# Optional bind address (default: 127.0.0.1:8787)
$env:POLY_PORT_BIND="127.0.0.1:8787"

# Required only for private endpoints
$env:POLYMARKET_PRIVATE_KEY="0x..."
$env:POLY_SIGNATURE_TYPE="gnosis-safe"   # eoa | proxy | gnosis-safe
$env:POLY_FUNDER="0x..."                 # optional

cargo run --bin strategy_port
```

Health check:

```powershell
Invoke-RestMethod "http://127.0.0.1:8787/health"
```

## 2) Public Endpoints (no private key needed)

| Endpoint | Data |
|---|---|
| `GET /v1/public/ok` | CLOB health status |
| `GET /v1/public/time` | CLOB server time |
| `GET /v1/public/geoblock` | `blocked,country,region,ip` |
| `GET /v1/public/markets?cursor=` | Market page with full market objects |
| `GET /v1/public/markets/sampling?cursor=` | Sampling market page |
| `GET /v1/public/markets/simplified?cursor=` | Simplified market page |
| `GET /v1/public/markets/sampling-simplified?cursor=` | Simplified sampling page |
| `GET /v1/public/market/{condition_id}` | Single market detail (`question,tokens,fees,min_tick`) |
| `GET /v1/public/token/{token_id}/book` | Order book (`bids,asks,timestamp,hash`) |
| `GET /v1/public/tokens/books?ids=ID1,ID2` | Batch order books |
| `GET /v1/public/token/{token_id}/price?side=buy` | Price for one token and side |
| `GET /v1/public/tokens/prices?ids=ID1,ID2&side=buy` | Batch prices map |
| `GET /v1/public/token/{token_id}/midpoint` | Midpoint |
| `GET /v1/public/tokens/midpoints?ids=ID1,ID2` | Batch midpoints |
| `GET /v1/public/token/{token_id}/spread` | Spread |
| `GET /v1/public/tokens/spreads?ids=ID1,ID2` | Batch spreads |
| `GET /v1/public/token/{token_id}/last-trade` | Last trade (`price,side`) |
| `GET /v1/public/tokens/last-trades?ids=ID1,ID2` | Batch last trades |
| `GET /v1/public/token/{token_id}/tick-size` | Minimum tick size |
| `GET /v1/public/token/{token_id}/fee-rate` | Base fee bps |
| `GET /v1/public/token/{token_id}/neg-risk` | Neg-risk flag |
| `GET /v1/public/token/{token_id}/price-history?interval=1d&fidelity=30` | Price history points |

`interval`: `1m | 1h | 6h | 1d | 1w | max`

## 3) Private Endpoints (private key required)

| Endpoint | Data |
|---|---|
| `GET /v1/private/orders?market=&asset=&cursor=` | Account open orders page |
| `GET /v1/private/order/{order_id}` | Single order detail |
| `GET /v1/private/trades?market=&asset=&cursor=` | Account trades page |
| `GET /v1/private/balance?asset_type=collateral` | Balance and allowances |
| `POST /v1/private/update-balance?asset_type=collateral` | Force refresh balance cache |
| `GET /v1/private/api-keys` | API key debug info |
| `GET /v1/private/account-status` | `closed_only` flag |

`asset_type`: `collateral | conditional`

## 4) PowerShell Examples

```powershell
# sampling markets
Invoke-RestMethod "http://127.0.0.1:8787/v1/public/markets/sampling"

# one token order book
Invoke-RestMethod "http://127.0.0.1:8787/v1/public/token/51939490109676186832507970701169130490548061087912630009168726706475001411420/book"

# one token price and midpoint
Invoke-RestMethod "http://127.0.0.1:8787/v1/public/token/51939490109676186832507970701169130490548061087912630009168726706475001411420/price?side=buy"
Invoke-RestMethod "http://127.0.0.1:8787/v1/public/token/51939490109676186832507970701169130490548061087912630009168726706475001411420/midpoint"

# refresh and read collateral balance
Invoke-RestMethod -Method Post "http://127.0.0.1:8787/v1/private/update-balance?asset_type=collateral"
Invoke-RestMethod "http://127.0.0.1:8787/v1/private/balance?asset_type=collateral"

# read orders and trades
Invoke-RestMethod "http://127.0.0.1:8787/v1/private/orders"
Invoke-RestMethod "http://127.0.0.1:8787/v1/private/trades"
```

## 5) Source Files

- Service: `C:\Polyquant\poly-ok-check\src\bin\strategy_port.rs`
- WS dumper: `C:\Polyquant\poly-ok-check\src\bin\ws_dump.rs`
- Execution loop: `C:\Polyquant\poly-ok-check\src\bin\exec_loop.rs`
