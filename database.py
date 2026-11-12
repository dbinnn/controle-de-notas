import json
import os
import sqlite3
from datetime import date, datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "controle_notas.db")
SEED_PATH = os.path.join(BASE_DIR, "empresas_seed.json")


def agora_iso():
    return datetime.now().isoformat(timespec="seconds")


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _colunas(conn, tabela):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}


def _adicionar_coluna(conn, tabela, definicao):
    nome = definicao.split()[0]
    if nome not in _colunas(conn, tabela):
        conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {definicao}")


def init_db():
    conn = get_db()
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS empresas (
            codigo INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            cnpj TEXT,
            ativa INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT,
            atualizado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            codigo INTEGER NOT NULL,
            tipo_nota TEXT,
            qtd_nf INTEGER NOT NULL DEFAULT 0,
            qtd_nfs INTEGER NOT NULL DEFAULT 0,
            qtd_cte INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0,
            observacao TEXT,
            responsavel TEXT,
            status TEXT NOT NULL DEFAULT 'PENDENTE',
            prazo TEXT,
            observacoes_internas TEXT,
            lancado_por TEXT,
            criado_em TEXT NOT NULL,
            atualizado_por TEXT,
            atualizado_em TEXT,
            concluido_em TEXT,
            excluido INTEGER NOT NULL DEFAULT 0,
            excluido_por TEXT,
            excluido_em TEXT,
            FOREIGN KEY (codigo) REFERENCES empresas (codigo)
        );

        CREATE TABLE IF NOT EXISTS meses_fechados (
            mes TEXT PRIMARY KEY,
            fechado_por TEXT,
            fechado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS historico_lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lancamento_id INTEGER,
            acao TEXT NOT NULL,
            usuario TEXT,
            data_hora TEXT NOT NULL,
            dados_antes TEXT,
            dados_depois TEXT,
            detalhes TEXT
        );
        """
    )

    # Migrações para bancos de versões anteriores.
    for definicao in (
        "ativa INTEGER NOT NULL DEFAULT 1",
        "criado_em TEXT",
        "atualizado_em TEXT",
    ):
        _adicionar_coluna(conn, "empresas", definicao)

    for definicao in (
        "observacao TEXT",
        "responsavel TEXT",
        "status TEXT NOT NULL DEFAULT 'PENDENTE'",
        "prazo TEXT",
        "observacoes_internas TEXT",
        "lancado_por TEXT",
        "atualizado_por TEXT",
        "atualizado_em TEXT",
        "concluido_em TEXT",
        "excluido INTEGER NOT NULL DEFAULT 0",
        "excluido_por TEXT",
        "excluido_em TEXT",
    ):
        _adicionar_coluna(conn, "lancamentos", definicao)

    agora = agora_iso()
    conn.execute("UPDATE empresas SET ativa = 1 WHERE ativa IS NULL")
    conn.execute("UPDATE empresas SET criado_em = ? WHERE criado_em IS NULL OR criado_em = ''", (agora,))
    conn.execute("UPDATE lancamentos SET status = 'PENDENTE' WHERE status IS NULL OR status = ''")
    conn.execute("UPDATE lancamentos SET excluido = 0 WHERE excluido IS NULL")
    conn.execute(
        "UPDATE lancamentos SET criado_em = criado_em || 'T00:00:00' "
        "WHERE length(criado_em) = 10"
    )
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_lancamentos_data ON lancamentos(data);
        CREATE INDEX IF NOT EXISTS idx_lancamentos_codigo ON lancamentos(codigo);
        CREATE INDEX IF NOT EXISTS idx_lancamentos_status ON lancamentos(status);
        CREATE INDEX IF NOT EXISTS idx_lancamentos_excluido ON lancamentos(excluido);
        CREATE INDEX IF NOT EXISTS idx_historico_lancamento ON historico_lancamentos(lancamento_id);
        """
    )
    conn.commit()
    conn.close()
    sync_empresas()


def sync_empresas():
    """Inclui empresas do seed somente quando o código ainda não existe.

    Dados alterados pelo usuário no painel nunca são sobrescritos ao reiniciar.
    """
    if not os.path.exists(SEED_PATH):
        return
    try:
        with open(SEED_PATH, encoding="utf-8") as arquivo:
            empresas = json.load(arquivo)
    except (OSError, json.JSONDecodeError):
        return

    agora = agora_iso()
    conn = get_db()
    for empresa in empresas:
        conn.execute(
            """
            INSERT OR IGNORE INTO empresas
                (codigo, nome, cnpj, ativa, criado_em)
            VALUES (?, ?, ?, 1, ?)
            """,
            (empresa.get("codigo"), empresa.get("nome"), empresa.get("cnpj", ""), agora),
        )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------
# Empresas
# ------------------------------------------------------------------
def get_empresas(ativas=True):
    conn = get_db()
    where = "WHERE ativa = 1" if ativas is True else "WHERE ativa = 0" if ativas is False else ""
    rows = conn.execute(f"SELECT * FROM empresas {where} ORDER BY nome COLLATE NOCASE").fetchall()
    conn.close()
    return rows


def listar_empresas(busca=None, situacao="ativas", page=1, per_page=20):
    where = []
    params = []
    if situacao == "ativas":
        where.append("e.ativa = 1")
    elif situacao == "inativas":
        where.append("e.ativa = 0")
    if busca:
        termo = f"%{busca.lower()}%"
        where.append("(CAST(e.codigo AS TEXT) LIKE ? OR lower(e.nome) LIKE ? OR lower(COALESCE(e.cnpj,'')) LIKE ?)")
        params.extend([termo, termo, termo])
    where_sql = "WHERE " + " AND ".join(where) if where else ""

    conn = get_db()
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM empresas e {where_sql}", params
    ).fetchone()["n"]
    offset = max(page - 1, 0) * per_page
    rows = conn.execute(
        f"""
        SELECT e.*,
               COUNT(l.id) AS lancamentos_total,
               SUM(CASE WHEN l.excluido = 0 THEN 1 ELSE 0 END) AS lancamentos_ativos
        FROM empresas e
        LEFT JOIN lancamentos l ON l.codigo = e.codigo
        {where_sql}
        GROUP BY e.codigo
        ORDER BY e.nome COLLATE NOCASE
        LIMIT ? OFFSET ?
        """,
        params + [per_page, offset],
    ).fetchall()
    conn.close()
    return rows, total


def get_empresa(codigo):
    conn = get_db()
    row = conn.execute(
        """
        SELECT e.*,
               COUNT(l.id) AS lancamentos_total,
               SUM(CASE WHEN l.excluido = 0 THEN 1 ELSE 0 END) AS lancamentos_ativos
        FROM empresas e LEFT JOIN lancamentos l ON l.codigo = e.codigo
        WHERE e.codigo = ? GROUP BY e.codigo
        """,
        (codigo,),
    ).fetchone()
    conn.close()
    return row


def add_empresa(codigo, nome, cnpj, ativa=True):
    agora = agora_iso()
    conn = get_db()
    conn.execute(
        "INSERT INTO empresas (codigo, nome, cnpj, ativa, criado_em) VALUES (?, ?, ?, ?, ?)",
        (codigo, nome, cnpj, 1 if ativa else 0, agora),
    )
    conn.commit()
    conn.close()


def update_empresa(codigo, nome, cnpj, ativa=True):
    conn = get_db()
    conn.execute(
        "UPDATE empresas SET nome = ?, cnpj = ?, ativa = ?, atualizado_em = ? WHERE codigo = ?",
        (nome, cnpj, 1 if ativa else 0, agora_iso(), codigo),
    )
    conn.commit()
    conn.close()


def upsert_empresa_importacao(codigo, nome, cnpj, ativa=True):
    agora = agora_iso()
    conn = get_db()
    existente = conn.execute("SELECT codigo FROM empresas WHERE codigo = ?", (codigo,)).fetchone()
    if existente:
        conn.execute(
            "UPDATE empresas SET nome = ?, cnpj = ?, ativa = ?, atualizado_em = ? WHERE codigo = ?",
            (nome, cnpj, 1 if ativa else 0, agora, codigo),
        )
        acao = "atualizada"
    else:
        conn.execute(
            "INSERT INTO empresas (codigo, nome, cnpj, ativa, criado_em) VALUES (?, ?, ?, ?, ?)",
            (codigo, nome, cnpj, 1 if ativa else 0, agora),
        )
        acao = "cadastrada"
    conn.commit()
    conn.close()
    return acao


def set_empresa_ativa(codigo, ativa):
    conn = get_db()
    conn.execute(
        "UPDATE empresas SET ativa = ?, atualizado_em = ? WHERE codigo = ?",
        (1 if ativa else 0, agora_iso(), codigo),
    )
    conn.commit()
    conn.close()


def delete_empresa(codigo):
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) AS n FROM lancamentos WHERE codigo = ?", (codigo,)).fetchone()["n"]
    if total:
        conn.close()
        return False
    conn.execute("DELETE FROM empresas WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()
    return True


# ------------------------------------------------------------------
# Histórico / auditoria
# ------------------------------------------------------------------
def _serializar(dados):
    return json.dumps(dados, ensure_ascii=False, default=str, sort_keys=True) if dados is not None else None


def _row_dict(row):
    return dict(row) if row is not None else None


def _registrar_historico(conn, lancamento_id, acao, usuario, antes=None, depois=None, detalhes=None):
    conn.execute(
        """
        INSERT INTO historico_lancamentos
            (lancamento_id, acao, usuario, data_hora, dados_antes, dados_depois, detalhes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (lancamento_id, acao, usuario, agora_iso(), _serializar(antes), _serializar(depois), detalhes),
    )


def listar_historico(page=1, per_page=30, busca=None, acao=None, lancamento_id=None):
    where = []
    params = []
    if acao:
        where.append("h.acao = ?")
        params.append(acao)
    if lancamento_id:
        where.append("h.lancamento_id = ?")
        params.append(lancamento_id)
    if busca:
        termo = f"%{busca.lower()}%"
        where.append("(lower(COALESCE(h.usuario,'')) LIKE ? OR lower(COALESCE(h.detalhes,'')) LIKE ? OR CAST(h.lancamento_id AS TEXT) LIKE ?)")
        params.extend([termo, termo, termo])
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    conn = get_db()
    total = conn.execute(f"SELECT COUNT(*) AS n FROM historico_lancamentos h {where_sql}", params).fetchone()["n"]
    offset = max(page - 1, 0) * per_page
    rows = conn.execute(
        f"""
        SELECT h.*, e.nome AS empresa, l.codigo, l.data
        FROM historico_lancamentos h
        LEFT JOIN lancamentos l ON l.id = h.lancamento_id
        LEFT JOIN empresas e ON e.codigo = l.codigo
        {where_sql}
        ORDER BY h.id DESC LIMIT ? OFFSET ?
        """,
        params + [per_page, offset],
    ).fetchall()
    conn.close()
    return rows, total


def get_acoes_historico():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT acao FROM historico_lancamentos ORDER BY acao").fetchall()
    conn.close()
    return [r["acao"] for r in rows]


# ------------------------------------------------------------------
# Lançamentos
# ------------------------------------------------------------------
def _where_lancamentos(empresa=None, data_de=None, data_ate=None, tipo_nota=None,
                       status=None, responsavel=None, busca=None, excluidos=False, mes=None):
    where = ["l.excluido = ?"]
    params = [1 if excluidos else 0]
    if empresa:
        where.append("l.codigo = ?")
        params.append(empresa)
    if data_de:
        where.append("l.data >= ?")
        params.append(data_de)
    if data_ate:
        where.append("l.data <= ?")
        params.append(data_ate)
    if mes:
        where.append("substr(l.data, 1, 7) = ?")
        params.append(mes)
    if tipo_nota:
        where.append("l.tipo_nota = ?")
        params.append(tipo_nota)
    if status:
        where.append("l.status = ?")
        params.append(status)
    if responsavel:
        where.append("l.responsavel = ?")
        params.append(responsavel)
    if busca:
        termo = f"%{busca.lower()}%"
        where.append(
            "(CAST(l.codigo AS TEXT) LIKE ? OR lower(e.nome) LIKE ? OR "
            "lower(COALESCE(e.cnpj,'')) LIKE ? OR lower(COALESCE(l.observacao,'')) LIKE ?)"
        )
        params.extend([termo, termo, termo, termo])
    return "WHERE " + " AND ".join(where), params


def _enriquecer_lancamento(row):
    item = dict(row)
    item["atrasado"] = bool(
        item.get("prazo")
        and item.get("status") in ("PENDENTE", "EM_ANDAMENTO")
        and item["prazo"] < date.today().isoformat()
    )
    item["vence_hoje"] = bool(
        item.get("prazo") == date.today().isoformat()
        and item.get("status") in ("PENDENTE", "EM_ANDAMENTO")
    )
    return item


def listar_lancamentos(page=1, per_page=20, order="desc", **filtros):
    order = "ASC" if str(order).lower() == "asc" else "DESC"
    where_sql, params = _where_lancamentos(**filtros)
    conn = get_db()
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM lancamentos l JOIN empresas e ON e.codigo = l.codigo {where_sql}",
        params,
    ).fetchone()["n"]
    offset = max(page - 1, 0) * per_page
    rows = conn.execute(
        f"""
        SELECT l.*, e.nome AS empresa, e.cnpj AS cnpj, e.ativa AS empresa_ativa
        FROM lancamentos l JOIN empresas e ON e.codigo = l.codigo
        {where_sql}
        ORDER BY l.data {order}, l.id {order}
        LIMIT ? OFFSET ?
        """,
        params + [per_page, offset],
    ).fetchall()
    conn.close()
    return [_enriquecer_lancamento(r) for r in rows], total


def get_lancamentos(order="desc", **filtros):
    order = "ASC" if str(order).lower() == "asc" else "DESC"
    where_sql, params = _where_lancamentos(**filtros)
    conn = get_db()
    rows = conn.execute(
        f"""
        SELECT l.*, e.nome AS empresa, e.cnpj AS cnpj, e.ativa AS empresa_ativa
        FROM lancamentos l JOIN empresas e ON e.codigo = l.codigo
        {where_sql}
        ORDER BY l.data {order}, l.id {order}
        """,
        params,
    ).fetchall()
    conn.close()
    return [_enriquecer_lancamento(r) for r in rows]


def get_lancamento(lanc_id, incluir_excluido=True):
    conn = get_db()
    where_excluido = "" if incluir_excluido else "AND l.excluido = 0"
    row = conn.execute(
        f"""
        SELECT l.*, e.nome AS empresa, e.cnpj AS cnpj, e.ativa AS empresa_ativa
        FROM lancamentos l JOIN empresas e ON e.codigo = l.codigo
        WHERE l.id = ? {where_excluido}
        """,
        (lanc_id,),
    ).fetchone()
    conn.close()
    return _enriquecer_lancamento(row) if row else None


def encontrar_duplicado(data_str, codigo, tipo_nota, qtd_nf, qtd_nfs, qtd_cte, excluir_id=None):
    conn = get_db()
    sql = """
        SELECT l.*, e.nome AS empresa
        FROM lancamentos l JOIN empresas e ON e.codigo = l.codigo
        WHERE l.excluido = 0 AND l.data = ? AND l.codigo = ?
          AND COALESCE(l.tipo_nota,'') = ? AND l.qtd_nf = ? AND l.qtd_nfs = ? AND l.qtd_cte = ?
    """
    params = [data_str, codigo, tipo_nota or "", qtd_nf, qtd_nfs, qtd_cte]
    if excluir_id:
        sql += " AND l.id <> ?"
        params.append(excluir_id)
    sql += " ORDER BY l.id DESC LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


def add_lancamento(data_str, codigo, tipo_nota, qtd_nf, qtd_nfs, qtd_cte,
                    observacao, responsavel, status, prazo, observacoes_internas,
                    lancado_por=None):
    total = qtd_nf + qtd_nfs + qtd_cte
    agora = agora_iso()
    concluido_em = agora if status == "CONCLUIDA" else None
    conn = get_db()
    cursor = conn.execute(
        """
        INSERT INTO lancamentos
            (data, codigo, tipo_nota, qtd_nf, qtd_nfs, qtd_cte, total,
             observacao, responsavel, status, prazo, observacoes_internas,
             lancado_por, criado_em, concluido_em, excluido)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (data_str, codigo, tipo_nota, qtd_nf, qtd_nfs, qtd_cte, total,
         observacao, responsavel, status, prazo or None, observacoes_internas,
         lancado_por, agora, concluido_em),
    )
    lanc_id = cursor.lastrowid
    depois = _row_dict(conn.execute("SELECT * FROM lancamentos WHERE id = ?", (lanc_id,)).fetchone())
    _registrar_historico(conn, lanc_id, "CRIACAO", lancado_por, depois=depois)
    conn.commit()
    conn.close()
    return lanc_id


def update_lancamento(lanc_id, data_str, codigo, tipo_nota, qtd_nf, qtd_nfs, qtd_cte,
                       observacao, responsavel, status, prazo, observacoes_internas,
                       usuario=None):
    total = qtd_nf + qtd_nfs + qtd_cte
    conn = get_db()
    antes_row = conn.execute("SELECT * FROM lancamentos WHERE id = ?", (lanc_id,)).fetchone()
    if not antes_row:
        conn.close()
        return False
    antes = _row_dict(antes_row)
    if status == "CONCLUIDA":
        concluido_em = antes.get("concluido_em") or agora_iso()
    else:
        concluido_em = None
    conn.execute(
        """
        UPDATE lancamentos
        SET data = ?, codigo = ?, tipo_nota = ?, qtd_nf = ?, qtd_nfs = ?, qtd_cte = ?,
            total = ?, observacao = ?, responsavel = ?, status = ?, prazo = ?,
            observacoes_internas = ?, atualizado_por = ?, atualizado_em = ?, concluido_em = ?
        WHERE id = ?
        """,
        (data_str, codigo, tipo_nota, qtd_nf, qtd_nfs, qtd_cte, total,
         observacao, responsavel, status, prazo or None, observacoes_internas,
         usuario, agora_iso(), concluido_em, lanc_id),
    )
    depois = _row_dict(conn.execute("SELECT * FROM lancamentos WHERE id = ?", (lanc_id,)).fetchone())
    _registrar_historico(conn, lanc_id, "ALTERACAO", usuario, antes=antes, depois=depois)
    conn.commit()
    conn.close()
    return True


def soft_delete_lancamento(lanc_id, usuario=None, motivo=None):
    conn = get_db()
    antes_row = conn.execute("SELECT * FROM lancamentos WHERE id = ?", (lanc_id,)).fetchone()
    if not antes_row:
        conn.close()
        return False
    antes = _row_dict(antes_row)
    conn.execute(
        "UPDATE lancamentos SET excluido = 1, excluido_por = ?, excluido_em = ? WHERE id = ?",
        (usuario, agora_iso(), lanc_id),
    )
    depois = _row_dict(conn.execute("SELECT * FROM lancamentos WHERE id = ?", (lanc_id,)).fetchone())
    _registrar_historico(conn, lanc_id, "EXCLUSAO", usuario, antes=antes, depois=depois, detalhes=motivo)
    conn.commit()
    conn.close()
    return True


def restaurar_lancamento(lanc_id, usuario=None):
    conn = get_db()
    antes_row = conn.execute("SELECT * FROM lancamentos WHERE id = ? AND excluido = 1", (lanc_id,)).fetchone()
    if not antes_row:
        conn.close()
        return False
    antes = _row_dict(antes_row)
    conn.execute(
        "UPDATE lancamentos SET excluido = 0, excluido_por = NULL, excluido_em = NULL WHERE id = ?",
        (lanc_id,),
    )
    depois = _row_dict(conn.execute("SELECT * FROM lancamentos WHERE id = ?", (lanc_id,)).fetchone())
    _registrar_historico(conn, lanc_id, "RESTAURACAO", usuario, antes=antes, depois=depois)
    conn.commit()
    conn.close()
    return True


def excluir_lancamento_definitivamente(lanc_id, usuario=None):
    conn = get_db()
    antes_row = conn.execute("SELECT * FROM lancamentos WHERE id = ? AND excluido = 1", (lanc_id,)).fetchone()
    if not antes_row:
        conn.close()
        return False
    antes = _row_dict(antes_row)
    _registrar_historico(conn, lanc_id, "EXCLUSAO_DEFINITIVA", usuario, antes=antes)
    conn.execute("DELETE FROM lancamentos WHERE id = ?", (lanc_id,))
    conn.commit()
    conn.close()
    return True


def clear_lancamentos(usuario=None):
    conn = get_db()
    rows = conn.execute("SELECT * FROM lancamentos WHERE excluido = 0").fetchall()
    agora = agora_iso()
    for row in rows:
        antes = _row_dict(row)
        conn.execute(
            "UPDATE lancamentos SET excluido = 1, excluido_por = ?, excluido_em = ? WHERE id = ?",
            (usuario, agora, row["id"]),
        )
        depois = dict(antes)
        depois.update({"excluido": 1, "excluido_por": usuario, "excluido_em": agora})
        _registrar_historico(
            conn, row["id"], "EXCLUSAO_EM_LOTE", usuario,
            antes=antes, depois=depois, detalhes="Limpar todos os lançamentos",
        )
    conn.commit()
    conn.close()
    return len(rows)


def get_responsaveis():
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT responsavel FROM lancamentos WHERE responsavel IS NOT NULL AND trim(responsavel) <> '' ORDER BY responsavel"
    ).fetchall()
    conn.close()
    return [r["responsavel"] for r in rows]


# ------------------------------------------------------------------
# Resumo e acompanhamento
# ------------------------------------------------------------------
def calcular_resumo(codigo_filtro, mes_str):
    import calendar

    filtros = ["l.excluido = 0", "substr(l.data, 1, 7) = ?"]
    params = [mes_str]
    if codigo_filtro:
        filtros.append("l.codigo = ?")
        params.append(codigo_filtro)
    where = "WHERE " + " AND ".join(filtros)

    conn = get_db()
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(qtd_nf),0) AS nf,
               COALESCE(SUM(qtd_nfs),0) AS nfs,
               COALESCE(SUM(qtd_cte),0) AS cte,
               COALESCE(SUM(total),0) AS geral,
               MIN(data) AS primeira, MAX(data) AS ultima, COUNT(*) AS n
        FROM lancamentos l {where}
        """,
        params,
    ).fetchone()

    status_rows = conn.execute(
        f"SELECT status, COUNT(*) AS n FROM lancamentos l {where} GROUP BY status",
        params,
    ).fetchall()
    status_contagem = {r["status"]: r["n"] for r in status_rows}

    top = conn.execute(
        f"""
        SELECT e.codigo, e.nome, SUM(l.total) AS total
        FROM lancamentos l JOIN empresas e ON e.codigo = l.codigo
        {where}
        GROUP BY e.codigo, e.nome
        ORDER BY total DESC, e.nome COLLATE NOCASE
        LIMIT 1
        """,
        params,
    ).fetchone()

    empresa_nome = None
    if codigo_filtro:
        emp = conn.execute("SELECT nome FROM empresas WHERE codigo = ?", (codigo_filtro,)).fetchone()
        empresa_nome = emp["nome"] if emp else None

    ano, mes = map(int, mes_str.split("-"))
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    agregados = conn.execute(
        f"""
        SELECT data, SUM(qtd_nf) AS nf, SUM(qtd_nfs) AS nfs,
               SUM(qtd_cte) AS cte, SUM(total) AS total
        FROM lancamentos l {where}
        GROUP BY data
        """,
        params,
    ).fetchall()
    por_data = {r["data"]: r for r in agregados}
    day_rows = []
    for dia in range(1, ultimo_dia + 1):
        data_dia = f"{ano:04d}-{mes:02d}-{dia:02d}"
        r = por_data.get(data_dia)
        day_rows.append({
            "dia": dia,
            "data": data_dia,
            "nf": r["nf"] if r else 0,
            "nfs": r["nfs"] if r else 0,
            "cte": r["cte"] if r else 0,
            "total": r["total"] if r else 0,
        })
    conn.close()

    return {
        "total_nf": row["nf"],
        "total_nfs": row["nfs"],
        "total_cte": row["cte"],
        "total_geral": row["geral"],
        "primeira_data": row["primeira"],
        "ultima_data": row["ultima"],
        "n": row["n"],
        "empresa_nome": empresa_nome,
        "top_codigo": top["codigo"] if top else "-",
        "top_nome": top["nome"] if top else "-",
        "top_total": top["total"] if top else 0,
        "status": {
            "PENDENTE": status_contagem.get("PENDENTE", 0),
            "EM_ANDAMENTO": status_contagem.get("EM_ANDAMENTO", 0),
            "CONCLUIDA": status_contagem.get("CONCLUIDA", 0),
            "CANCELADA": status_contagem.get("CANCELADA", 0),
        },
    }, day_rows


def get_pendencias_dashboard(empresa=None, limite=10):
    hoje = date.today().isoformat()
    where = ["l.excluido = 0", "l.status IN ('PENDENTE','EM_ANDAMENTO')", "l.prazo IS NOT NULL"]
    params = []
    if empresa:
        where.append("l.codigo = ?")
        params.append(empresa)
    where_sql = "WHERE " + " AND ".join(where)
    conn = get_db()
    atrasadas = conn.execute(
        f"""
        SELECT l.*, e.nome AS empresa FROM lancamentos l JOIN empresas e ON e.codigo = l.codigo
        {where_sql} AND l.prazo < ? ORDER BY l.prazo ASC, l.id ASC LIMIT ?
        """,
        params + [hoje, limite],
    ).fetchall()
    hoje_rows = conn.execute(
        f"""
        SELECT l.*, e.nome AS empresa FROM lancamentos l JOIN empresas e ON e.codigo = l.codigo
        {where_sql} AND l.prazo = ? ORDER BY l.id ASC LIMIT ?
        """,
        params + [hoje, limite],
    ).fetchall()
    contagens = conn.execute(
        f"""
        SELECT
          SUM(CASE WHEN l.prazo < ? THEN 1 ELSE 0 END) AS atrasadas,
          SUM(CASE WHEN l.prazo = ? THEN 1 ELSE 0 END) AS hoje
        FROM lancamentos l {where_sql}
        """,
        [hoje, hoje] + params,
    ).fetchone()
    conn.close()
    return {
        "atrasadas": [_enriquecer_lancamento(r) for r in atrasadas],
        "hoje": [_enriquecer_lancamento(r) for r in hoje_rows],
        "qtd_atrasadas": contagens["atrasadas"] or 0,
        "qtd_hoje": contagens["hoje"] or 0,
    }


def evolucao_mensal(n_meses=6, empresa=None):
    where = ["excluido = 0"]
    params = []
    if empresa:
        where.append("codigo = ?")
        params.append(empresa)
    where_sql = "WHERE " + " AND ".join(where)
    conn = get_db()
    rows = conn.execute(
        f"""
        SELECT substr(data, 1, 7) AS mes,
               COALESCE(SUM(qtd_nf), 0) AS nf,
               COALESCE(SUM(qtd_nfs), 0) AS nfs,
               COALESCE(SUM(qtd_cte), 0) AS cte,
               COALESCE(SUM(total), 0) AS total
        FROM lancamentos
        {where_sql}
        GROUP BY mes
        ORDER BY mes DESC
        LIMIT ?
        """,
        params + [n_meses],
    ).fetchall()
    conn.close()
    return list(reversed(rows))


# ------------------------------------------------------------------
# Meses fechados
# ------------------------------------------------------------------
def mes_de_data(data_str):
    return data_str[:7]


def is_mes_fechado(mes_str):
    conn = get_db()
    row = conn.execute("SELECT * FROM meses_fechados WHERE mes = ?", (mes_str,)).fetchone()
    conn.close()
    return row


def fechar_mes(mes_str, usuario):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO meses_fechados (mes, fechado_por, fechado_em) VALUES (?, ?, ?)
        ON CONFLICT(mes) DO UPDATE SET fechado_por = excluded.fechado_por, fechado_em = excluded.fechado_em
        """,
        (mes_str, usuario, agora_iso()),
    )
    conn.commit()
    conn.close()


def desbloquear_mes(mes_str):
    conn = get_db()
    conn.execute("DELETE FROM meses_fechados WHERE mes = ?", (mes_str,))
    conn.commit()
    conn.close()
