# Paper placeholders

Use the CSV tables in this directory as the source of truth.

## Overall proposed values

- proposed_selected: 29
- available_decision_windows: 46
- proposed_coverage_pct: 63.04
- proposed_hit_rate_pct: 44.83
- proposed_brier: 0.243783
- proposed_p_l: -3.501979
- domain_switches: 2
- exits: 9
- operating_threshold: 0.5

## Table I overall by method

- method=market_only, signals=35, coverage_pct=76.09, hit_rate_pct=60.00, brier=0.225582, p_l=3.132816
- method=data_only, signals=10, coverage_pct=21.74, hit_rate_pct=70.00, brier=0.1835, p_l=1.883217
- method=news_only, signals=24, coverage_pct=52.17, hit_rate_pct=45.83, brier=0.250215, p_l=-2
- method=data_news, signals=34, coverage_pct=73.91, hit_rate_pct=52.94, brier=0.230593, p_l=-0.116783
- method=proposed_agent, signals=29, coverage_pct=63.04, hit_rate_pct=44.83, brier=0.243783, p_l=-3.501979

## Table II proposed by domain

- domain=cs2, signals=2, coverage_pct=10.53, hit_rate_pct=50.00, brier=0.17245, p_l=0.105263, share_pct=6.90
- domain=btc, signals=24, coverage_pct=100.00, hit_rate_pct=45.83, brier=0.250215, p_l=-2, share_pct=82.76
- domain=weather, signals=3, coverage_pct=100.00, hit_rate_pct=33.33, brier=0.239883, p_l=-1.607242, share_pct=10.34

## Table III threshold sensitivity

- threshold=0.25, signals=5, coverage_pct=10.87, hit_rate_pct=40.00, brier=0.21291, p_l=-1.501979
- threshold=0.5, signals=5, coverage_pct=10.87, hit_rate_pct=40.00, brier=0.21291, p_l=-1.501979
- threshold=0.75, signals=1, coverage_pct=2.17, hit_rate_pct=100.00, brier=0.1849, p_l=1.105263
- threshold=1.0, signals=0, coverage_pct=0.00, hit_rate_pct=, brier=, p_l=0

## Table IV example rows

- cs2_representative: domain=cs2, action=YES, market_prob=0.475, model_prob=0.57, edge=0.095, outcome=WIN
- btc_representative: domain=btc, action=NO, market_prob=0.5, model_prob=0.5025, edge=0.0025, outcome=WIN
- weather_representative: domain=weather, action=NO, market_prob=0.718, model_prob=0.870209, edge=0.152209, outcome=WIN
- switch_or_exit_case: domain=weather, action=NO, market_prob=0.675, model_prob=0.821963, edge=0.146963, outcome=LOSE
