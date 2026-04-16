---
name: "mm-mute"
description: Liga/desliga o registro de conversas (útil para testes)
user-invocable: true
---

# Mute — Silenciar registro de conversas

Ao receber `/mm-mute`, executar:

```bash
uv run memoria conversation-logger status
```

- Se estiver **ATIVO**, executar `uv run memoria conversation-logger mute` e informar: "Registro silenciado. Use `/mm-mute` de novo para reativar."
- Se estiver **SILENCIADO**, executar `uv run memoria conversation-logger unmute` e informar: "Registro reativado."

É um toggle simples. Não precisa de argumentos.
