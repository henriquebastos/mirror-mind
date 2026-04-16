"""MemoriaClient — fachada única para o sistema de memória."""

import json
import unicodedata

from memoria.db import get_connection
from memoria.embeddings import embedding_to_bytes, generate_embedding
from memoria.extraction import extract_memories, extract_tasks, extract_week_plan
from memoria.models import Attachment, Conversation, Identity, Memory, Message, Task
from memoria.search import MemoriaSearch
from memoria.store import Store


def _strip_accents(s: str) -> str:
    """Remove acentos para comparação textual (ex: 'episódio' → 'episodio')."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


class MemoriaClient:
    def __init__(self, env: str | None = None):
        from memoria.config import _DB_NAMES, _ENV_DIRS, _LOCAL_DIR

        if env is None:
            from memoria.config import MEMORIA_ENV

            env = MEMORIA_ENV
        self.env = env
        env_dir = _ENV_DIRS.get(env, _LOCAL_DIR)
        self.db_path = env_dir / _DB_NAMES.get(env, f"memoria_{env}.db")
        self.conn = get_connection(self.db_path)
        self.store = Store(self.conn)
        self.search_engine = MemoriaSearch(self.store)

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    def reset(self) -> None:
        """Apaga todos os dados do banco. Bloqueado em produção."""
        if self.is_production:
            raise RuntimeError(
                "reset() bloqueado em produção. Use MEMORIA_ENV=development ou MEMORIA_ENV=test."
            )
        self.conn.executescript("""
            DELETE FROM memory_access_log;
            DELETE FROM conversation_embeddings;
            DELETE FROM memories;
            DELETE FROM messages;
            DELETE FROM conversations;
            DELETE FROM identity;
            DELETE FROM attachments;
            DELETE FROM tasks;
        """)
        self.conn.commit()

    # --- Conversas ---

    def start_conversation(
        self,
        interface: str,
        persona: str | None = None,
        travessia: str | None = None,
        title: str | None = None,
    ) -> Conversation:
        """Inicia uma nova conversa."""
        conv = Conversation(
            interface=interface,
            persona=persona,
            travessia=travessia,
            title=title,
        )
        return self.store.create_conversation(conv)

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        token_count: int | None = None,
    ) -> Message:
        """Adiciona uma mensagem a uma conversa existente."""
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            token_count=token_count,
        )
        return self.store.add_message(msg)

    def end_conversation(
        self,
        conversation_id: str,
        extract: bool = True,
    ) -> list[Memory]:
        """Finaliza conversa: extrai memórias e tasks, gera embeddings, armazena."""
        from memoria.models import _now

        # Atualizar ended_at
        self.store.update_conversation(conversation_id, ended_at=_now())

        if not extract:
            return []

        # Buscar conversa e mensagens
        conv = self.store.get_conversation(conversation_id)
        messages = self.store.get_messages(conversation_id)

        if not messages:
            return []

        # Carrega slugs válidos de travessias para validar output do LLM
        valid_travessias = {
            ident.key for ident in self.store.get_identity_by_layer("travessia")
        } or None

        # Extrair memórias via LLM
        extracted = extract_memories(
            messages,
            persona=conv.persona if conv else None,
            travessia=conv.travessia if conv else None,
            valid_travessias=valid_travessias,
        )

        # Extrair tasks via LLM
        try:
            extracted_tasks = extract_tasks(
                messages,
                travessia=conv.travessia if conv else None,
                valid_travessias=valid_travessias,
            )
            for et in extracted_tasks:
                # Evitar duplicatas
                existing = self.store.find_tasks_by_title(et.title, et.travessia)
                if not existing:
                    self.add_task(
                        title=et.title,
                        travessia=et.travessia,
                        due_date=et.due_date,
                        stage=et.stage,
                        context=et.context,
                        source="conversation",
                    )
        except Exception:
            pass  # Falha na extração de tasks não deve impedir o fluxo

        # Gerar summary da conversa para embedding
        summary_parts = []
        for msg in messages:
            if msg.role in ("user", "assistant"):
                summary_parts.append(msg.content[:500])
        summary_text = " ".join(summary_parts)[:2000]

        if summary_text:
            summary_emb = generate_embedding(summary_text)
            self.store.store_conversation_embedding(
                conversation_id, embedding_to_bytes(summary_emb)
            )
            # Atualizar summary na conversa
            self.store.update_conversation(conversation_id, summary=summary_text[:500])

        # Persistir memórias extraídas com embeddings
        stored_memories = []
        for ext in extracted:
            embed_text = f"{ext.title}. {ext.content}"
            if ext.context:
                embed_text += f" Contexto: {ext.context}"

            emb = generate_embedding(embed_text)

            mem = Memory(
                conversation_id=conversation_id,
                memory_type=ext.memory_type,
                layer=ext.layer,
                title=ext.title,
                content=ext.content,
                context=ext.context,
                travessia=ext.travessia,
                persona=ext.persona,
                tags=json.dumps(ext.tags) if ext.tags else None,
                embedding=embedding_to_bytes(emb),
            )
            stored = self.store.create_memory(mem)
            stored_memories.append(stored)

        return stored_memories

    # --- Busca ---

    def search(
        self,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
        layer: str | None = None,
        travessia: str | None = None,
    ) -> list[tuple[Memory, float]]:
        """Busca memórias por similaridade híbrida."""
        return self.search_engine.search(
            query,
            limit=limit,
            memory_type=memory_type,
            layer=layer,
            travessia=travessia,
        )

    # --- Atalhos de consulta ---

    def get_by_type(self, memory_type: str) -> list[Memory]:
        """Retorna todas as memórias de um tipo."""
        return self.store.get_memories_by_type(memory_type)

    def get_by_layer(self, layer: str) -> list[Memory]:
        """Retorna todas as memórias de uma camada."""
        return self.store.get_memories_by_layer(layer)

    def get_by_travessia(self, travessia: str) -> list[Memory]:
        """Retorna todas as memórias de uma travessia."""
        return self.store.get_memories_by_travessia(travessia)

    def get_timeline(self, start: str, end: str) -> list[Memory]:
        """Retorna memórias em um período."""
        return self.store.get_memories_timeline(start, end)

    # --- Memória manual ---

    def add_memory(
        self,
        title: str,
        content: str,
        memory_type: str,
        layer: str = "ego",
        context: str | None = None,
        travessia: str | None = None,
        persona: str | None = None,
        tags: list[str] | None = None,
        conversation_id: str | None = None,
    ) -> Memory:
        """Adiciona uma memória manualmente (sem extração automática)."""
        embed_text = f"{title}. {content}"
        if context:
            embed_text += f" Contexto: {context}"

        emb = generate_embedding(embed_text)

        mem = Memory(
            conversation_id=conversation_id,
            memory_type=memory_type,
            layer=layer,
            title=title,
            content=content,
            context=context,
            travessia=travessia,
            persona=persona,
            tags=json.dumps(tags) if tags else None,
            embedding=embedding_to_bytes(emb),
        )
        return self.store.create_memory(mem)

    # --- Diário ---

    def add_journal(
        self,
        content: str,
        title: str | None = None,
        layer: str | None = None,
        tags: list[str] | None = None,
        conversation_id: str | None = None,
        travessia: str | None = None,
    ) -> Memory:
        """Adiciona uma entrada de diário, classificando via LLM se necessário."""
        from memoria.extraction import classify_journal_entry

        if not title or not layer or not tags:
            classification = classify_journal_entry(content)
            title = title or classification["title"]
            layer = layer or classification["layer"]
            tags = tags or classification["tags"]

        return self.add_memory(
            title=title,
            content=content,
            memory_type="journal",
            layer=layer,
            tags=tags,
            conversation_id=conversation_id,
            travessia=travessia,
        )

    # --- Identidade ---

    def set_identity(
        self,
        layer: str,
        key: str,
        content: str,
        version: str = "1.0.0",
    ) -> Identity:
        """Define ou atualiza um prompt de identidade."""
        identity = Identity(
            layer=layer,
            key=key,
            content=content,
            version=version,
        )
        return self.store.upsert_identity(identity)

    def get_identity(
        self,
        layer: str | None = None,
        key: str | None = None,
    ) -> str | list[Identity] | None:
        """Recupera identidade. Com layer+key retorna conteúdo. Só layer retorna lista."""
        if layer and key:
            ident = self.store.get_identity(layer, key)
            return ident.content if ident else None
        if layer:
            return self.store.get_identity_by_layer(layer)
        return self.store.get_all_identity()

    # --- Caminho (status de travessias) ---

    def get_caminho(self, travessia: str) -> str | None:
        """Recupera o Caminho de uma travessia.

        Se houver sync_file configurado, lê do arquivo externo.
        Fallback para o banco se o arquivo não existir.
        """
        sync_file = self.get_sync_file(travessia)
        if sync_file:
            from pathlib import Path

            path = Path(sync_file).expanduser()
            try:
                return path.read_text(encoding="utf-8")
            except (FileNotFoundError, PermissionError, OSError):
                pass  # fallback para o banco
        return self.get_identity("caminho", travessia)

    def set_caminho(self, travessia: str, content: str) -> Identity:
        """Define ou atualiza o Caminho de uma travessia."""
        return self.set_identity("caminho", travessia, content)

    def get_travessia_status(self, travessia: str = None) -> dict:
        """Reúne contexto completo para síntese de status.

        Se travessia=None, retorna todas as travessias.
        """
        if travessia:
            travessias = [travessia]
        else:
            all_t = self.store.get_identity_by_layer("travessia")
            travessias = [t.key for t in all_t]

        result = {}
        for t in travessias:
            result[t] = {
                "identity": self.get_identity("travessia", t),
                "caminho": self.get_caminho(t),
                "recent_memories": self.store.get_memories_by_travessia(t)[:10],
                "recent_conversations": self.store.get_recent_conversations_by_travessia(
                    t, limit=5
                ),
            }
        return result

    # --- Tasks ---

    def add_task(
        self,
        title: str,
        travessia: str | None = None,
        due_date: str | None = None,
        scheduled_at: str | None = None,
        time_hint: str | None = None,
        stage: str | None = None,
        context: str | None = None,
        source: str = "manual",
    ) -> Task:
        """Cria uma nova task."""
        task = Task(
            travessia=travessia,
            title=title,
            due_date=due_date,
            scheduled_at=scheduled_at,
            time_hint=time_hint,
            stage=stage,
            context=context,
            source=source,
        )
        return self.store.create_task(task)

    def ingest_week_plan(self, text: str) -> list[dict]:
        """Extrai itens de um plano semanal em linguagem natural.

        Retorna lista de dicts com items propostos (não salva — requer confirmação).
        """

        # Coletar travessias ativas para contexto do LLM
        all_travessias = self.store.get_identity_by_layer("travessia")
        travessia_context = []
        for t in all_travessias:
            desc = t.content[:200] if t.content else ""
            travessia_context.append({"slug": t.key, "description": desc})

        items = extract_week_plan(text, travessia_context)

        # Verificar similaridade com tasks existentes
        result = []
        for item in items:
            similar = self.store.find_tasks_by_title(item.title[:20])
            week_similar = [
                t for t in similar if t.due_date == item.due_date and t.status != "done"
            ]
            result.append(
                {
                    "item": item,
                    "similar_existing": week_similar,
                }
            )

        return result

    def save_week_items(self, items: list) -> list[Task]:
        """Salva itens confirmados do plano semanal.

        Recebe lista de ExtractedWeekItem.
        """
        from memoria.models import ExtractedWeekItem

        created = []
        for item in items:
            if isinstance(item, dict):
                item = item["item"] if "item" in item else ExtractedWeekItem(**item)
            task = self.add_task(
                title=item.title,
                travessia=item.travessia,
                due_date=item.due_date,
                scheduled_at=item.scheduled_at,
                time_hint=item.time_hint,
                context=item.context,
                source="week_plan",
            )
            created.append(task)
        return created

    def complete_task(self, task_id: str) -> None:
        """Marca uma task como concluída."""
        from memoria.models import _now

        self.store.update_task(task_id, status="done", completed_at=_now())

    def update_task(self, task_id: str, **kwargs) -> None:
        """Atualiza campos de uma task."""
        self.store.update_task(task_id, **kwargs)

    def list_tasks(
        self,
        travessia: str | None = None,
        status: str | None = None,
        open_only: bool = False,
    ) -> list[Task]:
        """Lista tasks com filtros."""
        if open_only:
            return self.store.get_open_tasks(travessia)
        if status:
            tasks = self.store.get_tasks_by_status(status)
            if travessia:
                tasks = [t for t in tasks if t.travessia == travessia]
            return tasks
        if travessia:
            return self.store.get_tasks_by_travessia(travessia)
        return self.store.get_all_tasks()

    def find_tasks(self, title_fragment: str, travessia: str | None = None) -> list[Task]:
        """Busca tasks por fragmento do título."""
        return self.store.find_tasks_by_title(title_fragment, travessia)

    def import_tasks_from_caminho(self, travessia: str) -> list[Task]:
        """Extrai tasks do caminho de uma travessia (checkboxes não marcados)."""
        from memoria.tasks import parse_caminho_tasks

        caminho = self.get_caminho(travessia)
        if not caminho:
            return []
        parsed = parse_caminho_tasks(caminho, travessia)
        created = []
        for task_data in parsed:
            # Evitar duplicatas por título + travessia
            existing = self.store.find_tasks_by_title(task_data["title"], travessia)
            if existing:
                continue
            task = self.add_task(
                title=task_data["title"],
                travessia=travessia,
                stage=task_data.get("stage"),
                source="caminho",
            )
            created.append(task)
        return created

    def get_sync_file(self, travessia: str) -> str | None:
        """Retorna o arquivo de sync configurado para uma travessia."""
        ident = self.store.get_identity("travessia", travessia)
        if not ident or not ident.metadata:
            return None
        try:
            meta = json.loads(ident.metadata)
            return meta.get("sync_file")
        except (json.JSONDecodeError, TypeError):
            return None

    def set_sync_file(self, travessia: str, file_path: str) -> None:
        """Configura o arquivo de sync para uma travessia."""
        ident = self.store.get_identity("travessia", travessia)
        if not ident:
            raise ValueError(f"Travessia '{travessia}' não encontrada.")
        try:
            meta = json.loads(ident.metadata) if ident.metadata else {}
        except (json.JSONDecodeError, TypeError):
            meta = {}
        meta["sync_file"] = file_path
        self.store.update_identity_metadata("travessia", travessia, json.dumps(meta))

    def sync_tasks_from_file(self, travessia: str) -> dict:
        """Sincroniza tasks de uma travessia a partir do arquivo de referência.

        Retorna dict com contagens: created, completed, unchanged.
        """
        from pathlib import Path

        from memoria.tasks import parse_caminho_tasks, parse_done_tasks

        sync_file = self.get_sync_file(travessia)
        if not sync_file:
            raise ValueError(
                f"Nenhum arquivo de sync configurado para '{travessia}'. "
                f"Use: mm:tasks sync-config {travessia} /caminho/do/arquivo"
            )

        path = Path(sync_file).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {sync_file}")

        content = path.read_text(encoding="utf-8")

        # Parsear tasks do arquivo (mesmo formato do caminho: checkboxes markdown)
        file_pending = parse_caminho_tasks(content, travessia)
        file_done = parse_done_tasks(content, travessia)

        existing_tasks = self.store.get_tasks_by_travessia(travessia)
        existing_by_title = {t.title: t for t in existing_tasks}

        result = {"created": 0, "completed": 0, "unchanged": 0}

        # Criar tasks novas (pendentes no arquivo, não existem no banco)
        for task_data in file_pending:
            if task_data["title"] not in existing_by_title:
                self.add_task(
                    title=task_data["title"],
                    travessia=travessia,
                    stage=task_data.get("stage"),
                    source="sync",
                )
                result["created"] += 1
            else:
                result["unchanged"] += 1

        # Marcar como done tasks que estão concluídas no arquivo mas abertas no banco
        for task_data in file_done:
            if task_data["title"] in existing_by_title:
                existing = existing_by_title[task_data["title"]]
                if existing.status != "done":
                    self.complete_task(existing.id)
                    result["completed"] += 1
                else:
                    result["unchanged"] += 1

        return result

    # --- Anexos (Attachments) ---

    def add_attachment(
        self,
        travessia_id: str,
        name: str,
        content: str,
        description: str | None = None,
        content_type: str = "markdown",
        tags: list[str] | None = None,
    ) -> Attachment:
        """Adiciona um anexo a uma travessia, gerando embedding do conteúdo."""
        emb = generate_embedding(content[:8000])

        att = Attachment(
            travessia_id=travessia_id,
            name=name,
            content=content,
            description=description,
            content_type=content_type,
            tags=json.dumps(tags) if tags else None,
            embedding=embedding_to_bytes(emb),
        )
        return self.store.create_attachment(att)

    def get_attachments(self, travessia_id: str) -> list[Attachment]:
        """Lista todos os anexos de uma travessia."""
        return self.store.get_attachments_by_travessia(travessia_id)

    def get_attachment(self, travessia_id: str, name: str) -> Attachment | None:
        """Retorna um anexo por nome dentro da travessia."""
        return self.store.get_attachment_by_name(travessia_id, name)

    def remove_attachment(self, travessia_id: str, name: str) -> bool:
        """Remove um anexo por nome."""
        att = self.store.get_attachment_by_name(travessia_id, name)
        if not att:
            return False
        return self.store.delete_attachment(att.id)

    def search_attachments(
        self,
        travessia_id: str,
        query: str,
        limit: int = 3,
    ) -> list[tuple[Attachment, float]]:
        """Busca semântica dentro dos anexos de uma travessia."""
        import numpy as np

        from memoria.embeddings import bytes_to_embedding

        query_emb = generate_embedding(query)
        attachments = self.store.get_all_attachments_with_embeddings(travessia_id)

        if not attachments:
            return []

        scored = []
        for att in attachments:
            att_emb = bytes_to_embedding(att.embedding)
            similarity = float(
                np.dot(query_emb, att_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(att_emb))
            )
            scored.append((att, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def search_all_attachments(
        self,
        query: str,
        limit: int = 5,
    ) -> list[tuple[Attachment, float]]:
        """Busca semântica em anexos de TODAS as travessias.

        Aplica boost quando termos da query aparecem no nome ou descrição
        do anexo, para que matches diretos não se percam no ranking.
        """
        import re

        import numpy as np

        from memoria.embeddings import bytes_to_embedding

        query_emb = generate_embedding(query)
        attachments = self.store.get_all_attachments_with_embeddings_global()

        if not attachments:
            return []

        # Extrai tokens da query (inclui números curtos como "6")
        query_tokens = [
            _strip_accents(t.lower())
            for t in re.findall(r"\w+", query)
            if len(t) >= 2 or t.isdigit()
        ]

        scored = []
        for att in attachments:
            att_emb = bytes_to_embedding(att.embedding)
            similarity = float(
                np.dot(query_emb, att_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(att_emb))
            )

            # Boost por match textual no nome/descrição/travessia
            # Expande "episodio6" → "episodio 6" para match de tokens individuais
            raw_searchable = f"{att.travessia_id} {att.name} {att.description or ''}".lower()
            searchable = _strip_accents(raw_searchable)
            searchable = re.sub(r"(\D)(\d)", r"\1 \2", searchable)
            searchable = re.sub(r"(\d)(\D)", r"\1 \2", searchable)
            matches = sum(1 for t in query_tokens if t in searchable)
            if query_tokens and matches:
                ratio = matches / len(query_tokens)
                # Boost proporcional: mais tokens presentes = boost maior
                boost = ratio * 0.15
                similarity += boost

            scored.append((att, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def detect_travessia(self, query: str, threshold: float = 0.35) -> list[tuple[str, float, str]]:
        """Detecta travessias relevantes a partir de um prompt do usuário.

        Usa dois níveis de matching:
          1. Match textual direto — ID da travessia aparece no texto
          2. Match semântico — embedding do query vs descrição da travessia

        Retorna lista de (travessia_id, score, match_type) ordenada por score.
        Só retorna resultados acima do threshold.
        """
        import re

        query_lower = _strip_accents(query.lower())
        query_tokens = set(re.findall(r"\w+", query_lower))

        travessias = self.store.get_identity_by_layer("travessia")
        if not travessias:
            return []

        # Nível 1: match textual direto (ID ou nome da travessia no query)
        text_matches = []
        for t in travessias:
            trav_id = t.key
            trav_id_normalized = _strip_accents(trav_id.replace("-", " ").lower())
            trav_id_tokens = set(trav_id_normalized.split())

            # Extrair nome da primeira linha do content (ex: "# O Reflexo")
            first_line = (t.content or "").split("\n")[0].strip().lstrip("# ").strip()
            trav_name_normalized = _strip_accents(first_line.lower())
            trav_name_tokens = set(re.findall(r"\w+", trav_name_normalized))

            # Check: algum token significativo do ID ou nome aparece no query?
            id_overlap = trav_id_tokens & query_tokens
            name_overlap = trav_name_tokens & query_tokens

            # Filtrar tokens muito genéricos (artigos, preposições)
            stopwords = {
                "o",
                "a",
                "os",
                "as",
                "de",
                "do",
                "da",
                "dos",
                "das",
                "e",
                "em",
                "no",
                "na",
            }
            id_overlap -= stopwords
            name_overlap -= stopwords

            if id_overlap or name_overlap:
                # Score baseado na proporção de tokens matched
                all_trav_tokens = (trav_id_tokens | trav_name_tokens) - stopwords
                matched = id_overlap | name_overlap
                score = len(matched) / max(len(all_trav_tokens), 1)
                text_matches.append((trav_id, min(1.0, score + 0.5), "text"))

        if text_matches:
            # Match textual é forte o suficiente — retornar sem gastar API
            text_matches.sort(key=lambda x: x[1], reverse=True)
            return text_matches

        # Nível 2: match semântico (quando não há match textual)
        try:
            query_emb = generate_embedding(query)
        except Exception:
            return []

        semantic_matches = []
        for t in travessias:
            # Usar descrição da travessia para embedding
            desc_text = t.content[:1000] if t.content else t.key
            try:
                desc_emb = generate_embedding(desc_text)
                import numpy as np

                similarity = float(
                    np.dot(query_emb, desc_emb)
                    / (np.linalg.norm(query_emb) * np.linalg.norm(desc_emb))
                )
                if similarity >= threshold:
                    semantic_matches.append((t.key, similarity, "semantic"))
            except Exception:
                continue

        semantic_matches.sort(key=lambda x: x[1], reverse=True)
        return semantic_matches

    def list_active_travessias(self) -> list[dict]:
        """Retorna lista resumida de travessias ativas para roteamento.

        Retorna dicts com: id, name, description (primeiras 150 chars).
        """
        import re

        travessias = self.store.get_identity_by_layer("travessia")
        result = []
        for t in travessias:
            content = t.content or ""
            # Extrair nome
            first_line = content.split("\n")[0].strip().lstrip("# ").strip()
            # Extrair status
            status_match = re.search(r"\*\*Status:\*\*\s*(\w+)", content)
            status = status_match.group(1) if status_match else "unknown"
            if status != "active":
                continue
            # Extrair descrição
            desc_match = re.search(r"## Descrição\s*\n+(.+?)(?:\n\n|\n##)", content, re.DOTALL)
            description = desc_match.group(1).strip()[:150] if desc_match else ""
            result.append(
                {
                    "id": t.key,
                    "name": first_line,
                    "description": description,
                }
            )
        return result

    def load_espelho_context(
        self,
        persona: str | None = None,
        travessia: str | None = None,
        org: bool = False,
        query: str | None = None,
    ) -> str:
        """Carrega contexto de identidade formatado para uso em prompt.

        Retorna texto com seções === layer/key === para injeção em system prompt.
        """
        sections = [
            ("self/soul", self.get_identity("self", "soul")),
            ("ego/behavior", self.get_identity("ego", "behavior")),
            ("ego/identity", self.get_identity("ego", "identity")),
            ("user/identity", self.get_identity("user", "identity")),
        ]

        if org:
            sections.append(
                ("organization/identity", self.get_identity("organization", "identity"))
            )
            sections.append(
                ("organization/principles", self.get_identity("organization", "principles"))
            )

        if persona:
            content = self.get_identity("persona", persona)
            if content:
                sections.append((f"persona/{persona}", content))

        # Carregar conhecimento relevante (ex: princípios da Liderança Soberana)
        knowledge_entries = self.store.get_identity_by_layer("knowledge")
        for entry in knowledge_entries:
            sections.append((f"knowledge/{entry.key}", entry.content))

        if travessia:
            content = self.get_identity("travessia", travessia)
            if content:
                sections.append((f"travessia/{travessia}", content))

        parts = []
        for label, content in sections:
            if content:
                parts.append(f"=== {label} ===\n{content}")

        # Anexos relevantes
        if query:
            if travessia:
                results = self.search_attachments(travessia, query, limit=5)
            else:
                results = self.search_all_attachments(query, limit=8)
            relevant = [(att, score) for att, score in results if score > 0.4]
            if relevant:
                att_parts = ["=== anexos relevantes ==="]
                for att, score in relevant:
                    source = f" [{att.travessia_id}]" if not travessia else ""
                    att_parts.append(f"--- {att.name}{source} (score: {score:.3f}) ---")
                    if att.description:
                        att_parts.append(f"Descrição: {att.description}")
                    att_parts.append(att.content)
                parts.append("\n".join(att_parts))

        return "\n\n".join(parts)

    def load_full_identity(self) -> str:
        """Carrega toda a identidade como texto formatado para injeção em prompt."""
        all_ids = self.store.get_all_identity()
        if not all_ids:
            return ""

        sections = {}
        for ident in all_ids:
            label = f"{ident.layer}/{ident.key}"
            sections[label] = ident.content

        parts = []
        for label, content in sections.items():
            parts.append(f"--- {label} ---\n{content}")
        return "\n\n".join(parts)
