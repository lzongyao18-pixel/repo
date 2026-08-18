param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$skillRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $skillRoot
$pythonExe = $env:TK_INGEST_PYTHON

if (-not $pythonExe) {
    $candidates = @()
    for ($index = 0; $index -lt $RemainingArgs.Count - 1; $index++) {
        if ($RemainingArgs[$index] -eq '--env-file') {
            $resolvedEnv = Resolve-Path -LiteralPath $RemainingArgs[$index + 1] -ErrorAction SilentlyContinue
            if ($resolvedEnv) {
                $candidates += Join-Path (Split-Path -Parent $resolvedEnv.Path) '.venv\Scripts\python.exe'
            }
            break
        }
    }
    $candidates += Join-Path (Get-Location).Path '.venv\Scripts\python.exe'
    $candidates += Join-Path $workspaceRoot '.venv\Scripts\python.exe'
    $pythonExe = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

if (-not $pythonExe -or -not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python runtime not found. Set TK_INGEST_PYTHON or create .venv next to the --env-file."
}

& $pythonExe (Join-Path $PSScriptRoot 'main.py') @RemainingArgs
exit $LASTEXITCODE
