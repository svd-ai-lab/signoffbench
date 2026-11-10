"""Four-output CDU supply controller.

The secondary pumps are controlled from the measured flange differential
pressure.  The two differential transmitters are checked against the supply
and return pressure measurements, so an open or implausible dP channel does
not remove pressure feedback.  All available pumps share the same speed
request; a drive which reports offline is commanded off and is brought back
into service as soon as its offline indication clears.

The primary valve uses a temperature PI loop with return-temperature and
facility-water feed-forward.  The minimum supply target includes the highest
qualified room dew point, which provides protection when room humidity rises
faster than the slow water-side temperature loop can respond.
"""

from __future__ import annotations

import math
import statistics


def _clip(value, lower, upper):
    return lower if value < lower else upper if value > upper else value


def _number(observation, key, fallback=0.0):
    try:
        value = float(observation[key])
    except (KeyError, TypeError, ValueError, OverflowError):
        return fallback
    return value if math.isfinite(value) else fallback


def _percentage(value):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(value):
        return 0.0
    return float(_clip(value, 0.0, 100.0))


class Controller:
    """CDU controller with no external dependencies or case-specific state."""

    def reset(self):
        """Clear all controller memory; safe to call repeatedly before a run."""
        # The soft-start request is below the normal running point.  It is
        # moved by the pressure loop in small increments, while the VFDs add
        # their own specified 10 %/s speed ramp.
        self._pump_speed = 40.0
        self._pump_underload = [0.0, 0.0, 0.0]

        self._temp_filtered = [None, None]
        self._temp_histories = [[], []]
        self._temp_bad_hold = [0.0, 0.0]
        self._temp_estimate = None
        self._temp_rate = 0.0
        self._ret_previous = None
        self._facility_previous = None
        self._valve_position_previous = None

        self._valve_integral = None

    def _estimate_supply_temperature(self, observation, target):
        """Fuse the redundant supply RTDs and reject obvious single-channel faults."""
        raw = [_number(observation, "T_sup1", 106.0),
               _number(observation, "T_sup2", 106.0)]
        facility = _clip(_number(observation, "T_fs", 20.0), -20.0, 60.0)
        ret = _clip(_number(observation, "T_ret", 30.0), -20.0, 100.0)
        valve_pos = _clip(_number(observation, "valve_pos", 0.0), 0.0, 100.0)

        valid = [0 <= value < 105.0 for value in raw]
        filtered_now = [None, None]
        for index, value in enumerate(raw):
            if valid[index]:
                old = self._temp_filtered[index]
                filtered_now[index] = value if old is None else old + 0.55 * (value - old)
                self._temp_filtered[index] = filtered_now[index]
                history = self._temp_histories[index]
                history.append(value)
                if len(history) > 24:
                    del history[0]
                self._temp_bad_hold[index] = max(0.0, self._temp_bad_hold[index] - 0.5)
            else:
                # An RTD transmitter open circuit is upscale.  The other well
                # remains available during the burst.
                self._temp_bad_hold[index] = max(self._temp_bad_hold[index], 2.0)
                self._temp_histories[index] = []

        if valid[0] and valid[1]:
            # A stuck or electrically noisy channel is recognizable when its
            # peer responds to a real process change.  Healthy RTD noise is
            # much smaller than the thresholds below.
            for index, other in ((0, 1), (1, 0)):
                history = self._temp_histories[index]
                peer = self._temp_histories[other]
                if len(history) >= 12 and len(peer) >= 12:
                    own_span = max(history) - min(history)
                    peer_span = max(peer) - min(peer)
                    if own_span < 0.06 and peer_span > 0.65:
                        self._temp_bad_hold[index] = max(self._temp_bad_hold[index], 8.0)

                    own_step = sum(abs(history[i] - history[i - 1])
                                   for i in range(1, len(history))) / (len(history) - 1)
                    peer_step = sum(abs(peer[i] - peer[i - 1])
                                    for i in range(1, len(peer))) / (len(peer) - 1)
                    if own_step > 0.42 and peer_step < 0.20:
                        self._temp_bad_hold[index] = max(self._temp_bad_hold[index], 8.0)

        # Process bounds help identify a slowly drifting channel.  A real
        # secondary supply should not be materially colder than facility
        # supply or hotter than return water.
        physically_plausible = [True, True]
        for index in range(2):
            if not valid[index]:
                physically_plausible[index] = False
                continue
            value = filtered_now[index]
            if value < facility - 1.5 or value > ret + 5.0:
                physically_plausible[index] = False

        usable = [valid[i] and self._temp_bad_hold[i] <= 0.0
                  for i in range(2)]
        # Prefer the physically plausible peer when only one channel is
        # plausible.  This also handles an upscale open-circuit indication.
        if valid[0] and valid[1] and physically_plausible[0] != physically_plausible[1]:
            usable[0] = physically_plausible[0]
            usable[1] = physically_plausible[1]

        candidates = [i for i in range(2) if usable[i]]
        if not candidates:
            candidates = [i for i in range(2) if valid[i] and physically_plausible[i]]
        if not candidates:
            candidates = [i for i in range(2) if valid[i]]

        if not candidates:
            estimate = self._temp_estimate
            if estimate is None:
                estimate = max(target, facility + 1.0)
        elif len(candidates) == 1:
            estimate = filtered_now[candidates[0]]
        else:
            first, second = filtered_now
            disagreement = abs(first - second)
            if disagreement <= 1.25:
                estimate = 0.5 * (first + second)
            else:
                # Predict the next supply state from the independent return,
                # facility-water and valve-position changes.  When a drifting
                # RTD separates from its peer, this favors the channel that
                # still follows the process and the prior controlled state.
                if self._temp_estimate is None:
                    predicted = target
                else:
                    predicted = self._temp_estimate
                    if self._ret_previous is not None:
                        predicted += 0.35 * _clip(ret - self._ret_previous, -3.0, 3.0)
                    if self._facility_previous is not None:
                        predicted += 0.15 * _clip(facility - self._facility_previous, -3.0, 3.0)
                    if self._valve_position_previous is not None:
                        predicted -= 0.04 * _clip(
                            valve_pos - self._valve_position_previous, -10.0, 10.0)
                    predicted += 0.25 * self._temp_rate

                score_first = abs(first - predicted)
                score_second = abs(second - predicted)
                if abs(score_first - score_second) > 0.45:
                    estimate = first if score_first < score_second else second
                else:
                    # With no clear dynamic winner, use the channel nearest
                    # the controlled operating band.  If return water is hot
                    # while the valve is nearly closed, the warmer peer is
                    # more credible: a negatively drifting RTD would otherwise
                    # hide a real supply-temperature rise.
                    if ret > target + 10.0 and valve_pos < 45.0:
                        estimate = max(first, second)
                    else:
                        estimate = first if abs(first - target) <= abs(second - target) else second

        if self._temp_estimate is None:
            self._temp_rate = 0.0
        else:
            measured_rate = _clip((estimate - self._temp_estimate) / 0.5, -0.45, 0.45)
            self._temp_rate = _clip(0.65 * self._temp_rate + 0.35 * measured_rate,
                                    -0.30, 0.30)

        self._temp_estimate = estimate
        self._ret_previous = ret
        self._facility_previous = facility
        self._valve_position_previous = valve_pos

        # Predict a little ahead of the slower thermowell to account for
        # water-side and actuator lag.  A falling supply is treated
        # conservatively for the dew-point guard.
        predicted_supply = estimate + 2.0 * self._temp_rate
        predicted_supply = _clip(predicted_supply, estimate - 2.0, estimate + 2.0)

        return estimate, predicted_supply

    @staticmethod
    def _estimate_differential_pressure(observation):
        """Median-vote dP transmitters against Psup - Pret."""
        p_sup = _clip(_number(observation, "P_sup", 0.0), -100.0, 250.0)
        p_ret = _clip(_number(observation, "P_ret", 0.0), -100.0, 250.0)
        pressure_difference = p_sup - p_ret
        candidates = []
        if 0.0 <= pressure_difference <= 150.0:
            candidates.append(pressure_difference)

        for key in ("dP1", "dP2"):
            value = _number(observation, key, -3.75)
            if not 0.0 <= value <= 150.0:
                continue
            # A channel far from the independently measured pressure
            # difference is likely open, noisy, frozen or drifting.
            if 0.0 <= pressure_difference <= 150.0 and abs(value - pressure_difference) > 8.0:
                continue
            candidates.append(value)

        if candidates:
            differential = float(statistics.median(candidates))
        else:
            # With all differential readings unusable, retain a bounded
            # pressure estimate instead of allowing a malformed command.
            differential = _clip(pressure_difference, 0.0, 150.0)
        return differential, p_sup, p_ret

    def _pump_commands(self, observation):
        dp, p_sup, p_ret = self._estimate_differential_pressure(observation)
        faults = [
            _number(observation, "faultA", 0.0) > 0.5,
            _number(observation, "faultB", 0.0) > 0.5,
            _number(observation, "faultC", 0.0) > 0.5,
        ]
        available = sum(not fault for fault in faults)

        # The normal differential target is below the nominal full-row design
        # point.  This leaves pressure headroom for service isolation while
        # still providing more than 90 % of each rack's design flow.  If a
        # valid flow reading is low while the speed request is already near
        # its limit, allow a small additional pressure request for degraded
        # equipment.
        dp_target = 80.0
        flow = _number(observation, "F_sec", -150.0)
        flow_valid = 0.0 <= flow <= 1000.0
        if flow_valid and flow < 440.0 and self._pump_speed >= 97.0:
            dp_target = min(82.0, dp_target + min(2.0, (440.0 - flow) * 0.01))

        # Protect absolute supply pressure as well as differential pressure.
        # The four-psi allowance covers normal pressure measurement error and
        # the buffered command/ramp response.
        if p_ret > 0.0:
            dp_target = min(dp_target, max(50.0, 116.0 - p_ret))

        if available:
            error = dp_target - dp
            # This is an incremental pressure controller: its output is a
            # speed request, and each scan adds only a small correction.  The
            # plant's 10 %/s VFD ramp remains the final actuator limit.
            change = _clip(0.25 * error, -4.0, 4.0)

            # Unfiltered pressure overrides limit the response time to a
            # sudden rack closure or high absolute header pressure.
            if dp > 90.0:
                change = min(change, -1.5 - 0.35 * (dp - 90.0))
            if dp > 93.0:
                change = min(change, -3.0)
            if dp > 94.0:
                change = -4.0
            if p_sup > 116.0:
                change = min(change, -2.0 - 0.6 * (p_sup - 116.0))
            if p_sup > 118.0:
                change = -4.0

            self._pump_speed = _clip(self._pump_speed + change, 20.0, 100.0)
            speed = self._pump_speed
        else:
            # A three-drive outage is outside the qualified operating envelope,
            # but all outputs remain finite and the pumps stay safely off.
            speed = 0.0

        # A flat pump curve can leave a weaker parallel pump near shut-off.
        # Estimate relative loading from the three drive power readings and
        # give a persistently underloaded, healthy pump a modest speed bias.
        # The common pressure loop backs the whole set down if that bias adds
        # too much head.
        pump_speeds = [
            _clip(_number(observation, "spdA", 0.0), 0.0, 100.0),
            _clip(_number(observation, "spdB", 0.0), 0.0, 100.0),
            _clip(_number(observation, "spdC", 0.0), 0.0, 100.0),
        ]
        powers = [
            max(0.0, _number(observation, "kWA", 0.0)),
            max(0.0, _number(observation, "kWB", 0.0)),
            max(0.0, _number(observation, "kWC", 0.0)),
        ]
        estimated_flows = [None, None, None]
        running = []
        for index in range(3):
            if faults[index]:
                self._pump_underload[index] = 0.0
                continue
            fraction = pump_speeds[index] / 100.0
            if fraction < 0.55:
                self._pump_underload[index] = 0.0
                continue
            baseline_power = 4.5 * fraction ** 3
            flow_estimate = max(
                0.0,
                (powers[index] - baseline_power) / (0.044 * fraction ** 2),
            )
            estimated_flows[index] = flow_estimate
            running.append(index)

        boosts = [0.0, 0.0, 0.0]
        if len(running) >= 2 and speed >= 60.0:
            reference_load = float(statistics.median(
                estimated_flows[index] for index in running
                if estimated_flows[index] is not None
            ))
            if reference_load > 45.0:
                for index in running:
                    own_load = estimated_flows[index]
                    if own_load is not None and own_load < 0.55 * reference_load:
                        self._pump_underload[index] += 0.5
                        if self._pump_underload[index] >= 3.0:
                            ratio = own_load / reference_load
                            boosts[index] = 12.0 * _clip((0.65 - ratio) / 0.65, 0.0, 1.0)
                    else:
                        self._pump_underload[index] = max(
                            0.0, self._pump_underload[index] - 0.5)

        return {
            "pumpA_cmd": 0.0 if faults[0] else min(100.0, speed + boosts[0]),
            "pumpB_cmd": 0.0 if faults[1] else min(100.0, speed + boosts[1]),
            "pumpC_cmd": 0.0 if faults[2] else min(100.0, speed + boosts[2]),
        }

    def _valve_command(self, observation):
        t_fs = _clip(_number(observation, "T_fs", 20.0), -20.0, 60.0)
        t_ret = _clip(_number(observation, "T_ret", 30.0), -20.0, 100.0)
        dew = _clip(_number(observation, "dew", 12.0), -10.0, 50.0)
        position = _clip(_number(observation, "valve_pos", 0.0), 0.0, 100.0)

        # The envelope permits dew points as high as 21 C.  Keeping a 26 C
        # floor avoids a condensation excursion after a fast humidity change;
        # facility water above that point raises the target by a small HX
        # approach allowance.
        target = max(26.0, dew + 5.0, t_fs + 3.0)
        _, predicted = self._estimate_supply_temperature(observation, target)

        error = predicted - target
        # Feed-forward opens the primary valve before return temperature has
        # heated the supply.  The facility term reduces the required opening
        # in cold water and adds opening in warm water.
        load_feedforward = 6.0 * max(0.0, t_ret - target - 5.0)
        facility_feedforward = 1.5 * (t_fs - 23.0)
        feedforward = load_feedforward + facility_feedforward

        kp = 6.0
        ki = 0.12
        if self._valve_integral is None:
            self._valve_integral = position - kp * error - feedforward

        unconstrained = self._valve_integral + kp * error + feedforward
        # Anti-windup when the actuator reaches either end of its stroke.
        if not ((unconstrained >= 100.0 and error > 0.0) or
                (unconstrained <= 0.0 and error < 0.0)):
            self._valve_integral = _clip(
                self._valve_integral + ki * error * 0.5, -100.0, 140.0)

        command = self._valve_integral + kp * error + feedforward

        # A useful kick across the qualified packing deadband prevents a
        # small, persistent temperature error from leaving a stiction valve
        # parked at its old position.
        if abs(error) > 0.8 and abs(command - position) < 5.5:
            command = position + (6.0 if error > 0.0 else -6.0)

        # Separate fast guard for cold supply.  It closes farther than the
        # packing deadband as the measured supply approaches dew + 2 K.
        cold_margin = predicted - (dew + 4.5)
        if cold_margin < 0.0:
            command = min(command, position - 5.5 - 2.0 * (-cold_margin))
            self._valve_integral = min(
                self._valve_integral,
                command - kp * error - feedforward)
        if predicted < dew + 3.0:
            command = min(command, position - 15.0)
            self._valve_integral = min(
                self._valve_integral,
                command - kp * error - feedforward)

        # Hot-supply recovery is the other end of the operating window.  The
        # normal PI term already opens strongly here; explicit thresholds also
        # help when the valve has been stuck and then releases.
        if predicted > 50.0:
            command = max(command, 90.0)
        if predicted > 53.0:
            command = 100.0

        command = _clip(command, 0.0, 100.0)
        return command

    def step(self, observation):
        """Return the four finite actuator percentages for one 0.5 s scan."""
        if not isinstance(observation, dict):
            observation = {}

        pumps = self._pump_commands(observation)
        valve = self._valve_command(observation)

        return {
            "pumpA_cmd": _percentage(pumps["pumpA_cmd"]),
            "pumpB_cmd": _percentage(pumps["pumpB_cmd"]),
            "pumpC_cmd": _percentage(pumps["pumpC_cmd"]),
            "valve_cmd": _percentage(valve),
        }
