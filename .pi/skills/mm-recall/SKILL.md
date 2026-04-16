---
name: "mm-recall"
description: Carrega mensagens de uma conversa anterior no contexto atual
user-invocable: true
---

# Recall — Retomar Conversa Anterior

Ao receber `/mm-recall <id>`, executar:

```bash
uv run memoria recall CONV_ID [--limit N]
```

O `CONV_ID` pode ser o ID completo ou apenas o prefixo (ex: `a3b2c1d4`).

O script imprime o conteúdo da conversa (header + mensagens). Usar como contexto para continuar o assunto ou responder perguntas sobre o que foi discutido.
