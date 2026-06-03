"""AURA chat prompt — now loaded from YAML.

Compat shim; see ``backend/prompts/registry.py``.
"""

from __future__ import annotations

from backend.prompts.registry import load_template

chat_prompt = load_template("chat")

# Legacy alias kept for any code that imported the system-string directly.
aura_system_prompt = (
    chat_prompt.messages[0].prompt.template
    if chat_prompt.messages and hasattr(chat_prompt.messages[0], "prompt")
    else ""
)
