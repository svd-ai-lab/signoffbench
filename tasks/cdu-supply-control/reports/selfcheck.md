# Self-check results

This report indexes the actual run evidence. The formal model evaluation is the 5 runs of this batch selected by score; results and full trajectories are in `metadata/trajectory_index.json`. This directory does not repeat the 5-run answering evidence.

| Check | Result and scope | Original record |
|---|---|---|
| Harbor quality check | 33 pass / 0 fail / 2 N/A; see harbor-check-20261108.md | evidence/selfcheck/harbor-check-20261108/ |
| Oracle, Nop and concurrency | Oracle=1 and Nop=0 for this batch; the records include the actual scoring range | evidence/selfcheck/current-preflight/ |
| Verifier regression | Oracle and 5 frozen submissions replayed, with physical metrics and reward unchanged; includes normal shutdown and post-timeout descendant cleanup tests | evidence/selfcheck/grader-validation/ |
| Adversarial self-check | 4 deterministic negative cases all give reward=0; a strong-model prompt attack and native analysis were also completed, covering local threshold tampering, leakage search and a constant controller. The tampering timed out the production run, the leakage search found no answer, and the constant controller was rejected across all 31 cases; no claim of comprehensive anti-cheat certification | evidence/selfcheck/e09-quick/; [strong-model run identity, results and limits](https://github.com/svd-ai-lab/benchmark-deliverables/blob/7b92bce566906e51cfb9ec190ea284db2c47e360/docs/harbor-utility-validation.md) |
| Offline build and images | The corresponding build sources, image measurements and offline layout records are retained; the 2 run images of this batch were rebuilt offline from the current source, retaining image identity, compressed size and build logs | evidence/selfcheck/offline-build01/、offline-layout-validation.json、current-image-size.json |


The current delivery package ships only the large FMU assets; images, wheels and debs are obtained by the preparation script against fixed identities. The offline build records above preserve historical execution facts; the current packaging does not claim fully offline availability.
