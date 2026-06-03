"""Prompt registry — load versioned ChatPromptTemplates from YAML.

Why YAML and not Python strings?
--------------------------------
Three reasons:
1. **Versioning.** Each template carries an explicit ``version`` field so
   eval runs (Plan 2 H2 + Plan 3 D5) can pin against a known revision
   instead of "whatever the current import says."
2. **Rollback safety.** Reverting a prompt no longer requires a Python
   diff that risks touching unrelated code.
3. **A/B and swap.** Loading "latest" vs an explicit version lets
   experiments toggle prompts via env config without redeploy.

File layout
-----------
``backend/prompts/templates/<version>/<name>.yaml``

YAML schema::

    name: theory
    version: v1
    description: ...
    metadata: {...}      # arbitrary; not consumed by the loader
    messages:
      - role: system     # role + content for text messages
        content: "..."
      - placeholder: history   # MessagesPlaceholder for chat history etc.
      - role: human
        content: "{message}"
"""
from __future__ import annotations

import logging
import threading
from functools import lru_cache
from pathlib import Path

import yaml
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_load_lock = threading.Lock()


def _resolve_path(name: str, version: str) -> Path:
    if version == "latest":
        # Pick the lexicographically last vN directory. v10 > v9 lexicographically
        # in zero-padded form (v01..v99); we deliberately use this convention.
        candidates = sorted(p for p in _TEMPLATES_DIR.iterdir() if p.is_dir())
        if not candidates:
            raise FileNotFoundError(
                f"No prompt template versions found under {_TEMPLATES_DIR}"
            )
        version_dir = candidates[-1]
    else:
        version_dir = _TEMPLATES_DIR / version
    path = version_dir / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt template not found: {name!r} version={version!r} at {path}"
        )
    return path


def _build_template(raw: dict) -> ChatPromptTemplate:
    """Translate the YAML message list into a LangChain ChatPromptTemplate."""
    # ``from_messages`` accepts a list of either (role, content) tuples or
    # MessagesPlaceholder instances; both shapes are valid.
    messages: list[tuple[str, str] | MessagesPlaceholder] = []
    for entry in raw.get("messages", []):
        if "placeholder" in entry:
            messages.append(MessagesPlaceholder(variable_name=entry["placeholder"]))
            continue
        role = entry.get("role")
        content = entry.get("content", "")
        if role not in ("system", "user", "human", "ai", "assistant"):
            raise ValueError(f"Unsupported role {role!r} in prompt template")
        # LangChain treats "user" and "human" identically; same for "ai" and "assistant".
        normalized = "human" if role == "user" else ("ai" if role == "assistant" else role)
        messages.append((normalized, content))
    return ChatPromptTemplate.from_messages(messages)


@lru_cache(maxsize=64)
def load_template(name: str, version: str = "latest") -> ChatPromptTemplate:
    """Load and cache a ChatPromptTemplate by name + version.

    ``version="latest"`` picks the highest-numbered ``v*`` directory.
    Cached because YAML parsing is non-trivial and templates are immutable
    once loaded; eval code that wants a fresh read can pass an explicit
    version or call :func:`load_template.cache_clear`.
    """
    with _load_lock:
        path = _resolve_path(name, version)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    logger.info(
        "loaded prompt template: name=%s version=%s file=%s",
        raw.get("name", name), raw.get("version", version), path,
    )
    return _build_template(raw)


def get_template_metadata(name: str, version: str = "latest") -> dict:
    """Return the YAML frontmatter (name, version, description, metadata) for tracing."""
    path = _resolve_path(name, version)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        "name": raw.get("name", name),
        "version": raw.get("version", version),
        "description": raw.get("description"),
        "metadata": raw.get("metadata", {}),
    }
