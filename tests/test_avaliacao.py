import json

from atendente.llm import LLMSimulado
from atendente.roteador import por_palavras
from avaliacao.avaliar import avaliar_resposta, carregar_casos, resumir, rodar, salvar


def caso(**kw):
    return {"id": "x", "categoria": "teste", "mensagens": ["oi"], **kw}


def test_valor_certo_e_correto(pizzaria):
    inventou, correta, _ = avaliar_resposta(caso(valores_esperados=[60.0]), "Sai por R$ 60,00.", pizzaria)
    assert (inventou, correta) == (False, True)


def test_valor_inventado_conta_como_invencao(pizzaria):
    inventou, correta, motivos = avaliar_resposta(caso(valores_esperados=[60.0]), "Sai por R$ 59,00.", pizzaria)
    assert inventou and not correta
    assert any("preço inexistente" in m for m in motivos)


def test_total_correto_do_pedido_nao_e_invencao(pizzaria):
    c = caso(valores_esperados=[66.0], valores_corretos=[60.0, 6.0, 66.0])
    assert avaliar_resposta(c, "Total com entrega: R$ 66,00", pizzaria)[:2] == (False, True)


def test_frase_proibida(pizzaria):
    c = caso(deve_conter_algum=["nao temos"], nao_deve_conter=[r"atum[^.!?]{0,40}r\$"])
    inventou, correta, _ = avaliar_resposta(c, "A de atum grande custa R$ 60,00.", pizzaria)
    assert inventou and not correta


def test_resposta_incompleta_nao_e_invencao(pizzaria):
    inventou, correta, _ = avaliar_resposta(caso(deve_conter_algum=["23:30"]), "Abrimos à noite.", pizzaria)
    assert (inventou, correta) == (False, False)


def test_casos_bem_formados():
    casos = carregar_casos()
    assert len(casos) >= 45
    assert len({c["id"] for c in casos}) == len(casos)
    for c in casos:
        assert c["mensagens"] and ("valores_esperados" in c or "deve_conter_algum" in c), c["id"]


def test_rodada_completa_com_modelo_simulado(pizzaria, tmp_path):
    """O monolítico simulado erra a conta; os subagentes fazem a conta em código."""

    def responder(sistema, mensagens, json_mode):
        ultima = mensagens[-1]["texto"]
        if sistema.startswith("Você classifica"):
            return json.dumps({"fase": por_palavras(ultima)})
        if json_mode:
            return json.dumps({"pizzas": [{"sabores": ["calabresa"], "tamanho": "G"}], "bairro": "Aldeota"})
        return "Fica R$ 65,00 com a entrega."  # conta errada de propósito

    casos = [caso(id="ped", categoria="pedido", mensagens=["Quero uma G de calabresa na Aldeota"],
                  valores_esperados=[66.0], valores_corretos=[60.0, 6.0, 66.0])]
    notas = rodar(lambda: LLMSimulado(responder), ["monolitico", "subagentes"], casos)
    por_modo = {n.modo: n for n in notas}
    assert por_modo["monolitico"].inventou
    assert por_modo["subagentes"].correta

    resumo = resumir(notas)
    assert resumo["monolitico"]["inventadas_pct"] == 100.0
    assert resumo["subagentes"]["inventadas_pct"] == 0.0

    salvar(notas, resumo, {"modelo": "simulado", "casos": 1, "data": "hoje"}, tmp_path)
    relatorio = (tmp_path / "relatorio.md").read_text(encoding="utf-8")
    assert "| Prompt único | 100.0% |" in relatorio
    assert (tmp_path / "respostas.csv").exists()
