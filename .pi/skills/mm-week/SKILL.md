---
name: "mm-week"
description: Planeja a semana — ingere texto livre com tarefas e compromissos, ou mostra visão semanal
user-invocable: true
---

# Week — Planejamento Semanal

Ao receber `/mm-week`, executar conforme os argumentos:

## Sem argumento — Visão da semana

```bash
uv run memoria week view
```

Mostra tasks e compromissos da semana corrente agrupados por dia.

**Regras de exibição:**
- Compromissos passados (com `scheduled_at` < agora) NÃO aparecem
- Tasks com `due_date` passado e status != done aparecem com indicador de atraso
- Items com `scheduled_at` mostram hora exata
- Items só com `time_hint` mostram o hint
- Travessia aparece ao lado quando presente

## Com texto — Ingerir plano semanal

```bash
uv run memoria week plan "TEXTO LIVRE"
```

O script extrai itens via LLM e retorna um JSON com os itens propostos + alertas de similaridade.

**Fluxo obrigatório:**
1. Executar o script com o texto do usuário
2. Apresentar os itens extraídos ao usuário em formato legível (tabela ou lista)
3. Se houver alertas de similaridade, mostrar
4. Perguntar: "Confirmo a criação destes itens?"
5. Após confirmação, executar: `uv run memoria week save`
   (o script lê os itens pendentes de um arquivo temporário)

**NUNCA salvar automaticamente sem confirmação do usuário.**

## Interpretação de argumentos

Se `$ARGUMENTS` está vazio ou é "view" → mostrar semana.
Se `$ARGUMENTS` contém texto descritivo → ingerir como plano.
