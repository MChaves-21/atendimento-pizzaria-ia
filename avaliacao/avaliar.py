"""Avaliação: prompt único x subagentes, nas mesmas perguntas.

    python -m avaliacao.avaliar                    # as duas versões, todos os casos
    python -m avaliacao.avaliar --modos subagentes --pausa 4

Para cada caso a conversa é reproduzida do zero e só a ÚLTIMA resposta é
avaliada, sem IA julgando IA:
- inventou: citou preço que não existe, afirmou ter sabor que não temos,
  ou bateu numa frase proibida do caso;
- correta: não inventou e trouxe o que o caso exige (valor certo, negativa...).

Saída em avaliacao/resultados/<modelo>/: respostas.csv, resumo.json, relatorio.md e grafico.png.
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
from atendente.verificador import _PRECO, _valor, valores_citados, verificar

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
    permitidos |= valores_citados(caso["mensagens"])  # repetir o valor que o cliente disse não é inventar
    motivos: list[str] = []

    v = verificar(resposta, pizzaria, permitidos)
    motivos += v.motivos()

    # sem a marcação de negrito/itálico: "**M** ou **G**" tem que valer como "M ou G"
    texto = normalizar(re.sub(r"[*_`]+", "", resposta))
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
        f"Modelo: `{info['modelo']}` · {info['casos']} casos · {info['data']}"
        + ("" if info.get("completo", True) else f" · **parcial: {info['casos']} de {info.get('total_casos')} casos**"),
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


class LimiteDaAPI(Exception):
    """A API recusou por limite (429) mesmo depois das retentativas."""


def _e_limite(erro: Exception) -> bool:
    resp = getattr(erro, "response", None)
    return getattr(resp, "status_code", None) == 429


def carregar_parcial(arquivo: Path) -> list[Nota]:
    if not arquivo.exists():
        return []
    with open(arquivo, encoding="utf-8") as f:
        return [Nota(**json.loads(l)) for l in f if l.strip()]


def rodar(fabrica_llm: Callable[[], LLM], modos: list[str], casos: list[dict],
          pausa: float = 0.0, progresso: bool = False, parcial: Path | None = None) -> list[Nota]:
    """Roda caso a caso, alternando as versões (assim um resultado parcial já é comparável).

    Com `parcial`, cada nota é gravada assim que sai e as já gravadas são puladas:
    se o limite diário da API acabar, a próxima execução continua de onde parou.
    """
    pizzaria = carregar()
    notas = carregar_parcial(parcial) if parcial else []
    feitos = {(n.modo, n.id) for n in notas}
    for i, caso in enumerate(casos, 1):
        for modo in modos:
            if (modo, caso["id"]) in feitos:
                continue
            try:
                nota = rodar_caso(caso, modo, fabrica_llm(), pizzaria)
            except Exception as erro:
                if _e_limite(erro):
                    raise LimiteDaAPI(f"limite da API atingido em {caso['id']} ({modo})") from erro
                raise
            notas.append(nota)
            if parcial:
                parcial.parent.mkdir(parents=True, exist_ok=True)
                with open(parcial, "a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(nota), ensure_ascii=False) + "\n")
            if progresso:
                status = "inventou" if nota.inventou else ("ok" if nota.correta else "incompleta")
                print(f"[{modo}] {i}/{len(casos)} {caso['id']}: {status}", flush=True)
            if pausa:
                time.sleep(pausa)
    return notas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modos", nargs="+", default=["monolitico", "subagentes"])
    ap.add_argument("--pausa", type=float, default=2.0, help="segundos entre casos (limite do plano gratuito)")
    ap.add_argument("--casos", type=Path, default=CASOS)
    ap.add_argument("--recomecar", action="store_true", help="apaga o progresso salvo e roda tudo de novo")
    args = ap.parse_args()

    import os
    from datetime import date

    casos = carregar_casos(args.casos)
    modelo = f"{os.getenv('LLM_PROVEDOR', 'gemini')}/{getattr(do_ambiente(), 'modelo', '?')}"
    pasta = RESULTADOS / re.sub(r"[^a-z0-9.-]+", "_", modelo.lower())  # uma pasta por modelo
    pasta.mkdir(parents=True, exist_ok=True)
    parcial = pasta / "parcial.jsonl"
    if args.recomecar:
        parcial.unlink(missing_ok=True)

    completo = True
    try:
        notas = rodar(do_ambiente, args.modos, casos, args.pausa, progresso=True, parcial=parcial)
    except LimiteDaAPI as e:
        completo = False
        print(f"\n{e}. O progresso foi salvo: rode de novo depois (ex.: amanhã) para continuar.")
        notas = carregar_parcial(parcial)

    # Só entram no resumo os casos que as duas versões já responderam (comparação justa)
    por_caso: dict[str, set] = {}
    for n in notas:
        por_caso.setdefault(n.id, set()).add(n.modo)
    comparaveis = [n for n in notas if por_caso[n.id] >= set(args.modos)]
    if not comparaveis:
        print("Nenhum caso respondido pelas duas versões ainda.")
        return

    n_casos = len({n.id for n in comparaveis})
    info = {
        "modelo": modelo,
        "casos": n_casos,
        "total_casos": len(casos),
        "completo": completo and n_casos == len(casos),
        "data": date.today().isoformat(),
    }
    resumo = resumir(comparaveis)
    salvar(comparaveis, resumo, info, pasta)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    print(f"\n{n_casos} de {len(casos)} casos. Relatório em {pasta / 'relatorio.md'}")


if __name__ == "__main__":
    main()
