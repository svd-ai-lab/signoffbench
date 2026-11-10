"""Run a public commissioning case and report its engineering obligations."""
import argparse
import hashlib
import json
import time
from pathlib import Path

from acceptance.native_metrics import evaluate
from acceptance.profile import evaluate_profile, load_profile
from runtime.run_fmu import run_fmu


def main():
    root = Path(__file__).resolve().parent
    cases = json.loads((root/'public-cases.json').read_text())['cases']
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, choices=[case['name'] for case in cases])
    parser.add_argument('--controller', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    asset = root/'plant'/args.case
    interface = json.loads((asset/'full-interface.json').read_text())
    started = time.time()
    result = run_fmu(args.controller.resolve(), asset/'plant.fmu', duration_s=interface['scenario']['tend'])
    diagnostics = evaluate(result['native_log'], interface['scenario'])
    selected = evaluate_profile(diagnostics['metrics'], load_profile(root/'public-acceptance.json'))
    result['selected_acceptance'] = selected
    result['acceptance'] = diagnostics
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, allow_nan=False))
    event = {'case': args.case, 'started_unix': started, 'finished_unix': time.time(),
             'passed': selected['passed'],
             'controller_sha256': hashlib.sha256(args.controller.read_bytes()).hexdigest()}
    with (root/'.case-events.jsonl').open('a') as stream:
        stream.write(json.dumps(event)+'\n')
    print(json.dumps({'selected_acceptance': selected, 'failed_obligations': {key: value for key, value in selected['obligations'].items() if not value['passed']}}, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
