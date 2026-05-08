# Paper placeholders

Use the CSV tables in this directory as the source of truth.

## Overall proposed values

- proposed_selected: 116
- available_decision_windows: 584
- proposed_coverage_pct: 19.86
- proposed_hit_rate_pct: 38.79
- proposed_brier: 0.329537
- proposed_p_l: -47.759052
- domain_switches: 1
- exits: 9
- operating_threshold: 0.5

## Table I overall by method

- method=market_only, signals=383, coverage_pct=65.58, hit_rate_pct=86.35, brier=0.073393, p_l=-16.13207
- method=data_only, signals=270, coverage_pct=46.23, hit_rate_pct=24.16, brier=0.152059, p_l=-172.705154
- method=news_only, signals=1, coverage_pct=0.17, hit_rate_pct=, brier=, p_l=0
- method=data_news, signals=270, coverage_pct=46.23, hit_rate_pct=24.16, brier=0.152059, p_l=-172.705154
- method=proposed_agent, signals=116, coverage_pct=19.86, hit_rate_pct=38.79, brier=0.329537, p_l=-47.759052

## Table II proposed by domain

- domain=cs2, signals=10, coverage_pct=50.00, hit_rate_pct=50.00, brier=0.16036, p_l=-0.784279, share_pct=8.62
- domain=btc, signals=0, coverage_pct=0.00, hit_rate_pct=, brier=, p_l=0, share_pct=0.00
- domain=weather, signals=106, coverage_pct=18.83, hit_rate_pct=37.74, brier=0.345498, p_l=-46.974772, share_pct=91.38

## Table III threshold sensitivity

- threshold=0.25, signals=116, coverage_pct=19.86, hit_rate_pct=38.79, brier=0.329537, p_l=-47.759052
- threshold=0.5, signals=10, coverage_pct=1.71, hit_rate_pct=80.00, brier=0.168796, p_l=4.287572
- threshold=0.75, signals=0, coverage_pct=0.00, hit_rate_pct=, brier=, p_l=0
- threshold=1.0, signals=0, coverage_pct=0.00, hit_rate_pct=, brier=, p_l=0

## Table IV example rows

- cs2_representative: domain=cs2, action=NO, market_prob=0.33, model_prob=0.445, edge=0.115, outcome=LOSE
- weather_representative: domain=weather, action=NO, market_prob=0.465, model_prob=0.821963, edge=0.356963, outcome=LOSE
- switch_or_exit_case: domain=weather, action=NO, market_prob=0.675, model_prob=0.821963, edge=0.146963, outcome=LOSE
