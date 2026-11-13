"""Verificador de respostas inventadas.

Confere, sem IA, se a resposta cita algum preço que não existe no cardápio
nem no pedido calculado. Roda em produção (a versão com subagentes descarta
a resposta e tenta de novo) e na avaliação (para contar as invenções).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .dados import Pizzaria, normalizar

# "R$ 46,00", "R$46", "46,00 reais", "R$ 1.234,50"
_PRECO = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)", re.IGNORECASE)

# Sabores comuns que a Bella Massa NÃO tem. Se a resposta disser que tem, é invenção.
SABORES_INEXISTENTES = [
    "pepperoni", "atum", "bacon", "napolitana", "baiana", "lombo", "camarao", "rucula",
    "palmito", "brocolis", "marguerita de bufala", "strogonoff", "banana", "prestigio",
]

_AFIRMACAO = r"(temos|tem|trabalhamos com|oferecemos|serve|servimos|sai por|custa)"


def _valor(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", "."))


@dataclass
class Resultado:
    precos_inventados: list[float] = field(default_factory=list)
    sabores_inventados: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.precos_inventados and not self.sabores_inventados

    def motivos(self) -> list[str]:
        m = [f"preço inexistente R$ {v:.2f}" for v in self.precos_inventados]
        m += [f"afirma ter o sabor {s}" for s in self.sabores_inventados]
        return m


def verificar(resposta: str, pizzaria: Pizzaria, valores_permitidos: set[float] | None = None) -> Resultado:
    """`valores_permitidos`: totais calculados em código para a conversa atual."""
    permitidos = pizzaria.precos_conhecidos() | (valores_permitidos or set())
    res = Resultado()

    for bruto in _PRECO.findall(resposta):
        v = _valor(bruto)
        if not any(abs(v - p) < 0.005 for p in permitidos):
            res.precos_inventados.append(v)

    texto = normalizar(resposta)
    for sabor in SABORES_INEXISTENTES:
        # "temos pepperoni" conta; "não temos pepperoni" não conta
        padrao = rf"(?<!nao ){_AFIRMACAO}[^.!?\n]{{0,40}}\b{sabor}\b"
        for m in re.finditer(padrao, texto):
            inicio = texto[max(0, m.start() - 12):m.start()]
            if "nao" not in inicio and "infelizmente" not in inicio:
                res.sabores_inventados.append(sabor)
                break
    return res
