# Delayed gateway restart for Windows — run as a detached process via Start-Process.
# The sleep gives the calling session time to finish responding.
# Usage (from agent):
#   Start-Process -WindowStyle Hidden powershell -ArgumentList "-ExecutionPolicy", "Bypass", "-File", "<path>\do-restart.ps1", "-WardingBin", "<resolved-path-to-warding.exe>"
param(
    [string]$WardingBin = "warding",
    [int]$DelaySec = 10,
    [string]$LogFile = ""
)

Start-Sleep -Seconds $DelaySec

# Resolve the binary — if a path was provided, verify it exists; otherwise fall back to PATH.
if ($WardingBin -ne "warding" -and (Test-Path $WardingBin)) {
    $bin = $WardingBin
} else {
    $found = Get-Command warding -ErrorAction SilentlyContinue
    if ($found) { $bin = $found.Source } else { $bin = $WardingBin }
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
        & $venvPython -m warding.cli restart 2>&1 | Out-Null
    }
}
