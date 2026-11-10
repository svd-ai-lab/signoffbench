#!/usr/bin/env python3
"""Independent full-interface verifier, with an unprivileged submission and protected trusted files."""
from __future__ import annotations

import concurrent.futures
import contextlib
import csv
import hashlib
import json
import multiprocessing
import os
import random
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, '/tests/work')
import runtime.run_fmu as runner
from acceptance.native_metrics import evaluate
from acceptance.profile import evaluate_profile, load_profile
from runtime.controller_interface import validate_commands, validate_observation
from runtime.subprocess_controller import SubprocessController

CASE_PUBLIC = Path('/public')
CASE_UID = 65534


class IsolatedController(SubprocessController):
    """Same-filesystem isolation: uid/gid 65534, no groups, no_new_privs; chroot removed."""

    def __init__(self, controller_path):
        self.controller_path = Path(controller_path).resolve()
        for path in ('/tests', '/logs/verifier'):  # Harbor may widen mounts; re-seal before every spawn.
            os.chmod(path, 0o700)
        target = CASE_PUBLIC / 'controller.py'
        shutil.copyfile(self.controller_path, target)
        os.chmod(target, 0o444)
        import ctypes
        prctl = ctypes.CDLL(None, use_errno=True).prctl

        def isolate():
            if prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS: setuid/cap files cannot grant privilege.
                raise OSError(ctypes.get_errno(), 'PR_SET_NO_NEW_PRIVS failed')
            os.chdir(CASE_PUBLIC)  # Mirror old jail-root cwd; -I omits script dir from sys.path.
            os.setgroups([])
            os.setgid(CASE_UID)
            os.setuid(CASE_UID)
            os.umask(0o077)

        # Unlinked, root-created output files cannot be held open as pipes by a
        # detached descendant. pread keeps the reader independent of child offsets.
        self._capture = contextlib.ExitStack()
        self._offset = 0
        self._pending = b''
        self._deadline = time.monotonic() + 900  # Same ceiling as the outer verifier.
        try:
            self._stdout = self._capture.enter_context(tempfile.TemporaryFile(dir='/logs/verifier'))  # noqa: SIM115 - ExitStack owns controller lifetime
            self._stderr = self._capture.enter_context(tempfile.TemporaryFile(dir='/logs/verifier'))  # noqa: SIM115 - ExitStack owns controller lifetime
            self.process = subprocess.Popen(
                ['/usr/local/bin/python', '-I', '/public/controller_process.py', '--controller', str(target)],
                stdin=subprocess.PIPE, stdout=self._stdout, stderr=self._stderr,
                bufsize=0, start_new_session=True, preexec_fn=isolate,  # noqa: PLW1509 - single-threaded per-case worker
                env={'PATH': '/usr/local/bin:/usr/bin:/bin'},
            )
            os.set_blocking(self.process.stdin.fileno(), False)
        except BaseException:
            self._capture.close()
            raise

    def _remaining(self):
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('controller protocol exceeded verifier time budget')
        return remaining

    def _request(self, request):
        data = memoryview((json.dumps(request, separators=(',', ':')) + '\n').encode())
        while data:
            self._remaining()
            if self.process.poll() is not None:
                raise RuntimeError('controller exited before reading request')
            try:
                written = os.write(self.process.stdin.fileno(), data)
                data = data[written:]
            except BlockingIOError:
                select.select([], [self.process.stdin], [], min(self._remaining(), 0.05))

    def _response(self):
        while b'\n' not in self._pending:
            self._remaining()
            chunk = os.pread(self._stdout.fileno(), 65536, self._offset)
            if chunk:
                self._offset += len(chunk)
                self._pending += chunk
                if len(self._pending) > 1048576:
                    raise ValueError('controller protocol line exceeds 1 MiB')
            elif self.process.poll() is not None:
                size = os.fstat(self._stderr.fileno()).st_size
                tail = os.pread(self._stderr.fileno(), 65536, max(0, size - 65536))
                raise RuntimeError('controller process exited: ' + tail.decode(errors='replace'))
            else:
                time.sleep(min(self._remaining(), 0.0005))
        line, self._pending = self._pending.split(b'\n', 1)
        response = json.loads(line)
        if not isinstance(response, dict):
            raise TypeError('controller response is not an object')
        return response

    def reset(self):
        self._request({'type': 'reset'})
        response = self._response()
        if response != {'type': 'reset', 'ok': True}:
            raise RuntimeError(f'controller reset failed: {response}')

    def step(self, observation):
        validate_observation(observation)
        self._request({'type': 'step', 'observation': observation})
        response = self._response()
        if response.get('type') != 'commands':
            raise RuntimeError(f'controller step failed: {response}')
        return validate_commands(response.get('commands'))

    def close(self):
        """Reap the controller and descendants, including a detached child.

        Each case has a unique random UID in this verifier container. Reward
        permissions remain the scoring boundary; cleanup prevents descendants
        from retaining protocol pipes or leaking into subsequent cases.
        """
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cleanup_case_uids({CASE_UID})
        try:
            self.process.wait(timeout=2)
        finally:
            self.process.stdin.close()
            self._capture.close()


def cleanup_case_uids(uids):
    """Kill only candidate UIDs allocated by this root-owned verifier run."""
    if not all(type(uid) is int and 100000 <= uid < 2**31 for uid in uids):
        raise RuntimeError('refusing cleanup outside the per-case UID range')
    for _ in range(3):
        found = False
        for proc in Path('/proc').iterdir():
            if not proc.name.isdecimal():
                continue
            try:
                uid_line = next(line for line in (proc / 'status').read_text().splitlines()
                                if line.startswith('Uid:'))
                if int(uid_line.split()[1]) not in uids:
                    continue
                os.kill(int(proc.name), signal.SIGKILL)
                found = True
            except (FileNotFoundError, ProcessLookupError, StopIteration):
                continue
        if not found:
            break


def assessment_cases():
    manifest = json.loads(Path('/tests/cases.json').read_text())
    contract = load_profile('/tests/acceptance-profile.json')
    cases = manifest['cases']
    names = [case['name'] for case in cases]
    if len(names) != len(set(names)) or set(names) != set(contract['cases']):
        raise ValueError('complete frozen selected case set is required')
    return cases


def run_one_case(uid, case, candidate, profile):
    """Each native case owns a process, controller instance, UID and public cwd."""
    global CASE_PUBLIC, CASE_UID
    CASE_UID = uid
    CASE_PUBLIC = Path('/public/cases') / uuid.uuid4().hex
    CASE_PUBLIC.mkdir(parents=True, exist_ok=True)
    os.chmod(CASE_PUBLIC, 0o755)
    runner.SubprocessController = IsolatedController
    output = Path('/logs/verifier')
    try:
        name = case['name']
        case_started = time.time()
        plant = Path('/tests/assets') / name
        interface = json.loads((plant/'full-interface.json').read_text())
        scenario = interface['scenario']
        document = runner.run_fmu(candidate, plant/'plant.fmu', duration_s=scenario['tend'])
        native = document['native_log']
        if native['t'][0] != 0 or native['t'][-1] != scenario['tend']:
            raise ValueError('incomplete native trajectory')
        report = evaluate(native, scenario)
        report['selected_acceptance'] = evaluate_profile(report['metrics'], profile)
        report['passed'] = report['selected_acceptance']['passed']
        report['execution'] = {'valid': True, 'native_fmu': True,
                               'elapsed_s': time.time()-case_started}
        document['verifier_run_id'] = os.environ.get('DC05_VERIFIER_RUN_ID')
        document['acceptance'] = report
        # Keep the original strict serialization check, including non-finite
        # values outside the selected metrics, without retaining its large JSON.
        for _ in json.JSONEncoder(allow_nan=False).iterencode(document):
            pass
        document['timeseries_summary'] = {
            'retained': False,
            'trace_records': len(document['trace']),
            'native_samples': len(native['t']),
            'start_s': native['t'][0],
            'end_s': native['t'][-1],
        }
        del document['trace'], document['native_log']
        (output/(name+'.json')).write_text(json.dumps(document, allow_nan=False))
        return name, report
    except Exception as exc:  # noqa: BLE001 - report native/controller failures per case
        failure = {'passed': False, 'execution': {'valid': False},
                   'error': {'type': type(exc).__name__, 'message': str(exc)}}
        (output / (case['name'] + '.execution-error.json')).write_text(json.dumps(
            {'verifier_run_id': os.environ.get('DC05_VERIFIER_RUN_ID'), 'report': failure}))
        return case['name'], failure


def worker_main():
    output = Path('/logs/verifier')
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    os.chmod('/tests', 0o700)
    candidate = Path('/app/submission/controller.py')
    started = time.time()
    result = {'schema_version': 1, 'scope': 'supply-six-all31',
              'started_unix': started, 'cases': {}, 'reward': 0, 'candidate_sha256': None}
    runner.SubprocessController = IsolatedController
    profile_path = Path('/tests/acceptance-profile.json')
    try:
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError('submission/controller.py must be a regular file')
        result['candidate_sha256'] = hashlib.sha256(candidate.read_bytes()).hexdigest()
        profile = load_profile(profile_path)
        result['profile_sha256'] = hashlib.sha256(profile_path.read_bytes()).hexdigest()
        result['profile_version'] = profile['version']
        workers = int(os.environ.get('DC05_VERIFIER_WORKERS', '4'))
        if workers not in (1, 2, 4):
            raise ValueError('trusted worker configuration must be 1, 2 or 4')
        cases = assessment_cases()
        result['workers'] = workers
        # Neither UID nor cwd encodes a private case name or its manifest index.
        case_uids = random.SystemRandom().sample(range(100000, 2**31 - 1), len(cases))
        # The root supervisor needs these UIDs if a timeout kills a worker
        # before its controller.close() can run. Candidates cannot write here.
        uid_record = output / 'candidate-process-uids.json'
        uid_temp = output / 'candidate-process-uids.tmp'
        uid_temp.write_text(json.dumps({
            'verifier_run_id': os.environ.get('DC05_VERIFIER_RUN_ID'),
            'uids': case_uids,
        }))
        uid_temp.replace(uid_record)
        with concurrent.futures.ProcessPoolExecutor(
                max_workers=workers, mp_context=multiprocessing.get_context('spawn')) as executor:
            futures = [executor.submit(run_one_case, uid, case, candidate, profile)
                       for uid, case in zip(case_uids, cases, strict=True)]
            # Consume in frozen manifest order, regardless of completion order.
            for case, future in zip(cases, futures, strict=True):
                try:
                    name, report = future.result()
                except Exception as exc:  # noqa: BLE001 - report native/controller failures per case
                    name = case['name']
                    report = {'passed': False, 'execution': {'valid': False},
                              'error': {'type': type(exc).__name__, 'message': str(exc)}}
                result['cases'][name] = report
        execution_errors = {name: report['error'] for name, report in result['cases'].items()
                            if 'error' in report}
        if execution_errors:
            result['case_errors'] = execution_errors
            result['error'] = {'type': 'CaseExecutionError',
                               'message': 'Execution failure in: ' + ', '.join(execution_errors)}
        result['reward'] = int(bool(result['cases']) and all(r['passed'] for r in result['cases'].values()))
        result['outcome'] = ('execution_failure' if 'error' in result else
                             'accepted' if result['reward'] else 'engineering_failure')
    except Exception as exc:  # noqa: BLE001 - preserve execution failures separately from physical failures
        result['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        result['outcome'] = 'execution_failure'
    finally:
        result['execution_valid'] = 'error' not in result
        checks = []
        for name, report in result['cases'].items():
            if 'error' in report:
                checks.append({'name': name+':execution', 'status': 'failed', 'duration': 0,
                               'message': report['error']['message']})
                continue
            checks.extend({'name': name+':'+key, 'status': 'passed' if clause['passed'] else 'failed',
                           'duration': 0} for key, clause in report['selected_acceptance']['obligations'].items())
        if 'error' in result:
            checks.append({'name': 'controller_execution', 'status': 'failed', 'duration': 0,
                           'message': result['error']['message']})
        summary = {key: sum(item['status'] == key for item in checks)
                   for key in ('passed', 'failed', 'skipped', 'pending', 'other')}
        summary.update(tests=len(checks), start=int(started*1000), stop=int(time.time()*1000))
        (output/'ctrf.json').write_text(json.dumps({'results': {'tool': {'name': 'native-fmu'},
                                                              'summary': summary, 'tests': checks}}, indent=2))
        result.update(finished_unix=time.time(), elapsed_s=time.time()-started)
        (output/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False))
        with (output/'metric-case-matrix.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['case', 'metric', 'value', 'selected',
                                                       'status', 'comparator', 'threshold',
                                                       'violation_duration_s'])
            writer.writeheader()
            for name, report in result['cases'].items():
                if 'error' in report:
                    continue
                selected = {item['metric']: item for item in report['selected_acceptance']['obligations'].values()}
                for metric, value in report['metrics'].items():
                    if value is not None and not isinstance(value, (int, float)):
                        continue
                    item = selected.get(metric)
                    writer.writerow({'case': name, 'metric': metric, 'value': value,
                                     'selected': bool(item),
                                     'status': ('passed' if item['passed'] else 'failed') if item else 'diagnostic',
                                     'comparator': item['comparator'] if item else '',
                                     'threshold': item['threshold'] if item else '',
                                     'violation_duration_s': report['obligations'].get(metric, {}).get('violation_duration_s', '')})
        (output/'reward.txt').write_text(str(result['reward'])+'\n')
        print(json.dumps(result, allow_nan=False))


def supervise(command, output, timeout_s=840):
    """Keep a parent outside native code so solver hangs still produce artifacts."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    started = time.time()
    run_id = uuid.uuid4().hex
    process = subprocess.Popen(command, start_new_session=True,
                               env={**os.environ, 'DC05_VERIFIER_RUN_ID': run_id})
    error = None
    try:
        code = process.wait(timeout=timeout_s)
        if code != 0:
            error = {'type': 'VerifierProcessError', 'message': f'verifier worker exited {code}'}
    except subprocess.TimeoutExpired:
        error = {'type': 'TimeoutError', 'message': f'verifier exceeded {timeout_s}s native execution budget'}
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # Worker exited between timeout detection and group kill.
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            error['message'] += '; worker did not reap within 5s after SIGKILL' 
    uid_record = output / 'candidate-process-uids.json'
    if uid_record.is_file():
        recorded = json.loads(uid_record.read_text())
        if recorded.get('verifier_run_id') == run_id:
            cleanup_case_uids(set(recorded['uids']))
    if error is None and all((output / name).is_file() for name in ('reward.txt', 'report.json', 'ctrf.json')):
        return
    if error is None:
        error = {'type': 'VerifierArtifactsMissing', 'message': 'worker exited without complete verifier artifacts'}
    finished = time.time()
    # A timeout is an execution failure. Do not manufacture physical measurements.
    report = {'schema_version': 1, 'scope': 'configured-public-and-private-cases', 'reward': 0,
              'execution_valid': False, 'cases': {}, 'error': error, 'verifier_run_id': run_id,
              'started_unix': started, 'finished_unix': finished, 'elapsed_s': finished-started}
    # Preserve per-case completion evidence even if one native worker hangs.
    # Missing artifacts mean incomplete execution, never an invented physical failure.
    case_execution = {}
    try:
        inventory = assessment_cases()
    except (ValueError, OSError, KeyError) as exc:
        inventory = []
        report['case_inventory_error'] = str(exc)
    for case in inventory:
        name = case['name']
        path = output / (name + '.json')
        if path.is_file():
            try:
                document = json.loads(path.read_text())
                if document.get('verifier_run_id') == run_id:
                    report['cases'][name] = document['acceptance']
                    case_execution[name] = {'state': 'completed', 'valid': True}
                    continue
            except (ValueError, KeyError, OSError):
                pass  # A partial file is not a completed trajectory.
        failure_path = output / (name + '.execution-error.json')
        if failure_path.is_file():
            try:
                failure = json.loads(failure_path.read_text())
                if failure.get('verifier_run_id') == run_id:
                    report['cases'][name] = failure['report']
                    case_execution[name] = {'state': 'execution_failure', 'valid': False,
                                            'error': failure['report']['error']}
                    continue
            except (ValueError, KeyError, OSError):
                pass
        case_execution[name] = {'state': 'incomplete_at_supervisor_failure',
                                'valid': False, 'error': error}
    report['case_execution'] = case_execution
    checks = [{'name': 'controller_execution', 'status': 'failed', 'duration': finished-started,
               'message': error['message']}]
    summary = {'tests': 1, 'passed': 0, 'failed': 1, 'skipped': 0, 'pending': 0, 'other': 0,
               'start': int(started*1000), 'stop': int(finished*1000)}
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    (output/'ctrf.json').write_text(json.dumps({'results': {'tool': {'name': 'dc05-native-fmu'},
                                                          'summary': summary, 'tests': checks}}, indent=2)+'\n')
    (output/'reward.txt').write_text('0\n')
    print(json.dumps(report))


if __name__ == '__main__':
    if sys.argv[1:] == ['--worker']:
        worker_main()
    else:
        supervise([sys.executable, str(Path(__file__).resolve()), '--worker'], '/logs/verifier')
