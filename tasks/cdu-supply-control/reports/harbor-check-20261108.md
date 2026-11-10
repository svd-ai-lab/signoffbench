# Harbor quality check — 2026-11-08

Latest check: **33 pass / 0 fail / 2 not_applicable**. Both `task_toml_schema` and `task_readme` passed. The N/A items are `artifact_efficiency` and `do_not_modify_enforced`.

`metadata.difficulty` was removed, the original `difficulty_explanation` text was moved to the task README, and the outdated statement in the README claiming that the procurement difficulty field was still retained was removed. The simulation, controller, scoring thresholds and timeout configuration were not modified.

## Input and reproducibility identity

- Source commit: `3dee034a8cdfdfba3b48c3a331fc940fea049bd1`.
- res-1 run: `/opt/sb/benchmark-deliverables/runs/cdu-metadata-readme-3dee034/check`; the complete native job and trajectories are retained in that directory.
- Harbor 0.25.0; native Codex 0.167.0; `openai/gpt-6.1-sol`, medium; a single check run, with no best-result selection.
- Used the unmodified 35-item `metadata/implementation-rubric-35.toml`, SHA-256 `19b879cd424cc22cc2f56d8f80ed98c9c386a8df0885377f7cb9d4ebab21df5a`.
- The image, command, runtime and the SHA-256 of every task file are in [receipt.json](../evidence/selfcheck/harbor-check-20261108/receipt.json). The input file inventory was verified item by item against the current offline-build-layout.
- The native [check_report.json](../evidence/selfcheck/harbor-check-20261108/check_report.json) was verified by `scripts/check_harbor_report.py` across all 35 outcomes and passed. The checking agent executed the reference controller, and all 31 cases passed under the production verifier.

## Revision history and scope of this round

The earlier check with input `51614a14743b1ceaa0ae27cedaf5a51ed74749c0` gave 32 pass / 1 fail / 2 N/A, the only failure being `task_readme`: it still claimed that the difficulty field was retained in the configuration. The original evidence of that round is retained at res-1 `/opt/sb/benchmark-deliverables/runs/cdu-metadata-readme-51614a1/check`. After correcting that statement, the final check above was run in a new directory.

The [2026-11-07 check notes](harbor-check-notes.md) and their original evidence are kept as historical record; its decision to retain the procurement field has been superseded by the user's instruction for this round. This quality check is not a new adversarial test, a model result or a full acceptance certification, and it does not re-adjudicate earlier timeout results.
