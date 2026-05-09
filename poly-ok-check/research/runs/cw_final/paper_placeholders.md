# Paper placeholders

Use the CSV tables in this directory as the source of truth.

## Overall proposed values

- proposed_selected: 37
- available_decision_windows: 54
- proposed_coverage_pct: 68.52
- proposed_hit_rate_pct: 62.16
- proposed_brier: 0.179921
- proposed_p_l: 3.675713
- domain_switches: 2
- exits: 9
- operating_threshold: 0.5

## Table I overall by method

- method=market_only, signals=44, coverage_pct=81.48, hit_rate_pct=70.45, brier=0.195506, p_l=9.310508
- method=data_only, signals=18, coverage_pct=33.33, hit_rate_pct=94.44, brier=0.07902, p_l=9.06091
- method=news_only, signals=24, coverage_pct=44.44, hit_rate_pct=45.83, brier=0.250215, p_l=-2
- method=data_news, signals=42, coverage_pct=77.78, hit_rate_pct=66.67, brier=0.176846, p_l=7.06091
- method=proposed_agent, signals=37, coverage_pct=68.52, hit_rate_pct=62.16, brier=0.179921, p_l=3.675713

## Table II proposed by domain

- domain=cs2, signals=2, coverage_pct=10.53, hit_rate_pct=50.00, brier=0.17245, p_l=0.105263, share_pct=5.41
- domain=btc, signals=24, coverage_pct=100.00, hit_rate_pct=45.83, brier=0.250215, p_l=-2, share_pct=64.86
- domain=weather, signals=11, coverage_pct=100.00, hit_rate_pct=100.00, brier=0.027911, p_l=5.57045, share_pct=29.73

## Table III threshold sensitivity

- threshold=0.25, signals=13, coverage_pct=24.07, hit_rate_pct=92.31, brier=0.050147, p_l=5.675713
- threshold=0.5, signals=11, coverage_pct=20.37, hit_rate_pct=90.91, brier=0.052514, p_l=4.71275
- threshold=0.75, signals=3, coverage_pct=5.56, hit_rate_pct=100.00, brier=0.072864, p_l=2.486497
- threshold=1.0, signals=0, coverage_pct=0.00, hit_rate_pct=, brier=, p_l=0

## Table IV example rows

- cs2_representative: domain=cs2, action=YES, market_prob=0.475, model_prob=0.57, edge=0.095, outcome=WIN
- btc_representative: domain=btc, action=NO, market_prob=0.5, model_prob=0.5025, edge=0.0025, outcome=WIN
- weather_representative: domain=weather, action=NO, market_prob=0.5915, model_prob=0.870209, edge=0.278709, outcome=WIN
- switch_or_exit_case: domain=weather, action=NO, market_prob=0.675, model_prob=0.807305, edge=0.132305, outcome=WIN
