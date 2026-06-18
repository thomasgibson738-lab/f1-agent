# Self-restarting backfill driver.
#
# Runs backfill_all.py repeatedly. Because the script skips parquet files that
# already exist, each pass only fetches what is still missing. We keep looping
# until a full pass adds ZERO new parquet files (i.e. everything fetchable has
# been fetched, or only no-data sessions remain). This survives the machine
# sleeping mid-download — when the process dies, we just start another pass.

$ErrorActionPreference = "Continue"
$root = "C:\Users\thoma\OneDrive\Desktop\f1-agent"
$py = Join-Path $root ".venv\Scripts\python.exe"
$lapsDir = Join-Path $root "data\laps"

function Count-Parquet {
    (Get-ChildItem $lapsDir -Recurse -File -Filter *.parquet -ErrorAction SilentlyContinue).Count
}

$pass = 0
$prevCount = -1
while ($true) {
    $pass++
    $before = Count-Parquet
    "$(Get-Date -Format o)  === loop pass $pass start - $before parquet files ===" |
        Tee-Object -FilePath (Join-Path $root "backfill_loop.log") -Append

    # Run a full pass. backfill_all.py writes backfill.log itself via its own
    # logging FileHandler, so we must NOT redirect to that same file (two writers
    # collide -> PermissionError). Send console output to a separate file.
    & $py (Join-Path $root "backfill_all.py") *>> (Join-Path $root "backfill_console.log")

    $after = Count-Parquet
    "$(Get-Date -Format o)  === loop pass $pass done - $after parquet files (+$($after - $before)) ===" |
        Tee-Object -FilePath (Join-Path $root "backfill_loop.log") -Append

    # Stop once a pass makes no progress (nothing new fetchable).
    if ($after -eq $before) {
        "$(Get-Date -Format o)  No new files this pass - backfill converged. Stopping." |
            Tee-Object -FilePath (Join-Path $root "backfill_loop.log") -Append
        break
    }
    Start-Sleep -Seconds 5
}
