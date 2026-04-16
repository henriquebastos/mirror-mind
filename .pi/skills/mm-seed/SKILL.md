---
name: "mm-seed"
description: Migra YAMLs de identidade para o banco de memória de produção
user-invocable: true
---

# Seed — Migração de YAMLs para o Banco

Carrega os arquivos YAML de identidade (self, ego, user, organization, personas, travessias) no banco de memória de produção.

```bash
python -m memoria seed --env production
```

Usar após modificar qualquer arquivo YAML de identidade no repositório para sincronizar com o banco.
