import pytest

from atendente import pedido as ped
from atendente.dados import moeda, normalizar


def test_normalizar_ignora_acento_e_caixa():
    assert normalizar("  Fátima ") == "fatima"
    assert normalizar("COCÓ") == "coco"


def test_moeda_no_formato_brasileiro():
    assert moeda(1234.5) == "R$ 1.234,50"
    assert moeda(6) == "R$ 6,00"


def test_busca_sabor_por_nome_parcial(pizzaria):
    assert pizzaria.pizza("frango").nome == "Frango com Catupiry"
    assert pizzaria.pizza("CARNE DE SOL").id == "carne-de-sol"
    assert pizzaria.pizza("pepperoni") is None


def test_taxa_de_entrega(pizzaria):
    assert pizzaria.taxa_entrega("aldeota") == 6.0
    assert pizzaria.taxa_entrega("Dionisio Torres") == 7.0
    assert pizzaria.taxa_entrega("Messejana") is None


@pytest.mark.parametrize(
    "bruto, total",
    [
        ({"pizzas": [{"sabores": ["calabresa"], "tamanho": "G"}], "bairro": "Aldeota"}, 66.0),
        ({"pizzas": [{"sabores": ["calabresa", "carne de sol"], "tamanho": "G"}], "bairro": "Meireles"}, 80.0),
        ({"pizzas": [{"sabores": ["frango"], "tamanho": "M", "quantidade": 2}], "bairro": "Cocó"}, 112.0),
        (
            {"pizzas": [{"sabores": ["quatro queijos"], "tamanho": "G", "borda": True}],
             "bebidas": [{"nome": "refrigerante 2 l"}], "bairro": "Papicu"},
            98.0,
        ),
        ({"pizzas": [{"sabores": ["margherita"], "tamanho": "G", "quantidade": 3}], "retirada": True}, 174.0),
    ],
)
def test_total_calculado_em_codigo(pizzaria, bruto, total):
    assert ped.total(ped.montar(bruto, pizzaria), pizzaria) == total


def test_meio_a_meio_cobra_o_sabor_mais_caro(pizzaria):
    item = ped.ItemPizza(["Margherita", "Carne de Sol com Nata"], "M")
    assert ped.preco_pizza(item, pizzaria) == 58.0


@pytest.mark.parametrize(
    "bruto, trecho",
    [
        ({"pizzas": [{"sabores": ["pepperoni"], "tamanho": "G"}]}, "Não temos o sabor"),
        ({"pizzas": [{"sabores": ["calabresa", "margherita"], "tamanho": "P"}]}, "Meio a meio só"),
        ({"pizzas": [{"sabores": ["calabresa"], "tamanho": "GG"}]}, "tamanho GG"),
        ({"pizzas": [{"sabores": ["calabresa"]}]}, "Qual o tamanho"),
        ({"pizzas": [{"sabores": ["calabresa"], "tamanho": "M"}], "bairro": "Messejana"}, "não entregamos"),
        ({"bebidas": [{"nome": "cerveja"}]}, "Não temos \"cerveja\""),
    ],
)
def test_pedido_invalido_vira_mensagem_para_o_cliente(pizzaria, bruto, trecho):
    with pytest.raises(ped.ErroPedido, match=trecho):
        ped.montar(bruto, pizzaria)


def test_resumo_traz_itens_taxa_e_total(pizzaria):
    p = ped.montar({"pizzas": [{"sabores": ["calabresa"], "tamanho": "G"}], "bairro": "aldeota"}, pizzaria)
    texto = ped.resumo(p, pizzaria)
    assert "Pizza G Calabresa: R$ 60,00" in texto
    assert "Entrega em Aldeota: R$ 6,00" in texto
    assert "Total: R$ 66,00" in texto


def test_resumo_avisa_pedido_minimo(pizzaria):
    p = ped.montar({"bebidas": [{"nome": "água"}]}, pizzaria)
    assert "pedido mínimo é R$ 30,00" in ped.resumo(p, pizzaria)


@pytest.mark.parametrize(
    "pedido_do_cliente, item",
    [("coca lata", "refri-lata"), ("guaraná 2L", "refri-2l"), ("coca dois litros", "refri-2l"),
     ("suco de caju", "suco"), ("água", "agua")],
)
def test_bebida_por_apelido(pizzaria, pedido_do_cliente, item):
    assert pizzaria.bebida(pedido_do_cliente)["id"] == item


def test_cerveja_continua_sem_existir(pizzaria):
    assert pizzaria.bebida("cerveja") is None
