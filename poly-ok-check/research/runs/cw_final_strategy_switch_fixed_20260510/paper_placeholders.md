# Paper placeholders

Use the CSV tables in this directory as the source of truth.

## Overall proposed values

- proposed_selected: 20
- available_decision_windows: 54
- proposed_coverage_pct: 37.04
- proposed_hit_rate_pct: 95.00
- proposed_brier: 0.103291
- proposed_p_l: 11.786171
- proposed_return_per_signal: 0.589309
- domain_switches: 2
- exits: 0
- trace_rows: 54
- operating_threshold: 0.5

## Table I overall by method

- method=market_only, signals=404, coverage_pct=66.78, hit_rate_pct=84.16, brier=0.083447, p_l=-17.13207, return_per_signal=-0.042406
- method=data_only, signals=436, coverage_pct=72.07, hit_rate_pct=18.58, brier=0.096215, p_l=-320.29884, return_per_signal=-0.73463
- method=news_only, signals=24, coverage_pct=3.97, hit_rate_pct=45.83, brier=0.250215, p_l=-2, return_per_signal=-0.083333
- method=data_news, signals=293, coverage_pct=48.43, hit_rate_pct=25.94, brier=0.160099, p_l=-174.705154, return_per_signal=-0.596263
- method=proposed_agent, signals=20, coverage_pct=37.04, hit_rate_pct=95.00, brier=0.103291, p_l=11.786171, return_per_signal=0.589309

## Table II proposed by domain

- domain=cs2, signals=5, coverage_pct=26.32, hit_rate_pct=100.00, brier=0.152755, p_l=4.215721, return_per_signal=0.843144, share_pct=25.00
- domain=btc, signals=4, coverage_pct=16.67, hit_rate_pct=75.00, brier=0.248756, p_l=2, return_per_signal=0.5, share_pct=20.00
- domain=weather, signals=11, coverage_pct=100.00, hit_rate_pct=100.00, brier=0.027911, p_l=5.57045, return_per_signal=0.506405, share_pct=55.00

## Table III threshold sensitivity

- threshold=0.5, signals=20, coverage_pct=37.04, hit_rate_pct=95.00, brier=0.103291, p_l=11.786171, return_per_signal=0.589309
- threshold=1.0, signals=20, coverage_pct=37.04, hit_rate_pct=95.00, brier=0.103291, p_l=11.786171, return_per_signal=0.589309
- threshold=1.5, signals=20, coverage_pct=37.04, hit_rate_pct=95.00, brier=0.103291, p_l=11.786171, return_per_signal=0.589309
- threshold=2.0, signals=14, coverage_pct=25.93, hit_rate_pct=92.86, brier=0.131645, p_l=8.853059, return_per_signal=0.632361
- threshold=2.5, signals=3, coverage_pct=5.56, hit_rate_pct=100.00, brier=0.072864, p_l=2.486497, return_per_signal=0.828832

## Table IV example rows

- cs2_representative: domain=cs2, action=YES, market_prob=0.475, model_prob=0.57, edge=0.095, score=2.664322, outcome=WIN
- btc_representative: domain=btc, action=NO, market_prob=0.5, model_prob=0.5025, edge=0.0025, score=2, outcome=WIN
- weather_representative: domain=weather, action=NO, market_prob=0.5915, model_prob=0.870209, edge=0.278709, score=3, outcome=WIN
- switch_or_exit_case: domain=weather, action=NO, market_prob=0.675, model_prob=0.807305, edge=0.132305, score=1.949413, outcome=WIN
