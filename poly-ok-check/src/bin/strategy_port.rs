use std::net::SocketAddr;
use std::str::FromStr;

use alloy::signers::Signer as _;
use alloy::signers::local::PrivateKeySigner;
use anyhow::Context;
use axum::extract::{Path, Query, State};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use polymarket_client_sdk::auth::Normal;
use polymarket_client_sdk::auth::state::Authenticated;
use polymarket_client_sdk::clob;
use polymarket_client_sdk::clob::types::request::{
    BalanceAllowanceRequest, LastTradePriceRequest, MidpointRequest, OrderBookSummaryRequest,
    OrdersRequest, PriceHistoryRequest, PriceRequest, SpreadRequest, TradesRequest,
};
use polymarket_client_sdk::clob::types::{AssetType, Interval, Side, SignatureType, TimeRange};
use polymarket_client_sdk::types::{Address, B256, U256};
use polymarket_client_sdk::{POLYGON, PRIVATE_KEY_VAR};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Clone)]
struct AppState {
    public_client: clob::Client,
    auth_client: Option<clob::Client<Authenticated<Normal>>>,
    startup: StartupInfo,
}

#[derive(Clone, Serialize)]
struct StartupInfo {
    bind: String,
    auth_enabled: bool,
    signature_type: Option<String>,
    signer_eoa: Option<String>,
    funder: Option<String>,
}

#[derive(Debug)]
struct ApiError {
    status: StatusCode,
    message: String,
}

impl ApiError {
    fn bad_request(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            message: message.into(),
        }
    }

    fn unauthorized(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::UNAUTHORIZED,
            message: message.into(),
        }
    }

    fn internal(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            message: message.into(),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (
            self.status,
            Json(json!({
                "ok": false,
                "error": self.message,
            })),
        )
            .into_response()
    }
}

type ApiResult = Result<Json<Value>, ApiError>;

fn parse_token_id(s: &str) -> Result<U256, ApiError> {
    U256::from_str(s).map_err(|_| ApiError::bad_request(format!("invalid token_id: {s}")))
}

fn parse_condition_id(s: &str) -> Result<B256, ApiError> {
    B256::from_str(s)
        .map_err(|_| ApiError::bad_request(format!("invalid condition_id (32-byte hex): {s}")))
}

fn parse_side(s: &str) -> Result<Side, ApiError> {
    match s.to_ascii_lowercase().as_str() {
        "buy" => Ok(Side::Buy),
        "sell" => Ok(Side::Sell),
        _ => Err(ApiError::bad_request(format!(
            "invalid side: {s}, expected buy|sell"
        ))),
    }
}

fn parse_asset_type(s: &str) -> Result<AssetType, ApiError> {
    match s.to_ascii_lowercase().as_str() {
        "collateral" => Ok(AssetType::Collateral),
        "conditional" => Ok(AssetType::Conditional),
        _ => Err(ApiError::bad_request(format!(
            "invalid asset_type: {s}, expected collateral|conditional"
        ))),
    }
}

fn parse_interval(s: &str) -> Result<Interval, ApiError> {
    match s {
        "1m" => Ok(Interval::OneMinute),
        "1h" => Ok(Interval::OneHour),
        "6h" => Ok(Interval::SixHours),
        "1d" => Ok(Interval::OneDay),
        "1w" => Ok(Interval::OneWeek),
        "max" => Ok(Interval::Max),
        _ => Err(ApiError::bad_request(format!(
            "invalid interval: {s}, expected 1m|1h|6h|1d|1w|max"
        ))),
    }
}

fn parse_token_ids_csv(s: &str) -> Result<Vec<U256>, ApiError> {
    let ids: Result<Vec<_>, _> = s
        .split(',')
        .map(str::trim)
        .filter(|x| !x.is_empty())
        .map(parse_token_id)
        .collect();
    let ids = ids?;
    if ids.is_empty() {
        return Err(ApiError::bad_request("ids is empty"));
    }
    Ok(ids)
}

fn ok(data: Value) -> ApiResult {
    Ok(Json(json!({
        "ok": true,
        "data": data,
    })))
}

fn to_value<T: serde::Serialize>(data: T) -> Result<Value, ApiError> {
    serde_json::to_value(data).map_err(|e| ApiError::internal(e.to_string()))
}

fn side_label(side: Side) -> &'static str {
    match side {
        Side::Buy => "buy",
        Side::Sell => "sell",
        _ => "unknown",
    }
}

fn auth_client(state: &AppState) -> Result<clob::Client<Authenticated<Normal>>, ApiError> {
    state.auth_client.clone().ok_or_else(|| {
        ApiError::unauthorized(format!(
            "authenticated endpoints disabled: set {} and restart",
            PRIVATE_KEY_VAR
        ))
    })
}

#[derive(Deserialize)]
struct CursorQuery {
    cursor: Option<String>,
}

#[derive(Deserialize)]
struct IdsQuery {
    ids: String,
}

#[derive(Deserialize)]
struct SideQuery {
    side: String,
}

#[derive(Deserialize)]
struct SpreadQuery {
    side: Option<String>,
}

#[derive(Deserialize)]
struct PriceHistoryQuery {
    interval: Option<String>,
    fidelity: Option<u32>,
}

#[derive(Deserialize)]
struct OrdersQuery {
    market: Option<String>,
    asset: Option<String>,
    cursor: Option<String>,
}

#[derive(Deserialize)]
struct BalanceQuery {
    asset_type: String,
    token: Option<String>,
}

#[derive(Deserialize)]
struct TokenPath {
    token_id: String,
}

#[derive(Deserialize)]
struct ConditionPath {
    condition_id: String,
}

#[derive(Deserialize)]
struct OrderPath {
    order_id: String,
}

async fn health(State(state): State<AppState>) -> ApiResult {
    ok(json!({
        "service": "strategy_port",
        "startup": state.startup,
    }))
}

async fn clob_ok(State(state): State<AppState>) -> ApiResult {
    let result = state
        .public_client
        .ok()
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(to_value(result)?)
}

async fn server_time(State(state): State<AppState>) -> ApiResult {
    let result = state
        .public_client
        .server_time()
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({ "server_time": result }))
}

async fn geoblock(State(state): State<AppState>) -> ApiResult {
    let result = state
        .public_client
        .check_geoblock()
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({
        "blocked": result.blocked,
        "ip": result.ip,
        "country": result.country,
        "region": result.region,
    }))
}

async fn markets(State(state): State<AppState>, Query(q): Query<CursorQuery>) -> ApiResult {
    let result = state
        .public_client
        .markets(q.cursor)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(to_value(result)?)
}

async fn sampling_markets(
    State(state): State<AppState>,
    Query(q): Query<CursorQuery>,
) -> ApiResult {
    let result = state
        .public_client
        .sampling_markets(q.cursor)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(to_value(result)?)
}

async fn simplified_markets(
    State(state): State<AppState>,
    Query(q): Query<CursorQuery>,
) -> ApiResult {
    let result = state
        .public_client
        .simplified_markets(q.cursor)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(to_value(result)?)
}

async fn sampling_simplified_markets(
    State(state): State<AppState>,
    Query(q): Query<CursorQuery>,
) -> ApiResult {
    let result = state
        .public_client
        .sampling_simplified_markets(q.cursor)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(to_value(result)?)
}

async fn market_by_condition(
    State(state): State<AppState>,
    Path(path): Path<ConditionPath>,
) -> ApiResult {
    let _ = parse_condition_id(&path.condition_id)?;
    let result = state
        .public_client
        .market(&path.condition_id)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(to_value(result)?)
}

async fn book(State(state): State<AppState>, Path(path): Path<TokenPath>) -> ApiResult {
    let token = parse_token_id(&path.token_id)?;
    let request = OrderBookSummaryRequest::builder().token_id(token).build();
    let result = state
        .public_client
        .order_book(&request)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(to_value(result)?)
}

async fn books(State(state): State<AppState>, Query(q): Query<IdsQuery>) -> ApiResult {
    let requests: Vec<_> = parse_token_ids_csv(&q.ids)?
        .into_iter()
        .map(|id| OrderBookSummaryRequest::builder().token_id(id).build())
        .collect();
    let result = state
        .public_client
        .order_books(&requests)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(to_value(result)?)
}

async fn price(
    State(state): State<AppState>,
    Path(path): Path<TokenPath>,
    Query(q): Query<SideQuery>,
) -> ApiResult {
    let token = parse_token_id(&path.token_id)?;
    let request = PriceRequest::builder()
        .token_id(token)
        .side(parse_side(&q.side)?)
        .build();
    let result = state
        .public_client
        .price(&request)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({
        "price": result.price.to_string(),
        "side": q.side.to_ascii_lowercase(),
    }))
}

async fn prices(
    State(state): State<AppState>,
    Query(q): Query<IdsQuery>,
    Query(side_q): Query<SideQuery>,
) -> ApiResult {
    let side = parse_side(&side_q.side)?;
    let requests: Vec<_> = parse_token_ids_csv(&q.ids)?
        .into_iter()
        .map(|id| PriceRequest::builder().token_id(id).side(side).build())
        .collect();
    let result = state
        .public_client
        .prices(&requests)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    let prices_json = if let Some(prices) = result.prices {
        let mut outer = serde_json::Map::new();
        for (token_id, sides) in prices {
            let mut inner = serde_json::Map::new();
            for (side, price) in sides {
                inner.insert(side_label(side).to_string(), json!(price.to_string()));
            }
            outer.insert(token_id.to_string(), Value::Object(inner));
        }
        Value::Object(outer)
    } else {
        Value::Null
    };
    ok(json!({ "prices": prices_json }))
}

async fn midpoint(State(state): State<AppState>, Path(path): Path<TokenPath>) -> ApiResult {
    let token = parse_token_id(&path.token_id)?;
    let request = MidpointRequest::builder().token_id(token).build();
    let result = state
        .public_client
        .midpoint(&request)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({ "mid": result.mid.to_string() }))
}

async fn midpoints(State(state): State<AppState>, Query(q): Query<IdsQuery>) -> ApiResult {
    let requests: Vec<_> = parse_token_ids_csv(&q.ids)?
        .into_iter()
        .map(|id| MidpointRequest::builder().token_id(id).build())
        .collect();
    let result = state
        .public_client
        .midpoints(&requests)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    let mut out = serde_json::Map::new();
    for (token_id, mid) in result.midpoints {
        out.insert(token_id.to_string(), json!(mid.to_string()));
    }
    ok(json!({ "midpoints": out }))
}

async fn spread(
    State(state): State<AppState>,
    Path(path): Path<TokenPath>,
    Query(q): Query<SpreadQuery>,
) -> ApiResult {
    let token = parse_token_id(&path.token_id)?;
    let side = q.side.as_deref().map(parse_side).transpose()?;
    let request = SpreadRequest::builder()
        .token_id(token)
        .maybe_side(side)
        .build();
    let result = state
        .public_client
        .spread(&request)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({ "spread": result.spread.to_string() }))
}

async fn spreads(State(state): State<AppState>, Query(q): Query<IdsQuery>) -> ApiResult {
    let requests: Vec<_> = parse_token_ids_csv(&q.ids)?
        .into_iter()
        .map(|id| SpreadRequest::builder().token_id(id).build())
        .collect();
    let result = state
        .public_client
        .spreads(&requests)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    let spreads_json = if let Some(spreads) = result.spreads {
        let mut out = serde_json::Map::new();
        for (token_id, spread) in spreads {
            out.insert(token_id.to_string(), json!(spread.to_string()));
        }
        Value::Object(out)
    } else {
        Value::Null
    };
    ok(json!({ "spreads": spreads_json }))
}

async fn last_trade(State(state): State<AppState>, Path(path): Path<TokenPath>) -> ApiResult {
    let token = parse_token_id(&path.token_id)?;
    let request = LastTradePriceRequest::builder().token_id(token).build();
    let result = state
        .public_client
        .last_trade_price(&request)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({
        "price": result.price.to_string(),
        "side": side_label(result.side),
    }))
}

async fn last_trades(State(state): State<AppState>, Query(q): Query<IdsQuery>) -> ApiResult {
    let requests: Vec<_> = parse_token_ids_csv(&q.ids)?
        .into_iter()
        .map(|id| LastTradePriceRequest::builder().token_id(id).build())
        .collect();
    let result = state
        .public_client
        .last_trades_prices(&requests)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    let data: Vec<Value> = result
        .into_iter()
        .map(|x| {
            json!({
                "token_id": x.token_id.to_string(),
                "price": x.price.to_string(),
                "side": side_label(x.side),
            })
        })
        .collect();
    ok(json!({ "last_trades": data }))
}

async fn tick_size(State(state): State<AppState>, Path(path): Path<TokenPath>) -> ApiResult {
    let token = parse_token_id(&path.token_id)?;
    let result = state
        .public_client
        .tick_size(token)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({
        "minimum_tick_size": result.minimum_tick_size.to_string(),
    }))
}

async fn fee_rate(State(state): State<AppState>, Path(path): Path<TokenPath>) -> ApiResult {
    let token = parse_token_id(&path.token_id)?;
    let result = state
        .public_client
        .fee_rate_bps(token)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({ "base_fee_bps": result.base_fee }))
}

async fn neg_risk(State(state): State<AppState>, Path(path): Path<TokenPath>) -> ApiResult {
    let token = parse_token_id(&path.token_id)?;
    let result = state
        .public_client
        .neg_risk(token)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({ "neg_risk": result.neg_risk }))
}

async fn price_history(
    State(state): State<AppState>,
    Path(path): Path<TokenPath>,
    Query(q): Query<PriceHistoryQuery>,
) -> ApiResult {
    let token = parse_token_id(&path.token_id)?;
    let interval = parse_interval(q.interval.as_deref().unwrap_or("1d"))?;
    let request = PriceHistoryRequest::builder()
        .market(token)
        .time_range(TimeRange::from_interval(interval))
        .maybe_fidelity(q.fidelity)
        .build();
    let result = state
        .public_client
        .price_history(&request)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    let history: Vec<Value> = result
        .history
        .into_iter()
        .map(|x| json!({ "t": x.t, "p": x.p.to_string() }))
        .collect();
    ok(json!({ "history": history }))
}

async fn private_orders(State(state): State<AppState>, Query(q): Query<OrdersQuery>) -> ApiResult {
    let client = auth_client(&state)?;
    let request = OrdersRequest::builder()
        .maybe_market(q.market.as_deref().map(parse_condition_id).transpose()?)
        .maybe_asset_id(q.asset.as_deref().map(parse_token_id).transpose()?)
        .build();
    let result = client
        .orders(&request, q.cursor)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    let data: Vec<Value> = result
        .data
        .into_iter()
        .map(|o| {
            json!({
                "id": o.id,
                "status": format!("{:?}", o.status),
                "owner": o.owner.to_string(),
                "maker_address": o.maker_address.to_string(),
                "market": o.market.to_string(),
                "asset_id": o.asset_id.to_string(),
                "side": side_label(o.side),
                "original_size": o.original_size.to_string(),
                "size_matched": o.size_matched.to_string(),
                "price": o.price.to_string(),
                "associate_trades": o.associate_trades,
                "outcome": o.outcome,
                "created_at": o.created_at.to_rfc3339(),
                "expiration": o.expiration.to_rfc3339(),
                "order_type": format!("{:?}", o.order_type),
            })
        })
        .collect();
    ok(json!({
        "data": data,
        "next_cursor": result.next_cursor,
        "limit": result.limit,
        "count": result.count,
    }))
}

async fn private_order(State(state): State<AppState>, Path(path): Path<OrderPath>) -> ApiResult {
    let client = auth_client(&state)?;
    let result = client
        .order(&path.order_id)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({
        "id": result.id,
        "status": format!("{:?}", result.status),
        "owner": result.owner.to_string(),
        "maker_address": result.maker_address.to_string(),
        "market": result.market.to_string(),
        "asset_id": result.asset_id.to_string(),
        "side": side_label(result.side),
        "original_size": result.original_size.to_string(),
        "size_matched": result.size_matched.to_string(),
        "price": result.price.to_string(),
        "associate_trades": result.associate_trades,
        "outcome": result.outcome,
        "created_at": result.created_at.to_rfc3339(),
        "expiration": result.expiration.to_rfc3339(),
        "order_type": format!("{:?}", result.order_type),
    }))
}

async fn private_trades(State(state): State<AppState>, Query(q): Query<OrdersQuery>) -> ApiResult {
    let client = auth_client(&state)?;
    let request = TradesRequest::builder()
        .maybe_market(q.market.as_deref().map(parse_condition_id).transpose()?)
        .maybe_asset_id(q.asset.as_deref().map(parse_token_id).transpose()?)
        .build();
    let result = client
        .trades(&request, q.cursor)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    let data: Vec<Value> = result
        .data
        .into_iter()
        .map(|t| {
            json!({
                "id": t.id,
                "taker_order_id": t.taker_order_id,
                "market": t.market.to_string(),
                "asset_id": t.asset_id.to_string(),
                "side": side_label(t.side),
                "size": t.size.to_string(),
                "fee_rate_bps": t.fee_rate_bps.to_string(),
                "price": t.price.to_string(),
                "status": format!("{:?}", t.status),
                "match_time": t.match_time.to_rfc3339(),
                "last_update": t.last_update.to_rfc3339(),
                "outcome": t.outcome,
                "bucket_index": t.bucket_index,
                "owner": t.owner.to_string(),
                "maker_address": t.maker_address.to_string(),
                "transaction_hash": t.transaction_hash.to_string(),
                "trader_side": format!("{:?}", t.trader_side),
                "error_msg": t.error_msg,
            })
        })
        .collect();
    ok(json!({
        "data": data,
        "next_cursor": result.next_cursor,
        "limit": result.limit,
        "count": result.count,
    }))
}

async fn private_balance(
    State(state): State<AppState>,
    Query(q): Query<BalanceQuery>,
) -> ApiResult {
    let client = auth_client(&state)?;
    let request = BalanceAllowanceRequest::builder()
        .asset_type(parse_asset_type(&q.asset_type)?)
        .maybe_token_id(q.token.as_deref().map(parse_token_id).transpose()?)
        .build();
    let result = client
        .balance_allowance(request)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    let mut allowances = serde_json::Map::new();
    for (addr, allowance) in result.allowances {
        allowances.insert(addr.to_string(), json!(allowance));
    }
    ok(json!({
        "balance": result.balance.to_string(),
        "allowances": allowances,
    }))
}

async fn private_update_balance(
    State(state): State<AppState>,
    Query(q): Query<BalanceQuery>,
) -> ApiResult {
    let client = auth_client(&state)?;
    let request = BalanceAllowanceRequest::builder()
        .asset_type(parse_asset_type(&q.asset_type)?)
        .maybe_token_id(q.token.as_deref().map(parse_token_id).transpose()?)
        .build();
    client
        .update_balance_allowance(request)
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({ "updated": true }))
}

async fn private_api_keys(State(state): State<AppState>) -> ApiResult {
    let client = auth_client(&state)?;
    let result = client
        .api_keys()
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({ "raw_debug": format!("{result:?}") }))
}

async fn private_account_status(State(state): State<AppState>) -> ApiResult {
    let client = auth_client(&state)?;
    let result = client
        .closed_only_mode()
        .await
        .map_err(|e| ApiError::internal(e.to_string()))?;
    ok(json!({ "closed_only": result.closed_only }))
}

fn parse_signature_type(raw: &str) -> SignatureType {
    match raw.to_ascii_lowercase().as_str() {
        "proxy" => SignatureType::Proxy,
        "gnosis-safe" | "gnosis_safe" | "safe" => SignatureType::GnosisSafe,
        _ => SignatureType::Eoa,
    }
}

fn parse_optional_addr_env(name: &str) -> Option<Address> {
    std::env::var(name)
        .ok()
        .and_then(|v| Address::from_str(v.trim()).ok())
}

fn signature_type_label(v: SignatureType) -> &'static str {
    match v {
        SignatureType::Eoa => "eoa",
        SignatureType::Proxy => "proxy",
        SignatureType::GnosisSafe => "gnosis-safe",
        _ => "unknown",
    }
}

async fn build_auth_client(
    base: &clob::Client,
) -> anyhow::Result<(clob::Client<Authenticated<Normal>>, StartupInfo)> {
    let private_key =
        std::env::var(PRIVATE_KEY_VAR).with_context(|| format!("{} not set", PRIVATE_KEY_VAR))?;
    let signer = PrivateKeySigner::from_str(&private_key)
        .context("invalid private key")?
        .with_chain_id(Some(POLYGON));

    let signature_type = parse_signature_type(
        &std::env::var("POLY_SIGNATURE_TYPE").unwrap_or_else(|_| "eoa".to_string()),
    );
    let funder = parse_optional_addr_env("POLY_FUNDER");

    let mut builder = base
        .clone()
        .authentication_builder(&signer)
        .signature_type(signature_type);
    if let Some(f) = funder {
        builder = builder.funder(f);
    }

    let client = builder
        .authenticate()
        .await
        .context("L1/L2 authentication failed")?;

    let info = StartupInfo {
        bind: String::new(),
        auth_enabled: true,
        signature_type: Some(signature_type_label(signature_type).to_string()),
        signer_eoa: Some(format!("{}", signer.address())),
        funder: funder.map(|x| format!("{x}")),
    };

    Ok((client, info))
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let bind = std::env::var("POLY_PORT_BIND").unwrap_or_else(|_| "127.0.0.1:8787".to_string());
    let socket_addr: SocketAddr = bind
        .parse()
        .with_context(|| format!("invalid POLY_PORT_BIND: {bind}"))?;

    let public_client = clob::Client::new(
        "https://clob.polymarket.com",
        clob::Config::builder().use_server_time(true).build(),
    )?;

    let (auth_client, mut startup) = match build_auth_client(&public_client).await {
        Ok((client, info)) => (Some(client), info),
        Err(_) => (
            None,
            StartupInfo {
                bind: bind.clone(),
                auth_enabled: false,
                signature_type: None,
                signer_eoa: None,
                funder: None,
            },
        ),
    };
    startup.bind = bind.clone();

    let state = AppState {
        public_client,
        auth_client,
        startup: startup.clone(),
    };

    let app = Router::new()
        .route("/health", get(health))
        .route("/v1/public/ok", get(clob_ok))
        .route("/v1/public/time", get(server_time))
        .route("/v1/public/geoblock", get(geoblock))
        .route("/v1/public/markets", get(markets))
        .route("/v1/public/markets/sampling", get(sampling_markets))
        .route("/v1/public/markets/simplified", get(simplified_markets))
        .route(
            "/v1/public/markets/sampling-simplified",
            get(sampling_simplified_markets),
        )
        .route("/v1/public/market/{condition_id}", get(market_by_condition))
        .route("/v1/public/token/{token_id}/book", get(book))
        .route("/v1/public/tokens/books", get(books))
        .route("/v1/public/token/{token_id}/price", get(price))
        .route("/v1/public/tokens/prices", get(prices))
        .route("/v1/public/token/{token_id}/midpoint", get(midpoint))
        .route("/v1/public/tokens/midpoints", get(midpoints))
        .route("/v1/public/token/{token_id}/spread", get(spread))
        .route("/v1/public/tokens/spreads", get(spreads))
        .route("/v1/public/token/{token_id}/last-trade", get(last_trade))
        .route("/v1/public/tokens/last-trades", get(last_trades))
        .route("/v1/public/token/{token_id}/tick-size", get(tick_size))
        .route("/v1/public/token/{token_id}/fee-rate", get(fee_rate))
        .route("/v1/public/token/{token_id}/neg-risk", get(neg_risk))
        .route(
            "/v1/public/token/{token_id}/price-history",
            get(price_history),
        )
        .route("/v1/private/orders", get(private_orders))
        .route("/v1/private/order/{order_id}", get(private_order))
        .route("/v1/private/trades", get(private_trades))
        .route("/v1/private/balance", get(private_balance))
        .route("/v1/private/update-balance", post(private_update_balance))
        .route("/v1/private/api-keys", get(private_api_keys))
        .route("/v1/private/account-status", get(private_account_status))
        .with_state(state);

    println!("strategy_port listening on http://{bind}");
    println!("auth_enabled: {}", startup.auth_enabled);
    if let Some(sig) = startup.signature_type {
        println!("signature_type: {sig}");
    }
    if let Some(addr) = startup.signer_eoa {
        println!("signer_eoa: {addr}");
    }
    if let Some(funder) = startup.funder {
        println!("funder: {funder}");
    }

    let listener = tokio::net::TcpListener::bind(socket_addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
