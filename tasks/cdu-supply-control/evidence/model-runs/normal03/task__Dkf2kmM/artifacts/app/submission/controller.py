"""Feedback controller for the CDU secondary pumps and primary valve."""

from collections import deque


def _clamp(value, low, high):
    return low if value < low else high if value > high else value


def _median(values):
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    middle = n // 2
    if n % 2:
        return ordered[middle]
    return 0.5 * (ordered[middle - 1] + ordered[middle])


class Controller:
    """Use redundant pressure and temperature signals with slow actuator loops."""

    def reset(self):
        # The pressure loop starts with the pumps called for; their VFD ramp is
        # the rate limit.  The integral then trims speed to the measured head.
        self._pump_base = 100.0
        self._pump_error_prev = None
        self._dp_filtered = None
        self._pump_offsets = [0.0, 0.0, 0.0]
        self._pump_flow_est = [None, None, None]

        self._temperature_channels = [None, None]
        self._temperature_history = [deque(maxlen=25), deque(maxlen=25)]
        self._temperature = None

        self._valve_command = None

    def _temperature_reading(self, observation):
        filtered = []
        valid = []
        for i, key in enumerate(("T_sup1", "T_sup2")):
            value = float(observation[key])
            # Open-circuit RTDs burn out above the declared engineering range.
            # Values outside plausible liquid-supply temperatures are ignored.
            if 2.0 <= value <= 75.0:
                hist = self._temperature_history[i]
                hist.append(value)
                recent = list(hist)[-3:]
                robust = _median(recent)
                previous = self._temperature_channels[i]
                if previous is None:
                    smooth = robust
                else:
                    # A real water-temperature step is slower than an isolated
                    # EMI spike.  Clip only extreme one-scan excursions.
                    robust = _clamp(robust, previous - 2.5, previous + 2.5)
                    smooth = previous + 0.35 * (robust - previous)
                self._temperature_channels[i] = smooth
                filtered.append(smooth)
                valid.append(True)
            else:
                filtered.append(self._temperature_channels[i])
                valid.append(False)

        selected = [filtered[i] for i in range(2) if valid[i] and filtered[i] is not None]
        if len(selected) == 2:
            a, b = filtered
            if abs(a - b) > 1.5:
                # A frozen transmitter has no instrument noise.  Once its
                # process value has separated from the moving channel, use the
                # moving channel rather than averaging a stale value into it.
                spans = []
                for hist in self._temperature_history:
                    recent = list(hist)[-16:]
                    spans.append(max(recent) - min(recent) if len(recent) >= 8 else 1.0)
                if spans[0] < 0.012 and spans[1] > 0.10:
                    selected = [b]
                elif spans[1] < 0.012 and spans[0] > 0.10:
                    selected = [a]
                else:
                    # Large high-frequency noise is identified by its recent
                    # sample-to-sample movement, independently of the process
                    # trend shared by both wells.
                    roughness = []
                    for hist in self._temperature_history:
                        recent = list(hist)[-16:]
                        diffs = [abs(recent[j] - recent[j - 1]) for j in range(1, len(recent))]
                        roughness.append(_median(diffs) if diffs else 0.0)
                    if roughness[0] > 0.35 and roughness[0] > 2.5 * max(roughness[1], 0.03):
                        selected = [b]
                    elif roughness[1] > 0.35 and roughness[1] > 2.5 * max(roughness[0], 0.03):
                        selected = [a]
                    else:
                        # A slowly drifting channel is only half-weighted.  The
                        # deliberately warm temperature target leaves ample
                        # condensation margin even at the qualified drift limit.
                        selected = [0.5 * (a + b)]
        elif len(selected) == 0:
            # T_ret is an independent, healthy process temperature and is a
            # conservative fallback during simultaneous short invalid bursts.
            selected = [float(observation["T_ret"])]

        measured = sum(selected) / len(selected)
        if self._temperature is None:
            self._temperature = measured
        else:
            # The two installed wells have several seconds of thermal lag; a
            # modest filter rejects their noise without delaying fault response.
            self._temperature += 0.40 * (measured - self._temperature)
        return self._temperature

    def _differential_pressure(self, observation):
        candidates = []
        for key in ("dP1", "dP2"):
            value = float(observation[key])
            # Open-loop dP transmitters report below zero (NAMUR failure level).
            if 0.0 <= value <= 150.0:
                candidates.append(value)
        pressure_difference = float(observation["P_sup"]) - float(observation["P_ret"])
        if -1.0 <= pressure_difference <= 150.0:
            candidates.append(max(0.0, pressure_difference))

        if not candidates:
            raw = self._dp_filtered if self._dp_filtered is not None else 0.0
        else:
            raw = _median(candidates)
        if self._dp_filtered is None:
            self._dp_filtered = raw
        else:
            self._dp_filtered += 0.40 * (raw - self._dp_filtered)
        return self._dp_filtered

    def _balance_pumps(self, observation):
        speeds = [float(observation[key]) for key in ("spdA", "spdB", "spdC")]
        powers = [float(observation[key]) for key in ("kWA", "kWB", "kWC")]
        faults = [float(observation[key]) >= 0.5 for key in ("faultA", "faultB", "faultC")]
        estimates = []

        for i in range(3):
            if faults[i] or speeds[i] < 35.0:
                self._pump_flow_est[i] = None
                continue
            n = max(0.20, speeds[i] / 100.0)
            # Invert the specified affinity power curve.  Efficiency tolerance
            # makes this approximate, so balancing is deliberately bounded.
            q = (powers[i] / (n * n) - 4.5 * n) / 0.044
            q = _clamp(q, 0.0, 400.0)
            previous = self._pump_flow_est[i]
            self._pump_flow_est[i] = q if previous is None else previous + 0.18 * (q - previous)
            estimates.append((i, self._pump_flow_est[i]))

        if len(estimates) >= 2:
            common_flow = _median([item[1] for item in estimates])
            for i, flow in estimates:
                # Correct persistent sharing errors by a small relative speed
                # trim.  The common pressure loop compensates the total head.
                desired = _clamp(0.035 * (common_flow - flow), -6.0, 6.0)
                self._pump_offsets[i] += 0.012 * (desired - self._pump_offsets[i])
        return None

    def step(self, observation):
        temp = self._temperature_reading(observation)
        dp = self._differential_pressure(observation)

        # Keep the flange differential well below the 95 psid limit.  This
        # leaves pressure margin for sensor calibration and trip transients,
        # while supplying the design head to each parallel rack branch.
        dp_target = 82.0
        error = dp_target - dp
        if self._pump_error_prev is not None:
            proportional = 0.32 * (error - self._pump_error_prev)
            integral = 0.075 * error * 0.5
            proposed = self._pump_base + proportional + integral
            if (proposed > 100.0 and error > 0.0) or (proposed < 20.0 and error < 0.0):
                proposed = self._pump_base + proportional
            self._pump_base = _clamp(proposed, 20.0, 100.0)
        self._pump_error_prev = error

        # Independent pressure protection makes a single noisy sample harmless
        # and pulls speed down quickly if the header approaches either limit.
        supply_pressure = float(observation["P_sup"])
        excess = max(dp - 88.0, 1.5 * (supply_pressure - 110.0), 0.0)
        if excess > 0.0:
            self._pump_base = max(20.0, self._pump_base - min(5.0, 0.65 * excess))

        self._balance_pumps(observation)
        commands = []
        for i in range(3):
            # Keep a command on an offline drive so it follows the requested
            # speed when a temporary mains loss has cleared and the VFD reboots.
            commands.append(_clamp(self._pump_base + self._pump_offsets[i], 20.0, 100.0))

        return_temperature = float(observation["T_ret"])
        facility_supply = float(observation["T_fs"])
        dew = float(observation["dew"])
        # A high working target tolerates RTD drift and gives a wide buffer to
        # the dew-point floor while staying far below the hot-supply ceiling.
        temperature_target = max(39.0, dew + 8.0)
        load_rise = max(0.0, return_temperature - temp)
        valve_target = 43.0 + 7.0 * (temp - temperature_target) + 1.0 * max(0.0, load_rise - 8.0)

        # Opening the primary valve cannot cool below a warmer facility inlet.
        if facility_supply >= temp - 0.5 and temp < 54.0:
            valve_target = min(valve_target, 20.0)
        valve_target = _clamp(valve_target, 0.0, 100.0)

        measured_valve = _clamp(float(observation["valve_pos"]), 0.0, 100.0)
        if self._valve_command is None:
            self._valve_command = measured_valve
        # The Belimo actuator itself is slow; this command slew avoids driving
        # it back and forth on small temperature changes and through stiction.
        valve_delta = _clamp(valve_target - self._valve_command, -5.0, 5.0)
        self._valve_command = _clamp(self._valve_command + valve_delta, 0.0, 100.0)

        return {
            "pumpA_cmd": commands[0],
            "pumpB_cmd": commands[1],
            "pumpC_cmd": commands[2],
            "valve_cmd": self._valve_command,
        }
