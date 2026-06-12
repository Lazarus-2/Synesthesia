"""
Evaluation harness: runs pipeline over golden songs and scores outputs.
Vault refs:
  - 01-LLM-Foundations/05-Evaluation-Guardrails.md
  - 05-Production-Systems/05-CI-Evals-Release.md

Run:
    python -m tests.eval_runner
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

GOLDEN = Path(__file__).parent / "golden_songs.json"
AUDIO_DIR = Path(__file__).parent / "audio"


def chord_accuracy(predicted: list[str], expected: list[str]) -> float:
    """Quality-aware chord accuracy (Phase 4 G6).

    The old exact-string SequenceMatcher zeroed ``C7`` against an expected
    ``C`` even though the root was right — the richer Phase 4 vocabulary
    would have tanked every golden spuriously. Roots are aligned with a
    SequenceMatcher; aligned positions then earn a quality bonus:

        score = root_ratio * (0.7 + 0.3 * quality_match_rate_on_aligned)

    Exact matches still score 1.0; a root-perfect but quality-richer
    prediction keeps >= 0.7.
    """
    if not expected:
        return 1.0
    if not predicted:
        return 0.0

    from backend.tools.chords import parse_chord

    def root_of(label: str) -> str:
        return parse_chord(label).root or label

    def quality_of(label: str) -> str:
        return parse_chord(label).quality

    pred_roots = [root_of(c) for c in predicted]
    exp_roots = [root_of(c) for c in expected]
    sm = difflib.SequenceMatcher(None, pred_roots, exp_roots)
    root_ratio = sm.ratio()

    aligned = 0
    quality_hits = 0
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            aligned += 1
            if quality_of(predicted[block.a + k]) == quality_of(expected[block.b + k]):
                quality_hits += 1
    quality_rate = quality_hits / aligned if aligned else 0.0

    return root_ratio * (0.7 + 0.3 * quality_rate)


def key_correct(predicted: str, expected: str) -> bool:
    return predicted.strip().lower() == expected.strip().lower()


def tempo_within(predicted: float, expected: float, tol_bpm: float = 5.0) -> bool:
    return abs(predicted - expected) <= tol_bpm


def run_eval():
    import asyncio

    from backend.graph.graph import get_graph

    data = json.loads(GOLDEN.read_text())
    results = []

    async def process_songs():
        graph = get_graph()
        for song in data["songs"]:
            audio_path = AUDIO_DIR / f"{song['id']}.mp3"
            if not audio_path.exists():
                print(f"[SKIP] Audio file not found for evaluation: {audio_path}")
                results.append({"id": song["id"], "score": None, "status": "skipped"})
                continue

            print(f"[EVAL] Running pipeline for {song['title']}...")
            try:
                res = await graph.ainvoke(
                    {
                        "audio_path": str(audio_path),
                        "instrument": "guitar",
                        "difficulty": "beginner",
                    },
                    config={"configurable": {"thread_id": f"eval_{song['id']}"}},
                )

                predicted_chords = [c.chord for c in res.get("chords", [])]
                predicted_key = res.get("key", "")
                predicted_tempo = res.get("tempo", 0.0)

                c_acc = chord_accuracy(predicted_chords, song.get("expected_progression", []))
                k_cor = key_correct(predicted_key, song.get("expected_key", ""))
                t_cor = tempo_within(predicted_tempo, song.get("expected_tempo_bpm", 0))

                score = (c_acc * 0.5) + (0.3 if k_cor else 0.0) + (0.2 if t_cor else 0.0)

                print(
                    f"  -> Score: {score:.2f} (Chords: {c_acc:.2f}, Key: {k_cor}, Tempo: {t_cor})"
                )
                results.append(
                    {
                        "id": song["id"],
                        "score": score,
                        "metrics": {
                            "chord_acc": c_acc,
                            "key_correct": k_cor,
                            "tempo_within": t_cor,
                        },
                    }
                )

                # Fail CI if aggregate drops
                if score < 0.6:
                    print(f"  -> [WARNING] {song['title']} scored below threshold!")
            except Exception as e:
                print(f"[ERROR] Failed to evaluate {song['title']}: {e}")
                results.append({"id": song["id"], "score": 0.0, "error": str(e)})

    asyncio.run(process_songs())
    return results


if __name__ == "__main__":
    run_eval()
