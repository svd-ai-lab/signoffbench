# Difficulty assessment summary

This batch planned 7 GPT-6 Luna / max runs; 6 were complete at the packaging cutoff, and the completed group passed 1/6. The unfinished run is not counted in the statistics. 5 runs were selected by native score such that the selected group passes at most 2/5, with ties broken by run number: normal01, normal02, normal03, normal04, normal05 were selected, with native scores 0, 0, 1, 0 and 0, giving the selected group 1/5 passes. The selected group is the result of a score-based filter, not an unscreened 5-sample pass rate.

| Run | reward | Passed cases | Answer minutes | Verifier minutes | Native steps | Agent turns |
|---|---:|---:|---:|---:|---:|---:|
| normal01 | 0 | 30/31 | 27.17 | 2.22 | 61 | 55 |
| normal02 | 0 | 26/31 | 22.62 | 2.38 | 22 | 16 |
| normal03 | 1 | 31/31 | 13.90 | 3.55 | 17 | 11 |
| normal04 | 0 | 30/31 | 25.73 | 2.47 | 53 | 47 |
| normal05 | 0 | 30/31 | 25.73 | 2.36 | 40 | 34 |

The 5 selected runs contain 930 native sub-checks in total. Full trajectories, scores and the selection basis are in metadata/trajectory_index.json, trial_metrics.csv and run_selection.json. Tokens use the native trajectory.final_metrics cumulative basis; cost is not estimated.
