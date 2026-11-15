from atendente import Atendente
from atendente.monolitico import prompt as prompt_monolitico

from .conftest import llm_roteiro


def test_bairro_depois_do_pedido_fecha_a_conta(pizzaria):
    llm = llm_roteiro(extracoes={
        "Quero uma G de calabresa": {"pizzas": [{"sabores": ["calabresa"], "tamanho": "G"}]},
        "É entrega no bairro Aldeota": {"bairro": "Aldeota"},
    })
    bot = Atendente(llm, pizzaria=pizzaria)
    bot.responder("Quero uma G de calabresa")
    r = bot.responder("É entrega no bairro Aldeota")
    assert "Entrega em Aldeota: R$ 6,00" in r.texto
    assert "Total: R$ 66,00" in r.texto
    assert 66.0 in bot.valores_do_pedido()


def test_sabor_inexistente_no_pedido(pizzaria):
    llm = llm_roteiro(extracoes={"Quero uma G de pepperoni": {"pizzas": [{"sabores": ["pepperoni"], "tamanho": "G"}]}})
    r = Atendente(llm, pizzaria=pizzaria).responder("Quero uma G de pepperoni")
    assert "Não temos o sabor" in r.texto


def test_entrega_fora_da_area(pizzaria):
    llm = llm_roteiro(extracoes={"Vocês entregam no bairro Messejana?": {"bairro": "Messejana"}})
    r = Atendente(llm, pizzaria=pizzaria).responder("Vocês entregam no bairro Messejana?")
    assert r.fase == "entrega"
    assert "não entregamos" in r.texto


def test_verificador_corrige_preco_inventado(pizzaria):
    llm = llm_roteiro(textos=["A Calabresa G custa R$ 59,90.", "A Calabresa G custa R$ 60,00."])
    r = Atendente(llm, pizzaria=pizzaria).responder("Quanto custa a calabresa G?")
    assert r.fase == "cardapio"
    assert r.corrigida
    assert "R$ 60,00" in r.texto
    assert "preço inexistente" in llm.chamadas[-1]["sistema"]  # o aviso foi para o modelo


def test_se_insistir_no_erro_usa_o_plano_b(pizzaria):
    llm = llm_roteiro(textos=["Custa R$ 59,90.", "Custa R$ 61,00."])
    r = Atendente(llm, pizzaria=pizzaria).responder("Quanto custa a calabresa G?")
    assert r.corrigida
    assert r.texto.startswith("Este é o nosso cardápio")


def test_subagente_de_cardapio_nao_ve_bairros(pizzaria):
    llm = llm_roteiro(textos=["A Margherita M custa R$ 46,00."])
    Atendente(llm, pizzaria=pizzaria).responder("Qual o preço da margherita?")
    sistema = llm.chamadas[-1]["sistema"]
    assert "Margherita" in sistema
    assert "Benfica" not in sistema  # só os dados da fase


def test_reclamacao_vai_para_humano_sem_chamar_resposta_livre(pizzaria):
    llm = llm_roteiro()
    r = Atendente(llm, pizzaria=pizzaria).responder("Meu pedido atrasou")
    assert r.fase == "humano"
    assert "equipe" in r.texto
    assert len(llm.chamadas) == 1  # só o roteador


def test_monolitico_manda_tudo_num_prompt(pizzaria):
    llm = llm_roteiro(textos=["Olá!"])
    bot = Atendente(llm, modo="monolitico", pizzaria=pizzaria)
    bot.responder("Oi")
    assert len(llm.chamadas) == 1
    assert llm.chamadas[0]["sistema"] == prompt_monolitico(pizzaria)
    assert "Benfica" in llm.chamadas[0]["sistema"] and "Margherita" in llm.chamadas[0]["sistema"]


def test_extracao_repetida_nao_duplica_itens(pizzaria):
    """A IA devolve o pedido completo a cada mensagem; o código substitui, não soma."""
    g_calabresa = {"sabores": ["calabresa"], "tamanho": "G"}
    llm = llm_roteiro(extracoes={
        "Quero uma G de calabresa": {"pizzas": [g_calabresa]},
        "Adiciona uma coca lata": {"pizzas": [g_calabresa], "bebidas": [{"nome": "refrigerante lata"}]},
    })
    bot = Atendente(llm, pizzaria=pizzaria)
    bot.responder("Quero uma G de calabresa")
    r = bot.responder("Adiciona uma coca lata")
    assert len(bot.pedido.pizzas) == 1
    assert "Subtotal: R$ 66,00" in r.texto


def test_repetir_valor_do_cliente_nao_dispara_o_plano_b(pizzaria):
    """Achado da 1ª avaliação real: o verificador barrava o R$ 50 que o próprio cliente disse."""
    llm = llm_roteiro(textos=["Hoje não temos promoção de duas pizzas por R$ 50,00."])
    r = Atendente(llm, pizzaria=pizzaria).responder("Tem promoção de duas pizzas por 50 reais? Quanto custa a pizza?")
    assert not r.corrigida
    assert "não temos promoção" in r.texto


def _llm_que_erra_a_entrega(pedido: dict):
    """Simula o gpt-oss-20b: o roteador manda o bairro para o humano e a reextração inventa bebida."""
    import json as _json

    from atendente.llm import LLMSimulado

    def responder(sistema, mensagens, json_mode):
        ultima = mensagens[-1]["texto"]
        if sistema.startswith("Você classifica"):
            return _json.dumps({"fase": "pedido" if ultima.startswith(("Quero", "Uma")) else "humano"})
        if sistema.startswith("Diga qual local"):
            return _json.dumps({"bairro": ultima, "retirada": False})
        if ultima.startswith(("Quero", "Uma")):
            return _json.dumps(pedido)
        return _json.dumps({**pedido, "bebidas": [{"nome": "refrigerante lata", "quantidade": 1}]})

    return LLMSimulado(responder)


def test_bairro_sozinho_fecha_o_pedido_em_codigo(pizzaria):
    """ped-04 com gpt-oss-20b: "Cocó" foi para o humano; depois, a reextração inventou uma coca."""
    pedido = {"pizzas": [{"sabores": ["frango com catupiry"], "tamanho": "M", "quantidade": 2}]}
    llm = _llm_que_erra_a_entrega(pedido)
    bot = Atendente(llm, pizzaria=pizzaria)
    bot.responder("Quero 2 pizzas M de frango com catupiry")
    n = len(llm.chamadas)
    r = bot.responder("Cocó")
    assert r.fase == "pedido"
    assert "Total: R$ 112,00" in r.texto
    assert "Refrigerante" not in r.texto
    assert len(llm.chamadas) == n  # nenhuma chamada à IA


def test_retirada_fecha_o_pedido_em_codigo(pizzaria):
    llm = _llm_que_erra_a_entrega({"pizzas": [{"sabores": ["calabresa"], "tamanho": "G"}]})
    bot = Atendente(llm, pizzaria=pizzaria)
    bot.responder("Quero uma G de calabresa")
    r = bot.responder("Vou retirar no balcão")
    assert "Total: R$ 60,00" in r.texto


def test_bairro_fora_da_area_com_pedido_em_andamento(pizzaria):
    """ped-12 com gpt-oss-20b: "Messejana" virou resumo do pedido, sem dizer que não entregamos."""
    llm = _llm_que_erra_a_entrega({"pizzas": [{"sabores": ["calabresa"], "tamanho": "M"}]})
    bot = Atendente(llm, pizzaria=pizzaria)
    bot.responder("Quero uma M de calabresa")
    r = bot.responder("Messejana")
    assert r.fase == "entrega"
    assert "Ainda não entregamos em Messejana" in r.texto


def test_bairro_no_texto(pizzaria):
    assert pizzaria.bairro_no_texto("é no Cocó") == "Cocó"
    assert pizzaria.bairro_no_texto("fatima") == "Fátima"
    assert pizzaria.bairro_no_texto("coco ralado") == "Cocó"  # o roteador só é pulado com pedido em andamento
    assert pizzaria.bairro_no_texto("Caucaia") is None
