"""Extração automática de memórias via LLM."""

import json
import re
import unicodedata

from openai import OpenAI

from memoria.config import (
    EXTRACTION_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    USER_NAME,
)
from memoria.models import ExtractedMemory, ExtractedWeekItem, Message

EXTRACTION_PROMPT = """Você é o sistema de memória do Espelho — segundo cérebro de {user_name}.

Analise a conversa abaixo e extraia memórias significativas. Cada memória deve ser algo que valha lembrar em conversas futuras.

## Tipos de memória
- **decision**: Decisão tomada (operacional ou estratégica)
- **insight**: Realização ou compreensão nova
- **idea**: Proposta ou conceito para implementação futura (feature, produto, abordagem)
- **journal**: Entrada de diário — registro pessoal de estado emocional, reflexão do momento, vivência
- **tension**: Tensão psicológica, conflito interno, dilema
- **learning**: Algo aprendido (técnico, pessoal, relacional)
- **pattern**: Padrão recorrente observado
- **commitment**: Compromisso assumido
- **reflection**: Reflexão profunda sobre identidade ou propósito

## Camadas Junguianas
- **self**: Realizações profundas sobre identidade, propósito, valores fundamentais
- **ego**: Decisões operacionais, estratégia, conhecimento do dia-a-dia
- **shadow**: Tensões, temas evitados, pontos cegos, resistências

## Regras
- Extraia entre 0 e 5 memórias (só o que for realmente significativo)
- Cada memória precisa de título conciso e conteúdo que faça sentido isolado
- O campo "context" deve capturar o contexto da conversa que gerou a memória
- Tags devem ser palavras-chave úteis para busca futura
- Se a conversa for trivial ou técnica demais, retorne lista vazia

## Formato de resposta
Retorne APENAS um JSON array, sem markdown:
[
  {{
    "title": "...",
    "content": "...",
    "context": "...",
    "memory_type": "...",
    "layer": "...",
    "tags": ["...", "..."],
    "travessia": "..." ou null,
    "persona": "..." ou null
  }}
]

Se não houver memórias significativas, retorne: []

## Conversa
"""


JOURNAL_CLASSIFICATION_PROMPT = """Você é o sistema de memória do Espelho — segundo cérebro de {user_name}.

Analise esta entrada de diário e classifique-a. Retorne APENAS um JSON object, sem markdown:

{{
  "title": "título conciso que capture a essência da entrada (máx 10 palavras)",
  "layer": "self ou ego ou shadow",
  "tags": ["tag1", "tag2", "..."]
}}

## Critérios para camada Junguiana
- **self**: Toca em identidade profunda, propósito, valores fundamentais, sentido de vida
- **ego**: Estado operacional do dia-a-dia, frustrações práticas, reflexões sobre trabalho/rotina
- **shadow**: Tensões não resolvidas, medos, padrões que se repetem, temas evitados, vulnerabilidade

## Regras para tags
- 3 a 6 tags emocionais/temáticas para busca futura
- Use palavras que capturem o sentimento, não apenas o assunto
- Exemplos: angústia, gratidão, solidão, clareza, exaustão, propósito, medo, esperança

## Entrada de diário
"""


TASK_EXTRACTION_PROMPT = """Você é o sistema de gestão de tarefas do Espelho — segundo cérebro de {user_name}.

Analise a conversa abaixo e identifique compromissos, próximas ações ou tarefas que {user_name} assumiu ou precisa fazer.

## Regras
- Extraia apenas compromissos concretos e acionáveis (não ideias vagas)
- Ignore tarefas já concluídas na conversa
- Cada task deve ter um título curto e acionável (verbo no infinitivo)
- Se houver data mencionada, extraia no formato YYYY-MM-DD
- Se houver travessia associada (projeto/contexto), inclua o slug
- Se não houver tasks, retorne lista vazia
- Máximo 5 tasks por conversa

## Formato de resposta
Retorne APENAS um JSON array, sem markdown:
[
  {{
    "title": "...",
    "due_date": "YYYY-MM-DD" ou null,
    "travessia": "slug" ou null,
    "stage": "etapa/ciclo" ou null,
    "context": "contexto breve de onde surgiu a task"
  }}
]

Se não houver tasks, retorne: []

## Conversa
"""


class ExtractedTask:
    """Task extraída pelo LLM."""

    def __init__(self, title: str, due_date=None, travessia=None, stage=None, context=None):
        self.title = title
        self.due_date = due_date
        self.travessia = travessia
        self.stage = stage
        self.context = context


def _get_extraction_client() -> OpenAI:
    """Retorna cliente para extração via OpenRouter."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY não configurada.")
    return OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)


def normalize_travessia_slug(raw: str | None) -> str | None:
    """Normaliza um slug de travessia proposto pelo LLM para o formato canônico.

    - Remove acentos (organização → organizacao)
    - Lowercase
    - Remove extensão .yaml se vier
    - Substitui espaços/underscores por hífen
    - Retorna None se vazio ou não-string
    """
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or s.lower() in ("null", "none"):
        return None
    # Remove extensão acidental
    if s.lower().endswith(".yaml"):
        s = s[:-5]
    # Remove acentos
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    # Normaliza separadores
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or None


def resolve_travessia(raw: str | None, valid_slugs: set[str] | None = None) -> str | None:
    """Normaliza e valida um slug de travessia.

    Se `valid_slugs` for fornecido, slugs fora dele caem para None.
    Sem `valid_slugs`, retorna apenas o slug normalizado.
    """
    slug = normalize_travessia_slug(raw)
    if slug is None:
        return None
    if valid_slugs is not None and slug not in valid_slugs:
        return None
    return slug


def format_transcript(messages: list[Message]) -> str:
    """Formata mensagens como transcript legível."""
    lines = []
    for msg in messages:
        role = USER_NAME if msg.role == "user" else "Espelho"
        lines.append(f"**{role}:** {msg.content}")
    return "\n\n".join(lines)


def extract_memories(
    messages: list[Message],
    persona: str | None = None,
    travessia: str | None = None,
    valid_travessias: set[str] | None = None,
) -> list[ExtractedMemory]:
    """Extrai memórias de uma conversa usando LLM.

    Se `valid_travessias` for fornecido, slugs de travessia propostos pelo LLM
    são normalizados e validados contra esse set. Slugs inválidos caem para
    None (ou para o default `travessia` se fornecido).
    """
    if not messages:
        return []

    transcript = format_transcript(messages)
    prompt = EXTRACTION_PROMPT.format(user_name=USER_NAME)
    if valid_travessias:
        prompt += (
            "\n## Travessias válidas (use APENAS estes slugs exatos ou null)\n"
            + "\n".join(f"- {slug}" for slug in sorted(valid_travessias))
            + "\n"
        )
    prompt += transcript

    client = _get_extraction_client()

    response = client.chat.completions.create(
        model=EXTRACTION_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    raw = response.choices[0].message.content.strip()

    # Limpar possível markdown wrapping
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    memories = []
    for item in data:
        try:
            mem = ExtractedMemory(**item)
            # Normaliza e valida o slug de travessia proposto pelo LLM
            mem.travessia = resolve_travessia(mem.travessia, valid_travessias)
            # Preencher persona/travessia default se vier vazio
            if not mem.persona and persona:
                mem.persona = persona
            if not mem.travessia and travessia:
                mem.travessia = travessia
            memories.append(mem)
        except Exception:
            continue

    return memories


def extract_tasks(
    messages: list[Message],
    travessia: str | None = None,
    valid_travessias: set[str] | None = None,
) -> list[ExtractedTask]:
    """Extrai tasks de uma conversa usando LLM."""
    if not messages:
        return []

    transcript = format_transcript(messages)
    prompt = TASK_EXTRACTION_PROMPT.format(user_name=USER_NAME)
    if valid_travessias:
        prompt += (
            "\n## Travessias válidas (use APENAS estes slugs exatos ou null)\n"
            + "\n".join(f"- {slug}" for slug in sorted(valid_travessias))
            + "\n"
        )
    prompt += transcript

    client = _get_extraction_client()

    response = client.chat.completions.create(
        model=EXTRACTION_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    tasks = []
    for item in data:
        try:
            raw_travessia = item.get("travessia")
            resolved = resolve_travessia(raw_travessia, valid_travessias)
            task = ExtractedTask(
                title=item["title"],
                due_date=item.get("due_date"),
                travessia=resolved or travessia,
                stage=item.get("stage"),
                context=item.get("context"),
            )
            tasks.append(task)
        except (KeyError, TypeError):
            continue

    return tasks


WEEK_PLAN_PROMPT = """Você é o sistema de planejamento temporal do Espelho — segundo cérebro de {user_name}.

Analise o texto abaixo e extraia TODOS os itens temporais: tarefas, compromissos, eventos, reuniões.

## Data de referência
Hoje é {today} ({weekday}).

## Travessias ativas (projetos/contextos)
{travessias}

## Regras de extração

1. **due_date** (obrigatório): Resolva TODAS as referências temporais relativas para datas absolutas (YYYY-MM-DD).
   - "hoje" → {today}
   - "amanhã" → dia seguinte
   - "sexta" → próxima sexta-feira a partir de hoje
   - etc.

2. **scheduled_at**: Use APENAS quando houver hora EXATA mencionada (ex: "às 19h", "15:00").
   Formato: YYYY-MM-DDTHH:MM. NÃO INVENTE HORÁRIOS.

3. **time_hint**: Use para referências vagas de período ("fim da tarde", "durante o dia", "manhã", "à tarde").
   Se houver scheduled_at, time_hint é null.

4. **travessia**: Associe ao slug da travessia ativa mais provável, usando a lista acima.
   Se não houver match claro, use null.

5. **title**: Curto e acionável. Se o item é tentativo ("vou ver se consigo"), incluir "(tentativo)" no título.

6. **context**: Breve nota de contexto extraída do texto original.

## Formato de resposta
Retorne APENAS um JSON array, sem markdown:
[
  {{
    "title": "...",
    "due_date": "YYYY-MM-DD",
    "scheduled_at": "YYYY-MM-DDTHH:MM" ou null,
    "time_hint": "..." ou null,
    "travessia": "slug" ou null,
    "context": "..."
  }}
]

Se não houver itens, retorne: []

## Texto
"""


def extract_week_plan(
    text: str,
    travessia_context: list[dict],
) -> list[ExtractedWeekItem]:
    """Extrai itens temporais de um plano semanal em linguagem natural."""
    from datetime import datetime

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    weekdays_pt = [
        "segunda-feira",
        "terça-feira",
        "quarta-feira",
        "quinta-feira",
        "sexta-feira",
        "sábado",
        "domingo",
    ]
    weekday = weekdays_pt[now.weekday()]

    travessias_text = (
        "\n".join(f"- **{t['slug']}**: {t['description'][:100]}" for t in travessia_context)
        if travessia_context
        else "(nenhuma travessia ativa)"
    )

    prompt = (
        WEEK_PLAN_PROMPT.format(
            user_name=USER_NAME,
            today=today,
            weekday=weekday,
            travessias=travessias_text,
        )
        + text
    )

    client = _get_extraction_client()

    response = client.chat.completions.create(
        model=EXTRACTION_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    items = []
    for item_data in data:
        try:
            item = ExtractedWeekItem(**item_data)
            items.append(item)
        except Exception:
            continue

    return items


def classify_journal_entry(content: str) -> dict:
    """Classifica uma entrada de diário via LLM."""
    client = _get_extraction_client()

    response = client.chat.completions.create(
        model=EXTRACTION_MODEL,
        messages=[{"role": "user", "content": JOURNAL_CLASSIFICATION_PROMPT.format(user_name=USER_NAME) + content}],
        temperature=0.3,
    )

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"title": content[:60], "layer": "ego", "tags": []}

    return {
        "title": data.get("title", content[:60]),
        "layer": data.get("layer", "ego"),
        "tags": data.get("tags", []),
    }
