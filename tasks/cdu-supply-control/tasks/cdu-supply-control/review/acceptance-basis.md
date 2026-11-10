# Acceptance bounds and validation

## What the bounds mean

This task checks a declared operating envelope, not numerical agreement with the
reference controller. Different algorithms may issue different commands and
produce different trajectories. A solution is correct when every assessed sample
remains within the stated service limits. No reference trajectory or controller
output is used as the expected answer.

| Bound | Engineering basis and benchmark allocation |
|---|---|
| 125 GPM per rack group | Four groups partition the 500 GPM nominal secondary flow of OCP Project Deschutes v1.0, section 3.1. The four-group split is the author's plant configuration. |
| At least 90% design flow | The commissioning low-flow service floor permits a 10% reduction from nominal flow. It is an author-selected task requirement, not a tolerance fitted to a controller's output. |
| Supply at least dew point + 2 K | Condensation protection margin; the benchmark applies it to physical plant truth rather than noisy controller measurements. Instrument accuracy and noise are separately defined in `environment/work/docs/qualification.md`. |
| Supply at most 55 C | The Deschutes liquid operating-temperature upper bound (v1.0 sections 3.1 and 5). |
| Supply at most 120 psig | Author-selected site alarm limit, 10 psi below the 130 psig product relief setting (Deschutes section 3.2). |
| Differential pressure at most 95 psid | Author-selected transient ceiling, 5 psi above the 80–90 psi nominal product range; the normal control target is 85 psid. |
| Less than 30 consecutive seconds below 50% design flow | Author-selected loss-of-service criterion for this simulated rack. It is a separate prolonged-starvation guard, not a claim that every real GPU trips at exactly 30 seconds. The 90% floor is stricter in this release; the starvation item remains explicit in the contract and report. |

Product source: OCP Project Deschutes CDU Specification v1.0, 26 February 2026,
https://www.opencompute.org/documents/ocp-specification-deschutes-v1-0-pdf.
The table distinguishes product facts from benchmark/site choices. These bounds
define the task before scoring; successful controllers establish feasibility
within this envelope, not the origin of the engineering requirements.

## Numerical and algorithm variation

The verifier evaluates physical truth on the fixed one-second log after 300 seconds
of startup. Sensor bias and noise affect the controller observations, not the truth
used for scoring. The healthy replacement and calibration ranges are specified in
`environment/work/docs/qualification.md`; fault combinations are bounded by the
published task scope. The runtime fixes the 0.5-second control scan and one-scan
command delay for all implementations.

The first five reported metrics are sums of **positive violations**, so zero means
no sample crossed a service limit. Zero is not a requirement that a computed
trajectory equal a reference trajectory to floating-point precision. Values on the
allowed side can differ freely. The comparison does not hide an epsilon around
the physical limits; controllers should retain operational margin. The isolated
sampling-timestamp check uses a separate 1e-8-second tolerance and is not a physical
acceptance allowance. Boundary probes in `boundary-probes.json` exercise exact
limits and crossings using the actual metric implementation.

## Validation with independent controllers

`independent-controller-results.json` contains the complete six-metric matrix for
each case in five frozen native model submissions, including distinct candidate
hashes and hashes of their original reports. Two independently generated
controllers (normal03 and normal05) passed every case; three others failed physical
requirements. This supports algorithm-independent feasibility and rejection of
actual incorrect implementations. It is not a new difficulty measurement of the
revised instruction, and it does not claim a general numerical sensitivity study
or robustness beyond the stated scenario envelope.

The boundary probes complement those native runs: they verify that equality is
accepted at each inclusive bound, small crossings are rejected, out-of-service
racks are excluded, and 29 versus 30 consecutive low-flow samples are distinguished.
These are deterministic metric tests, not substitute FMU or model runs. The
full native reports remain in the delivery's model-run evidence; the local matrix
makes the relevant evidence available inside this reviewer task directory.
