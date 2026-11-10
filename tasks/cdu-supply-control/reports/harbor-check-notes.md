# Harbor quality check

The native quality check of 2026-11-07 completed with **32 pass / 1 fail / 2 not_applicable**. The check input is bound to commit `a15979fb9f50c4d22f8c80d0303c4e2604a77f7c`, with all 186 task files matched item by item. It used Harbor 0.25.0, Codex 0.167.0, GPT-6.1 Sol / medium and `-a codex`.

The rubric is `docs/prompts/task-implementation.toml` from the official Terminal-Bench commit `ad8b8447d82d23456a8b99aa0b3c65e7abf0646c`, used unmodified; SHA-256: `19b879cd424cc22cc2f56d8f80ed98c9c386a8df0885377f7cb9d4ebab21df5a`.

The per-item outcomes determine the quality-check result; a native job reward=1 does not mean every check passed.

## Results

The only failing item is `task_toml_schema`.

The [metadata] section includes difficulty = "Level 3", which is outside the benchmark's explicitly allowed metadata fields. The README procurement explanation does not create an exception to this schema criterion.

Procurement requires retaining `metadata.difficulty = "Level 3"`, so this round keeps that field and the original rubric; the current quality check does not fully pass. The remaining applicable items, including `instruction_concision` and `solvable`, pass. The 2 N/A items are `artifact_efficiency` and `do_not_modify_enforced`.

The checker executed the reference controller; all 186 checks across the 31 cases passed, and 13 metric boundary probes were reproduced. See reports/difficulty.md for the model evaluation of the current task statement.

Raw report: `evidence/selfcheck/harbor-check-current/check_report.json`; the complete job, the input-hash receipt and the binding verification are stored in the same directory.
