# Paper placeholders

Use the CSV tables in this directory as the source of truth.

## Overall proposed values

- proposed_selected: 28
- available_decision_windows: 54
- proposed_coverage_pct: 51.85
- proposed_hit_rate_pct: 85.71
- proposed_brier: 0.145031
- proposed_p_l: 13.786171
- proposed_return_per_signal: 0.492363
- domain_switches: 1
- exits: 6
- trace_rows: 54
- operating_threshold: 0.5

## Table I overall by method

- method=market_only, signals=36, coverage_pct=66.67, hit_rate_pct=88.89, brier=0.176807, p_l=18.420966, return_per_signal=0.511693
- method=data_only, signals=21, coverage_pct=38.89, hit_rate_pct=100.00, brier=0.087678, p_l=13.171367, return_per_signal=0.627208
- method=news_only, signals=12, coverage_pct=22.22, hit_rate_pct=66.67, brier=0.249173, p_l=4, return_per_signal=0.333333
- method=data_news, signals=33, coverage_pct=61.11, hit_rate_pct=87.88, brier=0.146404, p_l=17.171367, return_per_signal=0.520344
- method=proposed_agent, signals=28, coverage_pct=51.85, hit_rate_pct=85.71, brier=0.145031, p_l=13.786171, return_per_signal=0.492363

## Table II proposed by domain

- domain=cs2, signals=5, coverage_pct=26.32, hit_rate_pct=100.00, brier=0.152755, p_l=4.215721, return_per_signal=0.843144, share_pct=17.86
- domain=btc, signals=12, coverage_pct=50.00, hit_rate_pct=66.67, brier=0.249173, p_l=4, return_per_signal=0.333333, share_pct=42.86
- domain=weather, signals=11, coverage_pct=100.00, hit_rate_pct=100.00, brier=0.027911, p_l=5.57045, return_per_signal=0.506405, share_pct=39.29

## Table III threshold sensitivity

- threshold=0.5, signals=28, coverage_pct=51.85, hit_rate_pct=85.71, brier=0.145031, p_l=13.786171, return_per_signal=0.492363
- threshold=1.0, signals=28, coverage_pct=51.85, hit_rate_pct=85.71, brier=0.145031, p_l=13.786171, return_per_signal=0.492363
- threshold=1.5, signals=28, coverage_pct=51.85, hit_rate_pct=85.71, brier=0.145031, p_l=13.786171, return_per_signal=0.492363
- threshold=2.0, signals=22, coverage_pct=40.74, hit_rate_pct=81.82, brier=0.174458, p_l=10.853059, return_per_signal=0.493321
- threshold=2.5, signals=3, coverage_pct=5.56, hit_rate_pct=100.00, brier=0.072864, p_l=2.486497, return_per_signal=0.828832

## Table IV example rows

- cs2_representative: domain=cs2, action=YES, market_prob=0.475, model_prob=0.57, edge=0.095, score=2.664322, outcome=WIN
- btc_representative: domain=btc, action=NO, market_prob=0.5, model_prob=0.5025, edge=0.0025, score=2, outcome=WIN
- weather_representative: domain=weather, action=NO, market_prob=0.5915, model_prob=0.870209, edge=0.278709, score=3, outcome=WIN
- switch_or_exit_case: domain=btc, action=NO, market_prob=0.5, model_prob=0.5025, edge=0.0025, score=2, outcome=WIN
