# CDU supply-control delivery notes

This package contains 1 data-center liquid-cooling dynamic control task and its supporting evaluation material.

Read reports/sample_brief.md first for the task, measured results, duration and resources; check the delivered files against metadata/submission_checklist.csv.

| Directory | Contents |
|---|---|
| tasks/cdu-supply-control/ | English task statement, task configuration, review notes, runtime environment, reference solution and independent verifier |
| metadata/ | Single-task inventory, model evaluation summary, trajectory index, file checksum inventory |
| evidence/model-runs/ | 5 native Harbor jobs, agent trajectories and verifier scores |
| evidence/selfcheck/ | Oracle, Nop and offline build run records |
| reports/ | Brief, difficulty report, self-check results, provenance and similarity notes |
| shared-assets/public-fmus/ | The 6 public FMUs shared by answering and scoring |
| metadata/build-dependencies.json | Dependency download manifest pinned by version, size and SHA-256 |

## Running

On a Linux/amd64 host use Docker, Python 3.12+ and Harbor 0.25.0. Initial preparation requires network access to download the pinned Python wheels, Debian debs and base images; these files are not distributed with the delivery package. The preparation script uses public HTTPS sources and needs no access to our S3 or SSH credentials; it verifies size and SHA-256 after download, then checks the complete task files and their permissions.

```sh
python3 tools/prepare-build.py ../harbor-build/cdu-supply-control --pull-images
harbor run -p ../harbor-build/cdu-supply-control -a oracle -n 1
```

`--verify-only` only validates the bundled files and the restore manifest; it neither downloads nor runs Docker. When a complete dependency SHA-256 cache is available, pass `--asset-dir /path/to/sha256`. The preparation script does not write downloaded files into the delivery directory; a failure does not publish the task directory. The auxiliary images Harbor needs are pulled by Harbor according to its own version configuration.

The model evaluation configuration is in metadata/baseline.json. When an agent actually answers, only the English task statement and the environment/ built environment are provided; tests/, solution/ and the task README.md are for review use.

## Images and large files

This package contains 31 FMUs (6 public, 25 hidden), plus the task source, build recipes, version and hash manifests, and native evaluation evidence. Docker images, wheels and debs are not distributed with the package. The restored task files after preparation keep exactly the same bytes and permissions as the original `metadata/offline-build-layout.json`; that filename is retained to preserve the existing replay interface.

Image measurement records are in evidence/selfcheck/current-image-size.json; those records describe historical run images and do not mean image files are bundled in the package.

## Evaluation results and check scope

This batch planned 7 GPT-6 Luna / max runs; 6 were complete at the packaging cutoff, and the completed group passed 1/6. The unfinished run is not counted in the statistics. 5 runs were selected by native score such that the selected group passes at most 2/5, with ties broken by run number: normal01, normal02, normal03, normal04, normal05 were selected, with native scores 0, 0, 1, 0 and 0, giving the selected group 1/5 passes. The selected group is the result of a score-based filter, not an unscreened 5-sample pass rate. Full trajectories are in metadata/trajectory_index.json.

The Harbor quality check of 2026-11-08 gave 33 pass, 0 fail, 2 N/A. The difficulty explanation was moved to the task README and the difficulty field was removed from metadata; see reports/harbor-check-20261108.md for the configuration and native results.

The self-check scope is in reports/selfcheck.md. 4 deterministic adversarial negative cases all give reward=0; this is not equivalent to a full strong-model prompt adversarial test. The current package does not claim full acceptance.

The version relationship between the model evaluation and the current delivery is in metadata/task_version_checks.json. The runs of this batch are bound to the current task statement; the original snapshots of the 5 selected runs and the selection record from packaging are fully retained.

## File verification

The out-of-package SHA-256 file verifies the archive; metadata/file_manifest.json registers every file except itself with its SHA-256. The delivery package does not depend on our SSH/S3 credentials; dependency downloads need access to public software sources — prepare an independent build context with the command above.
