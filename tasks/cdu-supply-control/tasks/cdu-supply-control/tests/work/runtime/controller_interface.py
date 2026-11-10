"""Four-actuator supply-control contract with 23 equipment observations."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

SCAN_S = 0.5
OBSERVATIONS = (
    'T_sup1', 'T_sup2', 'T_ret', 'P_sup', 'P_ret', 'dP1', 'dP2', 'F_sec',
    'T_fs', 'T_fr', 'P_fs', 'P_fr', 'valve_pos', 'spdA', 'spdB', 'spdC',
    'kWA', 'kWB', 'kWC', 'faultA', 'faultB', 'faultC', 'dew',
)
OUTPUTS = (
    'pumpA_cmd', 'pumpB_cmd', 'pumpC_cmd', 'valve_cmd',
)


def validate_ports(value: object, names: tuple[str, ...]) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError('exact declared controller ports are required')
    result = {}
    for name in names:
        item = value[name]
        if not isinstance(item, (int, float)) or not math.isfinite(item):
            raise ValueError(f'{name} must be a finite scalar')
        result[name] = float(item)
    # Retain native plant actuator saturation and physical actuator interpretation.
    # Do not introduce Python-only clipping or grading before native validation.
    return result


def validate_observation(value):
    return validate_ports(value, OBSERVATIONS)


def validate_commands(value):
    return validate_ports(value, OUTPUTS)


def load_controller(path):
    path = Path(path)
    spec = importlib.util.spec_from_file_location('candidate_controller', path)
    if spec is None or spec.loader is None:
        raise ValueError('controller must be an importable Python file')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    instance = module.Controller()
    if not callable(instance.reset) or not callable(instance.step):
        raise TypeError('controller must implement reset and step')
    return instance
