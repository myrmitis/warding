# Delayed gateway restart for Windows — run as a detached process via Start-Process.
# The sleep gives the calling session time to finish responding.
# Usage (from agent):
#   Start-Process -WindowStyle Hidden powershell -ArgumentList "-ExecutionPolicy", "Bypass", "-File", "<path>\do-restart.ps1", "-JunctionBin", "<resolved-path-to-junction.exe>"
param(
    [string]$JunctionBin = "junction",
    [int]$DelaySec = 10,
    [string]$LogFile = ""
)

Start-Sleep -Seconds $DelaySec

# Resolve the binary — if a path was provided, verify it exists; otherwise fall back to PATH.
if ($JunctionBin -ne "junction" -and (Test-Path $JunctionBin)) {
    $bin = $JunctionBin
} else {
    $found = Get-Command junction -ErrorAction SilentlyContinue
    if ($found) { $bin = $found.Source } else { $bin = $JunctionBin }
}

# Execute the restart, capturing any errors.
try {
    $output = & $bin restart 2>&1
    if ($LogFile) { "$(Get-Date -Format o) OK: $output" | Out-File -Append -Encoding utf8 $LogFile }
} catch {
    $err = $_.Exception.Message
    if ($LogFile) { "$(Get-Date -Format o) FAIL: $err" | Out-File -Append -Encoding utf8 $LogFile }
    # Last resort: try via python module
    $venvPython = Join-Path (Split-Path (Split-Path $bin)) "python.exe"
    if (Test-Path $venvPython) {
        & $venvPython -m junction.cli restart 2>&1 | Out-Null
    }
}
