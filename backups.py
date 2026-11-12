import os
import re
import shutil
import sqlite3
import tempfile
from datetime import date, datetime

from database import DB_PATH

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
TABELAS_OBRIGATORIAS = {"empresas", "lancamentos", "meses_fechados"}
_ultima_verificacao = None


def _garantir_pasta():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def _motivo_seguro(motivo):
    motivo = re.sub(r"[^a-zA-Z0-9_-]+", "_", motivo or "backup")
    return motivo.strip("_")[:40] or "backup"


def criar_backup(motivo="manual"):
    _garantir_pasta()
    if not os.path.exists(DB_PATH):
        return None
    instante = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    nome = f"controle_notas_{instante}_{_motivo_seguro(motivo)}.db"
    destino = os.path.join(BACKUP_DIR, nome)

    origem_conn = sqlite3.connect(DB_PATH, timeout=30)
    destino_conn = sqlite3.connect(destino)
    try:
        origem_conn.backup(destino_conn)
    finally:
        destino_conn.close()
        origem_conn.close()
    return destino


def garantir_backup_diario():
    global _ultima_verificacao
    hoje = date.today().isoformat()
    if _ultima_verificacao == hoje:
        return None
    _ultima_verificacao = hoje
    _garantir_pasta()
    prefixo = f"controle_notas_{date.today().strftime('%Y%m%d')}_"
    existentes = [n for n in os.listdir(BACKUP_DIR) if n.startswith(prefixo) and n.endswith("_automatico.db")]
    if existentes:
        return os.path.join(BACKUP_DIR, sorted(existentes)[-1])
    return criar_backup("automatico")


def listar_backups():
    _garantir_pasta()
    itens = []
    for nome in sorted(os.listdir(BACKUP_DIR), reverse=True):
        caminho = os.path.join(BACKUP_DIR, nome)
        if not os.path.isfile(caminho) or not nome.lower().endswith(".db"):
            continue
        stat = os.stat(caminho)
        itens.append({
            "nome": nome,
            "tamanho": stat.st_size,
            "modificado_em": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        })
    return itens


def caminho_backup(nome):
    nome_seguro = os.path.basename(nome)
    caminho = os.path.abspath(os.path.join(BACKUP_DIR, nome_seguro))
    if not caminho.startswith(os.path.abspath(BACKUP_DIR) + os.sep):
        return None
    if not os.path.isfile(caminho):
        return None
    return caminho


def validar_banco(caminho):
    try:
        conn = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        integridade = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tabelas = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        conn.close()
    except sqlite3.Error as exc:
        return False, f"O arquivo não é um banco SQLite válido: {exc}"

    if integridade.lower() != "ok":
        return False, "O banco enviado está corrompido (integrity_check falhou)."
    faltantes = TABELAS_OBRIGATORIAS - tabelas
    if faltantes:
        return False, "O arquivo não pertence ao Controle de Notas. Tabelas ausentes: " + ", ".join(sorted(faltantes))
    return True, None


def restaurar_banco(caminho_enviado):
    valido, erro = validar_banco(caminho_enviado)
    if not valido:
        return False, erro, None

    backup_anterior = criar_backup("antes_restauracao")
    pasta_db = os.path.dirname(DB_PATH)
    os.makedirs(pasta_db, exist_ok=True)
    fd, temporario = tempfile.mkstemp(prefix="restore_", suffix=".db", dir=pasta_db)
    os.close(fd)
    try:
        shutil.copy2(caminho_enviado, temporario)
        valido, erro = validar_banco(temporario)
        if not valido:
            return False, erro, backup_anterior

        # O banco trabalha em modo WAL. Antes de trocar o arquivo principal,
        # eliminamos arquivos auxiliares antigos para impedir que transações do
        # banco anterior sejam reaplicadas sobre o backup restaurado.
        if os.path.exists(DB_PATH):
            try:
                conn = sqlite3.connect(DB_PATH, timeout=30)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
            except sqlite3.Error:
                pass
        for sufixo in ("-wal", "-shm"):
            auxiliar = DB_PATH + sufixo
            if os.path.exists(auxiliar):
                os.remove(auxiliar)

        os.replace(temporario, DB_PATH)
        for sufixo in ("-wal", "-shm"):
            auxiliar = DB_PATH + sufixo
            if os.path.exists(auxiliar):
                os.remove(auxiliar)
    finally:
        if os.path.exists(temporario):
            os.remove(temporario)
    return True, None, backup_anterior
