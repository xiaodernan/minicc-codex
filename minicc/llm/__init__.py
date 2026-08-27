"""LLM layer: message types, the OpenAI-compatible provider, envelope fallback."""

from .base import LLMResponse, assistant_msg, system_msg, tool_result_msg, user_msg
from .envelope import EnvelopeParseError, extract_json_object, parse_envelope
from .openai_provider import OpenAICompatibleProvider

__all__ = [
    "LLMResponse",
    "OpenAICompatibleProvider",
    "EnvelopeParseError",
    "assistant_msg",
    "extract_json_object",
    "parse_envelope",
    "system_msg",
    "tool_result_msg",
    "user_msg",
]
