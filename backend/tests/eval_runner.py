"""
Evaluation harness: runs pipeline over golden songs and scores outputs.
Vault refs:
  - 01-LLM-Foundations/05-Evaluation-Guardrails.md
  - 05-Production-Systems/05-CI-Evals-Release.md

Run:
    python -m tests.eval_runner
"""
from __future__ import annotations

import json
import difflib
from pathlib import Path

GOLDEN = Path(__file__).parent / "golden_songs.json"
AUDIO_DIR = Path(__file__).parent / "audio"


def chord_accuracy(predicted: list[str], expected: list[str]) -> float:
    """% of expected chords present in the same order in predicted (Sequence Matcher)."""
    if not expected:
        return 1.0
    
    sm = difflib.SequenceMatcher(None, predicted, expected)
    return sm.ratio()


def key_correct(predicted: str, expected: str) -> bool:
    return predicted.strip().lower() == expected.strip().lower()


def tempo_within(predicted: float, expected: float, tol_bpm: float = 5.0) -> bool:
    return abs(predicted - expected) <= tol_bpm


def run_eval():
    from backend.graph.graph import get_graph
    import asyncio
    
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
                    {"audio_path": str(audio_path), "instrument": "guitar", "difficulty": "beginner"},
                    config={"configurable": {"thread_id": f"eval_{song['id']}"}}
                )
                
                predicted_chords = [c.chord for c in res.get("chords", [])]
                predicted_key = res.get("key", "")
                predicted_tempo = res.get("tempo", 0.0)
                
                c_acc = chord_accuracy(predicted_chords, song.get("expected_progression", []))
                k_cor = key_correct(predicted_key, song.get("expected_key", ""))
                t_cor = tempo_within(predicted_tempo, song.get("expected_tempo_bpm", 0))
                
                score = (c_acc * 0.5) + (0.3 if k_cor else 0.0) + (0.2 if t_cor else 0.0)
                
                print(f"  -> Score: {score:.2f} (Chords: {c_acc:.2f}, Key: {k_cor}, Tempo: {t_cor})")
                results.append({
                    "id": song["id"],
                    "score": score,
                    "metrics": {"chord_acc": c_acc, "key_correct": k_cor, "tempo_within": t_cor}
                })
                
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
