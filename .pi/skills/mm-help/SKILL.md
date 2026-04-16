---
name: "mm-help"
description: Shows available Mirror Mind commands and how to use them
user-invocable: true
---

# Help — Mirror Mind Commands

Mostrar ao usuário a lista de comandos disponíveis, formatada assim:

## Comandos disponíveis

### Modo Espelho

| Comando | O que faz |
|---------|-----------|
| `/mm-mirror` | Ativa o Modo Espelho manualmente (carregar identidade, persona, anexos, responder em 1ª pessoa) |
| | `--persona ID` — persona específica (terapeuta, mentora, professora, etc.) |
| | `--travessia ID` — contexto de uma travessia |
| | `--query "termos"` — busca de anexos relevantes |
| | `--org` — incluir identidade da organização |
| `/mm-consult <familia> "pergunta"` | Consulta outro LLM com contexto do Espelho |
| | Famílias: `gemini`, `grok`, `deepseek`, `openai`, `claude` (ou model_id direto) |
| | `[tier]` — lite (default), mid, flagship |
| | `--persona`, `--travessia`, `--query`, `--org` — mesmos do mirror |
| `/mm-consult <familia>` | Rerun — reenvia conversa atual para outro modelo |
| `/mm-consult credits` | Mostra saldo do OpenRouter |

### Travessias e Caminho

| Comando | O que faz |
|---------|-----------|
| `/mm-journeys` | Lista rápida de travessias com status e etapa atual |
| `/mm-journey [id]` | Status detalhado de uma ou todas as travessias |
| | Se a travessia tem `sync_file`, lê direto do arquivo externo |

### Memórias e Diário

| Comando | O que faz |
|---------|-----------|
| `/mm-memories` | Lista memórias registradas |
| | `--type TYPE` — decision, insight, idea, journal, tension, learning, pattern, commitment, reflection |
| | `--layer LAYER` — self, ego, shadow |
| | `--travessia ID` — filtrar por travessia |
| | `--search "texto"` — busca semântica |
| | `--limit N` — máximo de resultados (default: 20) |
| `/mm-journal "texto"` | Registra entrada de diário pessoal (classifica camada e tags via LLM) |
| | `--travessia ID` — associar a uma travessia |

### Tasks

| Comando | O que faz |
|---------|-----------|
| `/mm-tasks` | Lista tasks abertas (default: todas) |
| | `--travessia SLUG` — filtrar por travessia |
| | `--status STATUS` — todo, doing, done, blocked |
| | `--all` — incluir concluídas |
| `/mm-tasks add "título"` | Cria task |
| | `--travessia SLUG`, `--due YYYY-MM-DD`, `--stage ETAPA` |
| `/mm-tasks done ID` | Marca task como concluída |
| `/mm-tasks doing ID` | Marca task como em andamento |
| `/mm-tasks block ID` | Marca task como bloqueada |
| `/mm-tasks delete ID` | Remove task |
| `/mm-tasks import [slug]` | Importa tasks pendentes dos caminhos |
| `/mm-tasks sync [slug]` | Sincroniza tasks a partir de arquivo externo |
| `/mm-tasks sync-config SLUG /path` | Configura arquivo de referência para sync |

### Planejamento Semanal

| Comando | O que faz |
|---------|-----------|
| `/mm-week` | Mostra visão da semana corrente (compromissos e tasks por dia) |
| `/mm-week "texto livre"` | Ingere plano semanal — extrai itens via LLM, pede confirmação antes de salvar |

### Conversas e Registro

| Comando | O que faz |
|---------|-----------|
| `/mm-save [slug]` | Salva o último turno (pergunta + resposta) como Markdown em `conversas/` |
| | `--full` — salvar conversa completa em vez do último turno |
| `/mm-conversations` | Lista conversas recentes |
| | `--limit N`, `--travessia ID`, `--persona ID` |
| `/mm-recall ID` | Carrega conversa anterior no contexto atual |
| | `--limit N` — máximo de mensagens (default: 50) |
| `/mm-new` | Inicia nova conversa (encerra a atual sem extrair memórias) |
| `/mm-mute` | Liga/desliga registro de conversas (toggle) |

### Sistema

| Comando | O que faz |
|---------|-----------|
| `/mm-backup` | Faz backup do banco de memória |
| `/mm-seed` | Migra YAMLs do repositório para o banco (sobrescreve dados pessoais) |
| `/mm-help` | Mostra esta lista |

## Modos de operação

O Espelho tem dois modos que são ativados automaticamente:

- **Modo Espelho** — perguntas pessoais, de trabalho, estratégia, escrita, mentoria → a IA responde como você, em primeira pessoa
- **Modo Construtor** — perguntas sobre código, arquitetura, bugs → a IA age como desenvolvedor

Na dúvida, o Espelho pergunta qual modo usar.
