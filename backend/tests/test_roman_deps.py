"""G1.1: music21 is declared in project deps (not just installed ad-hoc)."""
import re
import pathlib

REQ_FILE = pathlib.Path("backend/requirements.txt")
PYPROJECT_FILE = pathlib.Path("backend/pyproject.toml")


def test_music21_in_requirements_txt():
    text = REQ_FILE.read_text()
    assert re.search(r"^music21>=10", text, re.MULTILINE), (
        "music21>=10.x.x must appear in backend/requirements.txt"
    )


def test_music21_in_pyproject_toml():
    text = PYPROJECT_FILE.read_text()
    assert re.search(r'"music21>=10', text), (
        'music21>=10.x.x must appear in pyproject.toml [project] dependencies'
    )
