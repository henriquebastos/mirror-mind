---
name: "mm-tasks"
description: Lista e gerencia tasks das travessias
user-invocable: true
---

# Tasks — Gestão de Tarefas

Ao receber `/mm-tasks`, executar:

```bash
uv run memoria tasks [SUBCOMMAND] [ARGS]
```

## Subcomandos

- **Sem argumento ou `list`**: Lista tasks abertas agrupadas por travessia
- `--travessia SLUG`: Filtra por travessia
- `--status STATUS`: Filtra por status (todo, doing, done, blocked)
- `--all`: Mostra todas (incluindo concluídas)
- `add "TÍTULO" --travessia SLUG [--due YYYY-MM-DD] [--stage ETAPA]`: Cria task
- `done TASK_ID`: Marca task como concluída
- `doing TASK_ID`: Marca task como em andamento
- `block TASK_ID`: Marca task como bloqueada
- `import [SLUG]`: Importa tasks pendentes dos caminhos (todas ou de uma travessia)
- `sync [SLUG]`: Sincroniza tasks a partir do arquivo de referência externo (todas configuradas ou uma travessia)
- `sync-config SLUG /caminho/do/arquivo`: Configura o arquivo de referência para sync de uma travessia
- `delete TASK_ID`: Remove uma task

## Interpretação de argumentos

Se `$ARGUMENTS` contém um slug de travessia (ex: `/mm-tasks reflexo`), usar como filtro `--travessia`.
Se contém "todas" ou "all", usar `--all`.
Se é uma frase como "preciso fazer X até sexta", criar task com `add`.

Apresentar resultado ao usuário de forma legível.
