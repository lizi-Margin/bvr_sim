param(
    [int]$Episodes = 500,
    [int[]]$Seeds = @(1111, 2222, 3333, 4444, 5555),
    [string]$Device = "cuda:0"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$config = Join-Path $repo "experiments\paper\f16_1v1_cpp.jsonc"
$runRoot = Join-Path $repo "runs\paper\f16_1v1"
$processes = @()

foreach ($seed in $Seeds) {
    $seedDir = Join-Path $runRoot "seed_$seed"
    $checkpoint = Join-Path $seedDir "ppo_cpp_seed$seed.pt"
    if (-not (Test-Path $checkpoint)) {
        throw "Missing completed checkpoint: $checkpoint"
    }
    $arguments = @(
        "-m", "bvr_sim_rl.evaluate",
        "--backend", "cpp",
        "--config", $config,
        "--checkpoint", $checkpoint,
        "--episodes", $Episodes,
        "--seed", "30000",
        "--device", $Device,
        "--output", (Join-Path $seedDir "eval.json")
    )
    $processes += Start-Process python -ArgumentList $arguments -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $seedDir "eval.stdout.log") -RedirectStandardError (Join-Path $seedDir "eval.stderr.log") -PassThru
}

$processes | Wait-Process
foreach ($process in $processes) {
    if ($process.ExitCode -ne 0) {
        throw "Evaluation process $($process.Id) failed with exit code $($process.ExitCode)"
    }
}

$inputs = @((Join-Path $runRoot "tactical\eval.json"))
$inputs += $Seeds | ForEach-Object { Join-Path $runRoot "seed_$_\eval.json" }
python (Join-Path $repo "experiments\paper\summarize_results.py") @inputs `
    --csv (Join-Path $runRoot "summary.csv") `
    --json (Join-Path $runRoot "summary.json")
