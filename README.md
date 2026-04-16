# Mirror Mind

Jungian AI mirror — a conscious reflection of its user, not a generic assistant.

The AI speaks in first person. You interact in first person. A dialogue between selves.

## How it works

Mirror Mind separates **code** (this repo) from **personal data** (your identity, personas, journeys). Your data lives outside the repo in a directory pointed to by `MIRROR_USER_DIR`.

```
# This repo (public, generic)
memoria/         → Long-term memory system (Python)
economy/         → Personal finance tracking
users/me/        → Template for your identity (copy and customize)
.pi/skills/      → Operational skills (mirror, consult, journey, etc.)

# Your data (private, outside the repo)
$MIRROR_USER_DIR/
  self/            → Soul and purpose (deepest identity)
  ego/             → Behavior, tone, and operational identity
  personas/        → Domain specialists (your custom lenses)
  user/            → Your profile (identity, DISC, Big Five)
  organization/    → Your organization's identity
  travessias/      → Journeys — projects and life arcs
  research/        → Your research notes
  tools/           → Your custom scripts
  reference.md     → Your operational reference
```

Personas are not separate entities — they are specialized lenses the ego activates based on context. The voice is always one.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) or [pi](https://github.com/mariozechner/coding-agent)
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (Python package manager)

## Quick start

```bash
# Clone the repository
git clone https://github.com/henriquebastos/mirror-mind.git
cd mirror-mind

# Install Python dependencies
uv sync

# Set up your identity from the template
mkdir -p ~/.config/espelho/myname
cp -r users/me/* ~/.config/espelho/myname

# Set up environment variables
cp .env.example .env
# Edit .env:
#   OPENAI_API_KEY=...           (embeddings)
#   OPENROUTER_API_KEY=...       (multi-LLM)
#   MIRROR_USER_DIR=~/.config/espelho/myname
#   MIRROR_USER_NAME=Your Name
```

## Setting up your identity

Mirror Mind is a framework — it ships with empty templates in `users/me/`. You copy them to your `MIRROR_USER_DIR` and fill them with **your** identity.

### 1. Define your soul and ego

Edit the YAML files in your `MIRROR_USER_DIR`:

- **`self/soul.yaml`** — Who you are at the deepest level. Purpose, values, worldview.
- **`ego/identity.yaml`** — Your operational identity. What you do, how you present yourself.
- **`ego/behavior.yaml`** — Tone and style rules. How the mirror should speak.
- **`user/identity.yaml`** — Your profile: name, role, background.
- **`organization/identity.yaml`** — Your company or project (optional).

### 2. Create your personas

Copy the template for each domain you want a specialized lens:

```bash
cd $MIRROR_USER_DIR
cp personas/_template.yaml personas/writer.yaml
cp personas/_template.yaml personas/therapist.yaml
```

Edit each file with the persona's identity, approach, and routing keywords. Personas inherit from `ego` (behavior) or `self` (full soul) depending on depth.

### 3. Create your journeys (travessias)

Copy the template for each ongoing journey:

```bash
cd $MIRROR_USER_DIR
cp travessias/_template.yaml travessias/my-journey.yaml
```

A travessia is any project, arc, or area of your life where things are happening and the mirror needs context.

### 4. Populate the memory bank

```bash
uv run python -m memoria.seed --env production
```

This migrates your YAML content into the memory database (`~/.espelho/memoria.db`).

### 5. Start using

```bash
claude  # or pi
```

Just talk. The mirror will route to the right persona automatically based on your message. If routing fails, use `/mm-mirror` explicitly.

## Commands

| Command        | What it does                                                                     |
| -------------- | -------------------------------------------------------------------------------- |
| `/mm-mirror`   | Activates mirror mode — loads identity, persona, attachments and responds as you |
| `/mm-consult`  | Consults other LLMs via OpenRouter with mirror context                           |
| `/mm-journey`  | Status of active journeys                                                        |
| `/mm-journeys` | Quick list of all journeys                                                       |
| `/mm-memories` | List stored memories (insights, ideas, decisions)                                |
| `/mm-tasks`    | Task management by journey                                                       |
| `/mm-week`     | Weekly planning (ingest free-form text or view week)                             |
| `/mm-journal`  | Record a personal journal entry                                                  |
| `/mm-save`     | Export current conversation to Markdown                                          |
| `/mm-backup`   | Backup the memory database                                                       |
| `/mm-seed`     | Migrate YAMLs to the memory bank                                                 |
| `/mm-mute`     | Toggle conversation recording (for testing)                                      |
| `/mm-new`      | Start a new conversation                                                         |
| `/mm-help`     | List available commands                                                          |

## Architecture

### Psychic layers (Jungian)

- **Self/Soul** — Deep identity, purpose, frequency. The unchanging core.
- **Ego** — Operational identity and behavior. How the self manifests day-to-day.
- **Personas** — Specialized expressions of the ego in specific domains.
- **Shadow** (planned) — Detection of unconscious patterns.

### Travessias

A generic AI knows nothing about your life. It answers in a vacuum. The mirror is different — it carries context about what you're going through.

A **travessia** (Portuguese for "crossing" or "passage") is any ongoing arc where the mirror needs to understand where you are, where you've been, and where you're headed. It can be:

- A project (building a product, writing a book)
- A life phase (career transition, financial restructuring)
- A practice (philosophical growth, health journey)
- A creative endeavor (a podcast series, a course)

Each travessia has:

- **Identity** — what it is, why it matters, what stage it's in
- **Caminho** (path) — a living status document, updated as things evolve
- **Memories** — insights, decisions, and ideas extracted from conversations
- **Tasks** — concrete next steps
- **Attachments** — reference documents the mirror can search semantically

When you talk to the mirror about a topic that relates to a travessia, it loads that context automatically. The mirror doesn't just know who you are — it knows what you're navigating.

### Memory system (`memoria/`)

Long-term memory with semantic search. Stores conversations, extracts memories via LLM, and offers hybrid search (cosine similarity + recency + reinforcement).

- **Database:** SQLite at `~/.espelho/memoria.db`
- **Embeddings:** OpenAI text-embedding-3-small
- **Extraction:** Gemini Flash via OpenRouter
- **Search:** Hybrid scoring (4 signals)

### Memory layers

- `self` → Deep realizations about identity, purpose, values
- `ego` → Operational decisions, strategy, daily knowledge
- `shadow` → Tensions, avoided themes, recurring blind spots
- `persona` → Domain-specific operational knowledge

## Stack

- **Python 3.10+** — memory and automation, managed with **uv**
- **SQLite** — memory bank at `~/.espelho/memoria.db`
- **OpenAI** — embeddings (text-embedding-3-small)
- **OpenRouter** — multi-LLM access (Gemini, GPT, Claude, etc.)
- **Claude Code** or **pi** — primary interface

## Principles

- **First person** — the AI speaks as you, not about you
- **Active capture** — extracts and organizes without being asked
- **Depth over superficiality** — go deep
- **Frankness** — direct, no flattery, challenge when necessary
- **Integration** — everything connects across journeys and domains

## License

MIT
