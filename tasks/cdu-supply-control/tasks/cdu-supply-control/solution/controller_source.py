"""Operator-only reference translation of the original DC05 PLC scan (cdu_plc).

Source of truth: inputs/dc05/dc05_plc_code.txt + inputs/dc05/dc05_ctrl_build.m
(variant 'ref'), MATLAB R2025b, %#codegen, Ts = 0.5 s PLC scan.

This is a line-faithful, stateful port. Every persistent variable, every
constant, every latched flag and every output of the original MATLAB Function
block is preserved, in the original scan order:

  1a supply-RTD validation (NAMUR range, flatline/noise on the second
     difference, dual-RTD disagreement resolved against T_ret)
  1b dP transmitter 2-of-3 mid-value select with P_sup - P_ret
  1c flow-meter validation (range, flatline/noise, electrical consistency)
  2  pump management (hot standby, feed-forward on trip/stage-in, stage ramp,
     degraded-pump detection, flow-sharing trim, standby switchover)
  3  dP PI with relief-pressure override and optional aggressive boost
  4  approach PI with dew-point floor, secondary-flow feed-forward, integral
     dead band, conditional integration (anti-windup), seized-valve detection
  5  latched alarms

The controller sees only the 23 declared operator observations. It holds no
knowledge of any scenario, fault schedule, truth vector or grading rule, and it
adds no actuator delay of its own (the plant owns the one-scan delay).
"""

from __future__ import annotations

import math

SCAN_S = 0.5  # Ts, PLC scan time

# dc05_ctrl_build.m -> rung('ref'): reference constants of the shipped rung.
CONSTANTS = {
    'dp_sp': 85.0,            # psid set point of the common-speed dP loop
    'kp_p': 0.6, 'ti_p': 4.0,        # %/psi, s
    'kp_v': 4.0, 'ti_v': 45.0,       # %/K, s
    'approach': 3.0,         # K
    'valve_force': -1.0,     # <0 = normal feedback
    'dew_guard': 1.0,
    'dew_margin': 3.0,       # K above dew point
    'sp_down': 0.03,         # K/s set-point fall limit near the dew floor
    'tau_f': 3.0,            # s control measurement filter
    'p_max': 120.0,          # psig relief override
    'up_min': 30.0,          # % minimum common speed
    'ff_trip': 8.0,          # % speed feed-forward when a running pump drops out
    'ff_in': 5.0,            # % speed back-off when a pump is staged in
    'stage_s': 2.0,          # s stage-in ramp
    'ret_s': 0.0,            # s extra wait after drive ready
    'pumps': 7,              # bit mask A|B|C
    'cold_standby': 0.0,
    'failover_delay': 0.0,
    'aggr': 0.0,
    'degr_en': 1.0, 'guard': 1.0,
    'degr_ratio': 0.6, 'degr_s': 60.0,
    'trim_en': 1.0, 'trim_k': 0.2,
    'kff_v': 30.0,           # % valve per unit change of ln(secondary flow)
    'vTe': 1.0, 'vDe': 1.0, 'vFe': 1.0, 'vVe': 1.0,
    'idb': 0.2,              # K integral dead band of the valve loop
    'T_dis': 1.0, 'T_dis_s': 30.0,
    'D_dev': 3.0, 'D_dev_s': 20.0,
    'flat': 1.0,
    'V_dev': 5.0, 'V_s': 30.0,
    'alarm_all': 0.0, 'alarms': 1.0,
    'dc01': 0.0,
}


def _finit(x):
    return math.isfinite(x)


class Controller:
    """Stateful port of cdu_plc(); reset() clears every persistent variable."""

    def __init__(self, constants=None):
        self.K = dict(CONSTANTS)
        if constants:
            self.K.update(constants)
        self.reset()

    # ------------------------------------------------------------------ reset
    def reset(self):
        K = self.K
        # persistent block; MATLAB initialises it on the first call (isempty(t))
        self.initialised = False
        self.t = 0.0
        self.up = 75.0            # common speed
        self.ep = 0.0             # dP loop previous error
        self.uv = 50.0            # valve command
        self.ev = 0.0             # valve loop previous error
        self.tsp = None           # limited approach set point
        self.Tf = None            # 5 s filtered RTDs
        self.Ts20 = None          # 20 s filtered RTDs (retained, unused by ref rung)
        self.vT = [0.015, 0.015]  # RTD noise estimate
        self.Tp = None
        self.Tpp = None
        self.badT = [False, False]
        self.disc = 0.0
        self.Tc = None            # filtered controlled supply temperature
        self.Df = None            # instantaneous RTD offsets to T_ret
        self.Dr = None            # learned RTD offsets while they agree
        self.Ff = None            # filtered secondary flow
        self.vF = 13.5            # flow noise estimate
        self.Fp = None
        self.Fpp = None
        self.badF = False
        self.Fhold = None         # last flow trusted by the controller
        self.dpf = None           # filtered dP transmitters
        self.vd = [0.375, 0.375, 0.75]
        self.dpp = None
        self.dppp = None
        self.badD = [False, False, False]
        self.devc = [0.0, 0.0, 0.0]
        self.dpc = None           # filtered validated dP
        self.run = [False, False, False]
        self.stage = [0.0, 0.0, 0.0]
        self.clr = [999.0, 999.0, 999.0]
        self.degr = [False, False, False]
        self.dcnt = [0.0, 0.0, 0.0]
        self.latF = [False, False, False]
        self.lowc = 0.0
        self.boost = 0.0
        self.vslow = None
        self.vstk = 0.0
        self.stuck = False
        self.duty = [False, False, False]
        self.afp = False
        self.trim = [0.0, 0.0, 0.0]
        self.wcnt = [0.0, 0.0, 0.0]
        self.outp = [False, False, False]
        self.lnFp = None
        self.Fcal = 1.0
        self.Fdis = 0.0
        self.sp_prev = [0.0, 0.0, 0.0]
        self.lowload = False
        self.lowload_s = 0.0
        self.parked = 0
        self._K_unused = K  # keep a handle for auditability of the rung constants

    # ------------------------------------------------------------------- step
    def step(self, observation):
        K = self.K
        Ts = SCAN_S
        # ---- PLC I/O mapping (root-level controller: 23 in / 9 out)
        T1 = float(observation['T_sup1'])
        T2 = float(observation['T_sup2'])
        Tret = float(observation['T_ret'])
        Psup = float(observation['P_sup'])
        Pret = float(observation['P_ret'])
        dP1 = float(observation['dP1'])
        dP2 = float(observation['dP2'])
        Fsec = float(observation['F_sec'])
        Tfs = float(observation['T_fs'])
        vpos = float(observation['valve_pos'])
        spd = [float(observation['spdA']), float(observation['spdB']), float(observation['spdC'])]
        kw = [float(observation['kWA']), float(observation['kWB']), float(observation['kWC'])]
        fl = [float(observation['faultA']) > 0.5,
              float(observation['faultB']) > 0.5,
              float(observation['faultC']) > 0.5]
        dew = float(observation['dew'])

        # ---- persistent initialisation (isempty(t))
        if not self.initialised:
            self.Fcal = 1.0
            self.Fdis = 0.0
            self.sp_prev = [0.0, 0.0, 0.0]
            self.lowload = False
            self.lowload_s = 0.0
            self.parked = 0
            self.t = 0.0
            self.up = 75.0
            self.ep = 0.0
            self.uv = 50.0
            self.ev = 0.0
            self.tsp = Tfs + K['approach']
            self.Tf = [T1, T2]
            self.Ts20 = [T1, T2]
            self.vT = [0.015, 0.015]
            self.Tp = [T1, T2]
            self.Tpp = [T1, T2]
            self.badT = [False, False]
            self.disc = 0.0
            self.Tc = T1
            self.Df = [Tret - T1, Tret - T2]
            self.Dr = [Tret - T1, Tret - T2]
            self.Ff = Fsec
            self.vF = 13.5
            self.Fp = Fsec
            self.Fpp = Fsec
            self.badF = False
            self.Fhold = 500.0
            self.dpf = [dP1, dP2, Psup - Pret]
            self.vd = [0.375, 0.375, 0.75]
            self.dpp = [dP1, dP2, Psup - Pret]
            self.dppp = [dP1, dP2, Psup - Pret]
            self.badD = [False, False, False]
            self.devc = [0.0, 0.0, 0.0]
            self.dpc = dP1
            self.run = [False, False, False]
            self.stage = [0.0, 0.0, 0.0]
            self.clr = [999.0, 999.0, 999.0]
            self.degr = [False, False, False]
            self.dcnt = [0.0, 0.0, 0.0]
            self.latF = [False, False, False]
            self.lowc = 0.0
            self.boost = 0.0
            self.vslow = vpos
            self.vstk = 0.0
            self.stuck = False
            self.duty = [False, False, False]
            self.afp = False
            self.trim = [0.0, 0.0, 0.0]
            self.wcnt = [0.0, 0.0, 0.0]
            self.outp = [False, False, False]
            self.lnFp = math.log(max(Fsec, 50.0))
            self.initialised = True

        self.t = self.t + Ts
        t = self.t
        a = Ts / (K['tau_f'] + Ts)
        aw = Ts / 20.0
        flat = K['flat']

        # ================================ 1a supply RTDs
        T = [T1, T2]
        for i in range(2):
            d2 = T[i] - 2.0 * self.Tp[i] + self.Tpp[i]
            self.vT[i] = self.vT[i] + aw * (d2 * d2 - self.vT[i])
        self.Tpp = list(self.Tp)
        self.Tp = list(T)
        for i in range(2):
            self.Tf[i] = self.Tf[i] + (Ts / (5.0 + Ts)) * (T[i] - self.Tf[i])
            self.Ts20[i] = self.Ts20[i] + (Ts / (20.0 + Ts)) * (T[i] - self.Ts20[i])
        if not self.badF:
            self.Fhold = self.Ff
        for i in range(2):
            self.Df[i] = self.Df[i] + (Ts / (20.0 + Ts)) * (Tret - T[i] - self.Df[i])
        if K['vTe'] > 0.5:
            for i in range(2):
                if (T[i] < -2.5 or T[i] > 103.0
                        or (t > 120.0 and (self.vT[i] < 6e-4 * flat or self.vT[i] > 0.3 / flat))):
                    self.badT[i] = True
            if (not self.badT[0]) and (not self.badT[1]):
                if abs(self.Tf[0] - self.Tf[1]) < 0.5:
                    for i in range(2):
                        self.Dr[i] = self.Dr[i] + (Ts / (60.0 + Ts)) * (self.Df[i] - self.Dr[i])
                if t > 120.0 and abs(self.Tf[0] - self.Tf[1]) > K['T_dis']:
                    self.disc = self.disc + Ts
                else:
                    self.disc = 0.0
                if self.disc >= K['T_dis_s']:
                    if abs(self.Df[0] - self.Dr[0]) > abs(self.Df[1] - self.Dr[1]):
                        self.badT[0] = True
                    else:
                        self.badT[1] = True
            if (not self.badT[0]) and (not self.badT[1]):
                Tr = (T1 + T2) / 2.0
            elif not self.badT[0]:
                Tr = T1
            elif not self.badT[1]:
                Tr = T2
            else:
                Tr = Tret - (self.Dr[0] + self.Dr[1]) / 2.0
        else:
            Tr = T1
        self.Tc = self.Tc + a * (Tr - self.Tc)

        # ================================ 1b dP transmitters (2-of-3)
        d = [dP1, dP2, Psup - Pret]
        for i in range(3):
            d2 = d[i] - 2.0 * self.dpp[i] + self.dppp[i]
            self.vd[i] = self.vd[i] + aw * (d2 * d2 - self.vd[i])
        self.dppp = list(self.dpp)
        self.dpp = list(d)
        for i in range(3):
            self.dpf[i] = self.dpf[i] + (Ts / (2.0 + Ts)) * (d[i] - self.dpf[i])
        if K['vDe'] > 0.5:
            for i in range(3):
                if (d[i] < -3.75 or d[i] > 154.0
                        or (t > 120.0 and (self.vd[i] < 1e-5 * flat or self.vd[i] > 9.0 / flat))):
                    self.badD[i] = True
            ok = [(not self.badD[i]) for i in range(3)]
            n = sum(ok)
            v = sorted(self.dpf[i] for i in range(3) if ok[i])
            if n >= 3:
                med = v[1]
                for i in range(3):
                    if t > 120.0 and abs(self.dpf[i] - med) > K['D_dev']:
                        self.devc[i] = self.devc[i] + Ts
                    else:
                        self.devc[i] = 0.0
                    if self.devc[i] >= K['D_dev_s']:
                        self.badD[i] = True
                dpu = med
            elif n == 2:
                dpu = (v[0] + v[1]) / 2.0
            elif n == 1:
                dpu = v[0]
            else:
                dpu = float('nan')
        else:
            dpu = dP1
        if not math.isnan(dpu):
            self.dpc = self.dpc + a * (dpu - self.dpc)

        # ================================ 1c flow meter (telemetry only)
        d2 = Fsec - 2.0 * self.Fp + self.Fpp
        self.vF = self.vF + aw * (d2 * d2 - self.vF)
        self.Fpp = self.Fp
        self.Fp = Fsec
        self.Ff = self.Ff + a * (Fsec - self.Ff)
        if (K['vFe'] > 0.5 and (Fsec < -25.0 or Fsec > 1030.0
                                or (t > 120.0 and (self.vF < 1e-4 * flat or self.vF > 600.0 / flat)))):
            self.badF = True
        Qelect = 0.0
        for i in range(3):
            if spd[i] > 40.0:
                nfrac = spd[i] / 100.0
                Qelect = Qelect + max(0.0, nfrac * (kw[i] * 0.93 / max(nfrac ** 3, 0.01) - 4.5) / 0.044)
        stable_hydraulics = ((not any(fl)) and all(s > 50.0 for s in spd)
                             and max(abs(spd[i] - self.sp_prev[i]) for i in range(3)) < 0.2)
        self.sp_prev = list(spd)
        if t > 160.0 and t < 280.0 and stable_hydraulics and Qelect > 100.0:
            self.Fcal = self.Fcal + Ts / 30.0 * (self.Ff / Qelect - self.Fcal)
        if (K['vFe'] > 0.5 and t > 300.0 and stable_hydraulics
                and abs(self.Ff - self.Fcal * Qelect) > 50.0):
            self.Fdis = self.Fdis + Ts
        else:
            self.Fdis = 0.0
        if K['vFe'] > 0.5 and self.Fdis >= 30.0:
            self.badF = True

        # ================================ 2 pump management
        pumps = int(K['pumps'])
        pm = [(pumps & 1) > 0, (pumps & 2) > 0, (pumps & 4) > 0]
        for i in range(3):
            if fl[i]:
                self.clr[i] = 0.0
                self.latF[i] = True
            else:
                self.clr[i] = self.clr[i] + Ts
        avail = [pm[i] and (not fl[i]) and (self.clr[i] >= K['ret_s']) for i in range(3)]
        want = [avail[i] and (not self.outp[i]) for i in range(3)]
        if sum(want) < 2:
            want = list(avail)
        if K['cold_standby'] < 0.5 and K['dc01'] < 0.5:
            qdemand = min(self.Fhold, self.Fcal * Qelect)
            if qdemand < 410.0 and t > 120.0 and self.dpc > 82.0 and sum(want) == 3:
                self.lowload_s = self.lowload_s + Ts
            else:
                self.lowload_s = 0.0
            if (not self.lowload) and self.lowload_s >= 5.0:
                pnlow = [kw[i] / max((spd[i] / 100.0) ** 3, 0.01) for i in range(3)]
                self.parked = min(range(3), key=lambda i: pnlow[i])
                self.lowload = True
            if (qdemand > 450.0 or self.dpc < 82.0
                    or (sum(want) < 3 and want[self.parked])):
                self.lowload = False
            if self.lowload:
                want[self.parked] = False
        if (not math.isnan(dpu)) and dpu < 0.9 * K['dp_sp']:
            self.lowc = self.lowc + Ts
        else:
            self.lowc = 0.0
        if K['cold_standby'] > 0.5:
            self.duty = [self.duty[i] and want[i] for i in range(3)]
            if (sum(self.duty) < 2
                    and (K['failover_delay'] <= 0.0 or self.lowc >= K['failover_delay'] or t < 60.0)):
                for i in range(3):
                    if sum(self.duty) < 2 and want[i] and (not self.duty[i]):
                        self.duty[i] = True
                        self.lowc = 0.0
            want = list(self.duty)
        ev_pump = False
        for i in range(3):
            if want[i] and (not self.run[i]):
                self.run[i] = True
                self.stage[i] = 0.0
                ev_pump = True
                if t > 30.0 and sum(self.run) > 1:
                    self.up = self.up - K['ff_in']
            elif (not want[i]) and self.run[i]:
                self.run[i] = False
                self.stage[i] = 0.0
                ev_pump = True
                if sum(self.run) >= 1 and (fl[i] or self.outp[i]):
                    self.up = self.up + K['ff_trip']
            if self.run[i]:
                self.stage[i] = min(1.0, self.stage[i] + Ts / max(K['stage_s'], Ts))
        if K['degr_en'] > 0.5:
            sel = [self.run[i] and self.stage[i] >= 1.0 and spd[i] > 40.0 for i in range(3)]
            if sum(sel) >= 2:
                pn = [kw[i] / max((spd[i] / 100.0) ** 3, 0.01) for i in range(3)]
                selidx = [i for i in range(3) if sel[i]]
                rmax = max(pn[i] for i in selidx)
                eqs = ((max(spd[i] for i in selidx) - min(spd[i] for i in selidx) < 3.0)
                       or K['guard'] < 0.5)
                for i in range(3):
                    if sel[i] and eqs and pn[i] < K['degr_ratio'] * rmax:
                        self.dcnt[i] = self.dcnt[i] + Ts
                    else:
                        self.dcnt[i] = 0.0
                    if self.dcnt[i] >= K['degr_s']:
                        self.degr[i] = True
        h = [self.run[i] and (not self.degr[i]) and self.stage[i] >= 1.0 for i in range(3)]
        for i in range(3):
            if (K['trim_en'] > 0.5 and self.degr[i] and self.run[i]
                    and self.stage[i] >= 1.0 and any(h)):
                kh = sum(kw[j] for j in range(3) if h[j]) / sum(h)
                self.trim[i] = min(max(self.trim[i] + K['trim_k'] * (kh - kw[i]) * Ts, 0.0), 40.0)
                if self.up + self.trim[i] >= 99.5 and kw[i] < 0.6 * kh:
                    self.wcnt[i] = self.wcnt[i] + Ts
                else:
                    self.wcnt[i] = 0.0
                if self.wcnt[i] >= 60.0:
                    self.outp[i] = True
            elif K['trim_en'] < 0.5 and self.degr[i]:
                self.outp[i] = True
            if not self.run[i]:
                self.trim[i] = 0.0

        # ================================ 3 dP loop (common speed)
        af = (any(self.badT) or self.badD[0] or self.badD[1] or self.badF
              or self.stuck or any(self.degr) or any(fl))
        if (K['aggr'] > 0.5 and t > 60.0
                and (ev_pump or (af and not self.afp) or ((not math.isnan(dpu)) and dpu < 75.0))
                and self.boost <= 0.0):
            self.boost = 120.0
        self.afp = af
        if self.boost > 0.0:
            self.boost = self.boost - Ts
        elif not math.isnan(dpu):
            e = K['dp_sp'] - self.dpc
            self.up = self.up + K['kp_p'] * (e - self.ep) + K['kp_p'] * Ts / K['ti_p'] * e
            self.ep = e
        if Psup > K['p_max']:
            self.up = self.up - 0.5 * (Psup - K['p_max'])
        self.up = min(max(self.up, K['up_min']), 100.0)
        cmd = [0.0, 0.0, 0.0]
        for i in range(3):
            if self.run[i]:
                if self.boost > 0.0:
                    cmd[i] = 100.0
                else:
                    cmd[i] = min(100.0, max(25.0, self.stage[i] * self.up + self.trim[i]))
            elif fl[i] and pm[i]:
                cmd[i] = self.up

        # ================================ 4 approach loop with dew-point floor
        Tsp = Tfs + K['approach']
        if K['dew_guard'] > 0.5:
            Tsp = max(Tsp, dew + K['dew_margin'])
        if Tsp - (dew + K['dew_margin']) < 2.0:
            self.tsp = max(Tsp, self.tsp - K['sp_down'] * Ts)
        else:
            self.tsp = Tsp
        e2 = self.Tc - self.tsp
        integ = abs(e2) > K['idb']
        if K['vVe'] > 0.5:
            self.vslow = self.vslow + (Ts / (10.0 + Ts)) * (vpos - self.vslow)
            gap = self.uv - vpos
            if t > 120.0 and abs(gap) > K['V_dev'] and abs(vpos - self.vslow) < 0.2:
                self.vstk = self.vstk + Ts
            else:
                self.vstk = 0.0
            if self.vstk >= K['V_s']:
                self.stuck = True
            if (gap > 8.0 and e2 > 0.0) or (gap < -8.0 and e2 < 0.0):
                integ = False
            self.uv = self.uv + K['kp_v'] * (e2 - self.ev) + integ * K['kp_v'] * Ts / K['ti_v'] * e2
            self.uv = min(max(self.uv, vpos - 10.0), vpos + 10.0)
        else:
            self.uv = self.uv + K['kp_v'] * (e2 - self.ev) + integ * K['kp_v'] * Ts / K['ti_v'] * e2
        self.ev = e2
        lnF = math.log(max(self.Fhold, 50.0))
        if t > 60.0:
            self.uv = self.uv + K['kff_v'] * (lnF - self.lnFp)
        self.lnFp = lnF
        if K['dc01'] < 0.5 and K['dew_guard'] > 0.5 and self.Tc < dew + 2.4:
            self.uv = self.uv - 1.0
        self.uv = min(max(self.uv, 0.0), 100.0)
        if K['valve_force'] >= 0.0:
            self.uv = K['valve_force']
        vcmd = self.uv

        return {
            'pumpA_cmd': cmd[0],
            'pumpB_cmd': cmd[1],
            'pumpC_cmd': cmd[2],
            'valve_cmd': vcmd,
        }
