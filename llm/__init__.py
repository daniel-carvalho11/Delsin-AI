"""Integração com LLM local. Depende apenas de core.contracts e config."""
from llm.brain import Brain, BrainReply, PendingAction
from llm.claude_code import ClaudeCodeBrain
from llm.conversation import ConversationSkill, actions_of
from llm.ollama import ChatResult, OllamaBrain, OllamaClient, OllamaError

__all__ = [
    "Brain", "BrainReply", "ChatResult", "ClaudeCodeBrain", "ConversationSkill", "OllamaBrain",
    "OllamaClient", "OllamaError", "PendingAction", "actions_of",
]
