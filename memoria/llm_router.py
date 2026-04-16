"""LLM Router — envia mensagens para modelos via OpenRouter."""

import json
import urllib.request
from dataclasses import dataclass

from openai import OpenAI

from memoria.config import (
    LLM_FAMILIES,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
)


@dataclass
class LLMResponse:
    model: str
    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_cost: float | None = None
    generation_id: str | None = None


@dataclass
class CreditInfo:
    total_credits: float
    total_usage: float
    balance: float


def resolve_model(family: str, tier: str = "mid") -> str:
    """Resolve família + tier para model_id do OpenRouter.

    Se family contém '/', assume que é um model_id direto.
    """
    if "/" in family:
        return family

    family_lower = family.lower()
    if family_lower not in LLM_FAMILIES:
        available = ", ".join(sorted(LLM_FAMILIES.keys()))
        raise ValueError(f"Família '{family}' não encontrada. Disponíveis: {available}")

    tiers = LLM_FAMILIES[family_lower]
    tier_lower = tier.lower()
    if tier_lower not in tiers:
        raise ValueError(f"Tier '{tier}' não existe para '{family}'. Use: lite, mid, flagship")

    return tiers[tier_lower]


def send_to_model(
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> LLMResponse:
    """Envia mensagens para um modelo via OpenRouter. Retorna resposta + metadados de custo."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY não configurada.")

    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
    )

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    content = response.choices[0].message.content.strip()

    # Extrair metadados de custo
    prompt_tokens = None
    completion_tokens = None
    total_cost = None
    generation_id = getattr(response, "id", None)

    if response.usage:
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

    return LLMResponse(
        model=model,
        content=content,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_cost=total_cost,
        generation_id=generation_id,
    )


def fetch_generation_cost(generation_id: str, retries: int = 4) -> float | None:
    """Busca custo real de uma geração via OpenRouter /api/v1/generation.

    A API do OpenRouter leva alguns segundos para disponibilizar dados.
    Usa backoff progressivo: 1s, 2s, 3s, 4s entre tentativas.
    """
    import time

    url = f"{OPENROUTER_BASE_URL}/generation?id={generation_id}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
    )
    for attempt in range(retries + 1):
        if attempt > 0:
            time.sleep(attempt)  # backoff: 1s, 2s, 3s, 4s
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode()).get("data", {})
                cost = data.get("total_cost")
                if cost is not None:
                    return float(cost)
        except Exception:
            pass
    return None


def get_credits() -> CreditInfo:
    """Consulta saldo do OpenRouter via /api/v1/credits."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY não configurada.")

    req = urllib.request.Request(
        f"{OPENROUTER_BASE_URL}/credits",
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())["data"]

    total = data.get("total_credits", 0)
    usage = data.get("total_usage", 0)

    return CreditInfo(
        total_credits=total,
        total_usage=usage,
        balance=total - usage,
    )
