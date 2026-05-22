# EcoCollect — iniciar o projeto (Windows)

$Root = $PSScriptRoot
Write-Host ""
Write-Host "EcoCollect — Iniciando..."
Write-Host "================================"

Write-Host ""
Write-Host "Iniciando backend (Flask + SQLite)..."
$env:PYTHONIOENCODING = "utf-8"
Start-Process -FilePath "python" -ArgumentList "server.py" -WorkingDirectory $Root -WindowStyle Normal

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Iniciando frontend..."
Start-Process -FilePath "python" -ArgumentList "-m", "http.server", "3000" -WorkingDirectory $Root -WindowStyle Normal

Write-Host ""
Write-Host "================================"
Write-Host "App rodando!"
Write-Host "  Frontend: http://localhost:3000"
Write-Host "  API:      http://localhost:5000/api"
Write-Host ""
Write-Host "Contas de demonstracao:"
Write-Host "  Gerador:  carlos@email.com / 123456"
Write-Host "  Coletor:  joao@email.com   / 123456"
Write-Host "================================"
