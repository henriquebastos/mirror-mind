---
name: "mm-backup"
description: Faz backup do banco de memória de produção
user-invocable: true
---

# Backup do Banco de Memória

Executa backup do banco de produção (`~/.espelho/memoria.db`).

```bash
uv run memoria backup
```

Este comando:
- Zipa o banco incluindo WAL/SHM para consistência
- Remove backups com mais de 30 dias
- O backup também roda automaticamente ao final de cada sessão via hook `SessionEnd`
