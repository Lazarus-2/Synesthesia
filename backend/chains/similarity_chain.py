"""
'Similar songs' chain using chord-progression embeddings.
Vault refs:
  - 02-LLM-Architecture/02-RAG-Architecture.md
  - 03-LangChain-Core/03-Retrieval-Chains.md
"""
from __future__ import annotations

from langchain_core.runnables import Runnable
from langchain_openai import OpenAIEmbeddings

from backend.config import get_settings

# Module 3 Lesson 3: replace with FAISS or pgvector
_IN_MEMORY_INDEX: list[tuple[str, list[float]]] = []


def embed_progression(chords: list[str]) -> list[float]:
    """Embed a chord sequence as a vector."""
    s = get_settings()
    emb = OpenAIEmbeddings(model=s.embedding_model, api_key=s.openai_api_key)
    text = " -> ".join(chords)
    return emb.embed_query(text)


def find_similar(chords: list[str], k: int = 5) -> list[dict]:
    """Return top-k similar song titles by cosine similarity."""
    # TODO(Module 3, Lesson 3):
    # 1. Compute query embedding.
    # 2. Replace _IN_MEMORY_INDEX with FAISS index.
    # 3. Return [{title, score, progression}, ...]
    raise NotImplementedError("Fill in during Module 3, Lesson 3")


def build_similarity_chain() -> Runnable:
    """LCEL chain wrapping find_similar for uniform composition."""
    from langchain_core.runnables import RunnableLambda
    return RunnableLambda(lambda x: find_similar(x["chords"], k=x.get("k", 5)))
