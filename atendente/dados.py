"""Leitura dos dados da pizzaria e consultas que NÃO passam pela IA.

Preços, taxas e horários saem sempre daqui. A IA nunca faz conta nem
"lembra" um preço: ela só interpreta o que o cliente quis dizer.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ARQUIVO_PADRAO = Path(__file__).resolve().parent.parent / "dados" / "pizzaria.json"


def normalizar(texto: str) -> str:
    """Minúsculas e sem acento, para comparar 'Fátima' com 'fatima'."""
    sem_acento = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


def moeda(valor: float) -> str:
    """32.5 -> 'R$ 32,50'"""
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@dataclass(frozen=True)
class Pizza:
    id: str
    nome: str
    ingredientes: str
    veggie: bool
    precos: dict[str, float]


class Pizzaria:
    def __init__(self, bruto: dict):
        self.bruto = bruto
        self.nome: str = bruto["nome"]
        self.horario: dict = bruto["horario"]
        self.pizzas = [Pizza(**p) for p in bruto["pizzas"]]
        self.tamanhos: dict[str, str] = bruto["tamanhos"]
        self.bebidas: list[dict] = bruto["bebidas"]
        self.regras: dict = bruto["regras_pedido"]
        self.entrega: dict = bruto["entrega"]

    # ── Busca por nome ──────────────────────────────────────────────────────
    def pizza(self, nome_ou_id: str) -> Pizza | None:
        alvo = normalizar(nome_ou_id)
        for p in self.pizzas:
            if alvo in (normalizar(p.id), normalizar(p.nome)):
                return p
        # aceita "frango" para "Frango com Catupiry", desde que seja único
        candidatos = [p for p in self.pizzas if alvo and alvo in normalizar(p.nome)]
        return candidatos[0] if len(candidatos) == 1 else None

    def bebida(self, nome_ou_id: str) -> dict | None:
        alvo = normalizar(nome_ou_id)
        for b in self.bebidas:
            if alvo in (normalizar(b["id"]), normalizar(b["nome"])):
                return b
        candidatos = [b for b in self.bebidas if alvo and alvo in normalizar(b["nome"])]
        if len(candidatos) == 1:
            return candidatos[0]
        return self._bebida_por_apelido(alvo)

    def _bebida_por_apelido(self, alvo: str) -> dict | None:
        """'coca', 'guaraná 2l', 'suco de caju', 'aguinha' -> item do cardápio."""
        refri = ("coca", "guarana", "fanta", "sprite", "refri", "refrigerante", "pepsi")
        if any(r in alvo for r in refri):
            dois_litros = any(x in alvo for x in ("2l", "2 l", "2 litros", "dois litros", "litrao"))
            return self.bebida("refri-2l" if dois_litros else "refri-lata")
        if "suco" in alvo:
            return self.bebida("suco")
        if "agua" in alvo:
            return self.bebida("agua")
        return None

    def taxa_entrega(self, bairro: str) -> float | None:
        """Taxa do bairro, ou None quando a pizzaria não entrega lá."""
        alvo = normalizar(bairro)
        for nome, taxa in self.entrega["bairros"].items():
            if normalizar(nome) == alvo:
                return taxa
        return None

    def bairro_oficial(self, bairro: str) -> str | None:
        alvo = normalizar(bairro)
        for nome in self.entrega["bairros"]:
            if normalizar(nome) == alvo:
                return nome
        return None

    # ── Valores que podem aparecer numa resposta ────────────────────────────
    def precos_conhecidos(self) -> set[float]:
        valores = {v for p in self.pizzas for v in p.precos.values()}
        valores |= {b["preco"] for b in self.bebidas}
        valores |= set(self.entrega["bairros"].values())
        valores.add(self.regras["borda_recheada"]["preco"])
        valores.add(self.regras["pedido_minimo"])
        return valores

    # ── Textos curtos para os prompts ───────────────────────────────────────
    def texto_cardapio(self) -> str:
        linhas = ["PIZZAS (preços P / M / G):"]
        for p in self.pizzas:
            pr = p.precos
            veg = " [vegetariana]" if p.veggie else ""
            linhas.append(
                f"- {p.nome}{veg}: {p.ingredientes}. "
                f"{moeda(pr['P'])} / {moeda(pr['M'])} / {moeda(pr['G'])}"
            )
        linhas.append("TAMANHOS: " + "; ".join(f"{k} = {v}" for k, v in self.tamanhos.items()))
        linhas.append("BEBIDAS:")
        linhas += [f"- {b['nome']}: {moeda(b['preco'])}" for b in self.bebidas]
        borda = self.regras["borda_recheada"]
        linhas.append(f"BORDA: {borda['descricao']}: + {moeda(borda['preco'])}")
        linhas.append(f"MEIO A MEIO: {self.regras['meio_a_meio']}")
        return "\n".join(linhas)

    def texto_horario(self) -> str:
        h = self.horario
        return f"Abrimos {h['dias']}, das {h['abre']} às {h['fecha']}. Fechado na {h['fechado']}."

    def texto_entrega(self) -> str:
        bairros = "; ".join(f"{b}: {moeda(t)}" for b, t in self.entrega["bairros"].items())
        return (
            f"Entregamos só nestes bairros (taxa): {bairros}. "
            f"Tempo médio: {self.entrega['tempo_medio_min']} minutos. "
            f"Retirada no balcão: {self.entrega['endereco_loja']}."
        )


@lru_cache(maxsize=4)
def carregar(caminho: str | None = None) -> Pizzaria:
    with open(caminho or ARQUIVO_PADRAO, encoding="utf-8") as f:
        return Pizzaria(json.load(f))
