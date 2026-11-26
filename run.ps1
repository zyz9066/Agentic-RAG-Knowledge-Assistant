$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pythonPath = $env:PYTHONPATH
if ([string]::IsNullOrWhiteSpace($pythonPath)) {
    $env:PYTHONPATH = $PSScriptRoot
} else {
    $env:PYTHONPATH = "$PSScriptRoot$([IO.Path]::PathSeparator)$pythonPath"
}

uv run --locked streamlit run app\ui.py --server.address=127.0.0.1 --server.headless=false
exit $LASTEXITCODE
