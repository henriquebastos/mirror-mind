---
name: "mm-consult"
description: Consulta outros LLMs via OpenRouter com contexto do Espelho
user-invocable: true
---

# Consult — Consultar outros LLMs

Envia prompts com contexto de identidade do Espelho para outros modelos via OpenRouter.

## Sintaxe

```
/mm-consult <familia> [tier] ["pergunta"]
/mm-consult credits
```

- **família:** gemini, grok, deepseek, openai, claude (ou model_id direto como `google/gemini-2.5-pro`)
- **tier:** `lite` (default), `mid`, `flagship`
- **pergunta presente** → envia direto
- **pergunta ausente** → Claude sintetiza a conversa e cria o prompt

## Fluxo

### Com pergunta explícita

Analisar a mensagem para determinar persona e travessia (mesmo roteamento do Espelho).

```bash
uv run memoria consult FAMILIA TIER "PERGUNTA" \
  [--persona PERSONA] [--travessia TRAVESSIA] [--org]
```

**Exemplos:**
- `/mm-consult gemini lite "como precificar o curso?"` → `run.py gemini lite "como precificar o curso?" --persona divulgadora`
- `/mm-consult deepseek "analise essa tensão"` → `run.py deepseek "analise essa tensão" --persona terapeuta`

**Apresentação:** O script imprime a resposta, custo e saldo. **Sempre mostrar a resposta completa ao usuário, sem resumir ou omitir.** Comentários do Claude, se houver, vêm depois da resposta integral.

### Sem pergunta (síntese da conversa)

Quando o usuário omite a pergunta, ele quer uma segunda opinião sobre a conversa atual. **Importante:** sintetizar apenas trechos do Modo Espelho (reflexão, estratégia, conteúdo). Ignorar completamente trechos do Modo Construtor (código, debug, arquitetura do projeto). O Claude deve:

1. **Sintetizar o contexto** — resumir a conversa em um prompt autocontido:
   - Qual o tema e objetivo da conversa
   - Que contexto relevante foi usado (travessia, anexos, referências)
   - O que já foi discutido/decidido
   - O que o usuário está pedindo (a última pergunta ou direção)

2. **Formular o pedido** — criar um prompt claro para o LLM externo, incluindo o contexto sintetizado e o que se espera como resposta.

3. **Enviar como ask** — usar o mesmo comando, passando o prompt sintetizado como pergunta:
   ```bash
   uv run memoria consult FAMILIA TIER "PROMPT_SINTETIZADO" \
     [--persona PERSONA] [--travessia TRAVESSIA] [--org]
   ```

**Importante:** O prompt sintetizado deve ser **autocontido** — o LLM externo não tem acesso à conversa, então tudo que ele precisa saber deve estar no prompt. Incluir dados concretos (nomes, números, trechos) em vez de referências vagas ("como discutimos").

**Exemplo:**
Conversa sobre sugestões de artigo para o episódio 5 do Reflexo. Claude sintetiza:

```
Estou preparando o episódio 5 da série Reflexo (série sobre liderança e complexidade).
O episódio aborda [pontos-chave do roteiro]. Já sugeri os temas: A, B e C.

Sugira 3 temas alternativos para um artigo focado em líderes de software,
mantendo o tom de profundidade sem academicismo.
```

## Credits — Saldo

```bash
uv run memoria consult credits
```

Mostra limite, uso e saldo restante do OpenRouter.

## Famílias e tiers disponíveis

| Família | Lite | Mid | Flagship |
|---------|------|-----|----------|
| gemini | gemini-2.5-flash-lite | gemini-2.5-flash | gemini-3.1-pro-preview |
| grok | grok-3-mini | grok-3 | grok-4 |
| deepseek | deepseek-chat | deepseek-v3.2 | deepseek-r1 |
| openai | gpt-4.1-mini | gpt-4.1 | o3 |
| claude | haiku-4.5 | sonnet-4.6 | opus-4.6 |
