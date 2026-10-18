"""Cliente HTTP mínimo para o Ollama (somente stdlib).

API usada: GET /api/version, GET /api/tags, POST /api/generate (carregar modelo),
POST /api/chat (resposta).

Segurança: por padrão só aceita servidores em loopback, e ignora variáveis
de proxy do ambiente (um http_proxy configurado desviaria o tráfego local).
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlparse

from llm.brain import BrainReply, DeltaCallback

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_MAX_RESPONSE_BYTES = 4_000_000


class OllamaError(Exception):
    """Falha de comunicação ou resposta inválida do Ollama (mensagem apresentável)."""


@dataclass(frozen=True, slots=True)
class ChatResult:
    text: str
    model: str
    tokens: int
    seconds: float

    @property
    def tokens_per_second(self) -> float:
        return self.tokens / self.seconds if self.seconds > 0 else 0.0


def normalize_model(name: str) -> str:
    return name if ":" in name else f"{name}:latest"


class OllamaClient:
    def __init__(self, base_url: str, timeout_s: float, *, allow_remote: bool = False) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(f"URL do Ollama inválida: {base_url!r}")
        if not allow_remote and parsed.hostname not in _LOOPBACK:
            raise ValueError(
                f"Servidor remoto bloqueado ({parsed.hostname}). "
                "Use DELSIN_LLM_ALLOW_REMOTE=1 se for intencional."
            )
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _request(self, method: str, path: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        try:
            with self._opener.open(request, timeout=timeout or self.timeout_s) as response:
                body = response.read(_MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError as exc:
            raise OllamaError(f"HTTP {exc.code}: {self._error_detail(exc)}") from exc
        except urllib.error.URLError as exc:
            raise OllamaError(f"Ollama inacessível em {self.base_url} ({exc.reason})") from exc
        except (TimeoutError, OSError) as exc:
            raise OllamaError(f"Sem resposta do Ollama em {timeout or self.timeout_s:.0f}s") from exc
        try:
            return json.loads(body)
        except ValueError as exc:
            raise OllamaError("Resposta inválida do Ollama") from exc

    @staticmethod
    def _error_detail(exc: urllib.error.HTTPError) -> str:
        try:
            return json.loads(exc.read(4000)).get("error", exc.reason)
        except (ValueError, OSError):
            return str(exc.reason)

    def version(self) -> str:
        return str(self._request("GET", "/api/version", timeout=3).get("version", "?"))

    def models(self) -> list[str]:
        return [m.get("name", "") for m in self._request("GET", "/api/tags", timeout=5).get("models", [])]

    def has_model(self, model: str) -> bool:
        wanted = normalize_model(model)
        return any(normalize_model(name) == wanted for name in self.models())

    def warm_up(self, model: str, keep_alive: str) -> None:
        """Carrega o modelo na memória (prompt vazio) para a 1ª resposta não pagar esse custo."""
        self._request("POST", "/api/generate", {"model": model, "keep_alive": keep_alive})

    def chat(self, model: str, messages: list[dict], *, options: dict, keep_alive: str) -> ChatResult:
        started = time.perf_counter()
        reply = self._request("POST", "/api/chat", {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options,
            "keep_alive": keep_alive,
        })
        message = reply.get("message") or {}
        if "content" not in message:
            raise OllamaError(reply.get("error") or "Resposta do Ollama sem conteúdo")
        return ChatResult(
            text=message["content"],
            model=reply.get("model", model),
            tokens=int(reply.get("eval_count") or 0),
            seconds=(reply.get("eval_duration") or 0) / 1e9 or time.perf_counter() - started,
        )


class OllamaBrain:
    """Cérebro local via Ollama. Não executa ferramentas; o histórico fica em memória."""

    name = "ollama"
    label = "Ollama (local, offline)"

    def __init__(self, client: OllamaClient, model: str, *, temperature: float, context_tokens: int,
                 max_response_tokens: int, history_turns: int, keep_alive: str) -> None:
        self._client = client
        self.model = model
        self._options = {"temperature": temperature, "num_ctx": context_tokens, "num_predict": max_response_tokens}
        self._keep_alive = keep_alive
        self._system_prompt = ""
        self._history: deque[dict] = deque(maxlen=history_turns * 2)
        self._lock = threading.Lock()

    def check(self) -> tuple[bool, str]:
        try:
            version = self._client.version()
            if not self._client.has_model(self.model):
                return False, f"modelo {self.model} não baixado (rode: ollama pull {self.model})"
        except OllamaError as exc:
            return False, str(exc)
        return True, f"ollama {version} · {self.model}"

    def start(self, system_prompt: str) -> None:
        self._system_prompt = system_prompt
        self._client.warm_up(self.model, self._keep_alive)

    def ask(self, text: str, on_delta: DeltaCallback | None = None) -> BrainReply:
        """Sem streaming no Ollama por enquanto: a resposta chega inteira."""
        with self._lock:
            history = list(self._history)
        messages = [{"role": "system", "content": self._system_prompt}, *history, {"role": "user", "content": text}]
        try:
            result = self._client.chat(self.model, messages, options=self._options, keep_alive=self._keep_alive)
        except OllamaError as exc:
            return BrainReply(str(exc), success=False)
        with self._lock:
            self._history.append({"role": "user", "content": text})
            self._history.append({"role": "assistant", "content": result.text})
        return BrainReply(result.text, meta={
            "model": result.model, "tokens": result.tokens, "tokens_per_second": result.tokens_per_second,
        })

    def reset(self) -> None:
        with self._lock:
            self._history.clear()

    def close(self) -> None:
        pass
