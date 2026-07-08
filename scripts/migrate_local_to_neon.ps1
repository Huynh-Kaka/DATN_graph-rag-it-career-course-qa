# Chuyển schema + dữ liệu PostgreSQL local (Docker) sang Neon.
#
# Yêu cầu: Docker Desktop, file .env có DATABASE_URL trỏ Neon (postgresql://...).
#
# Cách chạy (từ thư mục gốc repo):
#   .\scripts\migrate_local_to_neon.ps1
#
# Chỉ dump (chưa restore):
#   .\scripts\migrate_local_to_neon.ps1 -SkipRestore
#
# Chỉ dữ liệu (schema đã có trên Neon, ví dụ sau reset_db_v2.py):
#   .\scripts\migrate_local_to_neon.ps1 -DataOnly

param(
    [string]$DumpFile = "backups/career_chat_local_dump.sql",
    [string]$TargetUrl = "",
    [string]$PgUser = "career",
    [string]$PgDb = "career_chat",
    [switch]$SchemaOnly,
    [switch]$DataOnly,
    [switch]$SkipRestore
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Read-DatabaseUrlFromEnv {
    $envPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $envPath)) {
        throw "Không tìm thấy .env tại $envPath"
    }
    foreach ($line in Get-Content $envPath) {
        if ($line -match '^\s*DATABASE_URL\s*=\s*(.+)\s*$') {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    throw "DATABASE_URL chưa có trong .env"
}

function To-LibpqUrl([string]$Url) {
    $u = $Url -replace '^postgres://', 'postgresql://'
    $u = $u -replace '^postgresql\+asyncpg://', 'postgresql://'
    if ($u -notmatch '\?') {
        $u += '?sslmode=require'
    } elseif ($u -notmatch 'sslmode=') {
        $u += '&sslmode=require'
    }
    return $u
}

if (-not $TargetUrl) {
    $TargetUrl = Read-DatabaseUrlFromEnv
}
$libpqTarget = To-LibpqUrl $TargetUrl

$dumpDir = Split-Path -Parent $DumpFile
if ($dumpDir -and -not (Test-Path $dumpDir)) {
    New-Item -ItemType Directory -Path $dumpDir | Out-Null
}

Write-Host "==> Khởi động Postgres local (Docker)..."
docker compose up -d postgres | Out-Null

$pgDumpArgs = @(
    "-U", $PgUser,
    "-d", $PgDb,
    "--no-owner",
    "--no-acl",
    "--format=plain",
    "--encoding=UTF8"
)
if ($SchemaOnly) {
    $pgDumpArgs += "--schema-only"
} elseif ($DataOnly) {
    $pgDumpArgs += "--data-only", "--disable-triggers"
} else {
    $pgDumpArgs += "--clean", "--if-exists"
}

Write-Host "==> Dump local -> $DumpFile"
docker compose exec -T postgres pg_dump @pgDumpArgs | Set-Content -Path $DumpFile -Encoding utf8

$lineCount = (Get-Content $DumpFile | Measure-Object -Line).Lines
Write-Host "    Dump xong ($lineCount dòng)."

if ($SkipRestore) {
    Write-Host "Bỏ qua restore (-SkipRestore). Restore thủ công:"
    Write-Host "  Get-Content $DumpFile -Raw | docker run --rm -i postgres:16-alpine psql `"$libpqTarget`""
    exit 0
}

Write-Host "==> Restore lên Neon..."
Write-Host "    Host: $($libpqTarget -replace ':[^:@]+@', ':****@')"

Get-Content $DumpFile -Raw | docker run --rm -i postgres:16-alpine psql $libpqTarget 2>&1 | ForEach-Object { Write-Host $_ }

Write-Host "==> Xong. Kiểm tra:"
Write-Host "  python scripts/reset_db_v2.py   # chỉ khi cần tạo lại schema trống"
Write-Host "  curl http://localhost:8000/api/health"
