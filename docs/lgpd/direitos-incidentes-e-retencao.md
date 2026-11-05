# Direitos do titular, decisão automatizada, incidentes e retenção

Rascunho de 05/11/2026, para lapidar.

## Pedido do titular (art. 18)

O produtor pode pedir: confirmação de tratamento, acesso, correção, anonimização ou eliminação, portabilidade, informação sobre compartilhamento e revogação do consentimento. Como a cooperativa é a controladora dos dados dele, o pedido é atendido por ela, com a AgroValid executando.

```mermaid
sequenceDiagram
  autonumber
  participant T as Titular
  participant C as Cooperativa (controladora)
  participant A as AgroValid (operadora)
  T->>C: pedido pelo canal da cooperativa
  Note over T,A: Se chegar direto à AgroValid, ela repassa à cooperativa em até 2 dias úteis
  C->>C: confirma a identidade do titular
  C->>A: instrução: acesso, correção ou eliminação
  A->>A: localiza pelo documento_hash, executa e registra o pedido sem dado pessoal
  A-->>C: resultado + o que foi apagado ou exportado
  C-->>T: resposta (declaração completa em até 15 dias, art. 19, II)
```

- **Eliminação:** apaga as linhas de `cad` e `diag` do titular naquela organização, inclusive no lago (partição da organização). As cargas de dado público não mudam, porque não pertencem à cooperativa.
- **Revogação do consentimento:** a mesma eliminação, mais um bloqueio para o hash não voltar na próxima carteira sem novo consentimento.

## Decisão automatizada (art. 20)

O pré-diagnóstico ordena a carteira e aponta pendências, o que pode influir em crédito ou venda. Por isso:
- o sistema nunca decide nem diz "conforme"; o técnico decide;
- a ficha explica cada critério com a fonte, a data e o que não foi verificado;
- o titular pode pedir revisão por uma pessoa, pelo canal da cooperativa.

## Incidente de segurança (art. 48 e Resolução CD/ANPD nº 15/2024)

```mermaid
flowchart TD
  D[Detecção: alerta, relato, varredura] --> C[Conter: revogar chaves e sessões,<br/>fechar a rota, trocar segredos]
  C --> AV[Avaliar: quais dados, quantos titulares,<br/>quais organizações, há risco relevante?]
  AV -- "risco ou dano relevante" --> N[Avisar a cooperativa controladora<br/>imediatamente]
  N --> ANPD[Controladora comunica à ANPD e aos titulares<br/>em até 3 dias úteis]
  AV -- "sem risco relevante" --> R[Registrar o incidente<br/>e guardar por 5 anos]
  ANPD --> R
  R --> L[Lição aprendida vira issue]
```

- Guardar o registro de todo incidente, mesmo sem comunicação, por pelo menos 5 anos (Resolução nº 15/2024).
- O contrato de operador obriga a AgroValid a avisar a cooperativa sem demora, para que ela cumpra o prazo.

## Retenção e descarte

| Dado | Prazo proposto | Como descarta |
|---|---|---|
| Carteira, pré-diagnóstico e documentos pseudonimizados | Contrato + 6 meses | Rotina que apaga a organização em `cad`/`diag` e no lago |
| Contas de usuário inativas | 6 meses após a desativação | Exclusão no provedor de identidade |
| Log de acesso | 6 meses (Marco Civil, art. 15) | Expiração automática |
| Backups | Rotação do provedor (7 dias no Pro) | Expiração automática; a eliminação vale também para backups depois do ciclo |
| Registro de incidentes | 5 anos | Sem dado pessoal, só descrição |
