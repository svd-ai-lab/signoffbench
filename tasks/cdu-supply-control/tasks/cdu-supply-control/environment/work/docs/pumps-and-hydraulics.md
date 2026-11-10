# the CDU pumps and hydraulics

## Pump set (site-model design basis, [ours])

the CDU is a Deschutes build with the spec's 2 x 100 % pump pair replaced by **3 x 50 % pumps** (2 duty + 1 redundant, "N+1"), so a pump can be swapped while the CDU runs at full flow (spec 7.2). Each pump is the spec pump (SPECK TOEMA065200) hydraulics at half the flow: two pumps in parallel deliver the spec's one-pump curve (Fig 5.1.2), three exceed the spec's one-pump curve. Each pump has its own check valve on the discharge, its own VFD (ABB ACH580 class) and its own mains feed.

| Item | Value |
| --- | --- |
| Pumps | 3, in parallel, common suction (expansion tank 15 psig) and common discharge header |
| Rated point per pump | 250 GPM at ~104 psi pump head, 100 % speed (curve fit; the spec pump nameplate says 500 GPM at 112 psi) |
| Pump head at 100 % speed, per pump | H(q) = 120 + 0.0744 q - 5.524e-4 q^2 psi (q = GPM through that pump) |
| Affinity | at speed n (fraction): H(q, n) = n^2 H(q/n) |
| Common internal loss (HX secondary + filter + piping) | 5.89e-5 Q^2 psi, Q = CDU flow (8.7 psi of it is the HX, Fig 5.3.1) |
| Available dP at the CDU flanges | pump head - internal loss: two pumps at 100 %: 120 + 0.0372 Q - 1.97e-4 Q^2 (spec Fig 5.1.2) |
| Brake power per pump, 100 % speed | 4.5 + 0.044 q kW (15.5 kW at 250 GPM); affinity: P(q, n) = n^3 P(q/n) |
| Motor | 18.5 kW per pump; motor + VFD efficiency ~0.93 |
| VFD | speed command 0-100 %; below 20 % the drive stops the pump; accel/decel ramp 10 %/s; on a drive fault or loss of mains the pump coasts down (~10 s) |
| Check valves | one per pump, swing type, crack 0.5 psi |

Parallel operation note (modeled hydraulic behavior): pumps with flat curves run in parallel share flow badly when their heads differ; the weaker pump can be pushed back to shut-off behind its check valve and run without flow.

## Spec curves (Deschutes v1.0 figure fits, Q in GPM, dP in psi)

Two pumps (spec pumps) running, available pressure, PG25 (Fig 5.1.1):

| Speed | Fit |
| --- | --- |
| 100 % | 119 + 0.0211 Q - 9.34e-5 Q^2 |
| 90 % | 94.1 + 0.0148 Q - 8.41e-5 Q^2 |
| 80 % | 74.4 + 0.0107 Q - 7.96e-5 Q^2 |
| 66 % | 53.2 + 0.0103 Q - 9.07e-5 Q^2 |
| 50 % | 29.6 + 0.0112 Q - 9.88e-5 Q^2 |

One spec pump running (Fig 5.1.2), 100 %: 120 + 0.0372 Q - 1.97e-4 Q^2.

Heat exchanger secondary side dP, 2-pass (Fig 5.3.1): dP = -0.0131 + 1.41e-3 Q + 3.19e-5 Q^2 (8.7 psi at 500 GPM). The primary side has the same plates; the vendor gives the same curve for it.

Primary (facility) side across the CDU, control valve 100 % open, water (Fig 5.1.3): dP = 0.0785 + 1.58e-4 Q + 6.06e-5 Q^2 (15.3 psi at 500 GPM).

## Primary control valve

Belimo B6500 family, 5" characterized control valve, equal-percentage, Cv 290 (Belimo official product-page indexed excerpt; original document unavailable, the value is retained from the client model, with this source limitation). Actuator Belimo GKRX24-MFT class, 90 s full stroke as set here, position feedback from the actuator (2-10 V). If the stem seizes the actuator stalls (feedback stays where the valve is); worn packing makes the valve stick and jump.
