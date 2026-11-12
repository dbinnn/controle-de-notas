import os
import secrets
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
ENV_EXAMPLE_PATH = os.path.join(BASE_DIR, ".env.example")


def _garantir_env():
    if os.path.exists(ENV_PATH):
        return
    conteudo = ""
    if os.path.exists(ENV_EXAMPLE_PATH):
        with open(ENV_EXAMPLE_PATH, encoding="utf-8") as arquivo:
            conteudo = arquivo.read()
    conteudo += f"\nFLASK_SECRET_KEY={secrets.token_hex(32)}\n"
    with open(ENV_PATH, "w", encoding="utf-8") as arquivo:
        arquivo.write(conteudo)


_garantir_env()
load_dotenv(ENV_PATH)

SECRET_KEY = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_LOGIN_CONFIGURADO = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

ALLOWED_EMAILS = [
    e.strip().lower()
    for e in os.environ.get("ALLOWED_EMAILS", "").split(",")
    if e.strip()
]

ADMIN_EMAILS = [
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "").split(",")
    if e.strip()
]
if not ADMIN_EMAILS and ALLOWED_EMAILS:
    ADMIN_EMAILS = [ALLOWED_EMAILS[0]]

FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "false").strip().lower() == "true"
PORT = int(os.environ.get("PORT", "5000"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
