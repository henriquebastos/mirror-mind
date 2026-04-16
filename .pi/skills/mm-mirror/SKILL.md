---
name: "mm-mirror"
description: Ativa o Modo Espelho — carrega identidade, persona, anexos e registra resposta
user-invocable: true
---

# Modo Espelho — Procedimento Completo

Use este procedimento para responder no Modo Espelho. O roteamento automático no CLAUDE.md determina **quando** ativar; este skill detalha **como**.

## 1. Analisar a mensagem

Antes de carregar contexto, analisar a mensagem do usuário e decidir:
- **Persona:** qual persona ativar (ver roteamento por domínio no CLAUDE.md), ou nenhuma
- **Travessia:** se o tema se relaciona com uma travessia ativa (ver lista abaixo)
- **Organização:** se o tema envolve a organização do usuário

### Travessias ativas (para roteamento)

Para ver a lista atualizada, executar:
```bash
uv run memoria mirror travessias
```

**IMPORTANTE:** Sempre passe `--query` com o texto do prompt do usuário. Quando você não conseguir identificar a travessia manualmente, o script faz **auto-detecção** — match textual do ID/nome da travessia no query, com fallback para match semântico. Se você identificar a travessia, passe `--travessia` explicitamente (mais preciso e evita chamada de API).

## 2. Carregar contexto

```bash
uv run memoria mirror load \
  [--persona PERSONA_ID] \
  [--travessia TRAVESSIA_ID] \
  [--query "texto completo do prompt do usuário"] \
  [--org]
```

O script imprime toda a identidade carregada + anexos relevantes (score > 0.4). Usar a saída como contexto para a resposta.

**Exemplos:**
- Pergunta de mentoria: `--persona mentora --query "o prompt do usuário"`
- Pergunta sobre uma travessia: `--travessia reflexo --query "episódio 6 do reflexo"`
- Sem certeza da travessia: `--query "preciso definir o tema do artigo sobre o episódio 6 do reflexo"` (auto-detecta)
- Pergunta sobre negócio: `--org --persona minha-persona --query "o prompt"`
- Reflexão existencial sem persona: `--query "o prompt"`

## 3. Responder

- Responder **em primeira pessoa**, como o espelho — não como assistente
- Respeitar o vocabulário, tom e filosofia carregados do banco
- Aplicar modelo ego-persona conforme regras no CLAUDE.md

## 4. Registrar resposta

Após responder, registrar um resumo conciso (2-3 frases) da resposta:

```bash
uv run memoria mirror log "RESUMO_DA_RESPOSTA"
```
