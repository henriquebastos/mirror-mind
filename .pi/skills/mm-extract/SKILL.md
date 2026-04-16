---
name: "mm-extract"
description: Extrai memórias de conversas finalizadas que ainda não foram processadas pelo LLM. Use para processar backlog ou forçar extração imediata.
user-invocable: true
---

# mm-extract — Extração manual de memórias pendentes

Processa conversas fechadas (`ended_at` preenchido) que ainda não foram extraídas. Chama o LLM para cada uma, extrai insights, decisões, tasks e gera embeddings.

A extração automática acontece no `session_start` de cada harness (Claude Code e pi). Este skill existe para forçar processamento imediato ou processar lotes maiores que o default.

## Uso

```bash
uv run memoria conversation-logger extract-pending [LIMIT]
```

- `LIMIT` (opcional, default 10) — máximo de conversas a processar nesta rodada.

## Exemplo

```bash
uv run memoria conversation-logger extract-pending 20
```

Output:
```
Extraídas memórias de 3 conversa(s) pendente(s).
```

Ou, se não há pendências:
```
Nenhuma conversa pendente.
```

## Como funciona

1. Busca conversas com `ended_at IS NOT NULL` e sem `metadata.extracted = true`
2. Para cada uma, chama `end_conversation(extract=True)` que invoca o LLM de extração
3. Marca `metadata.extracted = true` para não reprocessar
4. Restaura o `ended_at` original (não sobrescreve com o timestamp da extração)

Erros em conversas individuais são logados mas não interrompem o processamento das demais.
