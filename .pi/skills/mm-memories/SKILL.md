---
name: "mm-memories"
description: Lista memórias do banco (insights, ideias, decisões, etc.) com filtros
user-invocable: true
---

# Memories — Memórias Registradas

Ao receber `/mm-memories`, executar:

```bash
uv run memoria memories [--type TYPE] [--layer LAYER] [--travessia ID] [--limit N] [--search QUERY]
```

Se `$ARGUMENTS` contém um tipo (ex: `/mm-memories ideas`), usar como `--type`.
Se contém uma query de busca (ex: `/mm-memories busca sintonizador`), usar como `--search`.

Tipos válidos: `decision`, `insight`, `idea`, `journal`, `tension`, `learning`, `pattern`, `commitment`, `reflection`.

Apresentar o resultado ao usuário de forma legível.
