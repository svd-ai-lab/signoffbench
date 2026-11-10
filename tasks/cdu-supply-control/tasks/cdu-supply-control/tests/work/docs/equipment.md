# Equipment model

The supplied FMUs were exported from the client’s Simulink equipment model in FMI 3.0 Co-Simulation format with Event Mode. They expose the thermal-liquid plant, instrumentation, fault behavior and scenario inputs. The supplied Python bridge retains the original one-scan actuator-command delay in an external buffer initialized to zero. Authoring used MATLAB/Simulink; execution uses Python/FMPy without MATLAB or Modelica. Controller authority is limited to the declared 23 observations and four actuator outputs.

## Plant contents

- TCS (secondary): expansion tank at pump suction (15 psig); 3 centrifugal pumps in parallel (pumps-and-hydraulics.md), each with a check valve; internal loss (filter, meter); Alfa Laval HX hot side (fitted to spec Table 5.3); supply flow meter and P/T; 50 ft supply wall manifold; 4 rack groups (isolation valve, quadratic rack impedance, 100 L, heat input); return manifold; return P/T.
- FWS (primary): facility supply header at T_FWS, facility differential (test case), strainer/pipe loss, HX cold side (P/T at HX inlet and outlet), primary control valve (equal-%, Cv 290, 90 s stroke), facility return header.
- VFDs: speed command 0-100 %; a command below 20 % stops the pump; ramp 10 %/s. A drive fault or loss of mains stops the drive (pump coasts down) and raises the drive's fault/offline flag; after mains returns the drive reboots in about 5 s, clears the flag and follows its speed command again (flying restart). A tripped drive (fault) stays off.
- Pump wear: a worn impeller makes less head at the same speed (the drive still reports the commanded speed); its power changes with both the hydraulic capacity loss and the separate efficiency loss (/app/docs/qualification.md).
- A pump's check valve can stick open: a stopped pump then passes reverse flow from the discharge header back to suction (the model represents the reverse leakage path, not reverse-shaft dynamics); the path closes once that pump runs.
- Primary valve: the actuator can stall on a seized stem (position feedback stays at the valve position) or the valve can stick and jump (packing friction).
- Instruments and their failure behaviour: instruments.md.
