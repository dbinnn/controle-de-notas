# Controle de Notas

Sistema web para escritórios de contabilidade registrarem, acompanharem e consolidarem as **solicitações de emissão de notas fiscais** dos clientes: NF (mercadorias), NFS (serviços) e CT-e (transporte).

Ele substitui a planilha manual: a equipe lança cada pedido, define prazo e responsável, acompanha o status e, no fim do mês, exporta tudo para Excel.

> Os dados que vêm no projeto (empresas, CPFs e CNPJs) são **fictícios** e servem só para demonstração.

## O que o sistema faz

- **Lançamentos**: data, empresa, tipo de nota, quantidades de NF/NFS/CT-e, prazo, responsável, observações e observações internas.
- **Status**: Pendente, Em andamento, Concluída e Cancelada, com destaque para solicitações atrasadas e que vencem hoje.
- **Resumo mensal**: totais por mês e por empresa, calendário com o detalhe por dia e fechamento/desbloqueio do mês.
- **Exportação para Excel** do mês e da empresa filtrados.
- **Cadastro de empresas**: inclusão, edição, inativação, pesquisa, importação e exportação em Excel.
- **Validações**: CPF, CNPJ e datas conferidos no servidor; bloqueio de quantidades zeradas; aviso de lançamento duplicado.
- **Histórico (auditoria)** de criação, alteração, exclusão e restauração.
- **Lixeira** com restauração; exclusão definitiva só para administrador.
- **Backups** automáticos diários, backup manual e restauração pelo painel, com checagem de integridade.
- **Login com Google** e lista de e-mails autorizados, com perfil de administrador.
- **Proteções**: token CSRF nos formulários e cabeçalhos de segurança HTTP.
- **Layout responsivo**, que funciona no celular.

## Tecnologias e linguagens

| Linguagem / tecnologia | Uso no projeto |
|---|---|
| **Python** | Servidor e regras de negócio (`app.py`, `database.py`, `validators.py` etc.) |
| **Flask** | Framework web em Python: rotas, telas e sessões |
| **HTML + Jinja2** | Telas do sistema (pasta `templates/`) |
| **CSS** | Aparência e layout responsivo (`static/style.css`) |
| **JavaScript** | Menu mobile, máscaras de CPF/CNPJ, confirmações e mensagens (`static/app.js`) |
| **SQL / SQLite** | Banco de dados local, em um único arquivo (`controle_notas.db`) |
| **Batch (.bat)** | Script `iniciar.bat`, que instala e abre o sistema no Windows com dois cliques |

Bibliotecas Python (em `requirements.txt`):

- [Flask](https://flask.palletsprojects.com/): framework web
- [Waitress](https://docs.pylonsproject.org/projects/waitress/): servidor de produção
- [openpyxl](https://openpyxl.readthedocs.io/): leitura e geração de planilhas Excel
- [Authlib](https://docs.authlib.org/) + [requests](https://requests.readthedocs.io/): login com Google (OAuth)
- [python-dotenv](https://pypi.org/project/python-dotenv/): leitura das configurações do arquivo `.env`

## O que precisa baixar para rodar

| Programa | Obrigatório? | Link |
|---|---|---|
| **Python 3.11 ou superior** | Sim | https://www.python.org/downloads/ |
| **Git** (para clonar o repositório) | Não: dá para baixar o ZIP pelo GitHub | https://git-scm.com/downloads |
| **Conta no Google Cloud** (para o login Google) | Não: sem ela o sistema roda em modo demonstração | https://console.cloud.google.com/ |
| **Editor de código**, ex.: VS Code | Não | https://code.visualstudio.com/ |

> No Windows, ao instalar o Python, marque a opção **"Add Python to PATH"**.

O SQLite já vem com o Python, então não é preciso instalar banco de dados.

## Como rodar

### Windows (jeito mais fácil)

1. Baixe o projeto (botão **Code → Download ZIP**) e extraia.
2. Dê dois cliques em `iniciar.bat`.
3. Na primeira vez ele instala as dependências e abre o navegador em http://localhost:5000.

### Windows, Linux ou macOS (pelo terminal)

```bash
git clone https://github.com/SEU_USUARIO/controle-de-notas.git
cd controle-de-notas

python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
python run_waitress.py
```

Depois, abra http://localhost:5000.

Na primeira execução, o sistema cria sozinho o arquivo `.env` (com uma chave secreta aleatória) e o banco `controle_notas.db`, já com as empresas de exemplo de `empresas_seed.json`.

## Modo demonstração x login Google

- **Sem `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no `.env`**, o sistema abre direto, **sem login**, e qualquer pessoa entra como administrador. Isso é bom para testar, mas **não use assim em rede compartilhada**: o servidor fica acessível para outros computadores da rede.
- **Com login Google**:
  1. No [Google Cloud Console](https://console.cloud.google.com/apis/credentials), crie uma credencial **OAuth 2.0 → Aplicativo da Web**.
  2. Cadastre esta URI de redirecionamento: `http://localhost:5000/auth/callback`
  3. Preencha o `.env`:

```env
GOOGLE_CLIENT_ID=seu-client-id
GOOGLE_CLIENT_SECRET=seu-client-secret
ALLOWED_EMAILS=usuario1@exemplo.com,usuario2@exemplo.com
ADMIN_EMAILS=usuario1@exemplo.com
```

O primeiro e-mail de `ALLOWED_EMAILS` vira administrador se `ADMIN_EMAILS` estiver vazio. Enquanto o app estiver em modo de testes no Google, inclua os e-mails também em **Usuários de teste** na tela de consentimento OAuth.

> **Nunca envie o `.env` ao GitHub.** Ele já está no `.gitignore`.

## Administrador

Só o administrador pode:

- acessar o painel de backups e restaurar o banco;
- limpar todos os lançamentos ativos;
- excluir definitivamente itens da lixeira;
- excluir empresas que nunca tiveram lançamentos.

Os demais usuários cadastram, editam, mandam para a lixeira e restauram lançamentos.

## Importação de empresas

Use `MODELO_IMPORTACAO_EMPRESAS.xlsx` como modelo. A primeira linha deve ter:

- `Código`: obrigatório e numérico;
- `Nome`: obrigatório;
- `CPF/CNPJ`: opcional, mas precisa ser válido quando preenchido;
- `Situação`: opcional, Ativa ou Inativa.

Se o código já existir, a importação atualiza nome, documento e situação. Empresas que não estão na planilha não são apagadas.

## Backups

Os backups ficam na pasta `backups/` (fora do Git). O sistema cria um backup:

- na primeira utilização de cada dia;
- antes de "Limpar todos";
- antes de uma exclusão definitiva;
- antes de restaurar outro banco;
- ao clicar em "Baixar backup agora".

## Estrutura do projeto

```text
app.py                  rotas e validações da aplicação
auth.py                 login Google e permissões
config.py               leitura do .env
database.py             banco SQLite, migrações, filtros e histórico
backups.py              backup, validação e restauração
validators.py           validação de CPF, CNPJ e datas
export.py               relatórios em Excel
run_waitress.py         inicia o servidor
iniciar.bat             atalho de instalação/execução no Windows
empresas_seed.json      empresas fictícias carregadas na primeira execução
templates/              telas HTML (Jinja2)
static/                 CSS, JavaScript e logo
```

## Problemas comuns

- **A janela abre e fecha**: abra o Prompt de Comando na pasta e rode `python run_waitress.py` para ver a mensagem de erro.
- **Erro de redirecionamento no login**: confira se a URI no Google Cloud é exatamente `http://localhost:5000/auth/callback`.
- **Usuário autorizado não entra**: confira se o e-mail está em `ALLOWED_EMAILS` e nos "Usuários de teste" do Google.
- **Importação ignora uma linha**: confira código, nome e validade do CPF/CNPJ.
