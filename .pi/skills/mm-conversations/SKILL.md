---
name: "mm-conversations"
description: Lista conversas recentes do banco de memória
user-invocable: true
---

# Conversations — Conversas Recentes

Ao receber `/mm-conversations`, executar:

```bash
uv run memoria conversations [--limit N] [--travessia ID] [--persona ID]
```

Se `$ARGUMENTS` contém filtros (ex: `/mm-conversations reflexo`), usar como `--travessia`.

Apresentar o resultado ao usuário. Informar que podem usar `/mm-recall <id>` para carregar uma conversa.
