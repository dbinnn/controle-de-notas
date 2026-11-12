import io
from datetime import date, datetime

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="087F7A")
HEADER_FONT = Font(name=FONT, bold=True, color="FFFFFF")
BOLD = Font(name=FONT, bold=True)
NORMAL = Font(name=FONT)
THIN = Side(style="thin", color="3A474C")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
STATUS_LABELS = {
    "PENDENTE": "Pendente",
    "EM_ANDAMENTO": "Em andamento",
    "CONCLUIDA": "Concluída",
    "CANCELADA": "Cancelada",
}


def _data_excel(valor):
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return valor


def _datetime_excel(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor))
    except ValueError:
        return valor


def _aplicar_cabecalho(ws, linha, headers):
    for col, texto in enumerate(headers, start=1):
        celula = ws.cell(row=linha, column=col, value=texto)
        celula.font = HEADER_FONT
        celula.fill = HEADER_FILL
        celula.border = BORDER
        celula.alignment = Alignment(horizontal="center", vertical="center")


def _ajustar_larguras(ws, larguras):
    for indice, largura in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(indice)].width = largura


def build_export(lancamentos, resumo, filtro_label, mes_label, day_rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lançamentos"

    headers = [
        "Data", "Código", "Empresa", "CPF/CNPJ", "Tipo de Nota",
        "Qtd. NF", "Qtd. NFS", "Qtd. CTE", "Total", "Status",
        "Prazo", "Responsável", "Observação", "Observações internas",
        "Criado por", "Criado em", "Atualizado por", "Atualizado em", "Concluído em",
    ]
    _aplicar_cabecalho(ws, 1, headers)

    for linha, lanc in enumerate(lancamentos, start=2):
        valores = [
            _data_excel(lanc["data"]), lanc["codigo"], lanc["empresa"], lanc["cnpj"], lanc["tipo_nota"],
            lanc["qtd_nf"], lanc["qtd_nfs"], lanc["qtd_cte"], lanc["total"],
            STATUS_LABELS.get(lanc["status"], lanc["status"]), _data_excel(lanc["prazo"]),
            lanc["responsavel"], lanc["observacao"], lanc["observacoes_internas"],
            lanc["lancado_por"], _datetime_excel(lanc["criado_em"]), lanc["atualizado_por"],
            _datetime_excel(lanc["atualizado_em"]), _datetime_excel(lanc["concluido_em"]),
        ]
        for coluna, valor in enumerate(valores, start=1):
            celula = ws.cell(row=linha, column=coluna, value=valor)
            celula.font = NORMAL
            celula.border = BORDER
            celula.alignment = Alignment(vertical="top", wrap_text=coluna in (13, 14))
        ws.cell(linha, 1).number_format = "DD/MM/YYYY"
        ws.cell(linha, 11).number_format = "DD/MM/YYYY"
        for coluna in (16, 18, 19):
            ws.cell(linha, coluna).number_format = "DD/MM/YYYY HH:MM:SS"

    _ajustar_larguras(ws, [12, 9, 30, 20, 13, 10, 10, 10, 10, 15, 12, 24, 35, 35, 26, 21, 26, 21, 21])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    rs = wb.create_sheet("Resumo")
    rs["A1"] = "Resumo do Controle de Notas"
    rs["A1"].font = Font(name=FONT, bold=True, size=15)
    rs["A3"] = "Empresa:"
    rs["A4"] = "Mês:"
    rs["A5"] = "Gerado em:"
    for celula in ("A3", "A4", "A5"):
        rs[celula].font = BOLD
    rs["B3"] = filtro_label
    rs["B4"] = mes_label
    rs["B5"] = datetime.now()
    rs["B5"].number_format = "DD/MM/YYYY HH:MM"

    indicadores = [
        (7, "Total NF", resumo["total_nf"]),
        (8, "Total NFS", resumo["total_nfs"]),
        (9, "Total CTE", resumo["total_cte"]),
        (10, "TOTAL GERAL", resumo["total_geral"]),
        (12, "Pendentes", resumo["status"]["PENDENTE"]),
        (13, "Em andamento", resumo["status"]["EM_ANDAMENTO"]),
        (14, "Concluídas", resumo["status"]["CONCLUIDA"]),
        (15, "Canceladas", resumo["status"]["CANCELADA"]),
    ]
    for linha, rotulo, valor in indicadores:
        rs.cell(linha, 1, rotulo).font = BOLD
        rs.cell(linha, 2, valor).font = NORMAL
        rs.cell(linha, 1).border = BORDER
        rs.cell(linha, 2).border = BORDER

    rs["D7"] = "Destaque no filtro"
    rs["D7"].font = BOLD
    rs["D8"] = "Código"
    rs["E8"] = resumo["top_codigo"]
    rs["D9"] = "Empresa"
    rs["E9"] = resumo["top_nome"]
    rs["D10"] = "Notas"
    rs["E10"] = resumo["top_total"]
    for linha in (8, 9, 10):
        rs.cell(linha, 4).font = BOLD

    rs["A18"] = f"Detalhe por dia — {mes_label}"
    rs["A18"].font = Font(name=FONT, bold=True, size=12)
    _aplicar_cabecalho(rs, 20, ["Dia", "Data", "NF", "NFS", "CTE", "Total"])
    for linha, item in enumerate(day_rows, start=21):
        valores = [item["dia"], _data_excel(item["data"]), item["nf"], item["nfs"], item["cte"], item["total"]]
        for coluna, valor in enumerate(valores, start=1):
            celula = rs.cell(linha, coluna, valor)
            celula.font = NORMAL
            celula.border = BORDER
        rs.cell(linha, 2).number_format = "DD/MM/YYYY"

    _ajustar_larguras(rs, [22, 18, 12, 20, 30, 12])
    rs.freeze_panes = "A20"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_empresas_export(empresas):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Empresas"
    headers = ["Código", "Nome", "CPF/CNPJ", "Situação", "Lançamentos ativos", "Lançamentos totais"]
    _aplicar_cabecalho(ws, 1, headers)
    for linha, empresa in enumerate(empresas, start=2):
        valores = [
            empresa["codigo"], empresa["nome"], empresa["cnpj"],
            "Ativa" if empresa["ativa"] else "Inativa",
            empresa["lancamentos_ativos"] or 0, empresa["lancamentos_total"] or 0,
        ]
        for coluna, valor in enumerate(valores, start=1):
            celula = ws.cell(linha, coluna, valor)
            celula.font = NORMAL
            celula.border = BORDER
    _ajustar_larguras(ws, [10, 38, 22, 12, 20, 20])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
