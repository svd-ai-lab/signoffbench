# Data-center liquid-cooling system dynamic control

- **Task ID:** cdu-supply-control
- **Category:** Science / Physics
- **Subcategory:** Dynamical Systems, feedback control, thermal-fluid systems and fault tolerance
- **Difficulty:** Level 3

## Task content

Write a Python controller for a CDU liquid-cooling installation with 3 pumps, coordinating the pumps and a control valve. Under sensor drift, power loss, load changes and rack-service switching, the supply flow, temperature and pressure must stay within engineering requirements.

The task is built from the author's data-center liquid-cooling project experience, combined with OCP material, public CDU vendor documentation and the Ahmed-Elsayed95 public training workload data. The agent must read the equipment interface, analyze the abnormal signals, design a closed-loop control strategy, and validate and correct the program through dynamic simulation.

## Acceptance and measured results

The independent verifier covers 31 cases and 6 engineering requirements; all passing gives reward 1, otherwise 0. This batch planned 7 GPT-6 Luna / max runs; 6 were complete at the packaging cutoff, and the completed group passed 1/6. The unfinished run is not counted in the statistics. 5 runs were selected by native score such that the selected group passes at most 2/5, with ties broken by run number: normal01, normal02, normal03, normal04, normal05 were selected, with native scores 0, 0, 1, 0 and 0, giving the selected group 1/5 passes. The selected group is the result of a score-based filter, not an unscreened 5-sample pass rate. The package includes the full trajectories of the 5 selected runs and 930 sub-checks.

## Duration and resources

| Item | Value |
|---|---|
| Estimated domain-expert solving time | 4 hours; with the control scheme known, implementation and validation reuse the supplied simulation and test tools |
| Actual model answering time | 13.9～27.2 minutes across the 5 selected runs |
| Actual verifier time | 2.2～3.5 minutes across the 5 selected runs |
| Answering container | 4 CPU, 4 GB memory, 20 GB disk limit |
| Independent verifier container | 4 CPU, 8 GB memory, 20 GB disk limit |
| Answering time limit | 7200 s |
| Verifier time limit | 900 s |
| Image build time limit | 1800 s |
| Runtime platform | Linux/amd64, CPU only; model requests go through the authorized US proxy; the task simulation and independent scoring do not depend on external services |
| Evaluation baseline | Harbor 0.25.0 / Codex 0.167.0; GPT-6 Luna, reasoning effort max |
| Task file size | About 291 MB after restoration into 2 build directories, including FMUs and offline dependencies |
| Delivery package size | The complete offline archive is accompanied by a separate size and SHA-256 checksum file |

## Delivery contents

Complete Harbor task directory, offline build dependencies, reference solution, independent verifier, single-task inventory, self-check records, 5 model evaluation results and the file checksum inventory. The code ships with the package; no access to an internal code repository is needed. See metadata/submission_checklist.csv for file locations.

## Similarity check

Text and engineering-content comparison was performed against 241 tasks from Terminal-Bench and Terminal-Bench Science, and no evidence was found sufficient to identify a copy or a simple parameter change. The closest task is also feedback control, but the equipment, interface and acceptance targets differ.

## Delivery status

The 5 completed runs of the current task statement were selected into the submission by score; all completed and pending runs are in metadata/run_selection.json. The Harbor check is 32 pass, 1 fail, 2 N/A; the only failing item is task_toml_schema, which concerns the difficulty field that procurement requires to be retained, pending explanation to the recipient.
