"""Permite executar `python -m memoria seed` e outros comandos."""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        sys.argv = [sys.argv[0]] + sys.argv[2:]  # remove 'seed' para argparse
        from memoria.seed import main

        main()
    else:
        print("Uso: python -m memoria seed [--env development|test|production]")
        sys.exit(1)
