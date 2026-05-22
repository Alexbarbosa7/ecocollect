#!/bin/bash
# EcoCollect — iniciar o projeto

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "EcoCollect — Iniciando..."
echo "================================"

# Backend
echo ""
echo "Iniciando backend (Flask + SQLite)..."
cd "$ROOT"
python3 server.py &
BACKEND_PID=$!
echo "  Backend: http://localhost:5000"
echo "  PID: $BACKEND_PID"

# Frontend
echo ""
echo "Iniciando frontend..."
cd "$ROOT"
python3 -m http.server 3000 &
FRONTEND_PID=$!
echo "  Frontend: http://localhost:3000"
echo "  PID: $FRONTEND_PID"

echo ""
echo "================================"
echo "App rodando!"
echo "  Frontend: http://localhost:3000"
echo "  API:      http://localhost:5000/api"
echo ""
echo "Contas de demonstracao:"
echo "  Gerador:  carlos@email.com / 123456"
echo "  Coletor:  joao@email.com   / 123456"
echo ""
echo "Para parar: kill $BACKEND_PID $FRONTEND_PID"
echo "================================"

wait
