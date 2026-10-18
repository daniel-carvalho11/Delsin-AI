"""Imitação mínima do `claude -p` em stream-json para testes (sem rede, sem cota).

Protocolo imitado: handshake `initialize`, texto em pedaços (stream_event),
pedido de aprovação `can_use_tool` (control_request) e resultado final.

Comportamentos por conteúdo da mensagem:
  "touch"  -> pede aprovação para Bash; responde conforme allow/deny
  "trave"  -> nunca responde (testa timeout)
  "morra"  -> encerra o processo (testa recuperação)
  outro    -> "eco <n>: <texto>" em 2 pedaços (n = turno no MESMO processo)
"""
import json
import sys
import time


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def delta(text: str) -> None:
    emit({"type": "stream_event", "event": {"type": "content_block_delta",
                                            "delta": {"type": "text_delta", "text": text}}})


def result(text: str) -> None:
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    emit({"type": "result", "subtype": "success", "is_error": False, "result": text,
          "duration_ms": 5, "total_cost_usd": 0.0, "permission_denials": [],
          "modelUsage": {"claude-opus-5-5": {}}})


def main() -> None:
    if sys.argv[1:3] == ["auth", "status"]:
        print(json.dumps({"loggedIn": True, "authMethod": "claude.ai"}))
        return
    emit({"type": "system", "subtype": "init", "session_id": "fake"})
    turn = 0
    lines = iter(sys.stdin)
    for line in lines:
        message = json.loads(line)
        if message["type"] == "control_request":  # initialize
            emit({"type": "control_response", "response": {"subtype": "success",
                                                           "request_id": message["request_id"], "response": {}}})
            continue
        content = message["message"]["content"]
        turn += 1
        if "trave" in content:
            time.sleep(3600)
        if "morra" in content:
            sys.exit(3)
        if "touch" in content:
            emit({"type": "control_request", "request_id": "perm-1",
                  "request": {"subtype": "can_use_tool", "tool_name": "Bash",
                              "input": {"command": "touch /tmp/x"}}})
            answer = json.loads(next(lines))["response"]["response"]
            result("Arquivo criado." if answer["behavior"] == "allow" else "Ok, não criei.")
            continue
        text = f"eco {turn}: {content}"
        middle = len(text) // 2
        delta(text[:middle])
        delta(text[middle:])
        result(text)


if __name__ == "__main__":
    main()
