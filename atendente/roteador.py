"""Roteador: decide qual subagente atende cada mensagem.

O roteador só classifica. Ele não responde ao cliente e não conhece
preços, por isso o prompt dele é curto e difícil de "confundir".
"""

from __future__ import annotations

from .dados import normalizar
from .llm import LLM, Mensagem, extrair_json

FASES = ("info", "cardapio", "pedido", "entrega", "humano")

PROMPT = """Você classifica mensagens de clientes de uma pizzaria em UMA fase:
- info: cumprimento, horário de funcionamento, formas de pagamento, endereço da loja
- cardapio: dúvidas sobre sabores, ingredientes, tamanhos, preços, bebidas, opções vegetarianas
- pedido: o cliente quer pedir, alterar ou fechar um pedido ("quero", "me vê", "adiciona", "fecha")
- entrega: bairro, taxa de entrega, tempo de entrega, retirada no balcão
- humano: reclamação, problema com pedido já feito, ou assunto que não é da pizzaria

Considere as últimas mensagens para entender o contexto.
Responda só com JSON: {"fase": "<info|cardapio|pedido|entrega|humano>"}"""

_PALAVRAS = {
    "pedido": ["quero", "me ve", "manda", "adiciona", "pedir", "fecha", "vou querer", "pode ser"],
    "entrega": ["entrega", "bairro", "taxa", "demora", "retirar", "retirada", "chega"],
    "cardapio": ["sabor", "sabores", "cardapio", "preco", "quanto", "tamanho", "bebida", "vegetarian", "ingrediente", "tem pizza"],
    "humano": ["reclama", "atrasou", "errado", "veio frio", "cancelar", "gerente"],
    "info": ["horario", "abre", "fecha que horas", "pix", "cartao", "pagamento", "endereco", "oi", "ola", "boa noite"],
}


def por_palavras(texto: str) -> str:
    """Plano B, sem IA, para quando o modelo falhar ou devolver lixo."""
    t = normalizar(texto)
    for fase in ("humano", "pedido", "entrega", "cardapio", "info"):
        if any(p in t for p in _PALAVRAS[fase]):
            return fase
    return "info"


def classificar(llm: LLM, historico: list[Mensagem]) -> str:
    contexto = historico[-4:]
    try:
        fase = extrair_json(llm.gerar(PROMPT, contexto, json_mode=True)).get("fase", "")
        if fase in FASES:
            return fase
    except Exception:
        pass
    return por_palavras(historico[-1]["texto"])
