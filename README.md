# 🌱 EcoCollect

**Uber da Coleta Seletiva** — conecta quem quer descartar recicláveis com quem quer coletar, em tempo real.

---

## Estrutura do projeto

```
ecocollect/
├── server.py            # API Flask + SQLite
├── index.html           # App (HTML/CSS/JS puro)
├── requirements.txt     # Dependências Python
├── start.sh             # Iniciar tudo (Linux/macOS/Git Bash)
├── start.ps1            # Iniciar tudo (Windows PowerShell)
└── README.md
```

---

## Como rodar

### Requisitos
- Python 3.8+

### Instalar dependências
```bash
pip install -r requirements.txt
```

### Iniciar

**Windows (PowerShell):**
```powershell
.\start.ps1
```

**Linux / macOS / Git Bash:**
```bash
chmod +x start.sh
./start.sh
```

Ou manualmente (dois terminais, na pasta do projeto):
```bash
# Terminal 1 — backend
python server.py

# Terminal 2 — frontend
python -m http.server 3000
```

No Windows, se `python server.py` falhar por encoding do console, use antes:
```powershell
$env:PYTHONIOENCODING = "utf-8"
```

Acesse: **http://localhost:3000** (não abra o `index.html` direto pelo Explorer)

---

## Contas de demonstração

| Tipo    | E-mail             | Senha  |
|---------|--------------------|--------|
| Gerador | carlos@email.com   | 123456 |
| Coletor | joao@email.com     | 123456 |

---

## API — Endpoints

### Auth
| Método | Rota               | Descrição        |
|--------|--------------------|------------------|
| POST   | /api/auth/cadastro | Criar conta      |
| POST   | /api/auth/login    | Login            |
| GET    | /api/auth/me       | Dados do usuário |

### Solicitações
| Método | Rota                              | Descrição              |
|--------|-----------------------------------|------------------------|
| POST   | /api/solicitacoes                 | Criar solicitação      |
| GET    | /api/solicitacoes?status=aberta   | Listar solicitações    |
| POST   | /api/solicitacoes/:id/aceitar     | Coletor aceita         |
| POST   | /api/solicitacoes/:id/confirmar   | Confirmar coleta       |
| POST   | /api/solicitacoes/:id/cancelar    | Cancelar               |
| GET    | /api/solicitacoes/:id/rastreio    | Posição simulada do coletor (status aceita) |

### Perfil e Stats
| Método | Rota         | Descrição             |
|--------|--------------|-----------------------|
| PUT    | /api/perfil  | Atualizar perfil      |
| GET    | /api/ranking | Top geradores         |
| GET    | /api/stats   | Estatísticas gerais   |

---

## Sistema de pontos

| Ação                      | Pontos       |
|---------------------------|--------------|
| Coleta concluída (base)   | +50 pts      |
| Por kg coletado           | +5 pts/kg    |
| Material especial         | +80 pts      |
| Constância semanal        | +100 pts/mês |
| Indicar amigos            | +200 pts     |
| Avaliar o coletor         | +10 pts      |

### Níveis
| Nível      | Pontos mínimos |
|------------|---------------|
| 🌱 Semente  | 0             |
| 🌿 Broto    | 500           |
| 🌳 Árvore   | 2.000         |
| ⭐ Guardião | 5.000         |
| 🏆 Herói Verde | 10.000     |

---

## Banco de dados (SQLite)

**Tabelas:**
- `usuarios` — perfis de geradores e coletores
- `solicitacoes` — pedidos de coleta com status
- `avaliacoes` — avaliações mútuas pós-coleta
- `badges` — conquistas dos usuários

---

## Próximos passos

- [ ] Mapa em tempo real (Google Maps / Leaflet)
- [ ] Notificações push
- [ ] Tela completa do coletor
- [ ] Avaliações pós-coleta
- [ ] Gamificação: badges automáticos
- [ ] Painel admin para prefeitura
- [ ] App mobile (React Native)
