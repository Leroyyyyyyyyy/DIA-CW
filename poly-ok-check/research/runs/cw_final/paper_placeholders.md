# Paper placeholders

Use the CSV tables in this directory as the source of truth.

## Overall proposed values

- proposed_selected: 41
- available_decision_windows: 58
- proposed_coverage_pct: 70.69
- proposed_hit_rate_pct: 46.34
- proposed_brier: 0.228049
- proposed_p_l: -6.470404
- domain_switches: 2
- exits: 9
- operating_threshold: 0.5

## Table I overall by method

- method=market_only, signals=43, coverage_pct=74.14, hit_rate_pct=62.79, brier=0.216488, p_l=4.164391
- method=data_only, signals=22, coverage_pct=37.93, hit_rate_pct=59.09, brier=0.187059, p_l=-1.085208
- method=news_only, signals=24, coverage_pct=41.38, hit_rate_pct=45.83, brier=0.250215, p_l=-2
- method=data_news, signals=46, coverage_pct=79.31, hit_rate_pct=52.17, brier=0.22001, p_l=-3.085208
- method=proposed_agent, signals=41, coverage_pct=70.69, hit_rate_pct=46.34, brier=0.228049, p_l=-6.470404

## Table II proposed by domain

- domain=cs2, signals=2, coverage_pct=10.53, hit_rate_pct=50.00, brier=0.17245, p_l=0.105263, share_pct=4.88
- domain=btc, signals=24, coverage_pct=100.00, hit_rate_pct=45.83, brier=0.250215, p_l=-2, share_pct=58.54
- domain=weather, signals=15, coverage_pct=100.00, hit_rate_pct=46.67, brier=0.199996, p_l=-4.575667, share_pct=36.59

## Table III threshold sensitivity

- threshold=0.25, signals=17, coverage_pct=29.31, hit_rate_pct=47.06, brier=0.196755, p_l=-4.470404
- threshold=0.5, signals=17, coverage_pct=29.31, hit_rate_pct=47.06, brier=0.196755, p_l=-4.470404
- threshold=0.75, signals=3, coverage_pct=5.17, hit_rate_pct=66.67, brier=0.292457, p_l=0.79588
- threshold=1.0, signals=0, coverage_pct=0.00, hit_rate_pct=, brier=, p_l=0

## Table IV example rows

- cs2_representative: domain=cs2, action=YES, market_prob=0.475, model_prob=0.57, edge=0.095, outcome=WIN
- btc_representative: domain=btc, action=NO, market_prob=0.5, model_prob=0.5025, edge=0.0025, outcome=WIN
- weather_representative: domain=weather, action=NO, market_prob=0.465, model_prob=0.821963, edge=0.356963, outcome=LOSE
- switch_or_exit_case: domain=weather, action=NO, market_prob=0.675, model_prob=0.821963, edge=0.146963, outcome=LOSE
