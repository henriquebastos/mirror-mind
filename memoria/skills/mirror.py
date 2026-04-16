"""Espelho skill — carrega contexto de identidade e registra respostas."""

import argparse
import sys
from pathlib import Path

# Garante acesso ao pacote memoria
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from memoria import MemoriaClient


PERSONA_ICONS = {
    "escritora": "✒️",
    "divulgadora": "📣",
    "mentora": "🧭",
    "terapeuta": "🪞",
    "medica": "⚕️",
    "product-designer": "🎯",
    "professora": "🎓",
    "tecnica": "⚙️",
    "tesoureira": "💰",
    "pensadora": "💭",
    "sabe-tudo": "📖",
}


def _print_mirror_banner(persona=None):
    """Imprime banner visual de entrada no Modo Espelho."""
    mirror_line = "\033[38;5;183m⏺ Modo Espelho ativado\033[0m"
    print(mirror_line, file=sys.stderr)

    if persona:
        icon = PERSONA_ICONS.get(persona, "◇")
        persona_line = f"\033[38;5;183m  {icon} Persona: {persona}\033[0m"
        print(persona_line, file=sys.stderr)
    else:
        print("\033[38;5;183m  Ego respondendo sem persona\033[0m", file=sys.stderr)


def cmd_load(args):
    """Carrega identidade, persona, travessia e anexos. Imprime contexto para o Claude."""
    mem = MemoriaClient(env="production")

    travessia = args.travessia

    # Auto-detecção de travessia quando não especificada
    if not travessia and args.query:
        detected = mem.detect_travessia(args.query)
        if detected:
            travessia = detected[0][0]
            match_type = detected[0][2]
            score = detected[0][1]
            print(
                f"\033[38;5;183m  🧭 Travessia detectada: {travessia} "
                f"({match_type}, score: {score:.2f})\033[0m",
                file=sys.stderr,
            )

    _print_mirror_banner(args.persona)

    context = mem.load_espelho_context(
        persona=args.persona,
        travessia=travessia,
        org=args.org,
        query=args.query,
    )
    print(context)

    # Criar nova conversa para o Modo Espelho (assunto diferente do Construtor)
    from memoria.conversation_logger import switch_conversation
    switch_conversation(
        persona=args.persona,
        travessia=travessia,
    )


def cmd_log(args):
    """Registra resumo da resposta na sessão atual e atualiza o título."""
    from memoria.conversation_logger import is_muted, log_assistant_to_current, update_current_conversation
    if is_muted():
        return
    log_assistant_to_current(args.resumo)
    # Usa o resumo para gerar um título melhor
    title = _title_from_summary(args.resumo)
    update_current_conversation(title=title)
    print("Resposta registrada.", file=sys.stderr)


def _title_from_summary(summary: str) -> str:
    """Extrai título curto da primeira frase do resumo."""
    # Pega a primeira frase (até o primeiro ponto, interrogação ou exclamação)
    import re
    first_sentence = re.split(r'[.!?]', summary, maxsplit=1)[0].strip()
    if len(first_sentence) > 60:
        first_sentence = first_sentence[:60].rsplit(" ", 1)[0] + "..."
    return first_sentence


def cmd_travessias(args):
    """Lista travessias ativas para roteamento."""
    mem = MemoriaClient(env="production")
    travessias = mem.list_active_travessias()
    if not travessias:
        print("Nenhuma travessia ativa encontrada.")
        return
    for t in travessias:
        print(f"- **{t['id']}** — {t['name']}: {t['description']}")


def main():
    parser = argparse.ArgumentParser(description="Espelho skill")
    sub = parser.add_subparsers(dest="command", required=True)

    # load
    p_load = sub.add_parser("load", help="Carrega contexto de identidade")
    p_load.add_argument("--persona", help="ID da persona a carregar")
    p_load.add_argument("--travessia", help="ID da travessia a carregar")
    p_load.add_argument("--query", help="Termos de busca para anexos")
    p_load.add_argument("--org", action="store_true", help="Incluir identidade da organização")

    # log
    p_log = sub.add_parser("log", help="Registra resumo da resposta")
    p_log.add_argument("resumo", help="Resumo conciso da resposta (2-3 frases)")

    # travessias
    sub.add_parser("travessias", help="Lista travessias ativas")

    args = parser.parse_args()
    if args.command == "load":
        cmd_load(args)
    elif args.command == "log":
        cmd_log(args)
    elif args.command == "travessias":
        cmd_travessias(args)
