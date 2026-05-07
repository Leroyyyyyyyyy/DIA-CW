# Paper placeholders

Use the CSV tables in this directory as the source of truth.

## Overall proposed values

- proposed_selected: 117
- available_decision_windows: 582
- proposed_coverage_pct: 20.10
- proposed_hit_rate_pct: 39.32
- proposed_brier: 0.328836
- proposed_p_l: -46.759052
- domain_switches: 2
- exits: 9
- operating_threshold: 0.5

## Table I overall by method

- method=market_only, signals=381, coverage_pct=65.46, hit_rate_pct=86.61, brier=0.073393, p_l=-14.13207
- method=data_only, signals=269, coverage_pct=46.22, hit_rate_pct=24.16, brier=0.152059, p_l=-172.705154
- method=news_only, signals=1, coverage_pct=0.17, hit_rate_pct=100.00, brier=0.247506, p_l=1
- method=data_news, signals=270, coverage_pct=46.39, hit_rate_pct=24.44, brier=0.152413, p_l=-171.705154
- method=proposed_agent, signals=117, coverage_pct=20.10, hit_rate_pct=39.32, brier=0.328836, p_l=-46.759052

## Table II proposed by domain

- domain=cs2, signals=10, coverage_pct=52.63, hit_rate_pct=50.00, brier=0.16036, p_l=-0.784279, share_pct=8.55
- domain=btc, signals=1, coverage_pct=100.00, hit_rate_pct=100.00, brier=0.247506, p_l=1, share_pct=0.85
- domain=weather, signals=106, coverage_pct=18.86, hit_rate_pct=37.74, brier=0.345498, p_l=-46.974772, share_pct=90.60

## Table III threshold sensitivity

- threshold=0.25, signals=116, coverage_pct=19.93, hit_rate_pct=38.79, brier=0.329537, p_l=-47.759052
- threshold=0.5, signals=10, coverage_pct=1.72, hit_rate_pct=80.00, brier=0.168796, p_l=4.287572
- threshold=0.75, signals=0, coverage_pct=0.00, hit_rate_pct=, brier=, p_l=0
- threshold=1.0, signals=0, coverage_pct=0.00, hit_rate_pct=, brier=, p_l=0

## Table IV example rows

- cs2_representative: domain=cs2, action=NO, market_prob=0.33, model_prob=0.445, edge=0.115, outcome=LOSE
- btc_representative: domain=btc, action=NO, market_prob=0.5, model_prob=0.5025, edge=0.0025, outcome=WIN
- weather_representative: domain=weather, action=NO, market_prob=0.465, model_prob=0.821963, edge=0.356963, outcome=LOSE
- switch_or_exit_case: domain=weather, action=NO, market_prob=0.675, model_prob=0.821963, edge=0.146963, outcome=LOSE
