"""Six supply-control acceptance items on the unchanged one-second truth log."""
from __future__ import annotations

import numpy as np
from scipy.interpolate import interp1d

MANDATORY = ('rack_flow', 'dew_point', 'hot_supply', 'overpressure', 'dp_surge', 'starve_s')


def consecutive(mask):
    """Length of the current run at each sample, reset by a false sample."""
    result = np.zeros(len(mask), dtype=int)
    count = 0
    for index, value in enumerate(mask):
        count = count + 1 if value else 0
        result[index] = count
    return result


def evaluate(log, scenario, grade_start=300.0):
    """Compute only the six stated items; completion is also checked by the runner."""
    data = {key: np.asarray(value, dtype=float) for key, value in log.items()}
    t_all = data['t']
    if t_all.ndim != 1 or len(t_all) < 2 or not np.allclose(np.diff(t_all), 1, rtol=0, atol=1e-8):
        raise ValueError('native metrics require a complete 1-second log')
    if any(value.shape != t_all.shape or not np.isfinite(value).all() for value in data.values()):
        raise ValueError('invalid or nonfinite truth log')
    assessed = t_all >= grade_start
    t = t_all[assessed]
    if len(t) < 2:
        raise ValueError('missing assessment window')
    x = {name: value[assessed] for name, value in data.items()}
    groups = np.column_stack([x[f'F_g{i}'] for i in range(1, 5)]) / 125.
    iso = np.asarray(scenario['iso'], dtype=float)
    service = interp1d(iso[:, 0], iso[:, 1:], axis=0, fill_value='extrapolate')(t) >= .999
    if not np.any(service):
        raise ValueError('no in-service rack evidence')
    deficit = np.maximum(0, .90-groups)/.90
    deficit[~service] = 0
    low = (groups < .5) & service
    supply, dew, dp, pressure = x['T_sup'], x['dew'], x['dP'], x['P_sup']
    metrics = {
        'rack_flow': float(np.max(np.sum(deficit, axis=0))),
        'dew_point': float(np.maximum(0, dew+2-supply).sum()),
        'hot_supply': float(np.maximum(0, supply-55).sum()),
        'overpressure': float(np.maximum(0, pressure-120).sum()),
        'dp_surge': float(np.maximum(0, dp-95).sum()),
        'starve_s': float(max(np.max(consecutive(low[:, group])) for group in range(4))),
    }
    durations = {
        'rack_flow': float(np.max(np.sum((groups < .9) & service, axis=0))),
        'dew_point': float(np.sum(supply < dew+2)),
        'hot_supply': float(np.sum(supply > 55)),
        'overpressure': float(np.sum(pressure > 120)),
        'dp_surge': float(np.sum(dp > 95)),
        'starve_s': metrics['starve_s'],
    }
    obligations = {
        name: {'value': metrics[name], 'threshold': 30. if name == 'starve_s' else 0.,
               'comparator': '<' if name == 'starve_s' else '<=',
               'passed': bool(metrics[name] < 30. if name == 'starve_s' else metrics[name] <= 0.),
               'violation_duration_s': durations[name]}
        for name in MANDATORY
    }
    obligations['rack_flow']['duration_basis'] = 'largest violating sample count among in-service groups'
    obligations['starve_s']['duration_basis'] = 'longest consecutive low-flow run among in-service groups'
    return {'metrics': metrics, 'obligations': obligations,
            'passed': all(item['passed'] for item in obligations.values())}
