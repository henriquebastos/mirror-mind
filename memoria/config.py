"""Configuração central do sistema de memória."""

import os
from pathlib import Path

# Carregar .env se existir
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# Ambiente: 'production', 'development', 'test'
MEMORIA_ENV = os.environ.get("MEMORIA_ENV", "production")

# Diretórios por ambiente
_LOCAL_DIR = Path(os.environ.get("MEMORIA_DIR", Path.home() / ".espelho")).expanduser()

# Todos os ambientes em ~/.espelho (isolados pelo nome do banco)
_ENV_DIRS = {
    "production": Path(os.environ.get("MEMORIA_PROD_DIR", _LOCAL_DIR)),
    "development": _LOCAL_DIR,
    "test": _LOCAL_DIR,
}
MEMORIA_DIR = _ENV_DIRS.get(MEMORIA_ENV, _LOCAL_DIR)

# Banco isolado por ambiente
_DB_NAMES = {
    "production": "memoria.db",
    "development": "memoria_dev.db",
    "test": "memoria_test.db",
}
DB_PATH = MEMORIA_DIR / _DB_NAMES.get(MEMORIA_ENV, f"memoria_{MEMORIA_ENV}.db")

# OpenAI embeddings
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# OpenRouter para consulta a outros LLMs (opcional)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Google AI — mantido apenas para compatibilidade de imports antigos.
# A extração de memórias passa pelo OpenRouter para evitar rate limits do free tier.
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Extração de memórias via OpenRouter (paga por uso, sem rate limit do tier free)
EXTRACTION_MODEL = "google/gemini-2.5-flash-lite"

# Famílias de modelos LLM (família → tier → model_id no OpenRouter)
LLM_FAMILIES = {
    "gemini": {
        "lite": "google/gemini-2.5-flash-lite",
        "mid": "google/gemini-2.5-flash",
        "flagship": "google/gemini-3.1-pro-preview",
    },
    "grok": {
        "lite": "x-ai/grok-3-mini",
        "mid": "x-ai/grok-3",
        "flagship": "x-ai/grok-4",
    },
    "deepseek": {
        "lite": "deepseek/deepseek-chat",
        "mid": "deepseek/deepseek-v3.2",
        "flagship": "deepseek/deepseek-r1",
    },
    "openai": {
        "lite": "openai/gpt-4.1-mini",
        "mid": "openai/gpt-4.1",
        "flagship": "openai/o3",
    },
    "claude": {
        "lite": "anthropic/claude-haiku-4.5",
        "mid": "anthropic/claude-sonnet-4.6",
        "flagship": "anthropic/claude-opus-4.6",
    },
}

# Dados pessoais do usuário
USER_NAME = os.environ.get("MIRROR_USER_NAME", "Usuário")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_raw_user_dir = os.environ.get("MIRROR_USER_DIR", "users/me")
_user_path = Path(_raw_user_dir).expanduser()
USER_DIR: Path = _user_path if _user_path.is_absolute() else _REPO_ROOT / _user_path

# Busca híbrida — pesos
SEARCH_WEIGHTS = {
    "semantic": 0.6,
    "recency": 0.2,
    "reinforcement": 0.1,
    "relevance": 0.1,
}

# Recência — half-life em dias
RECENCY_HALF_LIFE_DAYS = 90
