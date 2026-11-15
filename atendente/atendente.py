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

    def _esperando_entrega(self) -> bool:
        """Há pedido em andamento e o bot perguntou "entrega ou retirada?"."""
        return bool(self.pedido.pizzas) and not self.pedido.bairro and not self.pedido.retirada

    def _fechar_entrega(self, bairro: str | None, retirada: bool) -> Resposta:
        """Completa o pedido em código: a IA não reextrai os itens (o modelo menor inventava bebida)."""
        self.pedido.bairro, self.pedido.retirada = bairro, retirada
        return Resposta(subagentes.texto_pedido(self.pedido, self.pizzaria), "pedido")

    def _subagentes(self) -> Resposta:
        z = self.pizzaria
        texto = self.historico[-1]["texto"]
        t = normalizar(texto)

        cita_item = roteador.por_palavras(texto) == "pedido" or any(
            normalizar(p.nome) in t for p in z.pizzas
        ) or z._bebida_por_apelido(t) is not None
        if self._esperando_entrega() and not cita_item:  # "mais uma coca, é na Aldeota" segue para a IA
            # "Cocó" sozinho confundia o roteador (já foi parar no atendimento humano)
            # e a reextração do pedido (o modelo menor achou que "Papicu" era sabor).
            # Se é a resposta à pergunta que o próprio bot fez, o código resolve.
            bairro = z.bairro_no_texto(texto)
            if bairro:
                return self._fechar_entrega(bairro, False)
            if any(p in t for p in ("retir", "balcao", "vou buscar", "busco ai")):
                return self._fechar_entrega(None, True)

        fase = roteador.classificar(self.llm, self.historico)
        if self._esperando_entrega() and not cita_item and len(t.split()) <= 4 \
                and roteador.por_palavras(texto) not in ("cardapio", "humano"):
            # resposta curta à pergunta do bairro, com um bairro que não atendemos ("Messejana")
            fase = "entrega"

        if fase == "pedido":
            saida, self.pedido = subagentes.pedido(self.llm, self.historico, z, self.pedido)
        elif fase == "entrega":
            local = subagentes.extrair_local(self.llm, self.historico)
            atendido = z.bairro_oficial(local["bairro"]) if local.get("bairro") else None
            if self._esperando_entrega() and (atendido or local.get("retirada")):
                return self._fechar_entrega(atendido, bool(local.get("retirada")) and not atendido)
            saida = subagentes.entrega(local, z)
        elif fase == "cardapio":
            saida = subagentes.cardapio(self.llm, self.historico, z)
        elif fase == "humano":
            saida = subagentes.humano(z)
        else:
            saida = subagentes.info(self.llm, self.historico, z)
        return Resposta(saida.texto, saida.fase, saida.corrigida)
