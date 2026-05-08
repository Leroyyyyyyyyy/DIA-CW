# Paper placeholders

Use the CSV tables in this directory as the source of truth.

## Overall proposed values

- proposed_selected: 119
- available_decision_windows: 584
- proposed_coverage_pct: 20.38
- proposed_hit_rate_pct: 38.46
- proposed_brier: 0.329596
- proposed_p_l: -48.759052
- domain_switches: 3
- exits: 9
- operating_threshold: 0.5

## Table I overall by method

- method=market_only, signals=383, coverage_pct=65.58, hit_rate_pct=86.35, brier=0.073393, p_l=-16.13207
- method=data_only, signals=270, coverage_pct=46.23, hit_rate_pct=24.16, brier=0.152059, p_l=-172.705154
- method=news_only, signals=2, coverage_pct=0.34, hit_rate_pct=0.00, brier=0.3364, p_l=-1
- method=data_news, signals=271, coverage_pct=46.40, hit_rate_pct=24.07, brier=0.152742, p_l=-173.705154
- method=proposed_agent, signals=119, coverage_pct=20.38, hit_rate_pct=38.46, brier=0.329596, p_l=-48.759052

## Table II proposed by domain

- domain=cs2, signals=11, coverage_pct=55.00, hit_rate_pct=50.00, brier=0.16036, p_l=-0.784279, share_pct=9.24
- domain=btc, signals=1, coverage_pct=100.00, hit_rate_pct=0.00, brier=0.3364, p_l=-1, share_pct=0.84
- domain=weather, signals=107, coverage_pct=19.01, hit_rate_pct=37.74, brier=0.345498, p_l=-46.974772, share_pct=89.92

## Table III threshold sensitivity

- threshold=0.25, signals=119, coverage_pct=20.38, hit_rate_pct=38.46, brier=0.329596, p_l=-48.759052
- threshold=0.5, signals=10, coverage_pct=1.71, hit_rate_pct=80.00, brier=0.168796, p_l=4.287572
- threshold=0.75, signals=0, coverage_pct=0.00, hit_rate_pct=, brier=, p_l=0
- threshold=1.0, signals=0, coverage_pct=0.00, hit_rate_pct=, brier=, p_l=0

## Table IV example rows

- cs2_representative: domain=cs2, action=NO, market_prob=0.33, model_prob=0.445, edge=0.115, outcome=LOSE
- btc_representative: domain=btc, action=YES, market_prob=0.5, model_prob=0.58, edge=0.08, outcome=LOSE
- weather_representative: domain=weather, action=NO, market_prob=0.465, model_prob=0.821963, edge=0.356963, outcome=LOSE
- switch_or_exit_case: domain=weather, action=NO, market_prob=0.675, model_prob=0.821963, edge=0.146963, outcome=LOSE
