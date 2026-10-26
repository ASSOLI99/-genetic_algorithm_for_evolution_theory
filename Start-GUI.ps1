param([ValidateRange(1, 65535)][int]$Port = 8765, [switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv-clean\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
}
Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        & python -m venv (Join-Path $PSScriptRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.13+ is required.' }
    }
    $check = @'
from importlib.metadata import version
from pathlib import Path
import sys, tomllib
try:
    pins = [line.split('==') for line in Path('requirements-dev.lock').read_text().splitlines() if line and not line.startswith('#')]
    pins.append(['evolution-lab-v2', tomllib.loads(Path('pyproject.toml').read_text())['project']['version']])
    sys.exit(any(version(package) != expected for package, expected in pins))
except Exception:
    sys.exit(1)
'@
    & $pythonPath -c $check
    if ($LASTEXITCODE -ne 0) {
        & $pythonPath -m pip install --disable-pip-version-check -r requirements-dev.lock
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
        & $pythonPath -m pip install --disable-pip-version-check -e '.[dev]'
        if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
    }
    if ($NoOpen) { & $pythonPath -m evolution_lab_v2 gui --port $Port --no-open }
    else { & $pythonPath -m evolution_lab_v2 gui --port $Port }
} finally { Pop-Location }
