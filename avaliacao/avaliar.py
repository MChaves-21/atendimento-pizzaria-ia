"""Avaliação: prompt único x subagentes, nas mesmas perguntas.

    python -m avaliacao.avaliar                    # as duas versões, todos os casos
    python -m avaliacao.avaliar --modos subagentes --pausa 4

Para cada caso a conversa é reproduzida do zero e só a ÚLTIMA resposta é
avaliada, sem IA julgando IA:
- inventou: citou preço que não existe, afirmou ter sabor que não temos,
  ou bateu numa frase proibida do caso;
- correta: não inventou e trouxe o que o caso exige (valor certo, negativa...).

Saída em avaliacao/resultados/: respostas.csv, resumo.json, relatorio.md e grafico.png.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable

from atendente.atendente import Atendente
from atendente.dados import Pizzaria, carregar, normalizar
from atendente.llm import LLM, do_ambiente
from atendente.verificador import _PRECO, _valor, verificar

PASTA = Path(__file__).resolve().parent
CASOS = PASTA / "casos.jsonl"
RESULTADOS = PASTA / "resultados"


def carregar_casos(caminho: Path = CASOS) -> list[dict]:
    with open(caminho, encoding="utf-8") as f:
        return [json.loads(linha) for linha in f if linha.strip()]


@dataclass
class Nota:
    id: str
    categoria: str
    modo: str
    resposta: str
    inventou: bool
    correta: bool
    motivos: str


def avaliar_resposta(caso: dict, resposta: str, pizzaria: Pizzaria,
                     valores_extras: set[float] | None = None) -> tuple[bool, bool, list[str]]:
    """Devolve (inventou, correta, motivos)."""
    permitidos = set(caso.get("valores_corretos", [])) | (valores_extras or set())
    motivos: list[str] = []

    v = verificar(resposta, pizzaria, permitidos)
    motivos += v.motivos()

    texto = normalizar(resposta)
    for padrao in caso.get("nao_deve_conter", []):
        if re.search(padrao, texto):
            motivos.append(f"frase proibida: {padrao}")
    inventou = bool(motivos)

    faltando = []
    valores = [_valor(x) for x in _PRECO.findall(resposta)]
    for esperado in caso.get("valores_esperados", []):
        if not any(abs(esperado - x) < 0.005 for x in valores):
            faltando.append(f"faltou o valor R$ {esperado:.2f}")
    alternativas = caso.get("deve_conter_algum")
    if alternativas and not any(normalizar(a) in texto for a in alternativas):
        faltando.append("faltou o conteúdo esperado")

    correta = not inventou and not faltando
    return inventou, correta, motivos + faltando


def rodar_caso(caso: dict, modo: str, llm: LLM, pizzaria: Pizzaria) -> Nota:
    bot = Atendente(llm, modo=modo, pizzaria=pizzaria)
    resposta = ""
    for mensagem in caso["mensagens"]:
        resposta = bot.responder(mensagem).texto
    extras = bot.valores_do_pedido() if modo == "subagentes" else set()
    inventou, correta, motivos = avaliar_resposta(caso, resposta, pizzaria, extras)
    return Nota(caso["id"], caso["categoria"], modo, resposta, inventou, correta, "; ".join(motivos))


def resumir(notas: list[Nota]) -> dict:
    resumo: dict = {}
    for modo in sorted({n.modo for n in notas}):
        do_modo = [n for n in notas if n.modo == modo]
        cats = sorted({n.categoria for n in do_modo})
        resumo[modo] = {
            "casos": len(do_modo),
            "inventadas_pct": round(100 * sum(n.inventou for n in do_modo) / len(do_modo), 1),
            "corretas_pct": round(100 * sum(n.correta for n in do_modo) / len(do_modo), 1),
            "por_categoria": {
                c: {
                    "inventadas_pct": round(100 * sum(n.inventou for n in do_modo if n.categoria == c)
                                            / sum(1 for n in do_modo if n.categoria == c), 1),
                    "corretas_pct": round(100 * sum(n.correta for n in do_modo if n.categoria == c)
                                          / sum(1 for n in do_modo if n.categoria == c), 1),
                }
                for c in cats
            },
        }
    return resumo


def salvar(notas: list[Nota], resumo: dict, info: dict, pasta: Path = RESULTADOS) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    with open(pasta / "respostas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(notas[0]).keys()))
        w.writeheader()
        w.writerows(asdict(n) for n in notas)
    (pasta / "resumo.json").write_text(
        json.dumps({"execucao": info, "resumo": resumo}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    linhas = [
        "# Resultado da avaliação",
        "",
        f"Modelo: `{info['modelo']}` · {info['casos']} casos · {info['data']}",
        "",
        "| Versão | Respostas inventadas | Respostas corretas |",
        "|---|---|---|",
    ]
    nomes = {"monolitico": "Prompt único", "subagentes": "Subagentes + código + verificador"}
    for modo, r in resumo.items():
        linhas.append(f"| {nomes.get(modo, modo)} | {r['inventadas_pct']}% | {r['corretas_pct']}% |")
    linhas += ["", "## Por categoria (inventadas / corretas)", ""]
    cats = sorted({c for r in resumo.values() for c in r["por_categoria"]})
    linhas.append("| Categoria | " + " | ".join(nomes.get(m, m) for m in resumo) + " |")
    linhas.append("|---|" + "---|" * len(resumo))
    for c in cats:
        cel = [
            f"{r['por_categoria'][c]['inventadas_pct']}% / {r['por_categoria'][c]['corretas_pct']}%"
            for r in resumo.values()
        ]
        linhas.append(f"| {c} | " + " | ".join(cel) + " |")
    falhas = [n for n in notas if not n.correta]
    if falhas:
        linhas += ["", "## Respostas que falharam", ""]
        for n in falhas:
            linhas.append(f"- **{n.id}** ({nomes.get(n.modo, n.modo)}): {n.motivos}")
    (pasta / "relatorio.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")

    try:
        _grafico(resumo, pasta / "grafico.png", info)
    except ImportError:
        pass  # matplotlib é opcional


def _grafico(resumo: dict, destino: Path, info: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    nomes = {"monolitico": "Prompt único", "subagentes": "Subagentes"}
    modos = list(resumo)
    inventadas = [resumo[m]["inventadas_pct"] for m in modos]
    fig, ax = plt.subplots(figsize=(6, 3.2), dpi=150)
    barras = ax.barh([nomes.get(m, m) for m in modos], inventadas, color=["#c2410c", "#15803d"][: len(modos)])
    for b, v in zip(barras, inventadas):
        ax.text(b.get_width() + 0.8, b.get_y() + b.get_height() / 2, f"{v}%", va="center", fontsize=11)
    ax.set_xlim(0, max(inventadas + [10]) * 1.25)
    ax.set_xlabel("Respostas com informação inventada (%)")
    ax.set_title(f"{info['casos']} casos · {info['modelo']}", fontsize=10, loc="left")
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    fig.tight_layout()
    fig.savefig(destino)
    plt.close(fig)


def rodar(fabrica_llm: Callable[[], LLM], modos: list[str], casos: list[dict],
          pausa: float = 0.0, progresso: bool = False) -> list[Nota]:
    pizzaria = carregar()
    notas = []
    for modo in modos:
        for i, caso in enumerate(casos, 1):
            notas.append(rodar_caso(caso, modo, fabrica_llm(), pizzaria))
            if progresso:
                n = notas[-1]
                status = "inventou" if n.inventou else ("ok" if n.correta else "incompleta")
                print(f"[{modo}] {i}/{len(casos)} {caso['id']}: {status}")
            if pausa:
                time.sleep(pausa)
    return notas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modos", nargs="+", default=["monolitico", "subagentes"])
    ap.add_argument("--pausa", type=float, default=2.0, help="segundos entre casos (limite do plano gratuito)")
    ap.add_argument("--casos", type=Path, default=CASOS)
    args = ap.parse_args()

    import os
    from datetime import date

    casos = carregar_casos(args.casos)
    modelo = getattr(do_ambiente(), "modelo", "?")
    notas = rodar(do_ambiente, args.modos, casos, args.pausa, progresso=True)
    resumo = resumir(notas)
    info = {
        "modelo": f"{os.getenv('LLM_PROVEDOR', 'gemini')}/{modelo}",
        "casos": len(casos),
        "data": date.today().isoformat(),
    }
    salvar(notas, resumo, info)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    print(f"\nRelatório em {RESULTADOS / 'relatorio.md'}")


if __name__ == "__main__":
    main()
