#!/usr/bin/env bash
# Evolution Lab - one-click launcher for macOS and Linux.
#
#   ./start.sh                 live laboratory (graphical interface in the browser)
#   ./start.sh smoke           quick demo report
#   ./start.sh standard        full prepared comparison
#   ./start.sh isolated        each reproduction program alone
#   ./start.sh invasion        rare facultative introduction
#   ./start.sh catastrophe     bottlenecks and droughts
#   ./start.sh smoke --no-open do not open the browser
#
# Mirrors Start-GUI.ps1 / Start-Experiment.ps1: verify dependencies, then either
# serve the local laboratory, or run the test suite, freeze the plan, run the
# batch and open REPORT.html.
set -euo pipefail
cd "$(dirname "$0")"

PROFILE="${1:-gui}"
case "$PROFILE" in --*) PROFILE=gui ;; esac
OPEN=1
for arg in "$@"; do [ "$arg" = "--no-open" ] && OPEN=0; done

case "$PROFILE" in
  smoke)    CONFIG=comparison_smoke.json ;;
  standard) CONFIG=comparison_ready.json ;;
  isolated) CONFIG=comparison_isolated.json ;;
  invasion) CONFIG=invasion_facultative.json ;;
  catastrophe) CONFIG=catastrophe_pilot.json ;;
  gui) CONFIG="" ;;
  *) echo "Unknown profile '$PROFILE' (use gui, smoke, standard, isolated, invasion or catastrophe)"; exit 2 ;;
esac

# Find Python 3.13+
PY=""
for candidate in python3.14 python3.13 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.13 or newer is required: https://www.python.org/downloads/"
  exit 1
fi

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "First run: creating a private Python environment in .venv ..."
  "$PY" -m venv .venv
fi

# Install pinned dependencies only when something is missing or has the wrong version.
if ! "$VENV_PY" - <<'EOF'
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys, tomllib
reqs = [l.split("==") for l in Path("requirements-dev.lock").read_text().splitlines() if l and not l.startswith("#")]
reqs.append(["evolution-lab-v2", tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]])
bad = []
for name, expected in reqs:
    try:
        if version(name) != expected:
            bad.append(name)
    except PackageNotFoundError:
        bad.append(name)
sys.exit(bool(bad))
EOF
then
  echo "Installing pinned dependencies ..."
  "$VENV_PY" -m pip install --disable-pip-version-check -q -r requirements-dev.lock
  "$VENV_PY" -m pip install --disable-pip-version-check -q -e '.[dev]'
fi

if [ "$PROFILE" = gui ]; then
  echo "Live laboratory: http://127.0.0.1:8765  (Ctrl+C stops it)"
  if [ "$OPEN" = 1 ]; then exec "$VENV_PY" -m evolution_lab_v2 gui --port 8765
  else exec "$VENV_PY" -m evolution_lab_v2 gui --port 8765 --no-open; fi
fi

"$VENV_PY" -m evolution_lab_v2 experiment --config "configs/$CONFIG" --plan-only
echo "Running the test suite before the experiment ..."
"$VENV_PY" -m pytest -q

OUTPUT="runs/${PROFILE}_$(date -u +%Y%m%d_%H%M%S)_$RANDOM"
echo "Results directory: $OUTPUT"
"$VENV_PY" -m evolution_lab_v2 experiment --config "configs/$CONFIG" --output "$OUTPUT"

REPORT="$OUTPUT/REPORT.html"
echo "Completed report: $REPORT"
if [ "$OPEN" = 1 ]; then
  if command -v open >/dev/null 2>&1; then open "$REPORT"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$REPORT" >/dev/null 2>&1 || true
  fi
fi
