"""Cérebro Claude via Claude Code CLI (assinatura do usuário, sem API key).

Um único processo `claude -p` de longa duração, conversando em stream-json:
o contexto fica no processo e cada pergunta não paga a inicialização.

Política de ferramentas (aplicada pelo próprio Claude Code):
- liberadas sem pedir: leitura (Read/Glob/Grep), pesquisa web e uma lista
  curta de comandos de consulta (df, free, uptime...);
- todo o resto é NEGADO (--permission-mode dontAsk) e volta em
  `permission_denials`. O Delsin transforma isso em pedido de aprovação; quem
  executa, se você aprovar, é o próprio Delsin (services/actions.py).
- --safe-mode: ignora CLAUDE.md, hooks, plugins e MCP das suas configurações;
- ANTHROPIC_API_KEY/AUTH_TOKEN são removidas do ambiente: o uso sai do plano.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path

from llm.brain import BrainReply, PendingAction, describe_action

log = logging.getLogger("delsin.llm.claude")

TOOLS = ("Bash", "Read", "Glob", "Grep", "Write", "Edit", "WebSearch", "WebFetch")
READ_ONLY_COMMANDS = (
    "df", "free", "uptime", "uname", "lscpu", "lsblk", "ps", "date", "whoami", "hostnamectl",
    "nvidia-smi", "sensors", "ls", "du", "which", "ip addr", "systemctl status", "wpctl status",
)
# Leitura proibida mesmo com Read liberado: credenciais e dados de navegador.
SENSITIVE_PATHS = (
    "~/.ssh/**", "~/.gnupg/**", "~/.aws/**", "~/.config/delsin/**", "~/.local/share/keyrings/**",
    "~/.mozilla/**", "~/.config/google-chrome/**", "~/.password-store/**", "**/.env", "**/*.pem", "**/*.key",
)
_STRIPPED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")


def allowed_rules() -> list[str]:
    rules = ["Read", "Glob", "Grep", "WebSearch", "WebFetch"]
    for command in READ_ONLY_COMMANDS:
        rules += [f"Bash({command})", f"Bash({command} *)"]
    return rules


def denied_rules() -> list[str]:
    return [f"{tool}({path})" for path in SENSITIVE_PATHS for tool in ("Read", "Grep", "Glob")]


class ClaudeCodeBrain:
    name = "claude"
    label = "Claude (assinatura via Claude Code)"

    def __init__(self, model: str, effort: str, timeout_s: float, workdir: Path,
                 binary: str = "claude") -> None:
        self.model = model
        self._effort = effort
        self._timeout_s = timeout_s
        self._workdir = workdir
        self._binary = binary
        self._system_prompt = ""
        self._proc: subprocess.Popen[str] | None = None
        self._events: queue.Queue[dict | None] = queue.Queue()
        self._lock = threading.Lock()

    # ---------- disponibilidade ----------

    def check(self) -> tuple[bool, str]:
        path = shutil.which(self._binary)
        if not path:
            return False, "Claude Code não encontrado (instale e rode `claude` uma vez para logar)"
        try:
            raw = subprocess.run([path, "auth", "status"], capture_output=True, text=True,
                                 timeout=15, env=self._env()).stdout
            status = json.loads(raw)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            return False, f"Não foi possível verificar o login do Claude Code: {exc}"
        if not status.get("loggedIn"):
            return False, "Claude Code sem login — rode `claude` no terminal e faça login"
        if status.get("authMethod") != "claude.ai":
            return False, f"Claude Code logado via {status.get('authMethod')}, não pela assinatura"
        return True, f"assinatura claude.ai · {self.model}"

    # ---------- ciclo de vida ----------

    def _env(self) -> dict[str, str]:
        return {k: v for k, v in os.environ.items() if k not in _STRIPPED_ENV}

    def _command(self) -> list[str]:
        return [
            shutil.which(self._binary) or self._binary, "-p",
            "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--model", self.model, "--effort", self._effort,
            "--tools", ",".join(TOOLS),
            "--allowedTools", *allowed_rules(),
            "--disallowedTools", *denied_rules(),
            "--permission-mode", "dontAsk",
            "--safe-mode", "--strict-mcp-config", "--no-session-persistence",
            "--system-prompt", self._system_prompt,
        ]

    def start(self, system_prompt: str) -> None:
        self._system_prompt = system_prompt
        with self._lock:
            self._spawn()

    def _spawn(self) -> None:
        self._kill()
        self._workdir.mkdir(parents=True, exist_ok=True)
        self._events = queue.Queue()
        self._proc = subprocess.Popen(
            self._command(), cwd=self._workdir, env=self._env(), text=True, bufsize=1,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._read_stdout, args=(self._proc, self._events),
                         name="delsin-claude-out", daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(self._proc,),
                         name="delsin-claude-err", daemon=True).start()
        log.info("Sessão Claude Code iniciada (pid %s, %s, esforço %s)", self._proc.pid, self.model, self._effort)

    @staticmethod
    def _read_stdout(proc: subprocess.Popen[str], events: queue.Queue) -> None:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                events.put(json.loads(line))
            except ValueError:
                log.debug("Linha não-JSON do Claude Code: %s", line[:200])
        events.put(None)  # processo terminou

    @staticmethod
    def _read_stderr(proc: subprocess.Popen[str]) -> None:
        for line in proc.stderr:
            if line.strip():
                log.debug("claude stderr: %s", line.strip()[:300])

    def _kill(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
            self._proc.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            self._proc.kill()
        self._proc = None

    def reset(self) -> None:
        with self._lock:
            if self._system_prompt:
                self._spawn()

    def close(self) -> None:
        with self._lock:
            self._kill()

    # ---------- conversa ----------

    def ask(self, text: str) -> BrainReply:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                if self._proc is not None:
                    log.warning("Sessão Claude Code encerrada (código %s); reiniciando", self._proc.returncode)
                self._spawn()
            message = {"type": "user", "message": {"role": "user", "content": text}}
            try:
                self._proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                self._proc.stdin.flush()
            except OSError as exc:
                self._proc = None
                return BrainReply(f"Falha ao falar com o Claude Code: {exc}", success=False)
            return self._collect()

    def _collect(self) -> BrainReply:
        texts: list[str] = []
        while True:
            try:
                event = self._events.get(timeout=self._timeout_s)
            except queue.Empty:
                log.warning("Claude Code sem resposta em %.0fs; reiniciando a sessão", self._timeout_s)
                self._spawn()
                return BrainReply("O Claude demorou demais e a sessão foi reiniciada. Tente de novo.", success=False)
            if event is None:
                self._proc = None
                return BrainReply("A sessão do Claude Code terminou inesperadamente. Veja o log.", success=False)
            kind = event.get("type")
            if kind == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        texts.append(block["text"])
            elif kind == "rate_limit_event":
                log.debug("Limite de uso: %s", event.get("rate_limit_info"))
            elif kind == "result":
                return self._reply(event, texts)

    @staticmethod
    def _reply(event: dict, texts: list[str]) -> BrainReply:
        actions = tuple(
            PendingAction(d.get("tool_name", "?"), d.get("tool_input") or {},
                          describe_action(d.get("tool_name", "?"), d.get("tool_input") or {}))
            for d in event.get("permission_denials") or []
            if d.get("tool_name") in ("Bash", "Write", "Edit")
        )
        text = (event.get("result") or "\n".join(texts)).strip()
        meta = {
            "model": next(iter(event.get("modelUsage") or {}), ""),
            "duration_ms": event.get("duration_ms"),
            "cost_equivalent_usd": event.get("total_cost_usd"),
        }
        if event.get("is_error"):
            log.warning("Claude Code retornou erro: %s", text[:300])
            return BrainReply(text or "O Claude Code retornou um erro.", success=False, meta=meta)
        return BrainReply(text, actions=actions, meta=meta)
