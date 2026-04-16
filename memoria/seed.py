"""Migração de identidade: YAMLs pessoais → banco de dados.

Uso:
    python -m memoria.seed                    # migra para dev (padrão)
    python -m memoria.seed --env production   # migra para produção
    python -m memoria.seed --env test         # migra para test
"""

import argparse
import sys
from pathlib import Path

import yaml

from memoria.client import MemoriaClient
from memoria.config import USER_DIR

# Mapeamento: (layer, key) → arquivo YAML (relativo a USER_DIR) + campo que contém o conteúdo
IDENTITY_MAP = {
    ("self", "soul"): ("self/soul.yaml", "soul"),
    ("ego", "identity"): ("ego/identity.yaml", "identity"),
    ("ego", "behavior"): ("ego/behavior.yaml", "behavior"),
    ("user", "identity"): ("user/identity.yaml", "user"),
    ("organization", "identity"): ("organization/identity.yaml", "identity"),
    ("organization", "principles"): ("organization/principles.yaml", "principles"),
}


def find_user_dir() -> Path:
    """Retorna o diretório de dados pessoais do usuário (via MIRROR_USER_DIR)."""
    if not USER_DIR.exists():
        raise FileNotFoundError(f"Diretório do usuário não encontrado: {USER_DIR}")
    return USER_DIR


def load_yaml_content(user_dir: Path, yaml_path: str, field: str) -> tuple[str, str]:
    """Carrega conteúdo de um campo de um YAML. Retorna (content, version)."""
    full_path = user_dir / yaml_path
    if not full_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {full_path}")

    with open(full_path) as f:
        data = yaml.safe_load(f)

    content = data.get(field, "")
    version = data.get("version", "1.0.0")
    return content, version


def load_persona_content(persona_file: Path) -> tuple[str, str, str]:
    """Carrega conteúdo pessoal de uma persona. Retorna (persona_id, content, version)."""
    with open(persona_file) as f:
        data = yaml.safe_load(f)

    persona_id = data.get("persona_id", persona_file.stem)
    version = data.get("version", "1.0.0")

    # Combina system_prompt + briefing como conteúdo pessoal da persona
    parts = []
    if data.get("system_prompt"):
        parts.append(data["system_prompt"])
    if data.get("briefing"):
        parts.append(f"\n\n# Briefing\n\n{data['briefing']}")

    content = "".join(parts)
    return persona_id, content, version


def load_travessia_content(travessia_file: Path) -> tuple[str, str, str]:
    """Carrega conteúdo de uma travessia. Retorna (travessia_id, content, version)."""
    with open(travessia_file) as f:
        data = yaml.safe_load(f)

    travessia_id = data.get("travessia_id", data.get("project_id", travessia_file.stem))
    version = data.get("version", "1.0.0")

    parts = []
    if data.get("name"):
        parts.append(f"# {data['name']}")
    if data.get("status"):
        parts.append(f"**Status:** {data['status']}")
    if data.get("description"):
        parts.append(f"\n## Descrição\n\n{data['description']}")
    if data.get("briefing"):
        parts.append(f"\n## Briefing\n\n{data['briefing']}")
    if data.get("context"):
        parts.append(f"\n## Contexto\n\n{data['context']}")

    content = "\n".join(parts)
    return travessia_id, content, version


def seed(env: str = "development", user_dir: Path | None = None) -> dict:
    """Executa a migração de identidade para o banco."""
    if user_dir is None:
        user_dir = find_user_dir()

    mem = MemoriaClient(env=env)
    results = {"created": 0, "updated": 0, "errors": []}

    # 1. Migrar identidade core (self, ego, user, organization)
    for (layer, key), (yaml_path, field) in IDENTITY_MAP.items():
        try:
            content, version = load_yaml_content(user_dir, yaml_path, field)
            if not content:
                results["errors"].append(f"{layer}/{key}: conteúdo vazio")
                continue

            existing = mem.store.get_identity(layer, key)
            mem.set_identity(layer, key, content, version)

            if existing:
                results["updated"] += 1
                print(f"  ↻ {layer}/{key} (atualizado)")
            else:
                results["created"] += 1
                print(f"  ✓ {layer}/{key}")
        except Exception as e:
            results["errors"].append(f"{layer}/{key}: {e}")
            print(f"  ✗ {layer}/{key}: {e}")

    # 2. Migrar personas
    personas_dir = user_dir / "personas"
    if personas_dir.exists():
        for persona_file in sorted(personas_dir.glob("*.yaml")):
            if persona_file.name.startswith("_"):
                continue  # Arquivos como _template.yaml são ignorados
            try:
                persona_id, content, version = load_persona_content(persona_file)
                if not content:
                    continue

                existing = mem.store.get_identity("persona", persona_id)
                mem.set_identity("persona", persona_id, content, version)

                if existing:
                    results["updated"] += 1
                    print(f"  ↻ persona/{persona_id} (atualizado)")
                else:
                    results["created"] += 1
                    print(f"  ✓ persona/{persona_id}")
            except Exception as e:
                results["errors"].append(f"persona/{persona_file.stem}: {e}")
                print(f"  ✗ persona/{persona_file.stem}: {e}")

    # 3. Migrar travessias
    travessias_dir = user_dir / "travessias"
    if travessias_dir.exists():
        for travessia_file in sorted(travessias_dir.glob("*.yaml")):
            if travessia_file.name.startswith("_"):
                continue  # Arquivos como _template.yaml são ignorados
            try:
                travessia_id, content, version = load_travessia_content(travessia_file)
                if not content:
                    continue

                existing = mem.store.get_identity("travessia", travessia_id)
                mem.set_identity("travessia", travessia_id, content, version)

                if existing:
                    results["updated"] += 1
                    print(f"  ↻ travessia/{travessia_id} (atualizado)")
                else:
                    results["created"] += 1
                    print(f"  ✓ travessia/{travessia_id}")
            except Exception as e:
                results["errors"].append(f"travessia/{travessia_file.stem}: {e}")
                print(f"  ✗ travessia/{travessia_file.stem}: {e}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Migra identidade dos YAMLs para o banco")
    parser.add_argument(
        "--env", default="development", choices=["development", "test", "production"]
    )
    args = parser.parse_args()

    print(f"Migrando identidade para [{args.env}]...\n")
    results = seed(env=args.env)

    print(f"\nResultado: {results['created']} criados, {results['updated']} atualizados")
    if results["errors"]:
        print(f"Erros: {len(results['errors'])}")
        for err in results["errors"]:
            print(f"  - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
