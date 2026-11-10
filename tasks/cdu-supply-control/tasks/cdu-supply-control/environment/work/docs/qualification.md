# Commissioning envelope

This document describes the equipment model's parameter capabilities. The 31-case supply-control release covers the operating conditions in the work request, including cold-water and humid operation. Acceptance consists only of the six items in that request. Public commissioning cases use nominal equipment. Acceptance includes replacement equipment and faults within the following ranges. The controller receives no parameter-set identifier. Simultaneous extreme corners are not required; combined degradation and pump loss are used only where the remaining equipment can supply the requested flow.

| Item | Qualification envelope | Basis and limitation |
| --- | --- | --- |
| Pump head curve | Per-pump multiplier 0.95–1.05 on the nominal head ordinate | [ours] qualification range informed by ISO 9906:2012 Table 8 grade 2B head tolerance ±5%; this is a model envelope, not a claim the installed SPECK pumps have this acceptance grade |
| Pump capacity curve | Per-pump multiplier 0.92–1.08 on the flow abscissa | [ours] qualification range informed by ISO 9906 Table 8 grade 2B flow tolerance ±8%; independent pumps need not share exactly at equal VFD speed; ISO acceptance tolerances combine manufacturing and measurement tolerances and do not assert a probability distribution |
| Pump efficiency | Per-pump relative efficiency 0.95–1.02 | [ours] spread around nominal, informed by ISO 9906 grade 2B efficiency tolerance −5%; the positive side is an author assumption, not an ISO upper acceptance limit |
| Impeller condition | Equivalent-speed factor 0.90–1.00; additional relative efficiency 0.94–1.00 | [ours] reduced-order wear model: hydraulic head and capacity follow affinity scaling while wear-related leakage can increase the shaft power needed per delivered hydraulic watt. The VFD speed register still reports shaft speed |
| Primary valve | Cv multiplier 0.95–1.05; equal-percentage rangeability 35–65, or linear / quick-opening trim | [ours] installation/trim alternatives. Fisher's handbook documents all three characteristic families; nominal Belimo trim is equal-percentage. Quick-opening is approximated by square root of fractional stem position |
| Valve stroke | 0.9–1.1 times nominal 90 s | [ours] installation envelope; nominal actuator setting remains as in /app/docs/pumps-and-hydraulics.md (Primary valve) |
| Valve packing | Stiction deadband 2–5% stroke, slip jump 1.2–3.5% stroke; seized stem is a separate fault | [ours] two-parameter stick-slip approximation. Choudhury et al. document the two-parameter S/J mechanism and a 2% example; the full ranges here are author-chosen and not Belimo product fault specifications |
| Healthy Pt100 channels | Fixed calibration bias up to ±0.20 K, slow drift up to 0.012 K over a 1200 s witness test, noise 0.04–0.06 K rms | Calibration/noise/drift allocation [ours], informed by IEC 60751 class B tolerance ±(0.3 + 0.005\|T\|) °C quoted by WIKA. The IEC tolerance is an accuracy envelope, **not** a noise standard deviation or an ageing-rate guarantee |
| Healthy pressure / dP channels | Calibration bias up to ±0.035 psi, drift up to 0.006 psi over a test, noise 0.015 psi rms | Allocation [ours]; Rosemount 3051C reference accuracy is ±0.065% span (range 5). At the model spans of 150/200 psi this gives ±0.0975/0.13 psi; chosen rms noise is stochastic, so those are not hard sample bounds. This is a representative industrial transmitter, not a claimed Deschutes BOM |
| Healthy flow meter | Gain error ±0.4%, fractional noise 0.03% of reading nominal sigma clipped at ±3 sigma, zero bias/drift | Allocation [ours] enforces the Deschutes ±0.5% reading specification: worst combined gain and noise is 0.4% + 1.004 × 0.09% = 0.49036% of reading. The percentage allocation and clipping are model choices; the source accuracy is not a Gaussian sigma. The noise scales with actual flow and vanishes at zero flow |
| Training load | B200 Llama-8B and B200 diffusion training traces; coherent training shapes and time-shifted trace segments | Published measured node power; converting node watts to rack liquid heat and phase-aligning groups are [ours], represented by the supplied commissioning simulations |

Low head/flow, wear and loss of a pump are combined only when the remaining equipment can still provide the requested flow with sensible control. Equipment spread changes the readings and hydraulic behavior used for control. The wider equipment model supports faults on either redundant channel and recurring faults; the complete fault scope is specified in the work request. Calibration spread and legitimate rack service remain healthy conditions.


## Implemented model variations

The pump tables are actually changed: `flow_rate_1D_TLU = nominal * pump_flow`, `head_1D_TLU = nominal * pump_head`, and power is scaled by head × flow / efficiency. The same power scaling is applied to VFD kW telemetry. Wear acts on the hydraulic effective speed and separately on efficiency; it changes the physical pump behavior.

The facility valve remains a physical valve. Its effective opening is mapped to the required Cv characteristic, while `valve_pos` reports actual stem position. Stiction and seizure act on that stem position, before the characteristic. Bias, gain, seeded noise and slow drift act on instrument signals independently of fault injection. Fault mode 6 is a recurring 10 s invalid burst every 60 s; it recovers between bursts.


## Site operating range

The row has four rack groups, each designed for 125 GPM. The acceptance runs use facility supply water from 17 to 30 °C, room dew point from 12 to 21 °C, load-bank and training workloads up to 2 MW, and partial-row service with deliberate rack-group isolation and restoration. These ranges describe the supplied tests; they do not imply every cross-product corner is required. This release uses water and 25 psid facility differential pressure; PG25 is not part of this 31-case qualification scope.
