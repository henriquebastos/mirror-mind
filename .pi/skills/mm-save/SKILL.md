---
name: "mm-save"
description: Salva o último turno da conversa como arquivo Markdown em conversas/
user-invocable: true
---

# Save — Exportar Turno para Markdown

Ao receber `/mm-save`, salva o **último turno** (mensagem do usuário + resposta do Claude).

```bash
uv run memoria save [SLUG]
```

Se o usuário passou argumento, usar como slug do arquivo.
Caso contrário, sugira um slug descritivo baseado no conteúdo do turno.

Para exportar a **conversa completa** (usado internamente no session-end):

```bash
uv run memoria save [SLUG] --full
```

Informar o caminho do arquivo gerado ao usuário.
