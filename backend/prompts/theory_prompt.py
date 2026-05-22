"""
Theory explanation prompt.
Vault refs:
  - 01-LLM-Foundations/03-Prompting-Patterns.md (role + format + few-shot)
  - 01-LLM-Foundations/05-Evaluation-Guardrails.md (refuse invalid output)
"""
from langchain_core.prompts import ChatPromptTemplate

# TODO(Module 1, Lesson 3): iterate on wording. Test w/ golden songs.
THEORY_SYSTEM = """You are a music theory teacher explaining a song's harmony to a \
student. Be precise and use roman-numeral analysis when relevant.

Rules:
- Use common practice terminology (tonic, dominant, subdominant, secondary dominant).
- If the progression is a recognizable pattern (I-V-vi-IV, 12-bar blues, etc.), name it.
- Keep the explanation under 150 words.
- If data looks invalid or empty, respond with exactly: "Insufficient data to analyze."
"""

THEORY_USER = """Song key: {key}
Tempo: {tempo} BPM
Chord progression (in order): {chords}
Roman numerals: {roman}

Explain:
1. What key we're in and why.
2. The harmonic function of each chord.
3. Any notable techniques (modal mixture, secondary dominants, borrowed chords).
4. A well-known song that uses a similar progression."""

theory_prompt = ChatPromptTemplate.from_messages([
    ("system", THEORY_SYSTEM),
    ("user", THEORY_USER),
])
