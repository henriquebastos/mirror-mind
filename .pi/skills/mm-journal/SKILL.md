---
name: "mm-journal"
description: Registra uma entrada de diário pessoal no banco de memória
user-invocable: true
---

# Journal — Diário Pessoal

Ao receber `/mm-journal`, executar:

```bash
uv run memoria journal [--travessia SLUG] "TEXTO_DA_ENTRADA"
```

O texto da entrada vem de `$ARGUMENTS`. Se o usuário não passou texto, perguntar: "O que você quer registrar no diário?"

O parâmetro `--travessia` é opcional. Se o usuário mencionar explicitamente uma travessia ou o contexto deixar claro que a entrada pertence a uma, passar o slug. Caso contrário, omitir — o journal fica como registro livre.

O script classifica automaticamente (título, camada junguiana, tags) via LLM e salva no banco.

Após executar, mostrar ao usuário o resultado da classificação (título, camada, tags) e confirmar que foi salvo.
