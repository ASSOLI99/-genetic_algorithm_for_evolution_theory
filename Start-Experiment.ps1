param(
    [ValidateSet('standard', 'smoke', 'isolated', 'invasion')]
    [string]$Profile = 'standard',
    [string]$Output = '',
    [switch]$Resume,
    [switch]$PlanOnly,
    [switch]$NoOpen
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv-clean\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
}
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        & python -m venv (Join-Path $projectRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.13+ is required to create the environment.' }
    }
    $dependencyCheck = @'
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys
requirements = [line.split('==') for line in Path('requirements-dev.lock').read_text().splitlines() if line and not line.startswith('#')]
requirements.append(['evolution-lab-v2', '0.2.0'])
problems = []
for package, expected in requirements:
    try:
        if version(package) != expected:
            problems.append(package)
    except PackageNotFoundError:
        problems.append(package)
sys.exit(bool(problems))
'@
    & $pythonPath -c $dependencyCheck
    if ($LASTEXITCODE -ne 0) {
        & $pythonPath -m pip install --disable-pip-version-check -r (Join-Path $projectRoot 'requirements-dev.lock')
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
        & $pythonPath -m pip install --disable-pip-version-check -e '.[dev]'
        if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
    }
    $configName = @{
        standard = 'comparison_ready.json'
        smoke = 'comparison_smoke.json'
        isolated = 'comparison_isolated.json'
        invasion = 'invasion_facultative.json'
    }[$Profile]
    $configPath = Join-Path $projectRoot ('configs\' + $configName)
    & $pythonPath -m evolution_lab_v2 experiment --config $configPath --plan-only
    if ($LASTEXITCODE -ne 0) { throw 'Experiment plan validation failed.' }
    if ($PlanOnly) { return }
    & $pythonPath -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Correctness tests failed; experiment was not started.' }
    if ($Resume -and [string]::IsNullOrWhiteSpace($Output)) {
        throw 'Resume requires -Output pointing to the original experiment directory.'
    }
    if ([string]::IsNullOrWhiteSpace($Output)) {
        $runName = $Profile + '_' + [DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss') + '_' + [Guid]::NewGuid().ToString('N').Substring(0, 6)
        $Output = Join-Path $projectRoot ('runs\' + $runName)
    }
    Write-Host ('Results directory: ' + $Output)
    Write-Host 'Progress and checkpoints are saved. See RUN_ME_AR.md for runtime estimates and resume instructions.'
    if ($Resume) {
        & $pythonPath -m evolution_lab_v2 experiment --config $configPath --output $Output --resume
    } else {
        & $pythonPath -m evolution_lab_v2 experiment --config $configPath --output $Output
    }
    if ($LASTEXITCODE -ne 0) { throw 'Experiment interrupted or failed. Preserve its directory and use -Resume with the same profile and output.' }
    $reportPath = Join-Path $Output 'REPORT.html'
    Write-Host ('Completed report: ' + $reportPath)
    if (-not $NoOpen) { Invoke-Item -LiteralPath $reportPath }
} finally {
    Pop-Location
}
