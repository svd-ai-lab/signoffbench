"""Four-actuator CDU controller for the 0.5 second plant interface."""

from __future__ import annotations

import math
from collections import deque


class Controller:
    """Coordinate the parallel secondary pumps and primary cooling valve."""

    SCAN_S = 0.5

    def reset(self):
        self._tick = 0

        # Temperature and return histories support rejection of a single bad
        # RTD without relying on its identity.
        self._t_smooth = [None, None]
        self._t_history = [deque(maxlen=121), deque(maxlen=121)]
        self._ret_smooth = None
        self._ret_history = deque(maxlen=121)
        self._last_temperature = None
        self._drifted_temperature_sensor = None

        # Valve PI state is initialized from position feedback for bumpless
        # transfer after the initial cooling ramp.
        self._valve_integral = None

        # Keep a cold start or an all-pumps restart from ramping all three
        # drives to the pressure ceiling before the feedback loop settles.
        self._pump_restart_until = 0.0

    @staticmethod
    def _value(observation, name, default=0.0):
        try:
            result = float(observation[name])
        except (KeyError, TypeError, ValueError, OverflowError):
            return float(default)
        if not math.isfinite(result):
            return float(default)
        return result

    @staticmethod
    def _clamp(value, low, high):
        return max(low, min(high, value))

    @staticmethod
    def _slope(history, now, window=30.0):
        points = [item for item in history if now - item[0] <= window]
        if len(points) < 24:
            return None
        mean_t = sum(item[0] for item in points) / len(points)
        mean_v = sum(item[2] for item in points) / len(points)
        denominator = sum((item[0] - mean_t) ** 2 for item in points)
        if denominator <= 1e-9:
            return None
        return sum((item[0] - mean_t) * (item[2] - mean_v) for item in points) / denominator

    @staticmethod
    def _residual_std(history, now, window=12.0):
        values = [item[1] - item[2] for item in history if now - item[0] <= window]
        if len(values) < 8:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        return math.sqrt(max(0.0, variance))

    @staticmethod
    def _frozen(history, now, window=12.0):
        values = [item[1] for item in history if now - item[0] <= window]
        return len(values) >= 18 and max(values) - min(values) <= 1e-8

    def _record_temperature(self, index, now, value):
        if not (-10.0 <= value <= 105.0):
            return False
        old = self._t_smooth[index]
        smooth = value if old is None else old + 0.28 * (value - old)
        self._t_smooth[index] = smooth
        self._t_history[index].append((now, value, smooth))
        return True

    def _temperature(self, observation, now):
        raw = [self._value(observation, "T_sup1", 106.0),
               self._value(observation, "T_sup2", 106.0)]
        valid = [self._record_temperature(i, now, raw[i]) for i in range(2)]

        t_ret = self._value(observation, "T_ret", 25.0)
        if self._ret_smooth is None:
            self._ret_smooth = t_ret
        else:
            self._ret_smooth += 0.25 * (t_ret - self._ret_smooth)
        self._ret_history.append((now, t_ret, self._ret_smooth))

        tf = self._value(observation, "T_fs", 20.0)
        for i in range(2):
            if valid[i] and raw[i] < tf - 2.0:
                # The secondary supply cannot be materially colder than the
                # facility water entering the exchanger.
                valid[i] = False

        if valid[0] and not valid[1]:
            estimate = self._t_smooth[0]
        elif valid[1] and not valid[0]:
            estimate = self._t_smooth[1]
        elif valid[0] and valid[1]:
            smooth1, smooth2 = self._t_smooth
            h1, h2 = self._t_history
            # Once a slow drift has been identified, keep using the other
            # well through later load and facility changes. Those real
            # transients can temporarily make both well slopes look alike.
            choose = (1 - self._drifted_temperature_sensor
                      if self._drifted_temperature_sensor is not None else None)

            frozen1 = self._frozen(h1, now)
            frozen2 = self._frozen(h2, now)
            if frozen1 and not frozen2:
                choose = 1
            elif frozen2 and not frozen1:
                choose = 0

            noise1 = self._residual_std(h1, now)
            noise2 = self._residual_std(h2, now)
            if choose is None:
                if noise1 > 0.22 and noise1 > max(0.10, 2.5 * noise2):
                    choose = 1
                elif noise2 > 0.22 and noise2 > max(0.10, 2.5 * noise1):
                    choose = 0

            slope1 = self._slope(h1, now)
            slope2 = self._slope(h2, now)
            slope_ret = self._slope(self._ret_history, now)
            separation = abs(smooth1 - smooth2)
            if (choose is None and slope1 is not None and slope2 is not None
                    and slope_ret is not None and separation > 0.18
                    and abs(slope1 - slope2) > 0.0025):
                # Healthy wells follow the same slow process trend. A drifting
                # or frozen channel develops a sustained slope disagreement;
                # return temperature provides a process reference for load
                # changes that move both supply wells together.
                expected = 0.22 * slope_ret
                cost1 = abs(slope1 - expected)
                cost2 = abs(slope2 - expected)
                if abs(slope_ret) < 0.0025:
                    choose = 0 if abs(slope1) < abs(slope2) else 1
                elif cost1 < 0.62 * cost2:
                    choose = 0
                elif cost2 < 0.62 * cost1:
                    choose = 1
                if choose is not None and now >= 60.0:
                    self._drifted_temperature_sensor = 1 - choose

            if choose is None and separation > 1.4:
                # As a final check, discard a channel that violates the broad
                # thermal envelope. If both remain plausible, the mean limits
                # the effect of an unresolved single-channel offset.
                low = min(tf, t_ret) - 2.0
                high = max(t_ret, tf) + 10.0
                plausible1 = low <= raw[0] <= high
                plausible2 = low <= raw[1] <= high
                if plausible1 and not plausible2:
                    choose = 0
                elif plausible2 and not plausible1:
                    choose = 1

            estimate = self._t_smooth[choose] if choose is not None else (smooth1 + smooth2) * 0.5
        else:
            # Both RTDs can be invalid during a short burst. Hold the last
            # trusted value, with return temperature as a finite cold-start
            # fallback.
            if self._last_temperature is not None:
                estimate = self._last_temperature
            else:
                estimate = t_ret

        if estimate is None or not math.isfinite(estimate):
            estimate = t_ret
        self._last_temperature = estimate
        return estimate, raw, valid

    @staticmethod
    def _differential_pressure(observation):
        candidates = []
        for name in ("dP1", "dP2"):
            value = Controller._value(observation, name, -10.0)
            if 0.0 <= value <= 150.0:
                candidates.append(value)
        p_sup = Controller._value(observation, "P_sup", 15.0)
        p_ret = Controller._value(observation, "P_ret", 15.0)
        pressure_difference = p_sup - p_ret
        if -1.0 <= pressure_difference <= 150.0:
            candidates.append(max(0.0, pressure_difference))
        if not candidates:
            return 0.0
        candidates.sort()
        middle = len(candidates) // 2
        if len(candidates) % 2:
            return candidates[middle]
        return 0.5 * (candidates[middle - 1] + candidates[middle])

    def _pumps(self, observation, now, differential_pressure):
        names = ("A", "B", "C")
        speeds = [self._value(observation, "spd" + name, 0.0) for name in names]
        faults = [self._value(observation, "fault" + name, 0.0) for name in names]
        healthy = [fault < 0.5 for fault in faults]
        count = sum(healthy)

        if count == 0:
            return {"pumpA_cmd": 0.0, "pumpB_cmd": 0.0, "pumpC_cmd": 0.0}

        base = 95.0 if count == 3 else 100.0
        target_dp = 86.0
        command = base + 0.40 * (target_dp - differential_pressure)

        active_speeds = [speeds[i] for i in range(3) if healthy[i]]
        if active_speeds and max(active_speeds) < 20.0 and differential_pressure < 25.0:
            self._pump_restart_until = max(self._pump_restart_until, now + 12.0)
        if now < self._pump_restart_until:
            command = min(command, base)

        # Leave margin for the 0.5 s command delay and the VFD acceleration
        # limit if a pump rejoins or the measured head briefly rises.
        if differential_pressure > 89.0:
            pressure_cap = base - 1.2 * (differential_pressure - 89.0)
            command = min(command, pressure_cap)
        p_sup = self._value(observation, "P_sup", 15.0)
        if p_sup > 115.0:
            command = min(command, base - 1.2 * (p_sup - 115.0))
        command = self._clamp(command, 20.0, 100.0)

        return {
            "pumpA_cmd": command if healthy[0] else 0.0,
            "pumpB_cmd": command if healthy[1] else 0.0,
            "pumpC_cmd": command if healthy[2] else 0.0,
        }

    def step(self, observation):
        now = self._tick * self.SCAN_S
        self._tick += 1

        temperature, _, _ = self._temperature(observation, now)
        differential_pressure = self._differential_pressure(observation)
        commands = self._pumps(observation, now, differential_pressure)

        dew = self._value(observation, "dew", 15.0)
        # Keep a practical margin beyond the acceptance boundary to cover RTD
        # calibration, process lag and valve stick-slip.
        target_temperature = dew + 6.0
        error = temperature - target_temperature
        position = self._clamp(self._value(observation, "valve_pos", 50.0), 0.0, 100.0)

        if now < 45.0:
            valve_command = 100.0
            self._valve_integral = None
        else:
            kp = 5.0
            ki = 0.04
            if self._valve_integral is None:
                self._valve_integral = position - kp * error

            proposed_integral = self._valve_integral + ki * error * self.SCAN_S
            unconstrained = proposed_integral + kp * error
            if (0.0 < unconstrained < 100.0
                    or (unconstrained >= 100.0 and error < 0.0)
                    or (unconstrained <= 0.0 and error > 0.0)):
                self._valve_integral = proposed_integral

            valve_command = self._clamp(self._valve_integral + kp * error, 0.0, 100.0)

        if temperature >= 52.0:
            valve_command = 100.0

        commands["valve_cmd"] = self._clamp(valve_command, 0.0, 100.0)
        return commands
