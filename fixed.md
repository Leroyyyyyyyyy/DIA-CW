# Fix Progress Log

## Context
- Target workspace: `D:\Polyquant\github_upload`
- Current head: `922fb70 Connect PMXT execution artifacts`
- Goal: fix evaluation evidence for selection-quality claims, not a claim that the proposed agent fully dominates every baseline.
- PDF policy: do not directly edit `main.pdf` until a paper source file is available.

## Checklist
- [x] Inspect target workspace and baseline outputs.
- [x] Implement domain-calibrated opportunity score.
- [x] Add Table IV `score`.
- [x] Export `action_trace.csv` and `action_counts.json`.
- [x] Update tests.
- [x] Regenerate coursework outputs.
- [x] Update paper-facing README/docs.
- [x] Run verification.

## Preserve-Data Rerun Checklist
- [x] Create branch for PMXT-preserving rerun.
- [x] Restore original `cw_final` generated files so baseline data is not overwritten.
- [x] Rerun experiment into a new output directory.
- [x] Re-run tests after the preserved-data rerun.
- [x] Stage only code/docs plus the new run directory.
- [x] Commit current work to local branch `fixed`.
- [ ] Push local branch `fixed` to remote without touching `main`.

## Progress

### 2026-05-10 - Baseline inspection
- Confirmed target repo is clean at `D:\Polyquant\github_upload`.
- Existing generated outputs are under `poly-ok-check\research\runs\cw_final`.
- Existing Table IV lacks `score`.
- Existing `domain_switches` and `exits` are derived from acted rows / `FLAT`, not an explicit state trace.
- Existing Table I shows proposed agent is not a raw-metric winner across all baselines, so wording must focus on selection quality.

### 2026-05-10 - Generator implementation
- Updated `poly-ok-check\research\evaluation\cw_tables.py`.
- Added domain-calibrated opportunity scoring using per-domain positive p95 scales for `data_score`, `news_score`, and `edge`.
- Added generated outputs: `score_calibration_diagnostics.csv`, `action_trace.csv`, and `action_counts.json`.
- Added `score` to Table IV and placeholders.
- Added `return_per_signal` to generated metric tables and placeholders.
- Changed `domain_switches` and `exits` placeholders to use explicit action trace counts.
- `python -m compileall research\evaluation\cw_tables.py` passed.

### 2026-05-10 - Targeted tests
- Updated `poly-ok-check\research\tests\test_cw_tables.py`.
- Added checks for Table IV `score`, `return_per_signal`, trace output columns, action counts, placeholder switch/exit values, and zero-only calibration components.
- Fixed the trace test fixture so the exit row has all-zero calibrated score.
- `python -m pytest research\tests\test_cw_tables.py -q` passed: 6 tests.

### 2026-05-10 - Regenerated outputs and docs
- Updated `poly-ok-check\research\config\cw_experiment.yaml` threshold grid to `[0.5, 1.0, 1.5, 2.0, 2.5]` for calibrated scores in `[0, 3]`.
- Regenerated `poly-ok-check\research\runs\cw_final`.
- New generated outputs:
  - `action_trace.csv`
  - `action_counts.json`
  - `score_calibration_diagnostics.csv`
  - `pmxt_execution_diagnostics.csv`
- Current action counts: `hold=20`, `enter=6`, `maintain=21`, `switch=1`, `exit=6`, `rows=54`.
- Current Table IV has columns: `case, domain, market_id, market_prob, model_prob, edge, score, action, outcome`.
- Added paper-facing replacement wording in `poly-ok-check\docs\paper_evidence_fixes.md`.
- Added a top-level README note pointing to the corrected evidence files.

### 2026-05-10 - Verification
- Full Python research test suite passed: `69 passed`.
- Final regeneration command passed with `loaded_reports=270`.
- Final trace counts: `hold=20`, `enter=6`, `maintain=21`, `switch=1`, `exit=6`, `rows=54`.
- Final Table IV columns include `score`.
- Added case-insensitive domain matching in the table generator and re-ran the full test/regeneration sequence successfully.
- `main.pdf` was not edited directly because no paper source file is present.

### 2026-05-10 - Preserve-data PMXT rerun branch
- Created branch `codex/pmxt-rerun-preserve-data`.
- User requested a fresh rerun without overwriting original data.
- Plan: restore tracked `cw_final` outputs to repository state, remove only the untracked generated files from `cw_final`, then write the new rerun to `poly-ok-check\research\runs\cw_final_pmxt_rerun_20260510`.
- Restored `poly-ok-check\research\runs\cw_final` generated outputs to the repository state; `git status` no longer shows `cw_final` changes.
- Reran the experiment into `poly-ok-check\research\runs\cw_final_pmxt_rerun_20260510` with `loaded_reports=270`.
- New rerun outputs include `table1_overall.csv`, `table2_by_domain.csv`, `table3_threshold.csv`, `table4_examples.csv`, `paper_placeholders.md`, `score_calibration_diagnostics.csv`, `action_trace.csv`, and `action_counts.json`.
- New rerun action counts: `hold=20`, `enter=6`, `maintain=21`, `switch=1`, `exit=6`, `rows=54`.
- New rerun Table IV includes `score`.
- PMXT code path is enabled and called, but no PMXT execution artifacts were found at `vendor\prediction-market-backtesting\output\pmxt_fills.csv`, `pmxt_executions.jsonl`, or `pmxt_trades.json`; diagnostics therefore recorded `pmxt_optional_noop`.
- Full Python research test suite passed again after the preserved-data rerun: `69 passed`.
- Staged code/docs plus the new run directory only; `cw_final` remains unchanged in `git status`.

### 2026-05-10 - Push request
- User requested pushing the current work to a new remote branch named `fixed`, not to `main`.
- Confirmed `origin` points to `https://github.com/Leroyyyyyyyyy/DIA-CW.git`.
- Confirmed no remote branch named `fixed` currently exists.
- Created local branch `fixed`.
- Created local commit `d503658` with message `Fix evaluation evidence outputs`.

## Commands Run
- `git status --short --branch`
- `git log -1 --oneline --decorate`
- `python -m compileall research\evaluation\cw_tables.py`
- `python -m pytest research\tests\test_cw_tables.py -q`
- `python -m pytest research\tests -q`
- `python -m research.run.run_cw_experiment --config research/config/cw_experiment.yaml --out-dir research/runs/cw_final`
- `git switch -c codex/pmxt-rerun-preserve-data`
- `git restore --staged --worktree -- poly-ok-check/research/runs/cw_final/...`
- `python -m research.run.run_cw_experiment --config research/config/cw_experiment.yaml --out-dir research/runs/cw_final_pmxt_rerun_20260510`
- `python -m pytest research\tests -q`
- `git add -- README.md fixed.md poly-ok-check/docs/paper_evidence_fixes.md poly-ok-check/research/config/cw_experiment.yaml poly-ok-check/research/evaluation/cw_tables.py poly-ok-check/research/tests/test_cw_tables.py poly-ok-check/research/runs/cw_final_pmxt_rerun_20260510`
- `git remote -v`
- `git ls-remote --heads origin fixed`
- `git switch -c fixed`
- `git commit -m "Fix evaluation evidence outputs"`

## Generated Outputs
- `poly-ok-check\research\runs\cw_final\table1_overall.csv`
- `poly-ok-check\research\runs\cw_final\table2_by_domain.csv`
- `poly-ok-check\research\runs\cw_final\table3_threshold.csv`
- `poly-ok-check\research\runs\cw_final\table4_examples.csv`
- `poly-ok-check\research\runs\cw_final\score_calibration_diagnostics.csv`
- `poly-ok-check\research\runs\cw_final\action_trace.csv`
- `poly-ok-check\research\runs\cw_final\action_counts.json`
- `poly-ok-check\research\runs\cw_final\paper_placeholders.md`
- `poly-ok-check\research\runs\cw_final_pmxt_rerun_20260510\table1_overall.csv`
- `poly-ok-check\research\runs\cw_final_pmxt_rerun_20260510\table2_by_domain.csv`
- `poly-ok-check\research\runs\cw_final_pmxt_rerun_20260510\table3_threshold.csv`
- `poly-ok-check\research\runs\cw_final_pmxt_rerun_20260510\table4_examples.csv`
- `poly-ok-check\research\runs\cw_final_pmxt_rerun_20260510\score_calibration_diagnostics.csv`
- `poly-ok-check\research\runs\cw_final_pmxt_rerun_20260510\action_trace.csv`
- `poly-ok-check\research\runs\cw_final_pmxt_rerun_20260510\action_counts.json`
- `poly-ok-check\research\runs\cw_final_pmxt_rerun_20260510\paper_placeholders.md`

## Test Results
- Targeted table tests: `6 passed`.
- Full research tests: `69 passed`.

## Remaining Issues
- `main.pdf` still needs manual/source-level update using `poly-ok-check\docs\paper_evidence_fixes.md` when the paper source is available.
- Current result interpretation must remain selection-quality focused; do not state that `proposed_agent` fully dominates every baseline.
- PMXT execution artifacts are not present locally, so the PMXT step currently runs as an optional no-op and records diagnostics instead of replacing actions with actual fills.
