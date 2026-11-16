#!/usr/bin/env bash
set -eo pipefail
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
PYTHON=${SMARTHOME_PYTHON:-"$HOME/SmartHome/conda_envs/backend/bin/python"}
# CANN sets optional variables; do not enable nounset when sourcing its script.
source /usr/local/Ascend/ascend-toolkit/set_env.sh
export SMARTHOME_VISION_BACKEND=om
export OMP_NUM_THREADS=2
export OPENBLAS_NUM_THREADS=2
cd "$PROJECT_ROOT/backend"
exec "$PYTHON" -m uvicorn deploy_app:app --host 127.0.0.1 --port 8000 --workers 1
