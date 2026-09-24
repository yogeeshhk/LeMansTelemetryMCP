# Run this script from any PowerShell directory; it keeps both owned processes alive.
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Project Python environment is missing. Run the README installation command first.'
}
Push-Location -LiteralPath $project
try {
    & $python -m lmu_mcp.launch
    if ($LASTEXITCODE -ne 0) { throw 'Le Mans MCP launcher failed; see the error above.' }
} finally {
    Pop-Location
}
