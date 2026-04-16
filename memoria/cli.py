"""CLI unificado: `memoria <subcomando>`."""

import sys


COMMANDS = {
    "seed": "memoria.seed",
    "backup": "memoria.backup",
    "session-intelligence": "memoria.session_intelligence",
    "conversation-logger": "memoria.conversation_logger",
    "consult": "memoria.skills.consult",
    "conversations": "memoria.skills.conversations",
    "journal": "memoria.skills.journal",
    "journey": "memoria.skills.journey",
    "journeys": "memoria.skills.journeys",
    "memories": "memoria.skills.memories",
    "mirror": "memoria.skills.mirror",
    "recall": "memoria.skills.recall",
    "save": "memoria.skills.save",
    "tasks": "memoria.skills.tasks",
    "week": "memoria.skills.week",
}

USAGE = """\
uso: memoria <comando> [args...]

comandos:
  seed                   Migra identidade dos YAMLs para o banco
  backup                 Backup do banco de memória
  session-intelligence   Análise de sessões
  conversation-logger    Hooks de conversa (mute/unmute/status/switch/extract)

  consult                Consulta outros LLMs via OpenRouter
  conversations          Lista conversas recentes
  journal                Registra entrada de diário
  journey                Status detalhado de uma travessia
  journeys               Lista travessias
  memories               Lista e busca memórias
  mirror                 Carrega contexto do Espelho
  recall                 Carrega conversa anterior
  save                   Exporta conversa para Markdown
  tasks                  Gestão de tasks por travessia
  week                   Planejamento semanal
"""


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(USAGE.strip())
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd not in COMMANDS:
        print(f"comando desconhecido: {cmd}")
        print(USAGE.strip())
        sys.exit(1)

    # Remove o subcomando do argv para que o main() delegado veja só seus args
    sys.argv = [f"memoria {cmd}"] + sys.argv[2:]

    module = __import__(COMMANDS[cmd], fromlist=["main"])
    module.main()
