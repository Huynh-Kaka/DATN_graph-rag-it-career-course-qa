# Graph-RAG v2.2 — full verification (stops on first failure)
param(
    [switch]$BaselineOnly,
    [switch]$SkipBuildGold,
    [switch]$PostFix38,
    [switch]$SkipAblation
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("verification_v22_{0:yyyy-MM-dd}.txt" -f (Get-Date))
Start-Transcript -Path $LogFile -Append

function Step($Name, [scriptblock]$Block) {
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: $Name (exit $LASTEXITCODE)" -ForegroundColor Red
        Stop-Transcript
        exit $LASTEXITCODE
    }
    Write-Host "OK: $Name" -ForegroundColor Green
}

if ($BaselineOnly) {
    Step "D0 baseline E2E v21_38" {
        python scripts/eval_answer_quality.py `
            --gold data/eval/answer_quality_gold_v21_38.jsonl `
            --output-csv results/baseline_pre_router_v22.csv `
            --report-json results/baseline_pre_router_v22.json `
            --run-label v2.2-D0 `
            --delay 2.5
    }
    Stop-Transcript
    exit 0
}

Step "pytest" { python -m pytest tests/ -q --tb=short }

if (-not $SkipBuildGold) {
    Step "build answer_quality gold" {
        python scripts/build_answer_quality_gold.py --out data/eval/answer_quality_gold.jsonl --probe-neo4j
    }
    Step "export gold subsets" {
        python scripts/export_gold_subset.py --all
    }
}

Step "validate answer_quality gold" {
    python scripts/validate_gold.py data/eval/answer_quality_gold.jsonl --probe-neo4j
}

Step "eval_retrieval" {
    python scripts/eval_retrieval.py --k 5 --output-csv data/eval/retrieval_results.csv
}

if (-not $SkipAblation) {
    Step "analyze_gold_triviality" {
        python scripts/analyze_gold_triviality.py
    }
}

Step "smoke_judge" { python scripts/smoke_judge.py }

if ($PostFix38) {
    Step "D1 post-fix E2E v21_38" {
        python scripts/eval_answer_quality.py `
            --gold data/eval/answer_quality_gold_v21_38.jsonl `
            --output-csv results/post_fix_v21_38.csv `
            --report-json results/post_fix_v21_38.json `
            --run-label v2.2-D1 `
            --delay 2.5
    }
} else {
    Step "D2 E2E full 52" {
        python scripts/eval_answer_quality.py `
            --gold data/eval/answer_quality_gold.jsonl `
            --output-csv data/eval/answer_quality_results.csv `
            --report-json results/eval_summary.json `
            --run-label v2.2-D2 `
            --delay 2.5
    }
}

Step "summarize results" {
    if (Test-Path (Join-Path $Root "results/eval_summary.json")) {
        python scripts/summarize_eval_results.py `
            --report-json results/eval_summary.json `
            --baseline results/baseline_pre_router_v22.json `
            --out results/verification_summary_v22.json
    } else {
        Write-Host "SKIP summarize: results/eval_summary.json not found (run D2 first)" -ForegroundColor Yellow
    }
}

Write-Host "`nAll verification steps passed. Log: $LogFile" -ForegroundColor Green
Stop-Transcript
