# Paper Evidence Fixes

## What Changed
- Table IV now includes a calibrated `score` column generated from `table4_examples.csv`.
- `score_calibration_diagnostics.csv` records per-domain positive p95 scales for `data_score`, `news_score`, and `edge`.
- `action_trace.csv` records an explicit state trace with `hold`, `enter`, `maintain`, `switch`, and `exit`.
- `action_counts.json` is now the source of truth for switch and exit counts.
- Table I, II, and III include `return_per_signal` so the discussion can separate raw P/L from selectivity.

## Result Interpretation
Do not claim that the proposed agent fully dominates every baseline. The current generated results show:

- `market_only` has the highest raw P/L in Table I.
- `data_only` has the highest hit rate and lowest Brier score in Table I.
- `proposed_agent` remains positive across all three domains and has lower Brier than `market_only`, `news_only`, and `data_news`.
- The method evidence is therefore the calibrated cross-domain selection loop, not universal metric dominance.

Recommended wording:

> Table I should be interpreted as an ablation of information sources and action policies rather than as a claim that the proposed agent wins every aggregate metric. The proposed agent produced positive simulated P/L while using a calibrated cross-domain selector and an explicit action trace. Its Brier score improves on market-only, news-only, and data-plus-news in this snapshot, while the data-only baseline remains strongest on hit rate and Brier. This supports the proposed method as an auditable cross-domain opportunity selector, not as a universally superior trading rule.

## Opportunity Score Wording
Recommended wording:

> To avoid unfair comparison between domains with different raw score ranges, the reported opportunity score is domain-calibrated before the unified formula is applied. For each domain and each component, the evaluation computes the positive 95th-percentile scale from proposed-agent rows. The calibrated component is `min(raw_component / p95_scale, 1)`, with zero-only components mapped to zero. The final score is the sum of calibrated data score, calibrated news score, and calibrated edge, so Table III and Table IV use comparable domain-level opportunity values.

## Action Trace Wording
Recommended wording:

> Switch and exit counts are now derived from `action_trace.csv`, not inferred from acted rows or `FLAT` labels. Each decision timestamp records the calibrated score for CS2, BTC, and Weather when present, the selected domain, the previous active domain, and the resulting action type. The generated `action_counts.json` reports the trace-level counts used in the paper placeholders.

## Table IV Wording
Recommended wording:

> Table IV reports representative selected decisions using the calibrated score. The examples are chosen by calibrated opportunity score within each domain, and the switch case is taken from the explicit action trace. The table should be read as an audit trail from score, to selected action, to realized outcome.

## Current Generated Files
- `research/runs/cw_final/table1_overall.csv`
- `research/runs/cw_final/table2_by_domain.csv`
- `research/runs/cw_final/table3_threshold.csv`
- `research/runs/cw_final/table4_examples.csv`
- `research/runs/cw_final/score_calibration_diagnostics.csv`
- `research/runs/cw_final/action_trace.csv`
- `research/runs/cw_final/action_counts.json`
- `research/runs/cw_final/paper_placeholders.md`
