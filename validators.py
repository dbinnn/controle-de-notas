import re
from datetime import date, datetime


STATUS_VALIDOS = ("PENDENTE", "EM_ANDAMENTO", "CONCLUIDA", "CANCELADA")
TIPOS_NOTA_VALIDOS = ("NF", "NFS", "CTE")


def somente_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def validar_cpf(cpf):
    cpf = somente_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11
        if digito == 10:
            digito = 0
        if digito != int(cpf[tamanho]):
            return False
    return True


def validar_cnpj(cnpj):
    cnpj = somente_digitos(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_2 = [6] + pesos_1

    def calcular(base, pesos):
        resto = sum(int(n) * p for n, p in zip(base, pesos)) % 11
        return 0 if resto < 2 else 11 - resto

    d1 = calcular(cnpj[:12], pesos_1)
    d2 = calcular(cnpj[:12] + str(d1), pesos_2)
    return cnpj[-2:] == f"{d1}{d2}"


def formatar_documento(valor):
    digitos = somente_digitos(valor)
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    return valor.strip() if valor else ""


def validar_e_formatar_documento(valor, permitir_vazio=True):
    valor = (valor or "").strip()
    if not valor and permitir_vazio:
        return "", None

    digitos = somente_digitos(valor)
    if len(digitos) == 11:
        if not validar_cpf(digitos):
            return None, "CPF inválido. Confira os números informados."
    elif len(digitos) == 14:
        if not validar_cnpj(digitos):
            return None, "CNPJ inválido. Confira os números informados."
    else:
        return None, "Informe um CPF com 11 dígitos ou CNPJ com 14 dígitos."
    return formatar_documento(digitos), None


def validar_data_iso(valor, campo="data"):
    try:
        return date.fromisoformat((valor or "").strip()), None
    except (TypeError, ValueError):
        return None, f"Informe uma {campo} válida."


def validar_mes_iso(valor):
    valor = (valor or "").strip()
    try:
        datetime.strptime(valor, "%Y-%m")
        return valor, None
    except ValueError:
        return None, "Informe um mês válido."


def inteiro_nao_negativo(valor, campo):
    try:
        numero = int(str(valor or "0").strip() or "0")
    except ValueError:
        return None, f"{campo} precisa ser um número inteiro."
    if numero < 0:
        return None, f"{campo} não pode ser negativo."
    return numero, None
