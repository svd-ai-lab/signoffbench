#!/bin/bash
set -euo pipefail
python /solution/generate.py
python /app/run_case.py --case P1_pump_trip_2MW --controller /app/submission/controller.py --output /app/results/oracle-public.json
