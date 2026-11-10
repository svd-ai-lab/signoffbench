# CDU instruments and failure signals

## Instrument list (site-model I/O list, [ours])

| Tag | Measures | Range / signal | Dynamics and accuracy |
| --- | --- | --- | --- |
| T_sup1 | TCS supply temperature, RTD 1 | Pt100 4-wire, head transmitter 4-20 mA = 0-100 °C | thermowell ~4 s; noise ~0.05 °C |
| T_sup2 | TCS supply temperature, RTD 2 (second well, 0.5 m downstream) | as T_sup1 | deeper well ~8 s; noise ~0.05 °C |
| T_ret, T_fs, T_fr | TCS return, facility supply, facility return temperature | as T_sup1 | ~4 s |
| P_sup, P_ret | TCS supply / return pressure at the CDU flanges | 4-20 mA = 0-200 psig | noise 0.015 psi rms [ours] |
| dP1, dP2 | TCS supply-return differential at the CDU flanges | 4-20 mA = 0-150 psid | dP1 no damping, dP2 damping 2 s; noise 0.015 psi rms [ours] |
| F_sec | TCS flow (electromagnetic meter, supply) | 4-20 mA = 0-1000 GPM | +-0.5 % of reading (spec 3.2), noise 0.03% of reading nominal sigma, clipped ±3 sigma [ours] |
| P_fs, P_fr | facility pressure at HX primary inlet (after strainer) / HX primary outlet (before control valve) | 4-20 mA = 0-200 psig | noise 0.015 psi rms [ours] |
| valve_pos | primary valve actuator position feedback | 2-10 V | |
| spdX, kWX, faultX | per VFD over Modbus: output speed %, input power kW, fault/offline status | | |

## Engineering fault catalogue ([ours])

| Instrument | Failure | What the PLC reads |
| --- | --- | --- |
| RTD / temperature transmitter | open circuit (broken lead, RTD element) | upscale burnout: >= 21 mA, i.e. 106 °C or more (NAMUR NE 43) |
| RTD | drift (moisture in the head, element ageing) | slow offset growth, typically well under 1 °C per minute |
| RTD / transmitter | frozen value (failed head transmitter, stale Modbus register) | constant reading, no noise |
| RTD | damaged shield, loose terminal | large noise |
| Flow meter | signal loop open / power lost | <= 3.6 mA, i.e. -25 GPM for the 0-1000 GPM span; model under-range sentinel -150 GPM [ours] |
| dP transmitter | signal loop open / power lost | <= 3.6 mA, i.e. -2.5 % of span or below (NAMUR NE 43) |
| dP transmitter | impulse line partly plugged, diaphragm drift | slow drift |
| dP transmitter | loose terminal, EMI | large noise |
| Flow meter | electrode fouling, empty-pipe or frozen output | frozen or offset reading |
| Primary valve | seized stem | actuator stalls, feedback stays, command and position part |
| Primary valve | worn packing | valve sticks, then jumps (stick-slip) |
| Pump | worn impeller / wear rings | less head and less power at the same speed, nothing from the VFD |
| Pump | check valve held open by debris | a stopped pump passes reverse flow and spins backwards; nothing from the VFD |
| VFD / mains | drive trip; loss of mains | VFD fault / offline flag (Modbus) |

NAMUR NE 43 (signal levels for failure information of digital transmitters): measuring information 3.8-20.5 mA; failure information <= 3.6 mA or >= 21.0 mA.

The fault catalogue describes possible equipment behavior. Only the fault scope in the work request is assessed in this release. Calibration ranges are in `/app/docs/qualification.md`.
