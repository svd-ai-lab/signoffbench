"""Full original controller-port FMU runner; no scenario values enter the candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import shutil
import time
from pathlib import Path

from .controller_interface import OBSERVATIONS, OUTPUTS, SCAN_S
from .subprocess_controller import SubprocessController

# Legacy FMU log ports are fixed internal compatibility inputs, not candidate outputs.
PLANT_OUTPUTS = OUTPUTS + (
    "alm_pump", "alm_tsensor", "alm_dpsensor", "alm_flowmeter", "alm_valve",
)


def run_fmu(controller_path, fmu_path, duration_s=1200):
    from fmpy import extract, read_model_description
    from fmpy.fmi3 import FMU3Slave

    fmu_path = Path(fmu_path)
    description = read_model_description(str(fmu_path))
    if description.fmiVersion != '3.0' or not description.coSimulation.hasEventMode:
        raise ValueError('runner requires FMI 3 Co-Simulation with Event Mode')
    metadata = json.loads((fmu_path.parent/'full-interface.json').read_text())
    log_names = metadata['truth_names']
    variables = {v.name: v for v in description.modelVariables}
    if {v.name for v in description.modelVariables if v.causality == 'input'} != set(PLANT_OUTPUTS):
        raise ValueError('FMU must expose exactly the nine original command/alarm inputs')
    inputs = [variables[name].valueReference for name in PLANT_OUTPUTS]
    observations = [variables['obs_'+name].valueReference for name in OBSERVATIONS]
    truths = [variables['native_truth_vector'].valueReference]
    directory = extract(str(fmu_path))
    fmu = None
    started = time.monotonic()
    cpu_before = resource.getrusage(resource.RUSAGE_SELF)
    trace = []
    try:
        fmu = FMU3Slave(guid=description.guid, unzipDirectory=directory,
                        modelIdentifier=description.coSimulation.modelIdentifier, instanceName='original_dc05')
        fmu.instantiate(eventModeUsed=True)
        fmu.enterInitializationMode(startTime=0.0)
        fmu.setFloat64(inputs, [0.0]*len(inputs))
        fmu.exitInitializationMode()
        pending_command = [0.0]*4
        with SubprocessController(controller_path) as controller:
            for tick in range(round(duration_s/SCAN_S)+1):
                instant = tick*SCAN_S
                if tick:
                    fmu.enterEventMode()
                fmu.setFloat64(inputs[:4], pending_command)
                while fmu.updateDiscreteStates()[0]:
                    pass
                observation = dict(zip(OBSERVATIONS, fmu.getFloat64(observations)))
                raw_truth = fmu.getFloat64(truths, nValues=52)
                if abs(raw_truth[0]-instant) > 1e-9:
                    raise RuntimeError('FMU internal time differs from communication time')
                command = controller.step(observation)
                trace.append({'time_s': instant, 'observations': observation,
                              'native_truth': raw_truth, 'controller_outputs': command,
                              'applied_actuator_commands': dict(zip(OUTPUTS[:4], pending_command))})
                pending_command = [command[name] for name in OUTPUTS[:4]]
                fmu.setFloat64(inputs[4:], [0.0] * 5)
                fmu.enterStepMode()
                if instant >= duration_s:
                    break
                _, terminate, early_return, last_time = fmu.doStep(
                    currentCommunicationPoint=instant, communicationStepSize=SCAN_S)
                if terminate or early_return:
                    raise RuntimeError(f'FMU ended step early at {last_time}')
        fmu.terminate()
        native_log = {name: [] for name in log_names}
        for row in trace:
            if abs(row['time_s']-round(row['time_s'])) > 1e-9:
                continue
            # Original Simulink To Workspace logs current-scan controller outputs.
            # FMU raw truth is sampled before that scan; preserve it separately.
            aligned = row['native_truth'][:-9]+[row['controller_outputs'][name] for name in OUTPUTS] + [0.0] * 5
            for name, value in zip(log_names, aligned):
                native_log[name].append(value)
        cpu = resource.getrusage(resource.RUSAGE_SELF)
        return {'schema_version': 1, 'native_fmu': True, 'controller_interface': 'four_actuators_23_observations_v1',
                'fmu_sha256': hashlib.sha256(fmu_path.read_bytes()).hexdigest(),
                'candidate_sha256': hashlib.sha256(Path(controller_path).read_bytes()).hexdigest(),
                'scan_s': SCAN_S, 'command_delay_location': 'python_previous_scan_buffer', 'effective_command_delay_s': 0.5, 'event_mode': True, 'trace': trace,
                'native_log': native_log, 'native_log_sample_s': 1.0,
                'log_alignment': 'physical truth before scan; actual controller outputs from current scan',
                'resources': {'wall_s': time.monotonic()-started,
                              'main_cpu_s': cpu.ru_utime+cpu.ru_stime-cpu_before.ru_utime-cpu_before.ru_stime,
                              'main_peak_rss_kib': cpu.ru_maxrss}}
    finally:
        if fmu is not None:
            fmu.freeInstance()
        shutil.rmtree(directory, ignore_errors=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controller', required=True)
    parser.add_argument('--fmu', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run_fmu(args.controller, args.fmu)
    args.output.write_text(json.dumps(result, allow_nan=False))
    print(json.dumps({key: value for key, value in result.items() if key not in {'trace', 'native_log'}}))
