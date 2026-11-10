## Vendor practice (published CDU controller manuals; for reference, not the CDU's sequence)

Vertiv CoolChip CDU070 Operation and Maintenance Guide (SL-80016, 2025):

- Three supply temperature sensors T3a/b/c: "The controller takes an average between all 3 readings as its input value." A sensor more than 1 °C from the others raises a "Diff. Out of Limits" alarm "after a default 30 second delay" and the controller then averages the two remaining sensors. An open-circuit sensor raises its "Sensor Fault" alarm "with no time delay".
- Pressure sensor fault: reading outside the normal range; "For DP control, if system differential pressure is not valid, then pump speed will remain at last known demand."
- "All sensors related to control (PS1, PS2 and T2) are redundant ... so a single sensor failure will not impact the operation or the status of the CoolChip CDU070."
- Run/standby pumps: "If Pump 1 fails to reach 90% (default) of the DP/flow demand in the default time period of 100 seconds, it is assumed there is a pump flow/pressure fault. The pump ramps down to a stop. Pump 2 is initialized." Duty rotation weekly; changeover takes about 0.25 s (P210 default 250 ms).
- Low flow / low DP alarm at 80 % of set point after 30 s (P204-P206). Over-pressure alarm set point P211. Secondary temperature alarms 2 °C below/above set point (P310/P311).
- Group control: standby pumps "start in 75 ms and a 2 second ramp up ... to seamlessly maintain system differential pressure if a unit is lost without over/undershoots"; a failure speed offset (P217) is applied "to avoid spikes in differential pressure"; the 2 s VFD ramp "is designed to prevent a secondary discharge pressure over shoot on ... (pump) restart".
- After a power failure the unit restarts (P703 "Post Power Failure Options": Run).

Lenovo Neptune RM100 in-rack CDU user guide: low-flow alarm at 90 % of the flow set point after 100 s (P204, P206); pump failover when the running pump does not reach 90 % of demand within 100 s; secondary temperature alarms 2 °C from set point; dew-point offset 3 °C.

OCP Liquid-to-Liquid CDU Test Methodology r1, 3.2.4: "there will be system alarms and notifications communicated to the operator if the actual flow conditions deviate from preset values or when abnormal conditions occur."

The nominal noise above is for the released commissioning plant; qualification calibration, noise and drift envelopes are in qualification.md. The fault catalogue is an author-created witness-test list, not an observed vendor fleet history.

Cross-channel plausibility checking of redundant channels — the two supply RTDs, the two dP transmitters — is standard commissioning practice, consistent with the published sequences above: keep an agreement window with a short persistence delay, and when one channel departs, exclude it and carry the healthy channel. A supervisory release for this row is expected to know this; the instrument set deliberately ships the redundant pairs to support it.
