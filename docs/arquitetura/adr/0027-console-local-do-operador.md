# Console local do operador importa o pipeline direto

Situação: **aceito em 23/11/2026** (recomendação aceita pelo dono na issue #29).

## Context and Problem Statement

O pré-diagnóstico só roda pela linha de comando e a ficha sai como arquivo. Para o técnico usar sem terminal (e para a apresentação de 26/11/2026), ele precisa digitar um CAR, ver o cruzamento acontecer e abrir a ficha numa tela. A [ADR 0019](0019-separar-o-produto-em-camadas-isoladas-num-monolito-modular.md) diz que a API não lê o lago nem importa `pipeline/`, e que o front não fala com o banco. Uma tela que roda o pré-diagnóstico precisa decidir de onde chama o pipeline.

## Considered Options

* Console local (`console/`) que importa `pipeline/` direto e roda só em 127.0.0.1, na máquina do operador
* Console como cliente da API (`api/`), com uma rota nova que dispara o pré-diagnóstico
* Continuar só com a linha de comando

## Decision Outcome

Chosen option: "Console local que importa `pipeline/` direto", because é a mesma ferramenta da linha de comando com uma tela na frente: roda onde o lago e a chave de pseudonimização já estão, não abre porta pública e não exige a API de escrita, o login e o provedor de identidade que ainda não existem.

Regras:
* `python -m console` só escuta em `127.0.0.1` (não há opção de host) e recusa requisição com `Host` que não seja `127.0.0.1` ou `localhost` (contra DNS rebinding). Porta por `--porta`.
* O console **não é a API do produto**. A ADR 0019 continua valendo para `api/` (só banco, sem `pipeline/`) e para o front (`web/`, sem banco). Quando o console tiver de sair da máquina do operador, ele passa a ser cliente da API e esta ADR é substituída.
* O documento (CPF/CNPJ) só trafega no corpo de um POST JSON, é conferido pelo dígito verificador e vira `documento_hash` no pipeline (`pipeline.documentos`); não entra em URL, log, estado guardado nem arquivo. O pedido é lido sem modelo de validação, para que o erro nunca devolva o que foi digitado. Pedido que não seja `application/json` é recusado (um site de fora não consegue postar sem o preflight do CORS).
* A consulta grava uma execução `avulsa` com `comando = "console"` e `organizacao_id = 'demonstracao'`, como a linha de comando; a ficha (JSON, MD, HTML) vai para `data/saidas/console/`.
* SICAR fora do ar, CAR não localizado ou qualquer falha viram ficha "inconclusivo" com o motivo e o botão "tentar de novo" (ADR 0013); nunca "sem ocorrência".
* Sem dependência nova: FastAPI e uvicorn já estão no `requirements.txt`; HTML gerado com `html.escape`, CSS e JS puros em `console/estatico/`; a área de produção (KML/GeoJSON) vai como texto no JSON (até 2 MB), sem `python-multipart`, e é lida pelo mesmo leitor da carteira (`vetor.ler_area_producao`).
* Uma consulta por vez (o trabalho é o da linha de comando, ~2 s por imóvel).

### Consequences

* Good, because o técnico consulta sem terminal, com a mesma regra, o mesmo lago e a mesma rastreabilidade da linha de comando.
* Good, because nada novo fica exposto: sem porta pública, sem chave nova, sem segredo no navegador.
* Bad, because a tela fica presa à máquina que tem o lago; a cooperativa com vários técnicos precisa da API e do front (ADR 0019 a 0022).
* Bad, because as etapas mostradas são derivadas da ficha ao terminar: `prediagnostico.executar` ainda não avisa o progresso de cada fonte, então o tempo mostrado é o total medido.

## More Information

Issue #29. Telas da ficha e da carteira: #33 e #34. Regras de tela em `DESIGN.md` (§4, Mesa de triagem; §6, implementação no console).
