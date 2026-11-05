# Inventário de tratamentos e bases legais

Rascunho de 05/11/2026 (art. 37 da LGPD). Toda issue que trate dado pessoal novo atualiza esta tabela ([checklist de issue](../arquitetura/evolucao/checklist-de-issue.md)).

| Tratamento | Dados | Titular | Papel da AgroValid | Base legal (proposta) | Onde fica | Retenção (proposta) |
|---|---|---|---|---|---|---|
| Carteira da cooperativa | `id_produtor` da cooperativa, CAR, coordenadas, área de produção, commodity | Produtor | Operadora | A da cooperativa: execução de contrato com o cooperado (art. 7º, V) ou legítimo interesse (IX) | `cad`, Brasil | Enquanto durar o contrato + 6 meses; depois, descarte |
| Documento do produtor | CPF ou CNPJ, só como `documento_hash` (HMAC) | Produtor | Operadora | Consentimento escrito (art. 7º, I), como no fluxo atual; avaliar legítimo interesse com a cooperativa | `cad`/`diag`, Brasil; o CPF em claro nunca é gravado | Igual à carteira |
| Pré-diagnóstico | Critérios, evidências, resultado por imóvel | Produtor | Operadora | A da cooperativa | `diag`, Brasil | Histórico mensal pelo prazo do contrato (rastreabilidade); depois, descarte |
| Relatório AB+S | UUID do relatório, resposta pseudonimizada | Produtor | Operadora | Consentimento escrito do titular (ADR 0012) | `cad`/`diag`, Brasil | Igual à carteira |
| Contas de usuário | Nome, e-mail, organização, papel, fator de MFA | Técnico, administrador | Controladora | Execução de contrato (art. 7º, V) | Provedor de identidade, São Paulo | Enquanto ativa + 6 meses |
| Log de acesso e segurança | `request_id`, organização, rota, status, IP (só na borda e no log de segurança) | Usuário | Controladora | Legítimo interesse (segurança) e art. 15 do Marco Civil da Internet (6 meses de registro de acesso a aplicação) | Nuvem, Brasil; borda: Cloudflare | 6 meses |
| Proteção contra robôs | Sinais do navegador avaliados pelo Turnstile | Visitante | Controladora | Legítimo interesse (segurança) | Cloudflare (transferência internacional) | Conforme a Cloudflare |
| Dados públicos com nome de pessoa | Lista Suja (empregador), embargos do IBAMA (autuado) | Pessoas listadas | Controladora | Dado tornado público pelo órgão (art. 7º, §3º e §4º), com finalidade compatível: verificação socioambiental | `ref`/`geo`, documento só como hash | Enquanto a fonte publicar; versões antigas pelo prazo de rastreabilidade |

Pontos em aberto:
- A base legal do CPF (consentimento ou legítimo interesse) é decisão com a cooperativa e com o jurídico. Consentimento pode ser revogado, e o sistema precisa apagar o hash quando for.
- Fazer o teste de legítimo interesse (LIA) para os dados públicos e para o log de segurança.
- Confirmar se a AgroValid se enquadra como agente de pequeno porte (Resolução CD/ANPD nº 2/2022). O pré-diagnóstico pode ser tratamento de alto risco por afetar crédito, o que limita a dispensa.

## Suboperadores e transferência internacional

| Fornecedor | Para quê | Onde trata | Garantia |
|---|---|---|---|
| Banco gerenciado (Supabase, #9) | Banco e identidade | São Paulo | Contrato de tratamento do fornecedor |
| Nuvem da API (Cloud Run ou Fly.io) | Executar a API | São Paulo | Contrato de tratamento do fornecedor |
| Cloudflare | Borda, WAF, Turnstile, front estático | Global | Cláusulas-padrão (Resolução CD/ANPD nº 19/2024) |
| GitHub | Código e CI | EUA | Sem dado pessoal real (só sintético) |
