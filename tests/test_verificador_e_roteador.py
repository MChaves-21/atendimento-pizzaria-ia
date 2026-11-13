import json

from atendente.llm import LLMSimulado, extrair_json
from atendente.roteador import classificar, por_palavras
from atendente.verificador import verificar


def test_preco_do_cardapio_passa(pizzaria):
    assert verificar("A Calabresa G sai por R$ 60,00.", pizzaria).ok


def test_preco_inventado_e_barrado(pizzaria):
    res = verificar("A Calabresa G custa R$ 59,90.", pizzaria)
    assert not res.ok
    assert res.precos_inventados == [59.9]


def test_total_calculado_na_conversa_e_permitido(pizzaria):
    assert not verificar("Total: R$ 66,00", pizzaria).ok
    assert verificar("Total: R$ 66,00", pizzaria, {66.0}).ok


def test_formatos_de_preco(pizzaria):
    assert verificar("R$46 ou R$ 1.234,50", pizzaria, {1234.5}).ok


def test_afirmar_sabor_que_nao_existe_e_invencao(pizzaria):
    assert verificar("Temos sim pizza de pepperoni!", pizzaria).sabores_inventados == ["pepperoni"]


def test_negar_sabor_que_nao_existe_nao_e_invencao(pizzaria):
    assert verificar("Não temos pizza de pepperoni, mas temos calabresa.", pizzaria).ok
    assert verificar("Infelizmente não trabalhamos com atum.", pizzaria).ok


def test_extrair_json_com_cerca_de_codigo():
    assert extrair_json('```json\n{"fase": "pedido"}\n```') == {"fase": "pedido"}


def test_roteador_usa_a_fase_do_modelo():
    llm = LLMSimulado(lambda s, m, j: json.dumps({"fase": "entrega"}))
    assert classificar(llm, [{"papel": "cliente", "texto": "oi"}]) == "entrega"


def test_roteador_cai_nas_palavras_chave_se_o_modelo_falhar():
    llm = LLMSimulado(lambda s, m, j: "não sei")
    assert classificar(llm, [{"papel": "cliente", "texto": "quero uma G de calabresa"}]) == "pedido"


def test_palavras_chave():
    assert por_palavras("Meu pedido atrasou!") == "humano"
    assert por_palavras("Qual a taxa pro Benfica?") == "entrega"
    assert por_palavras("Quanto custa a pizza de frango?") == "cardapio"
    assert por_palavras("Boa noite") == "info"
