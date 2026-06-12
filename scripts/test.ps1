param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path $PSScriptRoot -Parent
$venvPython = Join-Path $projectRoot ".venv/Scripts/python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }
$runId = "$(Get-Date -Format yyyyMMdd-HHmmss)-$PID-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
$runRoot = ".pytest_tmp/$runId"

Push-Location $projectRoot

try {
    New-Item -ItemType Directory -Force -Path ".pytest_tmp" | Out-Null
    New-Item -ItemType Directory -Force -Path $runRoot | Out-Null

    & $python -m pytest @PytestArgs `
        --basetemp="$runRoot/tmp" `
        -o "cache_dir=$runRoot/cache"

    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
