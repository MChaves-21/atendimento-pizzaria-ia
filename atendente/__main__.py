"""Conversa pelo terminal.

    python -m atendente                 # subagentes
    python -m atendente --monolitico    # prompt único, para comparar
"""

import sys

from .atendente import Atendente
from .llm import do_ambiente


def main() -> None:
    modo = "monolitico" if "--monolitico" in sys.argv else "subagentes"
    bot = Atendente(do_ambiente(), modo=modo)
    print(f"{bot.pizzaria.nome} — modo {modo}. Digite 'sair' para encerrar.\n")
    while True:
        try:
            texto = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if texto.lower() in {"sair", "exit", "quit"}:
            break
        if not texto:
            continue
        r = bot.responder(texto)
        extra = f" [{r.fase}{', corrigida' if r.corrigida else ''}]" if modo == "subagentes" else ""
        print(f"Atendente{extra}: {r.texto}\n")


if __name__ == "__main__":
    main()
