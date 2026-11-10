"""Four actuator CDU controller.

The secondary pumps are controlled from the measured header differential
pressure.  This naturally reduces total flow when a rack branch is isolated
while preserving the pressure, and therefore flow, through the branches that
remain in service.
"""

from collections import deque


def _clip(value, low, high):
    return min(high, max(low, value))


def _median(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n & 1:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


class Controller:
    """CDU supply controller with no external dependencies or case inputs."""

    def reset(self):
        self.scan = 0

        self.dp_filtered = None
        self.pump_command = 100.0
        self.pump_offsets = [0.0, 0.0, 0.0]
        self.pump_flow_estimates = [None, None, None]

        self.temp_raw_1 = deque(maxlen=80)
        self.temp_raw_2 = deque(maxlen=80)
        self.temp_good_1 = deque(maxlen=80)
        self.temp_good_2 = deque(maxlen=80)
        self.tret_history = deque(maxlen=80)
        self.temp_diff_reference = None
        self.temp_reference_count = 0
        self.temp_suspect = None
        self.temp_suspect_count = 0
        self.temp_bad = None
        self.temp_bad_clear = 0
        self.last_temperature = None
        self.temperature_rate = 0.0

        self.valve_integral = None

    def _slope(self, history):
        """Robust temperature slope over a 10 second window, in K/s."""
        values = list(history)
        if len(values) < 40:
            return None
        recent = _median(values[-20:])
        older = _median(values[-40:-20])
        return (recent - older) / 10.0

    def _mad(self, history):
        values = list(history)
        if len(values) < 10:
            return 0.0
        middle = _median(values[-20:])
        return _median([abs(value - middle) for value in values[-20:]])

    def _temperature(self, observation):
        raw1 = float(observation['T_sup1'])
        raw2 = float(observation['T_sup2'])
        tret = float(observation['T_ret'])
        valid1 = -5.0 <= raw1 <= 105.0
        valid2 = -5.0 <= raw2 <= 105.0

        self.temp_raw_1.append(raw1)
        self.temp_raw_2.append(raw2)
        self.tret_history.append(tret)
        if valid1:
            self.temp_good_1.append(raw1)
        if valid2:
            self.temp_good_2.append(raw2)

        f1 = _median(list(self.temp_good_1)[-5:]) if self.temp_good_1 else None
        f2 = _median(list(self.temp_good_2)[-5:]) if self.temp_good_2 else None
        s1 = self._slope(self.temp_good_1)
        s2 = self._slope(self.temp_good_2)
        sr = self._slope(self.tret_history)

        # A failed channel can be open circuit, frozen, or much noisier than
        # its peer.  The latter two checks use several seconds of evidence so
        # normal transmitter noise does not switch channels.
        frozen1 = False
        frozen2 = False
        if len(self.temp_raw_1) >= 12 and valid1:
            tail = list(self.temp_raw_1)[-12:]
            frozen1 = max(tail) - min(tail) < 1e-5
        if len(self.temp_raw_2) >= 12 and valid2:
            tail = list(self.temp_raw_2)[-12:]
            frozen2 = max(tail) - min(tail) < 1e-5

        movement1 = (max(list(self.temp_good_1)[-24:]) - min(list(self.temp_good_1)[-24:])
                     if len(self.temp_good_1) >= 12 else 0.0)
        movement2 = (max(list(self.temp_good_2)[-24:]) - min(list(self.temp_good_2)[-24:])
                     if len(self.temp_good_2) >= 12 else 0.0)
        if frozen1 and (movement2 > 0.12 or abs(tret - list(self.tret_history)[-12]) > 0.2):
            valid1 = False
        if frozen2 and (movement1 > 0.12 or abs(tret - list(self.tret_history)[-12]) > 0.2):
            valid2 = False

        mad1 = self._mad(self.temp_good_1)
        mad2 = self._mad(self.temp_good_2)
        if mad1 > 0.45 and mad2 < 0.22:
            valid1 = False
        if mad2 > 0.45 and mad1 < 0.22:
            valid2 = False

        # Establish the normal offset between the two wells during steady
        # operation.  A slow fault drift then appears as a persistent change
        # in that offset.  Return temperature provides a third trend reference
        # to tell which supply channel is moving abnormally.
        if valid1 and valid2 and f1 is not None and f2 is not None:
            difference = f1 - f2
            if (self.temp_diff_reference is None and s1 is not None and s2 is not None
                    and abs(s1) < 0.02 and abs(s2) < 0.02
                    and abs(s1 - s2) < 0.004):
                self.temp_reference_count += 1
                if self.temp_reference_count >= 20:
                    self.temp_diff_reference = difference

            candidate = None
            if (self.temp_diff_reference is not None and s1 is not None and s2 is not None
                    and sr is not None and abs(difference - self.temp_diff_reference) > 0.60
                    and abs(s1 - s2) > 0.005
                    # Do not mistake the faster first thermowell for a fault
                    # during a real load step.  A transmitter drift remains
                    # visible after the shared fluid temperature settles.
                    and max(abs(s1), abs(s2), abs(sr)) < 0.04):
                score1 = abs(s1 - sr)
                score2 = abs(s2 - sr)
                if score1 > score2 + 0.002:
                    candidate = 1
                elif score2 > score1 + 0.002:
                    candidate = 2

            if candidate is not None:
                if self.temp_suspect == candidate:
                    self.temp_suspect_count += 1
                else:
                    self.temp_suspect = candidate
                    self.temp_suspect_count = 1
                if self.temp_suspect_count >= 8 and self.temp_bad is None:
                    self.temp_bad = candidate
                    self.temp_bad_clear = 0
            else:
                self.temp_suspect = None
                self.temp_suspect_count = 0

            if self.temp_bad is not None:
                baseline_ok = abs(difference - self.temp_diff_reference) < 0.28
                if baseline_ok and abs(s1 - s2) < 0.004:
                    self.temp_bad_clear += 1
                    if self.temp_bad_clear >= 60:
                        self.temp_bad = None
                        self.temp_bad_clear = 0
                else:
                    self.temp_bad_clear = 0

        if self.temp_bad == 1:
            temperature = f2 if valid2 else f1
        elif self.temp_bad == 2:
            temperature = f1 if valid1 else f2
        elif valid1 and valid2:
            temperature = 0.5 * (f1 + f2)
        elif valid1:
            temperature = f1
        elif valid2:
            temperature = f2
        else:
            # The two supply RTDs are not expected to fail together.  Return
            # temperature still gives a conservative fallback for hot-water
            # control if that occurs.
            temperature = min(54.0, max(0.0, tret - 6.0))

        if self.last_temperature is None:
            rate = 0.0
        else:
            instant_rate = (temperature - self.last_temperature) / 0.5
            self.temperature_rate = 0.65 * self.temperature_rate + 0.35 * instant_rate
            rate = self.temperature_rate
        self.last_temperature = temperature
        return temperature, rate

    def _balance_pumps(self, observation, faults):
        """Nudge unequal parallel pumps toward a more even hydraulic share.

        The VFD kW registers are useful here: a pump with normal shaft speed
        but very low absorbed power is contributing little flow.  The estimate
        is intentionally used only as a slow trim; header pressure remains the
        primary capacity and safety signal.
        """
        flows = []
        active_indices = []
        for index, name in enumerate('ABC'):
            speed = max(0.0, min(100.0, float(observation['spd' + name]))) / 100.0
            power = max(0.0, float(observation['kW' + name]))
            if faults[index] or speed < 0.55 or power < 0.2:
                self.pump_flow_estimates[index] = None
                flows.append(None)
                continue
            # Nominal input power includes motor/VFD losses.  Reverse-solving
            # the published affinity-scaled power curve gives a useful
            # relative, rather than metrology-grade, per-pump flow estimate.
            shaft_power = power * 0.93
            estimate = speed * (shaft_power / (speed ** 3) - 4.5) / 0.044
            estimate = _clip(estimate, 0.0, 500.0)
            previous = self.pump_flow_estimates[index]
            if previous is None:
                filtered = estimate
            else:
                filtered = 0.25 * estimate + 0.75 * previous
            self.pump_flow_estimates[index] = filtered
            flows.append(filtered)
            active_indices.append(index)

        if len(active_indices) != 3 or self.scan < 40:
            return self.pump_offsets

        average = sum(flows[index] for index in active_indices) / 3.0
        if average < 25.0:
            return self.pump_offsets
        threshold = max(40.0, 0.25 * average)
        for index in active_indices:
            deviation = average - flows[index]
            if deviation > threshold:
                # Only lift a clearly under-sharing unit.  Efficiency spread
                # also changes kW, so a modest apparent excess is not used to
                # throttle another pump.
                self.pump_offsets[index] += _clip(0.005 * deviation, 0.0, 0.4)
            else:
                self.pump_offsets[index] = max(0.0, self.pump_offsets[index] - 0.01)

        for index in active_indices:
            self.pump_offsets[index] = _clip(self.pump_offsets[index], 0.0, 8.0)
        return self.pump_offsets

    def step(self, observation):
        self.scan += 1

        # The pressure taps remain useful even when either dP transmitter is
        # failed.  A median of the three independent readings rejects one bad
        # dP channel without relying on fault-specific schedules.
        ps = float(observation['P_sup'])
        pr = float(observation['P_ret'])
        dp_candidates = [ps - pr]
        for key in ('dP1', 'dP2'):
            value = float(observation[key])
            if 0.0 <= value <= 150.0:
                dp_candidates.append(value)
        dp_now = _median(dp_candidates)
        if self.dp_filtered is None:
            self.dp_filtered = dp_now
        else:
            # Pressure transmitters are quiet, but the hydraulic model has a
            # short settling oscillation after every VFD update.  A two second
            # filter keeps the speed loop from chasing that oscillation.
            self.dp_filtered = 0.20 * dp_now + 0.80 * self.dp_filtered
        faults = [float(observation[f'fault{name}']) > 0.5 for name in 'ABC']
        any_fault = any(faults)

        # Hold the highest useful speed reserve during normal operation.  A
        # single drive loss then leaves two pumps close to their full-flow
        # point.  Pressure feedback trims speed as rack branches are isolated.
        emergency = self.dp_filtered > 92.0 or ps > 112.0
        if any_fault:
            desired_speed = 100.0
        else:
            # The proportional trim deliberately has low gain.  The pump
            # curve is steep enough that a small speed change moves header
            # pressure several psi; slower output movement avoids a limit
            # cycle around the differential-pressure target.
            dp_target = 84.0
            desired_speed = 100.0 - 0.80 * max(0.0, self.dp_filtered - dp_target)

        # Independent pressure guards operate even when a drive is offline.
        desired_speed = min(desired_speed,
                            100.0 - 0.75 * max(0.0, self.dp_filtered - 89.0),
                            100.0 - 0.70 * max(0.0, ps - 109.0))
        desired_speed = _clip(desired_speed, 25.0, 100.0)

        if any_fault:
            self.pump_command = 100.0
        elif emergency:
            # A quick drop is safe because the drive itself still enforces
            # its 10 %/s ramp.  It prevents a pressure pulse during row
            # isolation or a VFD restart.
            self.pump_command = min(self.pump_command, desired_speed)
        else:
            # Follow normal trims at a bounded rate so small sensor noise and
            # pressure ripple cannot make the drives hunt.
            change = _clip(desired_speed - self.pump_command, -0.75, 0.75)
            self.pump_command += change
        pump_speed = _clip(self.pump_command, 25.0, 100.0)
        if any_fault:
            self.pump_offsets = [0.0, 0.0, 0.0]
            self.pump_flow_estimates = [None, None, None]
            individual_speeds = [pump_speed, pump_speed, pump_speed]
        else:
            offsets = self._balance_pumps(observation, faults)
            individual_speeds = [
                _clip(pump_speed + offsets[index], 25.0, 100.0)
                for index in range(3)
            ]

        temperature, temperature_rate = self._temperature(observation)
        dew = float(observation['dew'])
        tfs = float(observation['T_fs'])
        target = _clip(dew + 5.0, 15.0, 50.0)
        error = temperature - target
        predicted_error = error + 16.0 * temperature_rate

        valve_pos = _clip(float(observation['valve_pos']), 0.0, 100.0)
        if self.valve_integral is None:
            self.valve_integral = valve_pos
        kp = 5.0
        ki = 0.025
        raw_valve = self.valve_integral + kp * predicted_error
        valve_command = _clip(raw_valve, 0.0, 100.0)

        # Back-calculation prevents integral windup when the 90 second valve
        # stroke reaches either end stop.
        saturated_error = valve_command - raw_valve
        self.valve_integral += ki * error * 0.5 + saturated_error * (0.5 / 18.0)
        self.valve_integral = _clip(self.valve_integral, -100.0, 200.0)

        # When facility water is below the condensation-safe temperature,
        # close the valve before the slow actuator can carry the supply below
        # its lower safety margin.  Re-open once load pushes the supply warm.
        cold_facility = tfs < dew + 2.0
        if cold_facility and temperature < dew + 6.0:
            valve_command = 0.0
            self.valve_integral = 0.0
        elif temperature >= 52.0:
            valve_command = 100.0
            self.valve_integral = min(100.0, self.valve_integral)

        valve_command = _clip(valve_command, 0.0, 100.0)

        return {
            'pumpA_cmd': float(individual_speeds[0]),
            'pumpB_cmd': float(individual_speeds[1]),
            'pumpC_cmd': float(individual_speeds[2]),
            'valve_cmd': float(valve_command),
        }
