"""Pedido e cálculo do total, 100% em código.

A IA só transforma "quero uma G meio calabresa meio portuguesa e uma coca 2L"
em itens. Validar sabores e somar valores é trabalho daqui, porque é aí
que um modelo de linguagem mais erra.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dados import Pizzaria, moeda


@dataclass
class ItemPizza:
    sabores: list[str]  # nomes oficiais; 2 sabores = meio a meio
    tamanho: str        # P, M ou G
    borda: bool = False
    quantidade: int = 1


@dataclass
class ItemBebida:
    nome: str
    preco: float
    quantidade: int = 1


@dataclass
class Pedido:
    pizzas: list[ItemPizza] = field(default_factory=list)
    bebidas: list[ItemBebida] = field(default_factory=list)
    bairro: str | None = None        # nome oficial do bairro, ou None
    retirada: bool = False


class ErroPedido(ValueError):
    """Algo no pedido não existe ou não é permitido. A mensagem vai direto para o cliente."""


def preco_pizza(item: ItemPizza, pizzaria: Pizzaria) -> float:
    if item.tamanho not in pizzaria.tamanhos:
        raise ErroPedido(f"Não temos o tamanho {item.tamanho}. Os tamanhos são P, M e G.")
    if not 1 <= len(item.sabores) <= 2:
        raise ErroPedido("Cada pizza pode ter 1 sabor ou ser meio a meio (2 sabores).")
    if len(item.sabores) == 2 and item.tamanho == "P":
        raise ErroPedido("Meio a meio só nos tamanhos M e G.")
    precos = []
    for sabor in item.sabores:
        pizza = pizzaria.pizza(sabor)
        if pizza is None:
            raise ErroPedido(f"Não temos o sabor \"{sabor}\" no cardápio.")
        precos.append(pizza.precos[item.tamanho])
    valor = max(precos)  # meio a meio cobra o sabor mais caro
    if item.borda:
        valor += pizzaria.regras["borda_recheada"]["preco"]
    return valor * item.quantidade


def montar(bruto: dict, pizzaria: Pizzaria) -> Pedido:
    """Converte o JSON extraído pela IA em Pedido, validando tudo contra o cardápio."""
    pedido = Pedido()
    for p in bruto.get("pizzas", []) or []:
        sabores = [s for s in (p.get("sabores") or []) if s]
        if not sabores:
            raise ErroPedido("Qual sabor você quer?")
        oficiais = []
        for s in sabores:
            pizza = pizzaria.pizza(s)
            if pizza is None:
                raise ErroPedido(f"Não temos o sabor \"{s}\" no cardápio.")
            oficiais.append(pizza.nome)
        tamanho = str(p.get("tamanho") or "").upper()
        if not tamanho:
            raise ErroPedido(f"Qual o tamanho da {' / '.join(oficiais)}? Temos P, M e G.")
        item = ItemPizza(oficiais, tamanho, bool(p.get("borda")), int(p.get("quantidade") or 1))
        preco_pizza(item, pizzaria)  # valida tamanho e meio a meio
        pedido.pizzas.append(item)

    for b in bruto.get("bebidas", []) or []:
        bebida = pizzaria.bebida(b.get("nome", ""))
        if bebida is None:
            raise ErroPedido(f"Não temos \"{b.get('nome')}\" entre as bebidas.")
        pedido.bebidas.append(ItemBebida(bebida["nome"], bebida["preco"], int(b.get("quantidade") or 1)))

    if bruto.get("retirada"):
        pedido.retirada = True
    elif bruto.get("bairro"):
        oficial = pizzaria.bairro_oficial(bruto["bairro"])
        if oficial is None:
            raise ErroPedido(
                f"Ainda não entregamos em {bruto['bairro']}. "
                "Você pode retirar no balcão, se preferir."
            )
        pedido.bairro = oficial
    return pedido


def subtotal(pedido: Pedido, pizzaria: Pizzaria) -> float:
    pizzas = sum(preco_pizza(i, pizzaria) for i in pedido.pizzas)
    bebidas = sum(b.preco * b.quantidade for b in pedido.bebidas)
    return round(pizzas + bebidas, 2)


def taxa(pedido: Pedido, pizzaria: Pizzaria) -> float:
    if pedido.retirada or not pedido.bairro:
        return 0.0
    return pizzaria.taxa_entrega(pedido.bairro) or 0.0


def total(pedido: Pedido, pizzaria: Pizzaria) -> float:
    return round(subtotal(pedido, pizzaria) + taxa(pedido, pizzaria), 2)


def resumo(pedido: Pedido, pizzaria: Pizzaria) -> str:
    """Texto do resumo, montado em código: nenhum número vem da IA."""
    if not pedido.pizzas and not pedido.bebidas:
        return "Ainda não anotei nenhum item. O que você gostaria de pedir?"
    linhas = []
    for i in pedido.pizzas:
        sabor = " / ".join(i.sabores) if len(i.sabores) == 1 else "meio " + " e meio ".join(i.sabores)
        borda = " com borda recheada" if i.borda else ""
        linhas.append(f"- {i.quantidade}x Pizza {i.tamanho} {sabor}{borda}: {moeda(preco_pizza(i, pizzaria))}")
    for b in pedido.bebidas:
        linhas.append(f"- {b.quantidade}x {b.nome}: {moeda(b.preco * b.quantidade)}")
    linhas.append(f"Subtotal: {moeda(subtotal(pedido, pizzaria))}")
    if pedido.retirada:
        linhas.append("Retirada no balcão: sem taxa")
    elif pedido.bairro:
        linhas.append(f"Entrega em {pedido.bairro}: {moeda(taxa(pedido, pizzaria))}")
    linhas.append(f"Total: {moeda(total(pedido, pizzaria))}")
    minimo = pizzaria.regras["pedido_minimo"]
    if subtotal(pedido, pizzaria) < minimo:
        linhas.append(f"Obs.: o pedido mínimo é {moeda(minimo)}.")
    return "\n".join(linhas)
