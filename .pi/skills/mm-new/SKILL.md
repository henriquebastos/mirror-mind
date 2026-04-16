---
name: "mm-new"
description: "Inicia uma nova conversa, encerrando a sessão de memória ativa"
---

# New — Iniciar nova conversa

Ao receber `/mm-new`, executar:

```bash
uv run memoria conversation-logger switch
```

Informar o resultado ao usuário:
- Se criou: "Nova conversa iniciada. A anterior foi encerrada."
- Se não havia sessão ativa: "Nenhuma sessão ativa encontrada."
