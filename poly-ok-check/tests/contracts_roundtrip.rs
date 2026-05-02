use std::fs;
use std::path::PathBuf;

use poly_ok_check::contracts::{HubSlice, MarketSnapshot, OpportunityCandidate};

fn fixture_path(file: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join(file)
}

#[test]
fn market_snapshot_roundtrip() {
    let raw = fs::read_to_string(fixture_path("snapshot.json")).expect("read snapshot fixture");
    let parsed: MarketSnapshot = serde_json::from_str(&raw).expect("parse snapshot fixture");
    let encoded = serde_json::to_string(&parsed).expect("encode snapshot");
    let reparsed: MarketSnapshot = serde_json::from_str(&encoded).expect("reparse snapshot");
    assert_eq!(parsed.market_id, reparsed.market_id);
    assert_eq!(parsed.quality_flags, reparsed.quality_flags);
}

#[test]
fn opportunity_roundtrip() {
    let raw =
        fs::read_to_string(fixture_path("opportunity.json")).expect("read opportunity fixture");
    let parsed: OpportunityCandidate =
        serde_json::from_str(&raw).expect("parse opportunity fixture");
    let encoded = serde_json::to_string(&parsed).expect("encode opportunity");
    let reparsed: OpportunityCandidate =
        serde_json::from_str(&encoded).expect("reparse opportunity");
    assert_eq!(parsed.agent_id, reparsed.agent_id);
    assert_eq!(parsed.direction, reparsed.direction);
}

#[test]
fn hub_slice_roundtrip() {
    let raw = fs::read_to_string(fixture_path("slice.json")).expect("read slice fixture");
    let parsed: HubSlice = serde_json::from_str(&raw).expect("parse slice fixture");
    let encoded = serde_json::to_string(&parsed).expect("encode slice");
    let reparsed: HubSlice = serde_json::from_str(&encoded).expect("reparse slice");
    assert_eq!(parsed.hub_ts, reparsed.hub_ts);
    assert_eq!(
        parsed.slice_meta.market_count,
        reparsed.slice_meta.market_count
    );
}
