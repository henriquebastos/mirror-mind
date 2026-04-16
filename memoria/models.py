"""Modelos Pydantic para o sistema de memória."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Message(BaseModel):
    id: str = Field(default_factory=lambda: _uuid())
    conversation_id: str
    role: str  # 'user', 'assistant', 'system'
    content: str
    created_at: str = Field(default_factory=lambda: _now())
    token_count: int | None = None
    metadata: str | None = None


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: _uuid())
    title: str | None = None
    started_at: str = Field(default_factory=lambda: _now())
    ended_at: str | None = None
    interface: str  # 'claude_code', 'cli', 'django'
    persona: str | None = None
    travessia: str | None = None
    summary: str | None = None
    tags: str | None = None  # JSON array
    metadata: str | None = None


class Memory(BaseModel):
    id: str = Field(default_factory=lambda: _uuid())
    conversation_id: str | None = None
    memory_type: str  # 'decision', 'insight', 'idea', 'journal', 'tension', 'learning', 'pattern', 'commitment', 'reflection'
    layer: str = "ego"  # 'self', 'ego', 'shadow'
    title: str
    content: str
    context: str | None = None
    travessia: str | None = None
    persona: str | None = None
    tags: str | None = None  # JSON array
    created_at: str = Field(default_factory=lambda: _now())
    relevance_score: float = 1.0
    embedding: bytes | None = None
    metadata: str | None = None


class Identity(BaseModel):
    id: str = Field(default_factory=lambda: _uuid())
    layer: str  # 'self', 'ego', 'user', 'organization', 'persona'
    key: str  # 'soul', 'behavior', 'identity', 'principles', ou persona_id
    content: str
    version: str = "1.0.0"
    created_at: str = Field(default_factory=lambda: _now())
    updated_at: str = Field(default_factory=lambda: _now())
    metadata: str | None = None


class Attachment(BaseModel):
    id: str = Field(default_factory=lambda: _uuid())
    travessia_id: str
    name: str
    description: str | None = None
    content: str
    content_type: str = "markdown"  # markdown, text, yaml
    tags: str | None = None  # JSON array
    embedding: bytes | None = None
    created_at: str = Field(default_factory=lambda: _now())
    updated_at: str = Field(default_factory=lambda: _now())
    metadata: str | None = None


class Task(BaseModel):
    id: str = Field(default_factory=lambda: _uuid())
    travessia: str | None = None
    title: str
    status: str = "todo"  # 'todo', 'doing', 'done', 'blocked'
    due_date: str | None = None  # ISO date (YYYY-MM-DD)
    scheduled_at: str | None = None  # ISO datetime (YYYY-MM-DDTHH:MM) — compromissos com hora fixa
    time_hint: str | None = None  # string livre ("fim da tarde", "manhã", "durante o dia")
    stage: str | None = None  # etapa/ciclo dentro da travessia
    context: str | None = None
    source: str = "manual"  # 'manual', 'caminho', 'conversation', 'week_plan'
    created_at: str = Field(default_factory=lambda: _now())
    updated_at: str = Field(default_factory=lambda: _now())
    completed_at: str | None = None
    metadata: str | None = None


class ExtractedWeekItem(BaseModel):
    """Item extraído de um plano semanal (task ou compromisso)."""

    title: str
    due_date: str  # YYYY-MM-DD (obrigatório — sempre resolvido pelo LLM)
    scheduled_at: str | None = None  # YYYY-MM-DDTHH:MM para hora fixa
    time_hint: str | None = None  # "manhã", "tarde", "fim da tarde", etc.
    travessia: str | None = None
    context: str | None = None


class ExtractedMemory(BaseModel):
    """Memória extraída pelo LLM antes de receber id e embedding."""

    title: str
    content: str
    context: str | None = None
    memory_type: str
    layer: str = "ego"
    tags: list[str] = Field(default_factory=list)
    travessia: str | None = None
    persona: str | None = None


def _uuid() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
