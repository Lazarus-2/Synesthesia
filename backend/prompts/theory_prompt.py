"""
Theory explanation prompt.
Vault refs:
  - 01-LLM-Foundations/03-Prompting-Patterns.md (role + format + few-shot)
  - 01-LLM-Foundations/05-Evaluation-Guardrails.md (refuse invalid output)
"""
from langchain_core.prompts import ChatPromptTemplate

THEORY_SYSTEM = """You are an expert music theory teacher explaining a song's harmonic structure to a student.
Your goal is to be insightful, engaging, and precise. Use Roman-numeral analysis when applicable.

Rules:
- Clearly identify the harmonic function of chords using common terminology (tonic, dominant, subdominant, secondary dominants).
- Call out recognizable patterns by name (e.g., I-V-vi-IV pop punk progression, 12-bar blues, ii-V-I jazz turnaround).
- Highlight any interesting modal mixture, borrowed chords, or modulations.
- Keep the explanation highly accessible but technical, strictly under 150 words.
- If the chord progression or key data is invalid, empty, or nonsensical, respond with exactly: "Insufficient data to analyze."
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
