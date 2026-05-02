use std::str::FromStr;

use alloy::signers::Signer as _;
use alloy::signers::local::PrivateKeySigner;
use anyhow::{Context, anyhow, bail};
use polymarket_client_sdk::auth::Normal;
use polymarket_client_sdk::auth::state::Authenticated;
use polymarket_client_sdk::clob::types::{OrderType, Side, SignatureType};
use polymarket_client_sdk::clob::{Client, Config};
use polymarket_client_sdk::types::{Address, Decimal, U256};
use polymarket_client_sdk::{POLYGON, PRIVATE_KEY_VAR, derive_proxy_wallet, derive_safe_wallet};
use tokio::time::{Duration, sleep};

// Hardcoded defaults so the command can run without setting env vars each time.
// Replace DEFAULT_PRIVATE_KEY with your real key if you want fully no-env execution.
const DEFAULT_PRIVATE_KEY: &str = "0xYOUR_PRIVATE_KEY";
const DEFAULT_TOKEN_ID: &str =
    "51939490109676186832507970701169130490548061087912630009168726706475001411420";
const DEFAULT_SIDE: &str = "BUY";
const DEFAULT_SIZE: &str = "1";
const DEFAULT_START_PRICE: &str = "0.45";
const DEFAULT_REPLACE_PRICE: &str = "0.44";
const DEFAULT_DRY_RUN: bool = true;
const DEFAULT_CANCEL_AFTER_SECS: u64 = 3;
const DEFAULT_CANCEL_REPLACEMENT: bool = true;
const DEFAULT_SIGNATURE_TYPE: SignatureType = SignatureType::Eoa;

#[derive(Debug, Clone)]
struct Settings {
    token_id: U256,
    side: Side,
    size: Decimal,
    start_price: Decimal,
    replace_price: Decimal,
    dry_run: bool,
    cancel_after_secs: u64,
    cancel_replacement: bool,
    signature_type: SignatureType,
    funder: Option<Address>,
}

fn parse_bool(name: &str, default: bool) -> anyhow::Result<bool> {
    let raw = match std::env::var(name) {
        Ok(v) => v,
        Err(_) => return Ok(default),
    };
    match raw.to_ascii_lowercase().as_str() {
        "1" | "true" | "yes" | "y" | "on" => Ok(true),
        "0" | "false" | "no" | "n" | "off" => Ok(false),
        _ => Err(anyhow!(
            "{name} must be one of true/false/1/0/yes/no, got: {raw}"
        )),
    }
}

fn parse_side() -> anyhow::Result<Side> {
    let raw = std::env::var("POLY_SIDE").unwrap_or_else(|_| DEFAULT_SIDE.to_string());
    match raw.to_ascii_uppercase().as_str() {
        "BUY" => Ok(Side::Buy),
        "SELL" => Ok(Side::Sell),
        _ => Err(anyhow!("POLY_SIDE must be BUY or SELL, got: {raw}")),
    }
}

fn parse_decimal_env(name: &str, default: &str) -> anyhow::Result<Decimal> {
    let raw = std::env::var(name).unwrap_or_else(|_| default.to_string());
    Decimal::from_str(&raw).with_context(|| format!("{name} parse failed: {raw}"))
}

fn parse_signature_type() -> anyhow::Result<SignatureType> {
    let raw = std::env::var("POLY_SIGNATURE_TYPE").unwrap_or_else(|_| "eoa".to_string());
    match raw.to_ascii_lowercase().as_str() {
        "eoa" => Ok(SignatureType::Eoa),
        "proxy" => Ok(SignatureType::Proxy),
        "gnosis-safe" | "gnosis_safe" | "safe" => Ok(SignatureType::GnosisSafe),
        _ => Err(anyhow!(
            "POLY_SIGNATURE_TYPE must be one of eoa/proxy/gnosis-safe, got: {raw}"
        )),
    }
}

fn parse_optional_funder() -> anyhow::Result<Option<Address>> {
    match std::env::var("POLY_FUNDER") {
        Ok(v) if !v.trim().is_empty() => {
            let addr = Address::from_str(v.trim())
                .with_context(|| format!("POLY_FUNDER must be a valid 0x address, got: {v}"))?;
            Ok(Some(addr))
        }
        _ => Ok(None),
    }
}

fn signature_type_label(v: SignatureType) -> &'static str {
    match v {
        SignatureType::Eoa => "eoa",
        SignatureType::Proxy => "proxy",
        SignatureType::GnosisSafe => "gnosis-safe",
        _ => "unknown",
    }
}

fn load_settings() -> anyhow::Result<Settings> {
    let token_id_raw =
        std::env::var("POLY_TOKEN_ID").unwrap_or_else(|_| DEFAULT_TOKEN_ID.to_string());
    let token_id =
        U256::from_str(&token_id_raw).context("POLY_TOKEN_ID must be a valid U256 string")?;
    let side = parse_side()?;
    let size = parse_decimal_env("POLY_SIZE", DEFAULT_SIZE)?;
    let start_price = parse_decimal_env("POLY_START_PRICE", DEFAULT_START_PRICE)?;
    let replace_price = parse_decimal_env("POLY_REPLACE_PRICE", DEFAULT_REPLACE_PRICE)?;
    let dry_run = parse_bool("POLY_DRY_RUN", DEFAULT_DRY_RUN)?;
    let cancel_after_secs = std::env::var("POLY_CANCEL_AFTER_SECS")
        .ok()
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(DEFAULT_CANCEL_AFTER_SECS);
    let cancel_replacement = parse_bool("POLY_CANCEL_REPLACEMENT", DEFAULT_CANCEL_REPLACEMENT)?;
    let signature_type = parse_signature_type().unwrap_or(DEFAULT_SIGNATURE_TYPE);
    let funder = parse_optional_funder()?;

    if size <= Decimal::ZERO {
        bail!("POLY_SIZE must be positive");
    }
    if start_price <= Decimal::ZERO || start_price >= Decimal::ONE {
        bail!("POLY_START_PRICE must be between 0 and 1");
    }
    if replace_price <= Decimal::ZERO || replace_price >= Decimal::ONE {
        bail!("POLY_REPLACE_PRICE must be between 0 and 1");
    }

    Ok(Settings {
        token_id,
        side,
        size,
        start_price,
        replace_price,
        dry_run,
        cancel_after_secs,
        cancel_replacement,
        signature_type,
        funder,
    })
}

async fn build_and_sign_limit(
    client: &Client<Authenticated<Normal>>,
    signer: &PrivateKeySigner,
    settings: &Settings,
    price: Decimal,
) -> anyhow::Result<polymarket_client_sdk::clob::types::SignedOrder> {
    let signable = client
        .limit_order()
        .token_id(settings.token_id)
        .side(settings.side)
        .order_type(OrderType::GTC)
        .post_only(true)
        .price(price)
        .size(settings.size)
        .build()
        .await
        .with_context(|| format!("build limit order failed at price={price}"))?;

    client
        .sign(signer, signable)
        .await
        .with_context(|| format!("sign order failed at price={price}"))
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let settings = load_settings()?;
    let private_key =
        std::env::var(PRIVATE_KEY_VAR).unwrap_or_else(|_| DEFAULT_PRIVATE_KEY.to_string());
    if private_key.trim().is_empty() || private_key == DEFAULT_PRIVATE_KEY {
        bail!(
            "Private key not set. Either set {PRIVATE_KEY_VAR} env var or edit DEFAULT_PRIVATE_KEY in exec_loop.rs"
        );
    }

    println!(
        "mode: {}",
        if settings.dry_run { "dry-run" } else { "real" }
    );
    println!("token_id: {}", settings.token_id);
    println!("side: {}", settings.side);
    println!("size: {}", settings.size);
    println!("start_price: {}", settings.start_price);
    println!("replace_price: {}", settings.replace_price);
    println!(
        "signature_type: {}",
        signature_type_label(settings.signature_type)
    );
    if let Some(funder) = settings.funder {
        println!("funder(override): {funder}");
    }

    if !settings.dry_run {
        let confirm = std::env::var("POLY_REAL_CONFIRM").unwrap_or_default();
        if confirm != "YES" {
            bail!("Real mode requires POLY_REAL_CONFIRM=YES");
        }
    }

    let base = Client::new(
        "https://clob.polymarket.com",
        Config::builder().use_server_time(true).build(),
    )?;
    let _ = base.ok().await?;
    let geoblock = base.check_geoblock().await?;
    println!(
        "geoblock: blocked={} country={} region={} ip={}",
        geoblock.blocked, geoblock.country, geoblock.region, geoblock.ip
    );
    if geoblock.blocked {
        bail!("IP is geoblocked; cannot continue");
    }

    let signer = PrivateKeySigner::from_str(&private_key)?.with_chain_id(Some(POLYGON));
    let eoa = signer.address();
    let derived_proxy = derive_proxy_wallet(eoa, POLYGON);
    let derived_safe = derive_safe_wallet(eoa, POLYGON);
    println!("signer_eoa: {eoa}");
    if let Some(v) = derived_proxy {
        println!("derived_proxy: {v}");
    }
    if let Some(v) = derived_safe {
        println!("derived_safe: {v}");
    }

    let mut auth_builder = base
        .authentication_builder(&signer)
        .signature_type(settings.signature_type);
    if let Some(funder) = settings.funder {
        auth_builder = auth_builder.funder(funder);
    }
    let client = auth_builder
        .authenticate()
        .await
        .context("L1/L2 authentication failed")?;

    let keys = client.api_keys().await?;
    let closed_only = client.closed_only_mode().await?;
    println!(
        "auth: api_keys={keys:?} closed_only_mode={}",
        closed_only.closed_only
    );

    let first_signed =
        build_and_sign_limit(&client, &signer, &settings, settings.start_price).await?;
    let first_payload = serde_json::to_string_pretty(&first_signed)?;
    println!("signed_order_preview(start): {first_payload}");

    if settings.dry_run {
        let replace_signed =
            build_and_sign_limit(&client, &signer, &settings, settings.replace_price).await?;
        let replace_payload = serde_json::to_string_pretty(&replace_signed)?;
        println!("dry-run: would POST start order, then cancel it, then post replacement");
        println!("signed_order_preview(replace): {replace_payload}");
        return Ok(());
    }

    let post = client.post_order(first_signed).await?;
    println!(
        "post(start): success={} status={} order_id={} error_msg={}",
        post.success,
        post.status,
        post.order_id,
        post.error_msg.unwrap_or_default()
    );
    if !post.success {
        bail!("start order post failed");
    }

    sleep(Duration::from_secs(settings.cancel_after_secs)).await;
    let canceled = client.cancel_order(&post.order_id).await?;
    println!(
        "cancel(start): canceled_count={} not_canceled_count={}",
        canceled.canceled.len(),
        canceled.not_canceled.len()
    );

    let replace_signed =
        build_and_sign_limit(&client, &signer, &settings, settings.replace_price).await?;
    let replace_post = client.post_order(replace_signed).await?;
    println!(
        "post(replace): success={} status={} order_id={} error_msg={}",
        replace_post.success,
        replace_post.status,
        replace_post.order_id,
        replace_post.error_msg.unwrap_or_default()
    );
    if !replace_post.success {
        bail!("replacement order post failed");
    }

    if settings.cancel_replacement {
        let cleanup = client.cancel_order(&replace_post.order_id).await?;
        println!(
            "cancel(replace): canceled_count={} not_canceled_count={}",
            cleanup.canceled.len(),
            cleanup.not_canceled.len()
        );
    }

    Ok(())
}
