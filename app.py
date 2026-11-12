import calendar
import json
import math
import os
import secrets
import tempfile
import unicodedata
import zipfile
from datetime import date, datetime

import openpyxl
from flask import (
    Flask, abort, flash, redirect, render_template, request, send_file,
    session, url_for,
)

import auth
import backups
import config
import database as db
from export import build_empresas_export, build_export
from validators import (
    STATUS_VALIDOS, TIPOS_NOTA_VALIDOS, inteiro_nao_negativo, somente_digitos, validar_data_iso,
    validar_e_formatar_documento, validar_mes_iso,
)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

db.init_db()
auth.init_auth(app)

STATUS_LABELS = {
    "PENDENTE": "Pendente",
    "EM_ANDAMENTO": "Em andamento",
    "CONCLUIDA": "Concluída",
    "CANCELADA": "Cancelada",
}
MESES_PT = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


# ------------------------------------------------------------------
# Proteções e utilidades globais
# ------------------------------------------------------------------
def _csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


@app.before_request
def antes_da_requisicao():
    if request.endpoint != "static":
        backups.garantir_backup_diario()
    if request.method == "POST":
        recebido = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
        esperado = session.get("_csrf_token")
        if not esperado or not recebido or not secrets.compare_digest(esperado, recebido):
            abort(400, description="Sessão expirada ou formulário inválido. Atualize a página e tente novamente.")


@app.after_request
def cabecalhos_seguranca(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.context_processor
def inject_globals():
    def pagina_url(numero):
        args = request.args.to_dict(flat=True)
        args["page"] = numero
        return url_for(request.endpoint, **(request.view_args or {}), **args)

    return {
        "current_user_name": auth.current_user_name(),
        "current_user_email": auth.current_user_email(),
        "current_user_admin": auth.is_admin(),
        "google_configurado": config.GOOGLE_LOGIN_CONFIGURADO,
        "csrf_token": _csrf_token,
        "status_labels": STATUS_LABELS,
        "status_validos": STATUS_VALIDOS,
        "pagina_url": pagina_url,
        "today_iso": date.today().isoformat(),
    }


@app.template_filter("data_br")
def data_br(valor):
    if not valor:
        return "—"
    try:
        return date.fromisoformat(str(valor)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(valor)


@app.template_filter("datetime_br")
def datetime_br(valor):
    if not valor:
        return "—"
    texto = str(valor)
    try:
        return datetime.fromisoformat(texto).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return texto


@app.template_filter("tamanho_arquivo")
def tamanho_arquivo(valor):
    numero = float(valor or 0)
    for unidade in ("B", "KB", "MB", "GB"):
        if numero < 1024 or unidade == "GB":
            return f"{numero:.1f} {unidade}"
        numero /= 1024


@app.template_filter("json_bonito")
def json_bonito(valor):
    if not valor:
        return "—"
    try:
        return json.dumps(json.loads(valor), ensure_ascii=False, indent=2, sort_keys=True)
    except (TypeError, json.JSONDecodeError):
        return str(valor)


def _usuario_atual():
    return auth.current_user_email() or auth.current_user_name() or "modo-aberto"


def _mes_atual_str():
    hoje = date.today()
    return f"{hoje.year:04d}-{hoje.month:02d}"


def _pagina_atual():
    try:
        return max(1, int(request.args.get("page", "1")))
    except ValueError:
        return 1


def _paginacao(total, page, per_page):
    paginas = max(1, math.ceil(total / per_page))
    page = min(max(page, 1), paginas)
    inicio = max(1, page - 2)
    fim = min(paginas, page + 2)
    return {
        "page": page,
        "pages": paginas,
        "total": total,
        "has_prev": page > 1,
        "has_next": page < paginas,
        "prev_num": page - 1,
        "next_num": page + 1,
        "numbers": range(inicio, fim + 1),
    }


def _dados_form_lancamento(form=None, entrada=None):
    if form is not None:
        return {
            "data": form.get("data", "").strip(),
            "codigo": form.get("codigo", "").strip(),
            "tipo_nota": form.get("tipo_nota", "").strip().upper(),
            "qtd_nf": form.get("qtd_nf", "0").strip() or "0",
            "qtd_nfs": form.get("qtd_nfs", "0").strip() or "0",
            "qtd_cte": form.get("qtd_cte", "0").strip() or "0",
            "status": form.get("status", "PENDENTE").strip().upper(),
            "prazo": form.get("prazo", "").strip(),
            "responsavel": form.get("responsavel", "").strip(),
            "observacao": form.get("observacao", "").strip(),
            "observacoes_internas": form.get("observacoes_internas", "").strip(),
        }
    if entrada:
        return {chave: str(entrada.get(chave) or "") for chave in (
            "data", "codigo", "tipo_nota", "qtd_nf", "qtd_nfs", "qtd_cte",
            "status", "prazo", "responsavel", "observacao", "observacoes_internas",
        )}
    return {
        "data": date.today().isoformat(),
        "codigo": "",
        "tipo_nota": "",
        "qtd_nf": "0",
        "qtd_nfs": "0",
        "qtd_cte": "0",
        "status": "PENDENTE",
        "prazo": "",
        "responsavel": auth.current_user_name() or auth.current_user_email() or "",
        "observacao": "",
        "observacoes_internas": "",
    }


def _validar_lancamento(dados, entrada_original=None):
    _, erro = validar_data_iso(dados["data"], "data do pedido")
    if erro:
        return None, erro

    if not dados["codigo"].isdigit():
        return None, "Informe um código de empresa válido."
    codigo = int(dados["codigo"])
    empresa = db.get_empresa(codigo)
    if not empresa:
        return None, f"Não existe empresa cadastrada com o código {codigo}."
    if not empresa["ativa"] and (not entrada_original or entrada_original["codigo"] != codigo):
        return None, "A empresa selecionada está inativa. Ative-a antes de criar novos lançamentos."

    if dados["tipo_nota"] not in TIPOS_NOTA_VALIDOS:
        return None, "Selecione o tipo de nota: NF, NFS ou CTE."

    quantidades = []
    for chave, rotulo in (("qtd_nf", "Qtd. NF"), ("qtd_nfs", "Qtd. NFS"), ("qtd_cte", "Qtd. CTE")):
        numero, erro = inteiro_nao_negativo(dados[chave], rotulo)
        if erro:
            return None, erro
        quantidades.append(numero)
    if sum(quantidades) == 0:
        return None, "Informe ao menos uma nota. As três quantidades não podem ficar zeradas."

    if dados["status"] not in STATUS_VALIDOS:
        return None, "Selecione um status válido."
    if not dados["responsavel"]:
        return None, "Informe o responsável pelo atendimento."
    if dados["prazo"]:
        _, erro = validar_data_iso(dados["prazo"], "data de prazo")
        if erro:
            return None, erro

    if len(dados["observacao"]) > 2000 or len(dados["observacoes_internas"]) > 4000:
        return None, "As observações ultrapassaram o limite permitido."

    if entrada_original:
        mes_original = db.mes_de_data(entrada_original["data"])
        if db.is_mes_fechado(mes_original):
            return None, f"O mês {mes_original} da data original está fechado. Desbloqueie-o antes de editar."
    mes_novo = db.mes_de_data(dados["data"])
    if db.is_mes_fechado(mes_novo):
        return None, f"O mês {mes_novo} está fechado. Desbloqueie-o no Resumo antes de alterar lançamentos."

    normalizado = dict(dados)
    normalizado.update({
        "codigo": codigo,
        "qtd_nf": quantidades[0],
        "qtd_nfs": quantidades[1],
        "qtd_cte": quantidades[2],
    })
    return normalizado, None


# ------------------------------------------------------------------
# Início e resumo
# ------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("resumo"))


@app.route("/resumo")
@auth.login_required
def resumo():
    codigo_txt = request.args.get("empresa", "").strip()
    codigo_filtro = int(codigo_txt) if codigo_txt.isdigit() else None
    mes_str = request.args.get("mes", "").strip() or _mes_atual_str()
    mes_str, erro_mes = validar_mes_iso(mes_str)
    if erro_mes:
        flash(erro_mes, "erro")
        mes_str = _mes_atual_str()

    resumo_data, day_rows = db.calcular_resumo(codigo_filtro, mes_str)
    pendencias = db.get_pendencias_dashboard(codigo_filtro)
    evolucao = db.evolucao_mensal(6, codigo_filtro)
    return render_template(
        "resumo.html",
        resumo=resumo_data,
        day_rows=day_rows,
        empresas=db.get_empresas(ativas=True),
        codigo_filtro=codigo_filtro,
        mes_str=mes_str,
        mes_fechado=db.is_mes_fechado(mes_str),
        evolucao=evolucao,
        pendencias=pendencias,
    )


@app.route("/resumo/fechar", methods=["POST"])
@auth.login_required
def fechar_mes():
    mes_str, erro = validar_mes_iso(request.form.get("mes", ""))
    if erro:
        flash(erro, "erro")
        return redirect(url_for("resumo"))
    db.fechar_mes(mes_str, _usuario_atual())
    flash(f"Mês {mes_str} fechado.", "sucesso")
    return redirect(url_for("resumo", mes=mes_str))


@app.route("/resumo/desbloquear", methods=["POST"])
@auth.login_required
def desbloquear_mes():
    mes_str, erro = validar_mes_iso(request.form.get("mes", ""))
    if erro:
        flash(erro, "erro")
        return redirect(url_for("resumo"))
    if request.form.get("confirmacao", "").strip().upper() != "DESBLOQUEAR":
        flash("Nada foi desbloqueado: a confirmação não corresponde.", "erro")
        return redirect(url_for("resumo", mes=mes_str))
    db.desbloquear_mes(mes_str)
    flash(f"Mês {mes_str} desbloqueado.", "sucesso")
    return redirect(url_for("resumo", mes=mes_str))


# ------------------------------------------------------------------
# Lançamentos
# ------------------------------------------------------------------
def _render_lancamentos(form_data=None, duplicado=None):
    filtros = {
        "empresa": request.args.get("empresa", "").strip(),
        "data_de": request.args.get("data_de", "").strip(),
        "data_ate": request.args.get("data_ate", "").strip(),
        "tipo_nota": request.args.get("tipo_nota", "").strip().upper(),
        "status": request.args.get("status", "").strip().upper(),
        "responsavel": request.args.get("responsavel", "").strip(),
        "busca": request.args.get("busca", "").strip(),
    }
    empresa_filtro = int(filtros["empresa"]) if filtros["empresa"].isdigit() else None
    page = _pagina_atual()
    per_page = 20
    entradas, total = db.listar_lancamentos(
        page=page,
        per_page=per_page,
        empresa=empresa_filtro,
        data_de=filtros["data_de"] or None,
        data_ate=filtros["data_ate"] or None,
        tipo_nota=filtros["tipo_nota"] or None,
        status=filtros["status"] or None,
        responsavel=filtros["responsavel"] or None,
        busca=filtros["busca"] or None,
    )
    paginacao = _paginacao(total, page, per_page)
    return render_template(
        "lancamentos.html",
        entradas=entradas,
        empresas=db.get_empresas(ativas=True),
        responsaveis=db.get_responsaveis(),
        filtros=filtros,
        form_data=form_data or _dados_form_lancamento(),
        duplicado=duplicado,
        paginacao=paginacao,
    )


@app.route("/lancamentos", methods=["GET", "POST"])
@auth.login_required
def lancamentos():
    if request.method == "POST":
        dados_form = _dados_form_lancamento(request.form)
        dados, erro = _validar_lancamento(dados_form)
        if erro:
            flash(erro, "erro")
            return _render_lancamentos(dados_form)

        duplicado = db.encontrar_duplicado(
            dados["data"], dados["codigo"], dados["tipo_nota"],
            dados["qtd_nf"], dados["qtd_nfs"], dados["qtd_cte"],
        )
        confirmado = request.form.get("confirmar_duplicado") == "1"
        if duplicado and not confirmado:
            flash("Encontramos um lançamento igual. Revise os dados antes de registrar novamente.", "aviso")
            return _render_lancamentos(dados_form, duplicado=dict(duplicado))

        db.add_lancamento(
            dados["data"], dados["codigo"], dados["tipo_nota"],
            dados["qtd_nf"], dados["qtd_nfs"], dados["qtd_cte"],
            dados["observacao"], dados["responsavel"], dados["status"],
            dados["prazo"], dados["observacoes_internas"], _usuario_atual(),
        )
        flash("Lançamento registrado com sucesso.", "sucesso")
        return redirect(url_for("lancamentos"))
    return _render_lancamentos()


@app.route("/lancamentos/<int:lanc_id>/editar", methods=["GET", "POST"])
@auth.login_required
def editar_lancamento(lanc_id):
    entrada = db.get_lancamento(lanc_id, incluir_excluido=False)
    if not entrada:
        flash("Lançamento não encontrado ou enviado para a lixeira.", "erro")
        return redirect(url_for("lancamentos"))

    duplicado = None
    form_data = _dados_form_lancamento(entrada=entrada)
    if request.method == "POST":
        form_data = _dados_form_lancamento(request.form)
        dados, erro = _validar_lancamento(form_data, entrada_original=entrada)
        if erro:
            flash(erro, "erro")
        else:
            duplicado_row = db.encontrar_duplicado(
                dados["data"], dados["codigo"], dados["tipo_nota"],
                dados["qtd_nf"], dados["qtd_nfs"], dados["qtd_cte"], excluir_id=lanc_id,
            )
            confirmado = request.form.get("confirmar_duplicado") == "1"
            if duplicado_row and not confirmado:
                duplicado = dict(duplicado_row)
                flash("Existe outro lançamento com os mesmos dados. Confirme para salvar mesmo assim.", "aviso")
            else:
                db.update_lancamento(
                    lanc_id, dados["data"], dados["codigo"], dados["tipo_nota"],
                    dados["qtd_nf"], dados["qtd_nfs"], dados["qtd_cte"],
                    dados["observacao"], dados["responsavel"], dados["status"],
                    dados["prazo"], dados["observacoes_internas"], _usuario_atual(),
                )
                flash("Lançamento atualizado e registrado no histórico.", "sucesso")
                return redirect(url_for("lancamentos"))

    return render_template(
        "editar.html",
        entrada=entrada,
        empresas=db.get_empresas(ativas=None),
        responsaveis=db.get_responsaveis(),
        form_data=form_data,
        duplicado=duplicado,
    )


@app.route("/lancamentos/<int:lanc_id>/excluir", methods=["POST"])
@auth.login_required
def excluir_lancamento(lanc_id):
    entrada = db.get_lancamento(lanc_id, incluir_excluido=False)
    if not entrada:
        flash("Lançamento não encontrado.", "erro")
        return redirect(url_for("lancamentos"))
    mes = db.mes_de_data(entrada["data"])
    if db.is_mes_fechado(mes):
        flash(f"O mês {mes} está fechado. Desbloqueie antes de excluir.", "erro")
        return redirect(url_for("lancamentos"))
    db.soft_delete_lancamento(lanc_id, _usuario_atual(), request.form.get("motivo", "").strip())
    flash("Lançamento movido para a lixeira. Ele pode ser restaurado.", "sucesso")
    return redirect(request.referrer or url_for("lancamentos"))


@app.route("/lancamentos/limpar", methods=["POST"])
@auth.admin_required
def limpar_lancamentos():
    if request.form.get("confirmacao", "").strip().upper() != "LIMPAR":
        flash("Nada foi apagado: a confirmação não corresponde.", "erro")
        return redirect(url_for("lancamentos"))
    caminho = backups.criar_backup("antes_limpar_todos")
    quantidade = db.clear_lancamentos(_usuario_atual())
    flash(
        f"{quantidade} lançamento(s) foram movidos para a lixeira. "
        + ("Um backup foi criado antes da operação." if caminho else ""),
        "sucesso",
    )
    return redirect(url_for("lancamentos"))


@app.route("/lixeira")
@auth.login_required
def lixeira():
    page = _pagina_atual()
    per_page = 20
    busca = request.args.get("busca", "").strip()
    entradas, total = db.listar_lancamentos(page=page, per_page=per_page, excluidos=True, busca=busca or None)
    return render_template(
        "lixeira.html",
        entradas=entradas,
        busca=busca,
        paginacao=_paginacao(total, page, per_page),
    )


@app.route("/lixeira/<int:lanc_id>/restaurar", methods=["POST"])
@auth.login_required
def restaurar_lancamento(lanc_id):
    entrada = db.get_lancamento(lanc_id, incluir_excluido=True)
    if not entrada or not entrada["excluido"]:
        flash("Item não encontrado na lixeira.", "erro")
        return redirect(url_for("lixeira"))
    mes = db.mes_de_data(entrada["data"])
    if db.is_mes_fechado(mes):
        flash(f"O mês {mes} está fechado. Desbloqueie antes de restaurar.", "erro")
        return redirect(url_for("lixeira"))
    db.restaurar_lancamento(lanc_id, _usuario_atual())
    flash("Lançamento restaurado.", "sucesso")
    return redirect(url_for("lixeira"))


@app.route("/lixeira/<int:lanc_id>/excluir-definitivo", methods=["POST"])
@auth.admin_required
def excluir_lancamento_definitivo(lanc_id):
    if request.form.get("confirmacao", "").strip().upper() != "EXCLUIR":
        flash("Nada foi excluído definitivamente: a confirmação não corresponde.", "erro")
        return redirect(url_for("lixeira"))
    backups.criar_backup("antes_exclusao_definitiva")
    if db.excluir_lancamento_definitivamente(lanc_id, _usuario_atual()):
        flash("Lançamento excluído definitivamente. O histórico da ação foi preservado.", "sucesso")
    else:
        flash("Item não encontrado na lixeira.", "erro")
    return redirect(url_for("lixeira"))


@app.route("/historico")
@auth.login_required
def historico():
    page = _pagina_atual()
    per_page = 30
    busca = request.args.get("busca", "").strip()
    acao = request.args.get("acao", "").strip()
    lancamento_txt = request.args.get("lancamento", "").strip()
    lancamento_id = int(lancamento_txt) if lancamento_txt.isdigit() else None
    rows, total = db.listar_historico(
        page=page, per_page=per_page, busca=busca or None,
        acao=acao or None, lancamento_id=lancamento_id,
    )
    return render_template(
        "historico.html", historico=rows, acoes=db.get_acoes_historico(),
        filtros={"busca": busca, "acao": acao, "lancamento": lancamento_txt},
        paginacao=_paginacao(total, page, per_page),
    )


# ------------------------------------------------------------------
# Empresas
# ------------------------------------------------------------------
@app.route("/empresas", methods=["GET", "POST"])
@auth.login_required
def empresas():
    if request.method == "POST":
        codigo_txt = request.form.get("codigo", "").strip()
        nome = request.form.get("nome", "").strip()
        documento, erro_documento = validar_e_formatar_documento(request.form.get("cnpj", ""))
        erro = None
        if not codigo_txt.isdigit():
            erro = "Código precisa ser numérico."
        elif not nome:
            erro = "Informe o nome da empresa."
        elif db.get_empresa(int(codigo_txt)):
            erro = f"Já existe empresa com o código {codigo_txt}."
        elif erro_documento:
            erro = erro_documento
        if erro:
            flash(erro, "erro")
        else:
            db.add_empresa(int(codigo_txt), nome, documento, ativa=True)
            flash("Empresa cadastrada.", "sucesso")
        return redirect(url_for("empresas"))

    busca = request.args.get("busca", "").strip()
    situacao = request.args.get("situacao", "ativas").strip()
    if situacao not in ("ativas", "inativas", "todas"):
        situacao = "ativas"
    page = _pagina_atual()
    per_page = 20
    rows, total = db.listar_empresas(busca=busca or None, situacao=situacao, page=page, per_page=per_page)
    return render_template(
        "empresas.html", empresas=rows, busca=busca, situacao=situacao,
        paginacao=_paginacao(total, page, per_page),
    )


@app.route("/empresas/<int:codigo>/editar", methods=["GET", "POST"])
@auth.login_required
def editar_empresa(codigo):
    empresa = db.get_empresa(codigo)
    if not empresa:
        flash("Empresa não encontrada.", "erro")
        return redirect(url_for("empresas"))
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        documento, erro_documento = validar_e_formatar_documento(request.form.get("cnpj", ""))
        ativa = request.form.get("ativa") == "1"
        if not nome:
            flash("Informe o nome da empresa.", "erro")
        elif erro_documento:
            flash(erro_documento, "erro")
        else:
            db.update_empresa(codigo, nome, documento, ativa)
            flash("Empresa atualizada.", "sucesso")
            return redirect(url_for("empresas"))
    return render_template("editar_empresa.html", empresa=empresa)


@app.route("/empresas/<int:codigo>/alternar", methods=["POST"])
@auth.login_required
def alternar_empresa(codigo):
    empresa = db.get_empresa(codigo)
    if not empresa:
        flash("Empresa não encontrada.", "erro")
    else:
        nova_situacao = not bool(empresa["ativa"])
        db.set_empresa_ativa(codigo, nova_situacao)
        flash(f"Empresa {'ativada' if nova_situacao else 'inativada'}.", "sucesso")
    return redirect(request.referrer or url_for("empresas"))


@app.route("/empresas/<int:codigo>/excluir", methods=["POST"])
@auth.admin_required
def excluir_empresa(codigo):
    if request.form.get("confirmacao", "").strip().upper() != "EXCLUIR":
        flash("Nada foi excluído: a confirmação não corresponde.", "erro")
    elif db.delete_empresa(codigo):
        flash("Empresa excluída.", "sucesso")
    else:
        flash("A empresa possui lançamentos e não pode ser excluída. Inative-a para preservar os dados.", "erro")
    return redirect(url_for("empresas"))


@app.route("/empresas/exportar")
@auth.login_required
def exportar_empresas():
    rows, _ = db.listar_empresas(situacao="todas", page=1, per_page=100000)
    buf = build_empresas_export(rows)
    return send_file(
        buf, as_attachment=True, download_name=f"empresas_{date.today().isoformat()}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _normalizar_cabecalho(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode("ascii")
    return texto.strip().lower().replace("/", "_").replace(" ", "_")


def _documento_da_planilha(valor):
    if valor is None or str(valor).strip() == "":
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    digitos = somente_digitos(str(valor))
    if len(digitos) < 11:
        digitos = digitos.zfill(11)
    elif 11 < len(digitos) < 14:
        digitos = digitos.zfill(14)
    return digitos


def _valor_ativo(valor):
    texto = _normalizar_cabecalho(valor)
    if texto in ("inativa", "inativo", "nao", "false", "0"):
        return False
    return True


@app.route("/empresas/importar", methods=["POST"])
@auth.login_required
def importar_empresas():
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        flash("Selecione uma planilha XLSX.", "erro")
        return redirect(url_for("empresas"))
    if not arquivo.filename.lower().endswith(".xlsx"):
        flash("Use uma planilha no formato .xlsx.", "erro")
        return redirect(url_for("empresas"))

    try:
        wb = openpyxl.load_workbook(arquivo.stream, data_only=True, read_only=True)
        ws = wb.active
        linhas = ws.iter_rows(values_only=True)
        cabecalho = next(linhas, None)
        if not cabecalho:
            raise ValueError("A planilha está vazia.")
        mapa = {_normalizar_cabecalho(valor): indice for indice, valor in enumerate(cabecalho)}
        idx_codigo = mapa.get("codigo")
        idx_nome = mapa.get("nome")
        idx_doc = next((mapa[k] for k in ("cpf_cnpj", "cnpj", "cpf", "documento") if k in mapa), None)
        idx_ativa = next((mapa[k] for k in ("situacao", "ativa", "ativo") if k in mapa), None)
        if idx_codigo is None or idx_nome is None:
            raise ValueError("A primeira linha precisa ter as colunas Código e Nome.")

        cadastradas = atualizadas = ignoradas = 0
        erros = []
        for numero_linha, linha in enumerate(linhas, start=2):
            if not linha or all(v is None or str(v).strip() == "" for v in linha):
                continue
            try:
                codigo_valor = linha[idx_codigo] if idx_codigo < len(linha) else None
                nome = str(linha[idx_nome] if idx_nome < len(linha) else "").strip()
                if isinstance(codigo_valor, float) and codigo_valor.is_integer():
                    codigo_valor = int(codigo_valor)
                codigo_txt = str(codigo_valor or "").strip()
                if not codigo_txt.isdigit() or not nome:
                    raise ValueError("código numérico e nome são obrigatórios")
                doc_bruto = _documento_da_planilha(linha[idx_doc]) if idx_doc is not None and idx_doc < len(linha) else ""
                documento, erro_doc = validar_e_formatar_documento(doc_bruto)
                if erro_doc:
                    raise ValueError(erro_doc)
                ativa = _valor_ativo(linha[idx_ativa]) if idx_ativa is not None and idx_ativa < len(linha) else True
                acao = db.upsert_empresa_importacao(int(codigo_txt), nome, documento, ativa)
                if acao == "cadastrada":
                    cadastradas += 1
                else:
                    atualizadas += 1
            except (ValueError, IndexError) as exc:
                ignoradas += 1
                if len(erros) < 8:
                    erros.append(f"Linha {numero_linha}: {exc}")
        wb.close()
    except (ValueError, OSError, zipfile.BadZipFile, openpyxl.utils.exceptions.InvalidFileException) as exc:
        flash(f"Não foi possível importar: {exc}", "erro")
        return redirect(url_for("empresas"))

    mensagem = f"Importação concluída: {cadastradas} cadastrada(s), {atualizadas} atualizada(s)"
    if ignoradas:
        mensagem += f" e {ignoradas} ignorada(s). " + " | ".join(erros)
        flash(mensagem, "aviso")
    else:
        flash(mensagem + ".", "sucesso")
    return redirect(url_for("empresas", situacao="todas"))


# ------------------------------------------------------------------
# Backups
# ------------------------------------------------------------------
@app.route("/backups")
@auth.admin_required
def painel_backups():
    return render_template("backups.html", backups=backups.listar_backups())


@app.route("/backups/baixar")
@auth.admin_required
def baixar_backup_manual():
    caminho = backups.criar_backup("manual")
    if not caminho:
        flash("O banco ainda não existe para gerar backup.", "erro")
        return redirect(url_for("painel_backups"))
    return send_file(caminho, as_attachment=True, download_name=os.path.basename(caminho), mimetype="application/octet-stream")


@app.route("/backups/arquivo/<path:nome>")
@auth.admin_required
def baixar_backup_existente(nome):
    caminho = backups.caminho_backup(nome)
    if not caminho:
        abort(404)
    return send_file(caminho, as_attachment=True, download_name=os.path.basename(caminho), mimetype="application/octet-stream")


@app.route("/backups/restaurar", methods=["POST"])
@auth.admin_required
def restaurar_backup():
    if request.form.get("confirmacao", "").strip().upper() != "RESTAURAR":
        flash("A restauração foi cancelada: a confirmação não corresponde.", "erro")
        return redirect(url_for("painel_backups"))
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo de backup .db.", "erro")
        return redirect(url_for("painel_backups"))
    if not arquivo.filename.lower().endswith(".db"):
        flash("O backup precisa estar no formato .db.", "erro")
        return redirect(url_for("painel_backups"))

    fd, temporario = tempfile.mkstemp(prefix="upload_backup_", suffix=".db")
    os.close(fd)
    try:
        arquivo.save(temporario)
        sucesso, erro, backup_anterior = backups.restaurar_banco(temporario)
        if not sucesso:
            flash(erro, "erro")
        else:
            db.init_db()
            flash(
                "Banco restaurado com sucesso. "
                + (f"O banco anterior foi salvo como {os.path.basename(backup_anterior)}." if backup_anterior else ""),
                "sucesso",
            )
    finally:
        if os.path.exists(temporario):
            os.remove(temporario)
    return redirect(url_for("painel_backups"))


# ------------------------------------------------------------------
# Exportação mensal
# ------------------------------------------------------------------
@app.route("/export")
@auth.login_required
def export():
    codigo_txt = request.args.get("empresa", "").strip()
    codigo_filtro = int(codigo_txt) if codigo_txt.isdigit() else None
    mes_str = request.args.get("mes", "").strip() or _mes_atual_str()
    mes_str, erro = validar_mes_iso(mes_str)
    if erro:
        flash(erro, "erro")
        return redirect(url_for("resumo"))

    resumo_data, day_rows = db.calcular_resumo(codigo_filtro, mes_str)
    lancamentos_filtrados = db.get_lancamentos(order="asc", empresa=codigo_filtro, mes=mes_str)
    filtro_label = resumo_data["empresa_nome"] if codigo_filtro else "Todas as empresas"
    ano, mes = map(int, mes_str.split("-"))
    mes_label = f"{MESES_PT[mes]}/{ano}"
    buf = build_export(lancamentos_filtrados, resumo_data, filtro_label, mes_label, day_rows)
    sufixo = f"_empresa_{codigo_filtro}" if codigo_filtro else ""
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"controle_notas_{mes_str}{sufixo}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.errorhandler(413)
def arquivo_grande(_erro):
    flash(f"O arquivo ultrapassa o limite de {config.MAX_UPLOAD_MB} MB.", "erro")
    return redirect(request.referrer or url_for("resumo"))


if __name__ == "__main__":
    app.run(debug=config.FLASK_DEBUG, host="0.0.0.0", port=config.PORT)
