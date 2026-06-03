"""Theory explanation prompt — now loaded from YAML.

Kept as a thin compat shim so existing chain imports
(``from backend.prompts.theory_prompt import theory_prompt``) keep working.
See ``backend/prompts/registry.py`` for the schema and versioning rules.
"""
from backend.prompts.registry import load_template

theory_prompt = load_template("theory")
