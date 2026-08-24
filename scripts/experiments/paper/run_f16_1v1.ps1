param(
    [int]$Timesteps = 100000,
    [int]$EvaluationEpisodes = 500,
    [int[]]$Seeds = @(1111, 2222, 3333, 4444, 5555),
    [string]$Device = "cuda:0"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$config = Join-Path $repo "scripts\experiments\paper\f16_1v1_cpp.jsonc"
$runRoot = Join-Path $repo "runs\paper\f16_1v1"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null

foreach ($seed in $Seeds) {
    $seedDir = Join-Path $runRoot "seed_$seed"
    New-Item -ItemType Directory -Force -Path $seedDir | Out-Null
    $stdout = Join-Path $seedDir "train.stdout.log"
    $stderr = Join-Path $seedDir "train.stderr.log"
    $arguments = @(
        "-m", "bvr_sim_rl",
        "--backend", "cpp",
        "--config", $config,
        "--timesteps", $Timesteps,
        "--rollouts", "256",
        "--seed", $seed,
        "--logdir", $seedDir,
        "--device", $Device,
        "--checkpoint-interval", "10000",
        "--write-interval", "1000"
    )
    $process = Start-Process python -ArgumentList $arguments -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Set-Content -Path (Join-Path $seedDir "train.pid") -Value $process.Id
}

$baselineDir = Join-Path $runRoot "tactical"
New-Item -ItemType Directory -Force -Path $baselineDir | Out-Null
$baselineArgs = @(
    "-m", "bvr_sim_rl.evaluate",
    "--backend", "cpp",
    "--config", $config,
    "--method", "tactical",
    "--episodes", $EvaluationEpisodes,
    "--seed", "30000",
    "--output", (Join-Path $baselineDir "eval.json")
)
$baseline = Start-Process python -ArgumentList $baselineArgs -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $baselineDir "eval.stdout.log") -RedirectStandardError (Join-Path $baselineDir "eval.stderr.log") -PassThru
Set-Content -Path (Join-Path $baselineDir "eval.pid") -Value $baseline.Id

Write-Host "Started $($Seeds.Count) training runs and tactical evaluation under $runRoot"
