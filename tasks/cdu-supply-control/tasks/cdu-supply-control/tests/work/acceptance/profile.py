"""Versioned acceptance selection over the complete native metric library."""
from __future__ import annotations

import hashlib
import json
import math
import operator
from pathlib import Path

SEMANTICS_VERSION = 'native_1s_after300_supply_six_v1'
COMPARATORS = {'<=': operator.le, '<': operator.lt, '>=': operator.ge,
               '>': operator.gt, '==': operator.eq}


def load_profile(path, verify_source=True):
    path = Path(path)
    profile = json.loads(path.read_text())
    if profile['metric_semantics'] != SEMANTICS_VERSION:
        raise ValueError('unsupported metric semantics version')
    if verify_source:
        actual = hashlib.sha256(Path(__file__).with_name('native_metrics.py').read_bytes()).hexdigest()
        lock = json.loads(path.with_name('metric-implementation.json').read_text())
        if lock['semantics_version'] != SEMANTICS_VERSION or lock['metrics_source_sha256'] != actual:
            raise ValueError('metric implementation differs from frozen profile')
    obligations = profile['obligations']
    for item in obligations:
        item.setdefault('id', item['metric'])
    ids = [item['id'] for item in obligations]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('profile requires unique selected obligations')
    for item in obligations:
        if item['comparator'] not in COMPARATORS or not math.isfinite(item['threshold']):
            raise ValueError('invalid selected threshold')
    if 'cases' in profile and (not profile['cases'] or len(profile['cases']) != len(set(profile['cases']))):
        raise ValueError('profile requires a nonempty unique case set')
    return profile


def evaluate_profile(metrics, profile):
    """Only selected obligations gate reward; unselected metrics stay diagnostic."""
    checks = {}
    for item in profile['obligations']:
        value = metrics[item['metric']]
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('selected metric lacks finite physical evidence: '+item['metric'])
        checks[item['id']] = {**item, 'value': value,
                              'passed': bool(COMPARATORS[item['comparator']](value, item['threshold']))}
    return {'passed': all(check['passed'] for check in checks.values()), 'obligations': checks}
