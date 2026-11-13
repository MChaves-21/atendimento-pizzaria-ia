import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atendente.dados import carregar  # noqa: E402
from atendente.llm import LLMSimulado  # noqa: E402
from atendente.roteador import por_palavras  # noqa: E402


@pytest.fixture
def pizzaria():
    return carregar()


def llm_roteiro(extracoes: dict[str, dict] | None = None, textos: list[str] | None = None) -> LLMSimulado:
    """IA simulada:
    - roteador: classifica por palavras-chave;
    - extração de pedido/bairro: devolve o JSON cadastrado para a última mensagem;
    - respostas livres: devolve os textos da lista, em ordem.
    """
    extracoes = extracoes or {}
    fila = list(textos or [])

    def responder(sistema, mensagens, json_mode):
        ultima = mensagens[-1]["texto"]
        if sistema.startswith("Você classifica"):
            return json.dumps({"fase": por_palavras(ultima)})
        if json_mode:
            return json.dumps(extracoes.get(ultima, {}))
        return fila.pop(0) if fila else "Posso ajudar em mais alguma coisa?"

    return LLMSimulado(responder)
