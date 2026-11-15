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


def test_bairro_sozinho_responde_a_pergunta_do_pedido_sem_passar_pelo_roteador(pizzaria):
    """Caso ped-04 com gpt-oss-20b: o roteador mandou "Cocó" para o atendimento humano."""
    import json as _json

    from atendente.llm import LLMSimulado

    pedido = {"pizzas": [{"sabores": ["frango com catupiry"], "tamanho": "M", "quantidade": 2}]}

    def responder(sistema, mensagens, json_mode):
        ultima = mensagens[-1]["texto"]
        if sistema.startswith("Você classifica"):
            return _json.dumps({"fase": "pedido" if ultima.startswith("Quero") else "humano"})
        if ultima == "Cocó":
            return _json.dumps({**pedido, "bairro": "Cocó"})
        return _json.dumps(pedido)

    llm = LLMSimulado(responder)
    bot = Atendente(llm, pizzaria=pizzaria)
    bot.responder("Quero 2 pizzas M de frango com catupiry")
    r = bot.responder("Cocó")
    assert r.fase == "pedido"
    assert "Total: R$ 112,00" in r.texto
    assert not any(c["sistema"].startswith("Você classifica") for c in llm.chamadas[2:])


def test_bairro_no_texto(pizzaria):
    assert pizzaria.bairro_no_texto("é no Cocó") == "Cocó"
    assert pizzaria.bairro_no_texto("fatima") == "Fátima"
    assert pizzaria.bairro_no_texto("coco ralado") == "Cocó"  # o roteador só é pulado com pedido em andamento
    assert pizzaria.bairro_no_texto("Caucaia") is None
