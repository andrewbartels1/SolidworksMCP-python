# Run ONE live SolidWorks test as a watchable demo and print only its evidence.
#
#   powershell -ExecutionPolicy Bypass -File tests\scripts\live_demo.ps1 `
#       tests/live/test_live_sw_issue106_tools.py::test_select_feature_live
#
# SolidWorks must be open, idle, with no documents, and running for 8+ minutes
# (tests/live/conftest.py waits otherwise). Each step is paced so a person can
# follow it in the SolidWorks window. Live tests print "[evidence] <label>:
# <payload>" lines; those, plus the pass/fail summary, are all that is shown.
param([Parameter(Mandatory = $true)][string]$Test)

Set-Location (Resolve-Path "$PSScriptRoot\..\..")
$env:SOLIDWORKS_MCP_RUN_REAL_INTEGRATION = "true"
$env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"
$env:SW_TEST_PACE_SECONDS = "8"
# Pause on each [evidence] line so SolidWorks shows the state it proves.
$env:SW_DEMO_HOLD_SECONDS = "6"

& .\.venv\Scripts\python.exe -m pytest $Test -s -x -n 0 --no-cov -p no:cacheprovider `
    -o addopts="" --asyncio-mode=auto --color=yes 2>&1 |
    Select-String -Pattern "\[evidence\]|PASSED|FAILED|SKIPPED|passed|failed|skipped|Error" |
    ForEach-Object { $_.Line }
