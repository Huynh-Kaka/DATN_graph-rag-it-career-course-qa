# Khởi động stack dev (Windows PowerShell)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Stack cloud từ .env (Neon + Qdrant Cloud + Neo4j Aura). Không cần docker compose cho DB."

Write-Host ""
Write-Host "Health: http://127.0.0.1:8000/api/health"
Write-Host "Chat UI: http://127.0.0.1:8000/chat.html"
Write-Host ""
Write-Host "Starting uvicorn..."
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
