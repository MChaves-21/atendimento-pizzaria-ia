"""Um subagente por fase do atendimento.

Cada um recebe um prompt curto e só os dados da sua fase. Quando o assunto
envolve números (pedido e entrega), a IA apenas extrai o que o cliente quis
dizer, e o texto com valores é montado em código.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import pedido as ped
from .dados import Pizzaria, moeda
from .llm import LLM, Mensagem, extrair_json
from .verificador import valores_citados, verificar

ESTILO = (
    "Responda em português do Brasil, em no máximo 3 frases, de forma simpática e direta. "
    "Use SOMENTE as informações abaixo. Se o cliente perguntar algo que não está aqui, "
    "diga que não temos ou que não sabe, sem inventar."
)


@dataclass
class Saida:
    texto: str
    fase: str
    tentativas: int = 1
    corrigida: bool = False  # True quando o verificador barrou a 1ª resposta


def _com_verificacao(llm: LLM, sistema: str, historico: list[Mensagem], pizzaria: Pizzaria,
                     fase: str, plano_b: str) -> Saida:
    """Gera, confere com o verificador e tenta de novo uma vez se houver invenção."""
    citados = valores_citados([m["texto"] for m in historico if m["papel"] == "cliente"])
    texto = llm.gerar(sistema, historico)
    res = verificar(texto, pizzaria, citados)
    if res.ok:
        return Saida(texto, fase)
    aviso = (
        sistema
        + "\n\nATENÇÃO: sua resposta anterior citou informação que não existe ("
        + "; ".join(res.motivos())
        + "). Responda de novo usando apenas os dados acima."
    )
    texto = llm.gerar(aviso, historico)
    if verificar(texto, pizzaria, citados).ok:
        return Saida(texto, fase, tentativas=2, corrigida=True)
    return Saida(plano_b, fase, tentativas=2, corrigida=True)


def info(llm: LLM, historico: list[Mensagem], pizzaria: Pizzaria) -> Saida:
    r = pizzaria.regras
    sistema = (
        f"Você é o atendente da {pizzaria.nome}. Cumprimente e tire dúvidas gerais.\n{ESTILO}\n\n"
        f"HORÁRIO: {pizzaria.texto_horario()}\n"
        f"PAGAMENTO: {', '.join(r['pagamento'])}\n"
        f"ENDEREÇO: {pizzaria.entrega['endereco_loja']}\n"
        "Se o cliente quiser pedir, convide-o a dizer o sabor e o tamanho."
    )
    plano_b = f"Olá! Aqui é a {pizzaria.nome}. {pizzaria.texto_horario()} Em que posso ajudar?"
    return _com_verificacao(llm, sistema, historico, pizzaria, "info", plano_b)


def cardapio(llm: LLM, historico: list[Mensagem], pizzaria: Pizzaria) -> Saida:
    sistema = (
        f"Você tira dúvidas sobre o cardápio da {pizzaria.nome}.\n{ESTILO}\n"
        "Cite preços exatamente como estão abaixo, sem arredondar nem somar.\n\n"
        f"{pizzaria.texto_cardapio()}"
    )
    plano_b = "Este é o nosso cardápio:\n" + pizzaria.texto_cardapio()
    return _com_verificacao(llm, sistema, historico, pizzaria, "cardapio", plano_b)


PROMPT_EXTRACAO_PEDIDO = """Extraia o pedido COMPLETO do cliente, considerando a conversa inteira até agora
(se ele pediu mais um item, inclua os anteriores; se trocou um item, use o novo).
Não calcule preços. Não invente itens. Para sabores, use o nome como o cliente falou; para bebidas, o nome do cardápio mais parecido (coca = refrigerante).
Responda só com JSON neste formato:
{
  "pizzas": [{"sabores": ["nome"], "tamanho": "P|M|G|null", "borda": false, "quantidade": 1}],
  "bebidas": [{"nome": "nome", "quantidade": 1}],
  "bairro": "nome do bairro ou null",
  "retirada": false,
  "finalizar": false
}
Meio a meio = dois sabores na mesma pizza. "finalizar" = true quando o cliente diz que é só isso / pode fechar.
Sabores do cardápio: {sabores}. Bebidas: {bebidas}."""


def pedido(llm: LLM, historico: list[Mensagem], pizzaria: Pizzaria, atual: ped.Pedido) -> tuple[Saida, ped.Pedido]:
    """A IA extrai os itens; validar, somar e escrever o resumo é com o código."""
    sistema = PROMPT_EXTRACAO_PEDIDO.replace(
        "{sabores}", ", ".join(p.nome for p in pizzaria.pizzas)
    ).replace("{bebidas}", ", ".join(b["nome"] for b in pizzaria.bebidas))
    try:
        bruto = extrair_json(llm.gerar(sistema, historico, json_mode=True))
    except Exception:
        return Saida("Não entendi o pedido. Pode repetir com o sabor e o tamanho?", "pedido"), atual

    try:
        novo = ped.montar(bruto, pizzaria)
    except ped.ErroPedido as e:
        return Saida(str(e), "pedido"), atual

    # A IA devolve o pedido completo: os itens SUBSTITUEM os anteriores (nunca somam),
    # para um item repetido na extração não virar pizza em dobro.
    if novo.pizzas or novo.bebidas:
        atual.pizzas, atual.bebidas = novo.pizzas, novo.bebidas
    if novo.bairro or novo.retirada:
        atual.bairro, atual.retirada = novo.bairro, novo.retirada

    texto = "Anotado! Seu pedido até agora:\n" + ped.resumo(atual, pizzaria)
    if not atual.bairro and not atual.retirada:
        texto += "\nÉ para entrega (em qual bairro?) ou retirada no balcão?"
    elif bruto.get("finalizar"):
        texto += f"\nPedido confirmado! Tempo médio de {pizzaria.entrega['tempo_medio_min']} minutos."
    else:
        texto += "\nDeseja mais alguma coisa?"
    return Saida(texto, "pedido"), atual


PROMPT_EXTRACAO_BAIRRO = """Diga qual local de entrega o cliente citou na ÚLTIMA mensagem (bairro, cidade
ou região, como ele escreveu), ou null se não citou nenhum. Não corrija nem troque o nome.
Responda só com JSON: {"bairro": "nome ou null", "retirada": false}"""


def entrega(llm: LLM, historico: list[Mensagem], pizzaria: Pizzaria) -> Saida:
    try:
        dados = extrair_json(llm.gerar(PROMPT_EXTRACAO_BAIRRO, historico[-2:], json_mode=True))
    except Exception:
        dados = {}
    tempo = pizzaria.entrega["tempo_medio_min"]
    if dados.get("retirada"):
        return Saida(f"Pode retirar no balcão, sem taxa: {pizzaria.entrega['endereco_loja']}.", "entrega")
    bairro = dados.get("bairro")
    if not bairro or str(bairro).lower() == "null":
        return Saida(pizzaria.texto_entrega(), "entrega")
    taxa = pizzaria.taxa_entrega(bairro)
    if taxa is None:
        return Saida(
            f"Ainda não entregamos em {bairro}. "
            f"Atendemos: {', '.join(pizzaria.entrega['bairros'])}. Você também pode retirar no balcão.",
            "entrega",
        )
    return Saida(
        f"Entregamos em {pizzaria.bairro_oficial(bairro)}, sim! Taxa de {moeda(taxa)} "
        f"e tempo médio de {tempo} minutos.",
        "entrega",
    )


def humano(pizzaria: Pizzaria) -> Saida:
    return Saida(
        "Entendi. Vou chamar uma pessoa da nossa equipe para te ajudar com isso, só um instante.",
        "humano",
    )
