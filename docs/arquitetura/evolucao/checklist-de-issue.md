# Checklist de toda issue nova

Toda issue criada a partir de 05/11/2026 responde a estas perguntas na seção "Notas técnicas" ou em "Riscos". "Não se aplica" vale, mas precisa estar escrito. Base: [arquitetura-alvo](README.md), [segurança](seguranca.md) e [LGPD](../../lgpd/README.md).

## Camadas
- [ ] Em qual camada mexe (pipeline, lago, banco, API, BFF, front, borda)? Alguma camada passa a falar com outra que não é vizinha?
- [ ] Muda contrato (YAML) ou a API pública (`/v1`)? Se muda a API, é compatível com a versão anterior?

## Segurança
- [ ] Rota nova: quem pode chamar, com qual papel no banco, e qual teste prova que uma organização não lê a outra?
- [ ] Algum segredo, token ou identificador novo? Onde fica e onde nunca pode ficar?
- [ ] Entrada nova vinda de fora (arquivo, formulário, fonte pública)? Como é validada e qual o limite de tamanho?
- [ ] Rota anônima ou cara? Qual o limite por identidade e se precisa de Turnstile.
- [ ] Dependência, serviço externo ou ferramenta de agente nova? (Só com o dono.)

## LGPD
- [ ] Trata dado pessoal novo? Qual a finalidade, a base legal e o prazo de retenção? Atualizar o [inventário](../../lgpd/inventario-e-bases-legais.md).
- [ ] O dado pessoal sai do Brasil ou vai para um terceiro novo?
- [ ] O resultado pode afetar o titular (crédito, venda)? Então a ficha mostra fonte, data e o que não foi verificado, e nunca diz "conforme".

## Confiabilidade e rastreabilidade
- [ ] A resposta ou a saída diz de qual execução, carga e fonte veio?
- [ ] O que acontece se a fonte ou o banco falhar? (Inconclusivo com motivo, nunca "sem ocorrência".)
- [ ] Migração segue expandir e depois contrair?

## Desempenho e escala
- [ ] Onde roda o trabalho pesado? (No pipeline, em lote; a API só lê resultado pronto.)
- [ ] A consulta usa índice? Qual o volume esperado no cenário otimista (várias cooperativas, 500 imóveis cada)?
