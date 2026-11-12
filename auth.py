import functools

from authlib.integrations.flask_client import OAuth
from flask import Blueprint, redirect, render_template, request, session, url_for, flash

import config

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()
google = None


def init_auth(app):
    global google
    oauth.init_app(app)
    if config.GOOGLE_LOGIN_CONFIGURADO:
        google = oauth.register(
            name="google",
            client_id=config.GOOGLE_CLIENT_ID,
            client_secret=config.GOOGLE_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    app.register_blueprint(auth_bp)


def current_user_email():
    return session.get("user_email")


def current_user_name():
    return session.get("user_name") or session.get("user_email")


def is_admin():
    email = (current_user_email() or "").lower()
    if not config.GOOGLE_LOGIN_CONFIGURADO:
        return True
    return bool(email and email in config.ADMIN_EMAILS)


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not config.GOOGLE_LOGIN_CONFIGURADO:
            return view(*args, **kwargs)
        if not session.get("user_email"):
            return redirect(url_for("auth.login", next=request.full_path if request.query_string else request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not is_admin():
            flash("Esta ação é exclusiva para administradores.", "erro")
            return redirect(request.referrer or url_for("resumo"))
        return view(*args, **kwargs)
    return wrapped


@auth_bp.route("/login")
def login():
    if not config.GOOGLE_LOGIN_CONFIGURADO:
        return redirect(url_for("resumo"))
    if session.get("user_email"):
        return redirect(url_for("resumo"))
    session["login_next"] = request.args.get("next") or url_for("resumo")
    return render_template("login.html")


@auth_bp.route("/login/google")
def login_google():
    if not config.GOOGLE_LOGIN_CONFIGURADO:
        return redirect(url_for("resumo"))
    redirect_uri = url_for("auth.callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/callback")
def callback():
    if not google:
        return redirect(url_for("resumo"))
    token = google.authorize_access_token()
    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").lower()

    if not email or email not in config.ALLOWED_EMAILS:
        return render_template("acesso_negado.html", email=email), 403

    session["user_email"] = email
    session["user_name"] = userinfo.get("name", email)
    destino = session.pop("login_next", None) or url_for("resumo")
    return redirect(destino)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
