"""Imitação mínima do `claude -p --input-format stream-json` para testes (sem rede, sem cota).

Comportamentos por conteúdo da mensagem:
  "touch"  -> responde e devolve um Bash negado em permission_denials
  "trave"  -> nunca responde (testa timeout)
  "morra"  -> encerra o processo (testa recuperação)
  outro    -> "eco <n>: <texto>" (n = número do turno no MESMO processo)
"""
import json
import sys
import time


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    if sys.argv[1:3] == ["auth", "status"]:
        print(json.dumps({"loggedIn": True, "authMethod": "claude.ai"}))
        return
    emit({"type": "system", "subtype": "init", "session_id": "fake"})
    turn = 0
    for line in sys.stdin:
        content = json.loads(line)["message"]["content"]
        turn += 1
        if "trave" in content:
            time.sleep(3600)
        if "morra" in content:
            sys.exit(3)
        denials = []
        if "touch" in content:
            text = "Vou criar o arquivo; aguardo sua aprovação."
            denials = [{"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "touch /tmp/x"}},
                       {"tool_name": "WebFetch", "tool_use_id": "t2", "tool_input": {"url": "https://x"}}]
        else:
            text = f"eco {turn}: {content}"
        emit({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
        emit({"type": "result", "subtype": "success", "is_error": False, "result": text,
              "duration_ms": 5, "total_cost_usd": 0.0, "permission_denials": denials,
              "modelUsage": {"claude-opus-5-5": {}}})


if __name__ == "__main__":
    main()
