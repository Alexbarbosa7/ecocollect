import sqlite3
import json
import hashlib
import hmac
import base64
import time
import os
import math
import urllib.request
import urllib.parse
from flask import Flask, request, jsonify, g, send_from_directory
from datetime import datetime

app = Flask(__name__)
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    return response

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        from flask import make_response
        r = make_response()
        r.headers["Access-Control-Allow-Origin"] = "*"
        r.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        r.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        return r

SECRET_KEY = "ecocollect_secret_2024"
DB_PATH = os.path.join(os.path.dirname(__file__), "ecocollect.db")
SIMULACAO_DURACAO_SEG = 120  # duração da viagem simulada (demo)

# Coordenadas aproximadas — Joinville/SC (demo, sem API externa)
BAIRROS_COORDS = {
    "boa vista": (-26.2980, -48.8420),
    "centro": (-26.3045, -48.8487),
    "america": (-26.2890, -48.8510),
    "bom retiro": (-26.3120, -48.8350),
    "gloria": (-26.3180, -48.8620),
    "itarare": (-26.2750, -48.8300),
    "jovelina": (-26.3350, -48.8400),
    "paraiso": (-26.2680, -48.8580),
}
JOINVILLE_PADRAO = (-26.3045, -48.8487)

# ─── banco de dados ───────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()

def _hash(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def geocode_endereco(endereco, bairro=None, cidade="Joinville", seed=0):
    """Geocodificação simulada estável para demo em Joinville."""
    chave = (bairro or "").strip().lower()
    if chave in BAIRROS_COORDS:
        base_lat, base_lng = BAIRROS_COORDS[chave]
    else:
        base_lat, base_lng = JOINVILLE_PADRAO
    h = int(hashlib.md5(f"{endereco}|{bairro}|{cidade}|{seed}".encode()).hexdigest()[:8], 16)
    off_lat = ((h % 1000) - 500) / 50000.0
    off_lng = (((h // 1000) % 1000) - 500) / 50000.0
    return round(base_lat + off_lat, 6), round(base_lng + off_lng, 6)

def migrate_db(db):
    """Adiciona colunas de rastreio/mapas em bancos criados antes da atualização."""
    cols = {row[1] for row in db.execute("PRAGMA table_info(solicitacoes)").fetchall()}
    novas_colunas = (
        ("lat", "REAL"),
        ("lng", "REAL"),
        ("origem_lat", "REAL"),
        ("origem_lng", "REAL"),
        ("rota_json", "TEXT"),
    )
    for col, tipo in novas_colunas:
        if col not in cols:
            db.execute(f"ALTER TABLE solicitacoes ADD COLUMN {col} {tipo}")
    db.commit()
    rows = db.execute(
        "SELECT id, endereco, bairro, cidade FROM solicitacoes WHERE lat IS NULL OR lng IS NULL"
    ).fetchall()
    for r in rows:
        lat, lng = geocode_endereco(r["endereco"], r["bairro"], r["cidade"] or "Joinville", r["id"])
        db.execute("UPDATE solicitacoes SET lat=?, lng=? WHERE id=?", (lat, lng, r["id"]))
    db.commit()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            senha_hash  TEXT NOT NULL,
            tipo        TEXT NOT NULL CHECK(tipo IN ('gerador','coletor')),
            roles       TEXT,
            telefone    TEXT,
            endereco    TEXT,
            cidade      TEXT DEFAULT 'Joinville',
            pontos      INTEGER DEFAULT 0,
            nivel       TEXT DEFAULT 'Semente',
            total_kg    REAL DEFAULT 0,
            total_coletas INTEGER DEFAULT 0,
            criado_em   TEXT DEFAULT (datetime('now')),
            foto_url    TEXT
        );

        CREATE TABLE IF NOT EXISTS solicitacoes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            gerador_id      INTEGER NOT NULL REFERENCES usuarios(id),
            coletor_id      INTEGER REFERENCES usuarios(id),
            status          TEXT DEFAULT 'aberta' CHECK(status IN ('aberta','aceita','coletada','cancelada')),
            materiais       TEXT NOT NULL,
            descricao       TEXT,
            endereco        TEXT NOT NULL,
            bairro          TEXT,
            cidade          TEXT DEFAULT 'Joinville',
            lat             REAL,
            lng             REAL,
            peso_estimado   REAL,
            peso_real       REAL,
            foto_confirmacao TEXT,
            pontos_ganhos   INTEGER DEFAULT 0,
            criado_em       TEXT DEFAULT (datetime('now')),
            aceito_em       TEXT,
            coletado_em     TEXT,
            origem_lat      REAL,
            origem_lng      REAL,
            rota_json       TEXT
        );

        CREATE TABLE IF NOT EXISTS avaliacoes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            solicitacao_id  INTEGER NOT NULL REFERENCES solicitacoes(id),
            avaliador_id    INTEGER NOT NULL REFERENCES usuarios(id),
            avaliado_id     INTEGER NOT NULL REFERENCES usuarios(id),
            nota            INTEGER NOT NULL CHECK(nota BETWEEN 1 AND 5),
            comentario      TEXT,
            criado_em       TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS badges (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
            tipo        TEXT NOT NULL,
            descricao   TEXT,
            ganho_em    TEXT DEFAULT (datetime('now'))
        );
    """)
    db.commit()
    migrate_db(db)

    # seed: usuários de demonstração
    try:
        db.execute("""
            INSERT INTO usuarios (nome, email, senha_hash, tipo, telefone, endereco, pontos, nivel, total_kg, total_coletas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("Carlos Mendes", "carlos@email.com", _hash("123456"),
              "gerador", "(47) 99999-1111", "Rua das Flores, 123 - Boa Vista",
              3100, "Árvore", 312.5, 47))
        db.execute("""
            INSERT INTO usuarios (nome, email, senha_hash, tipo, telefone, endereco, pontos, nivel, total_kg, total_coletas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("João Catador", "joao@email.com", _hash("123456"),
              "coletor", "(47) 98888-2222", "Rua dos Catadores, 45 - Centro",
              0, "Semente", 890.0, 120))
        lat1, lng1 = geocode_endereco("Rua das Flores, 123", "Boa Vista", "Joinville", 1)
        lat2, lng2 = geocode_endereco("Rua das Flores, 123", "Boa Vista", "Joinville", 2)
        db.execute("""
            INSERT INTO solicitacoes (gerador_id, status, materiais, descricao, endereco, bairro, peso_estimado, lat, lng)
            VALUES (1, 'aberta', '["Papelão","Plástico"]', 'Caixas de papelão e garrafas PET', 'Rua das Flores, 123', 'Boa Vista', 15.0, ?, ?)
        """, (lat1, lng1))
        db.execute("""
            INSERT INTO solicitacoes (gerador_id, status, materiais, descricao, endereco, bairro, peso_estimado, lat, lng)
            VALUES (1, 'aberta', '["Eletrônicos","Pilhas/baterias"]', 'Notebook antigo e pilhas usadas', 'Rua das Flores, 123', 'Boa Vista', 3.5, ?, ?)
        """, (lat2, lng2))
        db.commit()
    except sqlite3.IntegrityError:
        pass
    db.close()

def origem_coletor(dest_lat, dest_lng, coletor_id):
    """Ponto de partida simulado do coletor (~2–4 km do destino)."""
    ang = (coletor_id * 47 + int(dest_lat * 1000)) % 360
    rad = math.radians(ang)
    dist = 0.022 + (coletor_id % 5) * 0.003
    return (
        round(dest_lat + dist * math.cos(rad), 6),
        round(dest_lng + dist * math.sin(rad), 6),
    )

def gerar_rota(origem, destino, pontos=40):
    """Rota com leve curva (estilo navegação) entre origem e destino."""
    o_lat, o_lng = origem
    d_lat, d_lng = destino
    mx = (o_lat + d_lat) / 2
    my = (o_lng + d_lng) / 2
    dx, dy = d_lng - o_lng, d_lat - o_lat
    norm = math.hypot(dx, dy) or 1
    curva = 0.18 * math.hypot(dx, dy)
    cx = mx + (-dy / norm) * curva
    cy = my + (dx / norm) * curva
    rota = []
    for i in range(pontos):
        t = i / (pontos - 1)
        u = 1 - t
        lat = u * u * o_lat + 2 * u * t * cx + t * t * d_lat
        lng = u * u * o_lng + 2 * u * t * cy + t * t * d_lng
        rota.append([lat, lng])
    return rota

def interp_rota(pontos, progresso):
    """Interpola posição ao longo da rota (progresso 0..1)."""
    if not pontos:
        return JOINVILLE_PADRAO
    if progresso >= 1:
        return pontos[-1][0], pontos[-1][1]
    if progresso <= 0:
        return pontos[0][0], pontos[0][1]
    n = len(pontos) - 1
    pos = progresso * n
    i = min(int(pos), n - 1)
    frac = pos - i
    lat = pontos[i][0] + (pontos[i + 1][0] - pontos[i][0]) * frac
    lng = pontos[i][1] + (pontos[i + 1][1] - pontos[i][1]) * frac
    return lat, lng

def iniciar_rastreio(db, sol, coletor_id):
    """Define origem, destino e rota ao aceitar a coleta."""
    lat = sol["lat"]
    lng = sol["lng"]
    if lat is None or lng is None:
        lat, lng = geocode_endereco(sol["endereco"], sol["bairro"], sol["cidade"], sol["id"])
    o_lat, o_lng = origem_coletor(lat, lng, coletor_id)
    rota = gerar_rota((o_lat, o_lng), (lat, lng))
    db.execute("""
        UPDATE solicitacoes SET lat=?, lng=?, origem_lat=?, origem_lng=?, rota_json=?
        WHERE id=?
    """, (lat, lng, o_lat, o_lng, json.dumps(rota), sol["id"]))

def posicao_simulada(sol):
    """Calcula posição atual do coletor com base no tempo desde aceito_em."""
    if sol["status"] != "aceita" or not sol["aceito_em"]:
        return None
    try:
        aceito = datetime.strptime(sol["aceito_em"][:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        aceito = datetime.now()
    elapsed = max(0, (datetime.now() - aceito).total_seconds())
    progresso = min(1.0, elapsed / SIMULACAO_DURACAO_SEG)
    rota = json.loads(sol["rota_json"]) if sol["rota_json"] else []
    if not rota:
        o_lat, o_lng = sol["origem_lat"], sol["origem_lng"]
        d_lat, d_lng = sol["lat"], sol["lng"]
        if None in (o_lat, o_lng, d_lat, d_lng):
            return None
        rota = gerar_rota((o_lat, o_lng), (d_lat, d_lng))
    lat, lng = interp_rota(rota, progresso)
    restante = max(0, int(SIMULACAO_DURACAO_SEG - elapsed))
    dist_total = 0
    for i in range(1, len(rota)):
        dist_total += math.hypot(rota[i][0] - rota[i - 1][0], rota[i][1] - rota[i - 1][1])
    dist_restante = dist_total * (1 - progresso) * 111  # km aprox.
    return {
        "lat": lat,
        "lng": lng,
        "progresso": round(progresso, 3),
        "eta_segundos": restante,
        "eta_minutos": max(1, int(math.ceil(restante / 60))) if restante else 0,
        "chegou": progresso >= 1.0,
        "rota": rota,
    }

# ─── auth simples com token ───────────────────────────────────────

def criar_token(user_id, tipo):
    payload = f"{user_id}:{tipo}:{int(time.time()) + 86400 * 30}"
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{payload}:{sig}"
    return base64.b64encode(raw.encode()).decode()

def verificar_token(token):
    try:
        raw = base64.b64decode(token.encode()).decode()
        parts = raw.rsplit(":", 1)
        payload, sig = parts[0], parts[1]
        expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        uid, tipo, exp = payload.split(":")
        if int(exp) < int(time.time()):
            return None
        return {"id": int(uid), "tipo": tipo}
    except Exception:
        return None

def auth_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user = verificar_token(token)
        if not user:
            return jsonify({"erro": "Não autorizado"}), 401
        g.user = user
        return f(*args, **kwargs)
    return decorated

def calcular_pontos(materiais, peso_kg):
    base = 50
    por_kg = int((peso_kg or 0) * 5)
    especiais = {"Eletrônicos", "Pilhas", "Óleo de cozinha", "Pilhas/baterias"}
    bonus = 80 if any(m in especiais for m in (materiais or [])) else 0
    return base + por_kg + bonus

def atualizar_nivel(pontos):
    if pontos >= 10000: return "Herói Verde"
    if pontos >= 5000:  return "Guardião"
    if pontos >= 2000:  return "Árvore"
    if pontos >= 500:   return "Broto"
    return "Semente"


def get_roles_for_user(user_id):
    db = get_db()
    row = db.execute("SELECT roles, tipo FROM usuarios WHERE id=?", (user_id,)).fetchone()
    if not row:
        return []
    if row["roles"]:
        try:
            return json.loads(row["roles"])
        except Exception:
            return [row["tipo"]] if row["tipo"] else []
    return [row["tipo"]] if row["tipo"] else []


def has_role(role):
    try:
        return role in get_roles_for_user(g.user["id"])
    except Exception:
        return False

# ─── frontend (mesmo serviço no Render) ───────────────────────────

@app.route("/")
def serve_index():
    return send_from_directory(ROOT_DIR, "index.html")

@app.route("/api/auth/google-config", methods=["GET"])
def google_config():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    return jsonify({"google_client_id": client_id})

def verify_google_token(id_token):
    google_client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not google_client_id:
        return None
    try:
        url = "https://oauth2.googleapis.com/tokeninfo?id_token=" + urllib.parse.quote(id_token)
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data.get("aud") != google_client_id:
            return None
        if data.get("email_verified") not in ("true", "True", True, "1", 1):
            return None
        return data
    except Exception:
        return None

@app.route("/api/auth/google", methods=["POST"])
def google_login():
    d = request.get_json(silent=True) or {}
    id_token = d.get("id_token")
    if not id_token:
        return jsonify({"erro": "ID token do Google é obrigatório"}), 400
    payload = verify_google_token(id_token)
    if not payload:
        return jsonify({"erro": "Falha ao verificar token do Google"}), 401
    email = payload.get("email")
    nome = payload.get("name") or email.split("@")[0]
    tipo = d.get("tipo") if d.get("tipo") in ("gerador", "coletor", "ambos") else "gerador"
    db = get_db()
    user = db.execute("SELECT * FROM usuarios WHERE email=?", (email,)).fetchone()
    if user is None:
        try:
            roles_val = json.dumps(["gerador"]) if tipo == "gerador" else (json.dumps(["coletor"]) if tipo == "coletor" else json.dumps(["gerador","coletor"]))
            cur = db.execute(
                "INSERT INTO usuarios (nome, email, senha_hash, tipo, roles, telefone, endereco, foto_url) VALUES (?,?,?,?,?,?,?,?)",
                (nome, email, _hash(f"google:{email}"), ("gerador" if tipo=="ambos" else tipo), roles_val, None, None, payload.get("picture"))
            )
            db.commit()
            user = db.execute("SELECT * FROM usuarios WHERE id=?", (cur.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            return jsonify({"erro": "Erro ao criar usuário com Google"}), 500
    token = criar_token(user["id"], user["tipo"])
    return jsonify({"token": token, "usuario": _user_dict(user)})

# ─── rotas de autenticação ────────────────────────────────────────

@app.route("/api/auth/cadastro", methods=["POST"])
def cadastro():
    d = request.get_json(silent=True) or {}
    required = ["nome", "email", "senha", "tipo"]
    if not all(d.get(k) for k in required):
        return jsonify({"erro": "Campos obrigatórios: nome, email, senha, tipo"}), 400
    if d["tipo"] not in ("gerador", "coletor", "ambos"):
        return jsonify({"erro": "Tipo deve ser 'gerador', 'coletor' ou 'ambos'"}), 400
    db = get_db()
    try:
        # suportar escolha de roles (gerador, coletor, ambos)
        roles_val = json.dumps([d["tipo"]]) if d["tipo"] in ("gerador","coletor") else json.dumps(["gerador","coletor"])
        tipo_store = ("gerador" if d["tipo"] == "ambos" else d["tipo"])
        cur = db.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, tipo, roles, telefone, endereco) VALUES (?,?,?,?,?,?,?)",
            (d["nome"], d["email"], _hash(d["senha"]), tipo_store, roles_val,
             d.get("telefone"), d.get("endereco"))
        )
        db.commit()
        uid = cur.lastrowid
        token = criar_token(uid, tipo_store)
        user = db.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
        return jsonify({"token": token, "usuario": _user_dict(user)}), 201
    except sqlite3.IntegrityError:
        return jsonify({"erro": "E-mail já cadastrado"}), 409

@app.route("/api/auth/login", methods=["POST"])
def login():
    d = request.get_json(silent=True) or {}
    db = get_db()
    user = db.execute("SELECT * FROM usuarios WHERE email=? AND senha_hash=?",
                      (d.get("email"), _hash(d.get("senha","")))).fetchone()
    if not user:
        return jsonify({"erro": "E-mail ou senha incorretos"}), 401
    token = criar_token(user["id"], user["tipo"])
    return jsonify({"token": token, "usuario": _user_dict(user)})

@app.route("/api/auth/me", methods=["GET"])
@auth_required
def me():
    db = get_db()
    user = db.execute("SELECT * FROM usuarios WHERE id=?", (g.user["id"],)).fetchone()
    return jsonify(_user_dict(user))

def _user_dict(u):
    roles = []
    try:
        if u.get("roles"):
            roles = json.loads(u.get("roles"))
        else:
            roles = [u.get("tipo")]
    except Exception:
        roles = [u.get("tipo")]
    return {
        "id": u["id"], "nome": u["nome"], "email": u["email"],
        "tipo": u["tipo"], "roles": roles, "telefone": u["telefone"],
        "endereco": u["endereco"], "cidade": u["cidade"],
        "pontos": u["pontos"], "nivel": u["nivel"],
        "total_kg": u["total_kg"], "total_coletas": u["total_coletas"],
        "foto_url": u["foto_url"],
        "criado_em": u["criado_em"]
    }

# ─── rotas de solicitações ────────────────────────────────────────

@app.route("/api/solicitacoes", methods=["POST"])
@auth_required
def criar_solicitacao():
    if not has_role("gerador"):
        return jsonify({"erro": "Apenas geradores podem criar solicitações"}), 403
    d = request.get_json(silent=True) or {}
    if not d.get("materiais") or not d.get("endereco"):
        return jsonify({"erro": "Materiais e endereço são obrigatórios"}), 400
    db = get_db()
    lat, lng = geocode_endereco(d["endereco"], d.get("bairro"), d.get("cidade", "Joinville"))
    cur = db.execute("""
        INSERT INTO solicitacoes (gerador_id, materiais, descricao, endereco, bairro, peso_estimado, lat, lng)
        VALUES (?,?,?,?,?,?,?,?)
    """, (g.user["id"], json.dumps(d["materiais"]), d.get("descricao"),
          d["endereco"], d.get("bairro"), d.get("peso_estimado"), lat, lng))
    db.commit()
    sol = db.execute("SELECT * FROM solicitacoes WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(_sol_dict(sol)), 201

@app.route("/api/solicitacoes", methods=["GET"])
@auth_required
def listar_solicitacoes():
    db = get_db()
    status = request.args.get("status", "aberta")
    if has_role("coletor"):
        if status == "aceita":
            rows = db.execute("""
                SELECT s.*, u.nome as gerador_nome, u.telefone as gerador_tel
                FROM solicitacoes s JOIN usuarios u ON s.gerador_id = u.id
                WHERE s.status='aceita' AND s.coletor_id=?
                ORDER BY s.aceito_em DESC
            """, (g.user["id"],)).fetchall()
        else:
            rows = db.execute("""
                SELECT s.*, u.nome as gerador_nome, u.telefone as gerador_tel
                FROM solicitacoes s JOIN usuarios u ON s.gerador_id = u.id
                WHERE s.status=? ORDER BY s.criado_em DESC
            """, (status,)).fetchall()
    else:
        rows = db.execute("""
            SELECT s.*, u.nome as gerador_nome, u.telefone as gerador_tel
            FROM solicitacoes s JOIN usuarios u ON s.gerador_id = u.id
            WHERE s.gerador_id=? AND s.status=? ORDER BY s.criado_em DESC
        """, (g.user["id"], status)).fetchall()
    return jsonify([_sol_dict(r) for r in rows])

@app.route("/api/solicitacoes/<int:sid>/aceitar", methods=["POST"])
@auth_required
def aceitar_solicitacao(sid):
    if not has_role("coletor"):
        return jsonify({"erro": "Apenas coletores podem aceitar"}), 403
    db = get_db()
    sol = db.execute("SELECT * FROM solicitacoes WHERE id=?", (sid,)).fetchone()
    if not sol or sol["status"] != "aberta":
        return jsonify({"erro": "Solicitação não disponível"}), 400
    iniciar_rastreio(db, sol, g.user["id"])
    db.execute(
        "UPDATE solicitacoes SET status='aceita', coletor_id=?, aceito_em=datetime('now') WHERE id=?",
        (g.user["id"], sid),
    )
    db.commit()
    return jsonify({"ok": True, "mensagem": "Coleta aceita! Vá até o endereço."})

@app.route("/api/solicitacoes/<int:sid>/confirmar", methods=["POST"])
@auth_required
def confirmar_coleta(sid):
    if not has_role("gerador"):
        return jsonify({"erro": "Apenas o gerador pode confirmar a coleta"}), 403
    db = get_db()
    sol = db.execute("SELECT * FROM solicitacoes WHERE id=?", (sid,)).fetchone()
    if not sol or sol["gerador_id"] != g.user["id"] or sol["status"] != "aceita":
        return jsonify({"erro": "Solicitação não está aceita"}), 400
    d = request.json or {}
    peso_real = d.get("peso_real", sol["peso_estimado"] or 1)
    materiais = json.loads(sol["materiais"])
    pts = calcular_pontos(materiais, peso_real)
    db.execute("""
        UPDATE solicitacoes SET status='coletada', peso_real=?, pontos_ganhos=?,
        coletado_em=datetime('now') WHERE id=?
    """, (peso_real, pts, sid))
    novo_pts = (db.execute("SELECT pontos FROM usuarios WHERE id=?",
                (sol["gerador_id"],)).fetchone()["pontos"]) + pts
    nivel = atualizar_nivel(novo_pts)
    db.execute("UPDATE usuarios SET pontos=?, nivel=?, total_kg=total_kg+?, total_coletas=total_coletas+1 WHERE id=?",
               (novo_pts, nivel, peso_real, sol["gerador_id"]))
    db.execute("UPDATE usuarios SET total_kg=total_kg+?, total_coletas=total_coletas+1 WHERE id=?",
               (peso_real, sol["coletor_id"]))
    db.commit()
    return jsonify({"ok": True, "pontos_ganhos": pts, "total_pontos": novo_pts, "nivel": nivel})

@app.route("/api/solicitacoes/<int:sid>/cancelar", methods=["POST"])
@auth_required
def cancelar_solicitacao(sid):
    db = get_db()
    sol = db.execute("SELECT * FROM solicitacoes WHERE id=?", (sid,)).fetchone()
    if not sol or sol["gerador_id"] != g.user["id"] or sol["status"] not in ("aberta",):
        return jsonify({"erro": "Não é possível cancelar"}), 400
    db.execute("UPDATE solicitacoes SET status='cancelada' WHERE id=?", (sid,))
    db.commit()
    return jsonify({"ok": True})

def _sol_dict(r):
    d = dict(r)
    if isinstance(d.get("materiais"), str):
        try:
            d["materiais"] = json.loads(d["materiais"])
        except json.JSONDecodeError:
            d["materiais"] = []
    d.pop("rota_json", None)
    return d

@app.route("/api/solicitacoes/<int:sid>/rastreio", methods=["GET"])
@auth_required
def rastreio_solicitacao(sid):
    db = get_db()
    sol = db.execute("""
        SELECT s.*, c.nome as coletor_nome, c.telefone as coletor_tel
        FROM solicitacoes s
        LEFT JOIN usuarios c ON s.coletor_id = c.id
        WHERE s.id=?
    """, (sid,)).fetchone()
    if not sol:
        return jsonify({"erro": "Solicitação não encontrada"}), 404
    # permitir acesso se o usuário for o gerador da solicitação ou o coletor designado
    is_allowed = False
    if has_role("gerador") and sol["gerador_id"] == g.user["id"]:
        is_allowed = True
    if has_role("coletor") and sol["coletor_id"] == g.user["id"]:
        is_allowed = True
    if not is_allowed:
        return jsonify({"erro": "Acesso negado"}), 403
    if sol["status"] != "aceita":
        return jsonify({
            "ativo": False,
            "status": sol["status"],
            "mensagem": "Rastreio disponível apenas com coletor a caminho",
        })
    if not sol["rota_json"] or sol["origem_lat"] is None:
        iniciar_rastreio(db, sol, sol["coletor_id"] or 1)
        if not sol["aceito_em"]:
            db.execute(
                "UPDATE solicitacoes SET aceito_em=datetime('now') WHERE id=? AND aceito_em IS NULL",
                (sid,),
            )
        db.commit()
        sol = db.execute("""
            SELECT s.*, c.nome as coletor_nome, c.telefone as coletor_tel
            FROM solicitacoes s
            LEFT JOIN usuarios c ON s.coletor_id = c.id
            WHERE s.id=?
        """, (sid,)).fetchone()
    sim = posicao_simulada(sol)
    if not sim:
        return jsonify({"erro": "Rastreio indisponível"}), 400
    dest = {"lat": sol["lat"], "lng": sol["lng"], "endereco": sol["endereco"], "bairro": sol["bairro"]}
    origem = {"lat": sol["origem_lat"], "lng": sol["origem_lng"]}
    return jsonify({
        "ativo": True,
        "solicitacao_id": sid,
        "status": sol["status"],
        "coletor": {"nome": sol["coletor_nome"], "telefone": sol["coletor_tel"]},
        "destino": dest,
        "origem": origem,
        "coletor_pos": {"lat": sim["lat"], "lng": sim["lng"]},
        "rota": sim["rota"],
        "progresso": sim["progresso"],
        "eta_segundos": sim["eta_segundos"],
        "eta_minutos": sim["eta_minutos"],
        "chegou": sim["chegou"],
        "duracao_total_seg": SIMULACAO_DURACAO_SEG,
    })

# ─── rotas de perfil e ranking ────────────────────────────────────

@app.route("/api/perfil", methods=["PUT"])
@auth_required
def atualizar_perfil():
    d = request.get_json(silent=True) or {}
    nome = (d.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "Nome é obrigatório"}), 400
    db = get_db()
    db.execute("UPDATE usuarios SET nome=?, telefone=?, endereco=? WHERE id=?",
               (nome, d.get("telefone"), d.get("endereco"), g.user["id"]))
    db.commit()
    user = db.execute("SELECT * FROM usuarios WHERE id=?", (g.user["id"],)).fetchone()
    return jsonify(_user_dict(user))

@app.route("/api/ranking", methods=["GET"])
@auth_required
def ranking():
    db = get_db()
    rows = db.execute("""
        SELECT nome, pontos, nivel, total_kg, total_coletas
        FROM usuarios WHERE roles LIKE '%"gerador"%'
        ORDER BY pontos DESC LIMIT 10
    """).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/stats", methods=["GET"])
def stats_gerais():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    r = db.execute("""
        SELECT
          COUNT(*) as total_solicitacoes,
          SUM(CASE WHEN status='coletada' THEN 1 ELSE 0 END) as total_coletadas,
          SUM(CASE WHEN status='aberta' THEN 1 ELSE 0 END) as abertas,
          SUM(COALESCE(peso_real,0)) as total_kg,
          (SELECT COUNT(*) FROM usuarios WHERE roles LIKE '%"gerador"%') as geradores,
          (SELECT COUNT(*) FROM usuarios WHERE roles LIKE '%"coletor"%') as coletores
        FROM solicitacoes
    """).fetchone()
    db.close()
    return jsonify(dict(r))

# ─── inicialização ────────────────────────────────────────────────

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    print(f"EcoCollect rodando em http://localhost:{port}")
    print("Banco de dados:", DB_PATH)
    app.run(debug=debug, host="0.0.0.0", port=port)
