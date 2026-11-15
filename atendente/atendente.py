"""Orquestra a conversa nas duas arquiteturas.

- "subagentes": roteador -> subagente da fase -> verificador (padrão)
- "monolitico": um prompt único com tudo (linha de base)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import monolitico, roteador, subagentes
from . import pedido as ped
from .dados import Pizzaria, carregar, normalizar
from .llm import LLM, Mensagem


@dataclass
class Resposta:
    texto: str
    fase: str
    corrigida: bool = False


@dataclass
class Atendente:
    llm: LLM
    modo: str = "subagentes"
    pizzaria: Pizzaria = field(default_factory=carregar)
    historico: list[Mensagem] = field(default_factory=list)
    pedido: ped.Pedido = field(default_factory=ped.Pedido)

    def __post_init__(self):
        if self.modo not in ("subagentes", "monolitico"):
            raise ValueError("modo deve ser 'subagentes' ou 'monolitico'")

    def valores_do_pedido(self) -> set[float]:
        """Totais calculados em código: podem aparecer na resposta sem serem invenção."""
        if not self.pedido.pizzas and not self.pedido.bebidas:
            return set()
        p, z = self.pedido, self.pizzaria
        valores = {ped.subtotal(p, z), ped.taxa(p, z), ped.total(p, z)}
        valores |= {ped.preco_pizza(i, z) for i in p.pizzas}
        valores |= {b.preco * b.quantidade for b in p.bebidas}
        return valores

    def responder(self, texto_cliente: str) -> Resposta:
        self.historico.append({"papel": "cliente", "texto": texto_cliente})

        if self.modo == "monolitico":
            r = Resposta(monolitico.responder(self.llm, self.historico, self.pizzaria), "monolitico")
        else:
            r = self._subagentes()

        self.historico.append({"papel": "atendente", "texto": r.texto})
        return r

    def _aguardando_entrega(self, texto: str) -> bool:
        """Há pedido em andamento esperando "entrega ou retirada?" e o cliente respondeu isso."""
        if not self.pedido.pizzas or self.pedido.bairro or self.pedido.retirada:
            return False
        t = normalizar(texto)
        return bool(self.pizzaria.bairro_no_texto(texto)) or any(
            p in t for p in ("retir", "balcao", "vou buscar", "busco ai")
        )

    def _subagentes(self) -> Resposta:
        z = self.pizzaria
        if self._aguardando_entrega(self.historico[-1]["texto"]):
            # "Cocó" sozinho confundia o roteador (já foi parar no atendimento humano);
            # se é a resposta à pergunta que o próprio bot fez, nem precisa classificar
            fase = "pedido"
        else:
            fase = roteador.classificar(self.llm, self.historico)
        if fase == "pedido":
            saida, self.pedido = subagentes.pedido(self.llm, self.historico, z, self.pedido)
        elif fase == "entrega":
            saida = subagentes.entrega(self.llm, self.historico, z)
            # "Aldeota" respondendo a "é para entrega ou retirada?" completa o pedido em andamento
            if self.pedido.pizzas and not self.pedido.bairro and not self.pedido.retirada:
                saida, self.pedido = subagentes.pedido(self.llm, self.historico, z, self.pedido)
        elif fase == "cardapio":
            saida = subagentes.cardapio(self.llm, self.historico, z)
        elif fase == "humano":
            saida = subagentes.humano(z)
        else:
            saida = subagentes.info(self.llm, self.historico, z)
        return Resposta(saida.texto, saida.fase, saida.corrigida)
