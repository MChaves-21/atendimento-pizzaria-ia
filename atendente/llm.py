"""Clientes de modelo de linguagem.

Qualquer modelo serve, desde que implemente `gerar`. Há dois prontos
(Gemini e Groq, ambos com plano gratuito) e um simulado para os testes.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Callable, Protocol

import httpx

Mensagem = dict[str, str]  # {"papel": "cliente" | "atendente", "texto": "..."}


class LLM(Protocol):
    def gerar(self, sistema: str, mensagens: list[Mensagem], json_mode: bool = False) -> str: ...


def extrair_json(texto: str) -> dict:
    """Lê o JSON da resposta, mesmo se o modelo cercar com ```json."""
    texto = texto.strip()
    bloco = re.search(r"\{.*\}", texto, re.DOTALL)
    if not bloco:
        raise ValueError(f"Resposta sem JSON: {texto[:120]!r}")
    return json.loads(bloco.group(0))


class _ComRetentativa:
    """Repete a chamada quando a API devolve 429 (limite do plano gratuito) ou 5xx."""

    tentativas = 4

    def _post(self, url: str, **kw) -> dict:
        for tentativa in range(self.tentativas):
            r = httpx.post(url, timeout=60, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                # limite por minuto costuma liberar em até 1 min; o diário, não
                time.sleep(float(r.headers.get("retry-after") or [5, 15, 30, 60][tentativa]))
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return r.json()


class GeminiLLM(_ComRetentativa):
    def __init__(self, api_key: str, modelo: str = "gemini-2.5-flash", temperatura: float = 0.3):
        self.api_key, self.modelo, self.temperatura = api_key, modelo, temperatura

    def gerar(self, sistema: str, mensagens: list[Mensagem], json_mode: bool = False) -> str:
        corpo = {
            "systemInstruction": {"parts": [{"text": sistema}]},
            "contents": [
                {"role": "user" if m["papel"] == "cliente" else "model", "parts": [{"text": m["texto"]}]}
                for m in mensagens
            ],
            "generationConfig": {"temperature": self.temperatura},
        }
        if json_mode:
            corpo["generationConfig"]["responseMimeType"] = "application/json"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent"
        dados = self._post(url, params={"key": self.api_key}, json=corpo)
        return dados["candidates"][0]["content"]["parts"][0]["text"]


class GroqLLM(_ComRetentativa):
    def __init__(self, api_key: str, modelo: str = "openai/gpt-oss-120b", temperatura: float = 0.3):
        self.api_key, self.modelo, self.temperatura = api_key, modelo, temperatura

    def gerar(self, sistema: str, mensagens: list[Mensagem], json_mode: bool = False) -> str:
        corpo = {
            "model": self.modelo,
            "temperature": self.temperatura,
            "messages": [{"role": "system", "content": sistema}]
            + [
                {"role": "user" if m["papel"] == "cliente" else "assistant", "content": m["texto"]}
                for m in mensagens
            ],
        }
        if json_mode:
            corpo["response_format"] = {"type": "json_object"}
        # modelos com raciocínio às vezes devolvem a resposta vazia; uma nova tentativa costuma resolver
        texto = ""
        for _ in range(2):
            dados = self._post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=corpo,
            )
            texto = (dados["choices"][0]["message"].get("content") or "").strip()
            if texto:
                break
        return texto


class LLMSimulado:
    """Modelo falso para testes: uma função decide a resposta e cada chamada fica registrada."""

    def __init__(self, responder: Callable[[str, list[Mensagem], bool], str]):
        self.responder = responder
        self.chamadas: list[dict] = []

    def gerar(self, sistema: str, mensagens: list[Mensagem], json_mode: bool = False) -> str:
        self.chamadas.append({"sistema": sistema, "mensagens": list(mensagens), "json": json_mode})
        return self.responder(sistema, mensagens, json_mode)


def do_ambiente() -> LLM:
    """Escolhe o modelo pelas variáveis de ambiente (LLM_PROVEDOR=gemini|groq)."""
    provedor = os.getenv("LLM_PROVEDOR", "gemini").lower()
    if provedor == "groq":
        return GroqLLM(os.environ["GROQ_API_KEY"], os.getenv("LLM_MODELO", "openai/gpt-oss-120b"))
    return GeminiLLM(os.environ["GEMINI_API_KEY"], os.getenv("LLM_MODELO", "gemini-2.5-flash"))
