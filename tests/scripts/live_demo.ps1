# Run ONE live SolidWorks test as a watchable demo and print only its evidence.
#
#   powershell -ExecutionPolicy Bypass -File tests\scripts\live_demo.ps1 `
#       tests/live/test_live_sw_issue106_tools.py::test_select_feature_live
#
# Every open document is closed (unsaved changes discarded) before the test,
# and the test's part is left open afterwards. SolidWorks must be open, idle
# and running for 8+ minutes (tests/live/conftest.py waits otherwise). Each
# step is paced so a person can follow it in the SolidWorks window. Live tests
# print "[evidence] <label>: <payload>" lines; those, the "[live]" warm-up
# notice and the pass/fail summary are all that is shown.
#
# -CaptureDir <folder> also saves each evidence step as a PNG of the
# SolidWorks window with the payload captioned beneath it, then builds one GIF
# per test there (tests/scripts/make_demo_gif.py), for a PR or the docs.
#
# -Record also records the SolidWorks window through the test (about 12
# frames a second, changed frames only; tests/live/recorder.py) and builds
# <test>-motion.gif, sped up, with each tool call captioned beneath it. A
# 10 s countdown comes first: bring SolidWorks to the front and leave it
# uncovered, as the recorder copies the screen. Holds are shorter, since the
# recording shows every step anyway.
param(
    [Parameter(Mandatory = $true)][string]$Test,
    [string]$CaptureDir = "",
    [switch]$Record,
    [double]$Speed = 5.0
)

Set-Location (Resolve-Path "$PSScriptRoot\..\..")
$env:SOLIDWORKS_MCP_RUN_REAL_INTEGRATION = "true"
$env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"
$env:SW_TEST_PACE_SECONDS = "8"
# Pause on each [evidence] line so SolidWorks shows the state it proves.
$env:SW_DEMO_HOLD_SECONDS = "6"
# Close every open document before the test and leave its part open after.
$env:SW_DEMO_KEEP_OPEN = "true"
$env:SW_DEMO_CAPTURE_DIR = $CaptureDir
if ($Record) {
    $env:SW_DEMO_RECORD = "true"
    $env:SW_DEMO_RECORD_COUNTDOWN = "10"
    $env:SW_DEMO_HOLD_SECONDS = "0.5"
} else {
    $env:SW_DEMO_RECORD = ""
}

& .\.venv\Scripts\python.exe -m pytest $Test -s -x -n 0 --no-cov -p no:cacheprovider `
    -o addopts="" --asyncio-mode=auto --color=yes 2>&1 |
    ForEach-Object -Begin { $inEvidence = $false } -Process {
        # Evidence prints over several lines (label, call, result), ending
        # at a blank line; keep all of it plus the notices and the summary.
        $line = "$_"
        if ($line -match "\[evidence\]") { $inEvidence = $true }
        elseif ($line.Trim() -eq "") { $inEvidence = $false }
        if ($inEvidence -or $line -match "\[live\]|\[recorder\]|PASSED|FAILED|SKIPPED|passed|failed|skipped|Error") {
            $line
        }
    }

if ($CaptureDir -and $Record) {
    & .\.venv\Scripts\python.exe tests\scripts\make_demo_gif.py $CaptureDir --recording --speed $Speed
} elseif ($CaptureDir) {
    & .\.venv\Scripts\python.exe tests\scripts\make_demo_gif.py $CaptureDir
}
