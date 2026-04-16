"""Parser de tasks a partir de caminhos (markdown com checkboxes)."""

import re


def parse_caminho_tasks(caminho: str, travessia: str) -> list[dict]:
    """Extrai tasks pendentes (checkboxes não marcados) de um caminho.

    Retorna lista de dicts com title, stage, status.
    """
    tasks = []
    current_stage = None

    for line in caminho.split("\n"):
        # Detectar etapa atual (### Etapa N: ...)
        stage_match = re.match(r"###\s+(?:Etapa\s+\d+:\s*)?(.+?)(?:\s*[✅🚧⏸])?$", line.strip())
        if stage_match:
            raw_stage = stage_match.group(1).strip()
            # Ignorar etapas concluídas (marcadas com ✅)
            if "✅" in line:
                current_stage = None
                continue
            current_stage = raw_stage

        # Detectar ciclo/bloco (**Ciclo N — ...**)
        cycle_match = re.match(r"\*\*(.+?)(?:\s*[✅🚧⏸])?\s*:?\*\*", line.strip())
        if cycle_match and "✅" in line:
            # Ciclo concluído, pular tasks dentro dele
            current_stage = None
            continue
        elif cycle_match and current_stage is None:
            # Ciclo ativo dentro de etapa ativa
            pass

        # Extrair checkbox não marcado
        checkbox_match = re.match(r"\s*-\s*\[\s*\]\s+(.+)", line)
        if checkbox_match and current_stage is not None:
            title = checkbox_match.group(1).strip()
            # Limpar formatação markdown do título
            title = re.sub(r"\*\*(.+?)\*\*", r"\1", title)
            # Remover marcadores como (US3.6) mas manter info útil
            title = title.rstrip(".")

            tasks.append(
                {
                    "title": title,
                    "stage": current_stage,
                    "status": "todo",
                    "travessia": travessia,
                }
            )

    return tasks


def parse_done_tasks(caminho: str, travessia: str) -> list[dict]:
    """Extrai tasks concluídas (checkboxes marcados) de um markdown.

    Retorna lista de dicts com title, stage, status.
    """
    tasks = []
    current_stage = None

    for line in caminho.split("\n"):
        # Detectar etapa (### ...)
        stage_match = re.match(r"###\s+(?:Etapa\s+\d+:\s*)?(.+?)(?:\s*[✅🚧⏸])?$", line.strip())
        if stage_match:
            current_stage = stage_match.group(1).strip()

        # Extrair checkbox marcado
        checkbox_match = re.match(r"\s*-\s*\[x\]\s+(.+)", line, re.IGNORECASE)
        if checkbox_match:
            title = checkbox_match.group(1).strip()
            title = re.sub(r"\*\*(.+?)\*\*", r"\1", title)
            title = title.rstrip(".")

            tasks.append(
                {
                    "title": title,
                    "stage": current_stage,
                    "status": "done",
                    "travessia": travessia,
                }
            )

    return tasks
