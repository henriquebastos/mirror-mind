"""Consult skill — consulta outros LLMs via OpenRouter."""

import sys
from pathlib import Path

# Garante acesso ao pacote memoria
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from memoria import MemoriaClient
from memoria.llm_router import fetch_generation_cost, get_credits, resolve_model, send_to_model

TIERS = ("lite", "mid", "flagship")

SYSTEM_PREAMBLE = """Você é o Espelho (Mirror) do usuário descrito no contexto abaixo. Responda em primeira pessoa, como ele.
Respeite o vocabulário, tom e filosofia descritos no contexto de identidade.

"""


def cmd_ask(model_id: str, prompt: str, persona=None, travessia=None, org=False, query=None):
    """Envia prompt + contexto de identidade para um modelo."""
    mem = MemoriaClient(env="production")
    context = mem.load_espelho_context(
        persona=persona,
        travessia=travessia,
        org=org,
        query=query,
    )

    system_prompt = SYSTEM_PREAMBLE + context
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    print(f"Consultando {model_id}...", flush=True)
    resp = send_to_model(model_id, messages)

    # Resposta (imprime imediatamente)
    print(f"--- resposta via {resp.model} ---")
    print(resp.content)
    print(f"--- fim ---")

    # Tokens
    cost_parts = []
    if resp.prompt_tokens:
        cost_parts.append(f"prompt: {resp.prompt_tokens}")
    if resp.completion_tokens:
        cost_parts.append(f"completion: {resp.completion_tokens}")
    if cost_parts:
        print(f"[{', '.join(cost_parts)}]")

    # Custo real (busca assíncrona com backoff — após a resposta já estar impressa)
    if resp.generation_id:
        total_cost = fetch_generation_cost(resp.generation_id)
        if total_cost is not None:
            cost_brl = total_cost * USD_TO_BRL
            if total_cost < 0.01:
                print(f"Custo da chamada: ${total_cost:.6f} (R$ {cost_brl:.4f})")
            else:
                print(f"Custo da chamada: ${total_cost:.4f} (R$ {cost_brl:.2f})")

    # Saldo restante
    cmd_credits()



USD_TO_BRL = 5.7  # taxa aproximada, atualizar conforme necessário


def cmd_credits():
    """Mostra saldo do OpenRouter com barra de progresso."""
    info = get_credits()

    balance_brl = info.balance * USD_TO_BRL
    total_brl = info.total_credits * USD_TO_BRL

    # Barra de progresso (restante / total)
    bar_width = 20
    if info.total_credits > 0:
        fill = int(bar_width * info.balance / info.total_credits)
    else:
        fill = 0
    bar = "▓" * fill + "░" * (bar_width - fill)

    print(f"Saldo:    openrouter: {bar} R$ {balance_brl:.2f}")


def parse_args():
    """Parse manual para suportar: consult <familia> [tier] "pergunta" [--flags]

    Exemplos:
      consult credits
      consult gemini lite "pergunta aqui"
      consult gemini "pergunta"                  → ask com tier mid
      consult google/gemini-2.5-pro "pergunta"   → model_id direto
    """
    args = sys.argv[1:]
    if not args:
        print("Uso: consult <familia> [tier] [pergunta] [--persona P] [--travessia T] [--org]")
        print("     consult credits")
        sys.exit(1)

    # Credits
    if args[0] == "credits":
        return {"command": "credits"}

    # Extrair flags opcionais
    persona = None
    travessia = None
    org = False
    query = None
    positional = []

    i = 0
    while i < len(args):
        if args[i] == "--persona" and i + 1 < len(args):
            persona = args[i + 1]
            i += 2
        elif args[i] == "--travessia" and i + 1 < len(args):
            travessia = args[i + 1]
            i += 2
        elif args[i] == "--query" and i + 1 < len(args):
            query = args[i + 1]
            i += 2
        elif args[i] == "--org":
            org = True
            i += 1
        else:
            positional.append(args[i])
            i += 1

    if not positional:
        print("Erro: família do modelo é obrigatória.")
        sys.exit(1)

    family = positional[0]
    tier = "lite"
    prompt = None

    if len(positional) == 1:
        print("Erro: pergunta é obrigatória.")
        sys.exit(1)
    elif len(positional) == 2:
        if positional[1] in TIERS:
            print("Erro: pergunta é obrigatória.")
            sys.exit(1)
        else:
            # consult gemini "pergunta" → ask com mid
            prompt = positional[1]
    elif len(positional) >= 3:
        if positional[1] in TIERS:
            # consult gemini lite "pergunta"
            tier = positional[1]
            prompt = " ".join(positional[2:])
        else:
            # consult gemini "pergunta longa com espaços"
            prompt = " ".join(positional[1:])

    model_id = resolve_model(family, tier)

    return {
        "command": "ask",
        "model_id": model_id,
        "prompt": prompt,
        "persona": persona,
        "travessia": travessia,
        "org": org,
        "query": query,
    }


def main():
    parsed = parse_args()

    if parsed["command"] == "credits":
        cmd_credits()
    elif parsed["command"] == "ask":
        cmd_ask(
            parsed["model_id"],
            parsed["prompt"],
            persona=parsed.get("persona"),
            travessia=parsed.get("travessia"),
            org=parsed.get("org", False),
            query=parsed.get("query"),
        )
