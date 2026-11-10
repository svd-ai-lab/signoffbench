"""Supply-side controller for the three-pump CDU."""

from math import isfinite, sqrt
from statistics import median


class Controller:
    """Coordinate the secondary pumps and the primary heat-exchanger valve."""

    _PUMP_NAMES = ("A", "B", "C")
    _DP_TARGET = 85.0
    _DP_UNCERTAIN = 82.0
    _DP_PARTIAL_ROW = 79.0
    _SUPPLY_TARGET = 32.0

    def __init__(self):
        self.reset()

    def reset(self):
        # The wrapper may request a reset more than once before the first scan.
        self._temp_history = [[], []]
        self._flow_history = []
        self._dp_history = []
        self._speed_history = []
        self._last_temp = self._SUPPLY_TARGET

    @staticmethod
    def _clamp(value, lower, upper):
        return min(upper, max(lower, value))

    @staticmethod
    def _trim_append(history, value, limit=25):
        history.append(value)
        if len(history) > limit:
            del history[:-limit]

    def _supply_temperature(self, observation):
        raw = [float(observation["T_sup1"]), float(observation["T_sup2"])]
        valid = [(-5.0 <= value <= 105.0) for value in raw]

        for index in range(2):
            if valid[index]:
                self._trim_append(self._temp_history[index], raw[index])

        values = []
        noisy = [False, False]
        frozen = [False, False]
        for index in range(2):
            history = self._temp_history[index]
            if not valid[index] or not history:
                values.append(None)
                continue
            recent = history[-5:]
            values.append(float(median(recent)))

            # A shield/terminal fault creates much larger short-term scatter than
            # the specified healthy RTD noise.  The median also removes isolated
            # spikes before they reach the valve controller.
            window = history[-11:]
            if len(window) >= 7:
                center = float(median(window))
                mad = float(median([abs(item - center) for item in window]))
                noisy[index] = mad > 0.45

        # A frozen transmitter is exactly constant; its healthy mate continues
        # to show the normal RTD noise and follows real supply-temperature moves.
        if len(self._temp_history[0]) >= 12 and len(self._temp_history[1]) >= 12:
            spans = []
            for history in self._temp_history:
                window = history[-12:]
                spans.append(max(window) - min(window))
            if spans[0] < 0.002 and spans[1] > 0.08:
                frozen[0] = True
            elif spans[1] < 0.002 and spans[0] > 0.08:
                frozen[1] = True

        facility_supply = float(observation["T_fs"])
        return_temp = float(observation["T_ret"])
        facility_return = float(observation["T_fr"])
        low_plausible = facility_supply - 3.0
        high_plausible = max(return_temp, facility_return) + 3.0

        def plausibility_penalty(value):
            return max(0.0, low_plausible - value) + max(0.0, value - high_plausible)

        usable = [valid[i] and not noisy[i] and not frozen[i] and values[i] is not None
                  for i in range(2)]
        if usable[0] and usable[1]:
            first, second = values
            if abs(first - second) > 2.5:
                penalty0 = plausibility_penalty(first)
                penalty1 = plausibility_penalty(second)
                if penalty0 + 0.5 < penalty1:
                    estimate = first
                elif penalty1 + 0.5 < penalty0:
                    estimate = second
                else:
                    estimate = 0.5 * (first + second)
            else:
                estimate = 0.5 * (first + second)
        elif usable[0]:
            estimate = values[0]
        elif usable[1]:
            estimate = values[1]
        elif valid[0] and values[0] is not None and valid[1] and values[1] is not None:
            # If both channels are temporarily noisy/frozen, a robust midpoint is
            # safer than allowing either one to command a full valve stroke.
            estimate = 0.5 * (values[0] + values[1])
        elif valid[0] and values[0] is not None:
            estimate = values[0]
        elif valid[1] and values[1] is not None:
            estimate = values[1]
        else:
            # Both open-circuit signals are outside the assessed single-fault
            # envelope.  Hold the last valid estimate so output remains bounded.
            estimate = self._last_temp

        if not isfinite(estimate):
            estimate = self._last_temp
        self._last_temp = float(estimate)
        return float(estimate)

    @staticmethod
    def _differential_pressure(observation):
        candidates = []
        for key in ("dP1", "dP2"):
            value = float(observation[key])
            # NAMUR open-circuit values are negative and do not represent a
            # physical CDU differential.
            if 0.0 <= value <= 150.0:
                candidates.append(value)

        pressure_difference = float(observation["P_sup"]) - float(observation["P_ret"])
        if -5.0 <= pressure_difference <= 160.0:
            candidates.append(pressure_difference)

        if candidates:
            return float(median(candidates))
        return 0.0

    def _rack_count_estimate(self, observation, differential, speeds):
        flow = float(observation["F_sec"])
        self._trim_append(self._flow_history, flow, 31)
        self._trim_append(self._dp_history, differential, 31)
        self._trim_append(self._speed_history, max(speeds, default=0.0), 31)

        # The open-loop sentinel and impossible values are explicit failures.
        if flow < 0.0 or flow > 1000.0 or differential <= 1.0:
            return None

        # A frozen flow transmitter can look plausible while the rows are
        # changing.  Cross-check its lack of movement against pressure/speed.
        if len(self._flow_history) >= 16:
            recent_flow = self._flow_history[-16:]
            recent_dp = self._dp_history[-16:]
            recent_speed = self._speed_history[-16:]
            flow_span = max(recent_flow) - min(recent_flow)
            dp_span = max(recent_dp) - min(recent_dp)
            speed_span = max(recent_speed) - min(recent_speed)
            if flow_span < 0.02 and (dp_span > 0.5 or speed_span > 0.5):
                return None

        # At a given header differential, each fully open rack follows the same
        # quadratic branch curve.  The nominal design point is about 125 GPM at
        # 85 psid; normalize total flow by that per-row estimate to recognize
        # legitimate rack isolation without requiring an isolation input.
        expected_per_row = 125.0 * sqrt(max(differential, 1.0) / 85.0)
        estimate = flow / max(expected_per_row, 1.0)
        if estimate < 0.25 or estimate > 4.75:
            return None
        return float(estimate)

    def step(self, observation):
        supply = self._supply_temperature(observation)
        dew_point = float(observation["dew"])

        # The commissioned water/dew-point envelope is 17–30 C / 12–21 C.
        # A 32 C supply target leaves useful margin for RTD drift and slow valve
        # motion while remaining well below the 55 C hot-supply limit at 2 MW.
        target_temp = max(self._SUPPLY_TARGET, dew_point + 8.0)
        temp_error = supply - target_temp  # positive means open the primary valve
        valve_position = self._clamp(float(observation["valve_pos"]), 0.0, 100.0)

        # The actuator is slow and rate-limited.  Position feedback plus a
        # proportional position offset behaves as a gradual integral action:
        # it keeps moving while temperature is away from target and avoids
        # accumulating a large hidden integral during seizure or stiction.
        valve_gain = 10.0
        valve_command = self._clamp(
            valve_position + valve_gain * temp_error, 0.0, 100.0
        )

        differential = self._differential_pressure(observation)
        return_pressure = float(observation["P_ret"])

        faults = [float(observation[f"fault{name}"]) >= 0.5 for name in self._PUMP_NAMES]
        speeds = [self._clamp(float(observation[f"spd{name}"]), 0.0, 100.0)
                  for name in self._PUMP_NAMES]
        rack_estimate = self._rack_count_estimate(observation, differential, speeds)
        running_speed_samples = [speeds[i] for i in range(3)
                                 if not faults[i] and speeds[i] >= 20.0]
        if running_speed_samples:
            reference_speed = float(median(running_speed_samples))
        else:
            available_speeds = [speeds[i] for i in range(3) if not faults[i]]
            reference_speed = max(available_speeds, default=0.0)

        # With 3 x 50% pumps, regulating the shared header differential is a
        # direct proxy for each open rack's quadratic branch flow.  The pressure
        # signals are fused above so a single failed dP channel is outvoted by
        # its mate and P_sup - P_ret.  A square-root correction follows the pump
        # affinity law and responds promptly to trips and rack-service changes.
        if reference_speed < 2.0 or differential <= 1.0:
            pump_command = 100.0
        else:
            if rack_estimate is None:
                target_dp = self._DP_UNCERTAIN
            elif rack_estimate >= 3.6:
                target_dp = self._DP_TARGET
            elif rack_estimate >= 2.5:
                target_dp = self._DP_UNCERTAIN
            else:
                target_dp = self._DP_PARTIAL_ROW

            # When flow evidence is uncertain at the instant of a drive loss,
            # retain enough headroom for the remaining pair to recover.  A
            # partial-row pressure rise below takes precedence.
            if any(faults) and (rack_estimate is None or rack_estimate >= 2.5):
                target_dp = max(target_dp, self._DP_TARGET)
            if differential > self._DP_TARGET + 1.0:
                target_dp = min(target_dp, self._DP_PARTIAL_ROW)

            # Keep additional margin to the supply-pressure ceiling if the
            # return header is abnormally pressurized.
            allowed_dp = 118.0 - return_pressure
            if allowed_dp < target_dp:
                target_dp = max(45.0, allowed_dp)
            pump_command = reference_speed * sqrt(target_dp / max(differential, 1.0))
            pump_command = self._clamp(pump_command, 20.0, 100.0)

        return {
            "pumpA_cmd": float(pump_command),
            "pumpB_cmd": float(pump_command),
            "pumpC_cmd": float(pump_command),
            "valve_cmd": float(valve_command),
        }
