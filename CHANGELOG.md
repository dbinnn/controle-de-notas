# Changelog

## v2.0.5 — Versão pública

- Removidos todos os dados reais (empresas, usuários, banco, backups e logo); incluídas empresas fictícias de exemplo.
- Incluída a dependência `requests`, necessária para o login Google.

## v2.0.4 — Calendário recolhível

- O quadro “Detalhe por dia” agora inicia minimizado para deixar o resumo mais compacto.
- Adicionado botão “Mostrar calendário” / “Minimizar calendário”.
- A preferência do usuário é mantida no navegador para os próximos acessos.
- Ajustado o comportamento no celular para o botão ocupar toda a largura.

## v2.0.3 — Ajuste de configuração

- Ajustadas as listas de usuários autorizados e administradores no `.env.example`.

## v2.0.2 — Ampliação do cadastro de empresas

- Cadastro inicial de empresas carregado de `empresas_seed.json`.
- A sincronização usa `INSERT OR IGNORE`, portanto dados já existentes no banco do usuário não são sobrescritos.

## v2.0.1 — Correção de interação

- Corrigido o bloqueio invisível que impedia cliques em menus, botões e filtros.
- O fundo do modal de confirmação agora fica realmente removido da tela quando fechado.
- Adicionado versionamento aos arquivos CSS e JavaScript para evitar cache antigo do navegador.

# Alterações

## 2.0

- Correção integral dos filtros mensais e da exportação.
- Fluxo de status, prazo, responsável e conclusão.
- Auditoria completa de lançamentos.
- Lixeira e exclusão definitiva administrativa.
- Backups automáticos, manuais e restauração validada.
- Gestão completa de empresas e importação/exportação XLSX.
- Validação de CPF/CNPJ, datas, quantidades e duplicidades.
- Interface responsiva, paginação, menu mobile, favicon e modais próprios.
