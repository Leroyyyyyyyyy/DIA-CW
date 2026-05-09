# Paper placeholders

Use the CSV tables in this directory as the source of truth.

## Overall proposed values

- proposed_selected: 31
- available_decision_windows: 48
- proposed_coverage_pct: 64.58
- proposed_hit_rate_pct: 45.16
- proposed_brier: 0.23045
- proposed_p_l: -4.009442
- domain_switches: 2
- exits: 9
- operating_threshold: 0.5

## Table I overall by method

- method=market_only, signals=36, coverage_pct=75.00, hit_rate_pct=61.11, brier=0.222341, p_l=3.625353
- method=data_only, signals=12, coverage_pct=25.00, hit_rate_pct=66.67, brier=0.159105, p_l=1.375755
- method=news_only, signals=24, coverage_pct=50.00, hit_rate_pct=45.83, brier=0.250215, p_l=-2
- method=data_news, signals=36, coverage_pct=75.00, hit_rate_pct=52.78, brier=0.219845, p_l=-0.624245
- method=proposed_agent, signals=31, coverage_pct=64.58, hit_rate_pct=45.16, brier=0.23045, p_l=-4.009442

## Table II proposed by domain

- domain=cs2, signals=2, coverage_pct=10.53, hit_rate_pct=50.00, brier=0.17245, p_l=0.105263, share_pct=6.45
- domain=btc, signals=24, coverage_pct=100.00, hit_rate_pct=45.83, brier=0.250215, p_l=-2, share_pct=77.42
- domain=weather, signals=5, coverage_pct=100.00, hit_rate_pct=40.00, brier=0.158782, p_l=-2.114705, share_pct=16.13

## Table III threshold sensitivity

- threshold=0.25, signals=7, coverage_pct=14.58, hit_rate_pct=42.86, brier=0.162687, p_l=-2.009442
- threshold=0.5, signals=7, coverage_pct=14.58, hit_rate_pct=42.86, brier=0.162687, p_l=-2.009442
- threshold=0.75, signals=1, coverage_pct=2.08, hit_rate_pct=100.00, brier=0.1849, p_l=1.105263
- threshold=1.0, signals=0, coverage_pct=0.00, hit_rate_pct=, brier=, p_l=0

## Table IV example rows

- cs2_representative: domain=cs2, action=YES, market_prob=0.475, model_prob=0.57, edge=0.095, outcome=WIN
- btc_representative: domain=btc, action=NO, market_prob=0.5, model_prob=0.5025, edge=0.0025, outcome=WIN
- weather_representative: domain=weather, action=NO, market_prob=0.718, model_prob=0.870209, edge=0.152209, outcome=WIN
- switch_or_exit_case: domain=weather, action=NO, market_prob=0.675, model_prob=0.821963, edge=0.146963, outcome=LOSE
