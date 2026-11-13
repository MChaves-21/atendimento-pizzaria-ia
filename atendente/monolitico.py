"""Versão de comparação: um prompt único com tudo.

É o jeito mais comum de começar um chatbot: todos os dados e todas as regras
num só texto, e o modelo responde e faz as contas sozinho. Serve de linha de
base para medir o ganho dos subagentes.
"""

from __future__ import annotations

import json

from .dados import Pizzaria
from .llm import LLM, Mensagem


def prompt(pizzaria: Pizzaria) -> str:
    return f"""Você é o atendente virtual da {pizzaria.nome}, em {pizzaria.bruto['cidade']}.
Atenda o cliente do começo ao fim: cumprimente, tire dúvidas sobre o cardápio, monte o pedido,
calcule o total com a taxa de entrega e confirme. Seja simpático e objetivo.

Regras:
- Use somente os dados abaixo. Não invente sabores, preços nem bairros.
- Meio a meio só em M ou G; cobra o sabor mais caro.
- Some a taxa de entrega do bairro ao total. Se o bairro não estiver na lista, não entregamos.
- Reclamações e assuntos fora da pizzaria: diga que vai chamar uma pessoa da equipe.

DADOS DA PIZZARIA (JSON):
{json.dumps(pizzaria.bruto, ensure_ascii=False, indent=2)}"""


def responder(llm: LLM, historico: list[Mensagem], pizzaria: Pizzaria) -> str:
    return llm.gerar(prompt(pizzaria), historico)
