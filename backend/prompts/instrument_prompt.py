"""Instrument guide prompt — now loaded from YAML.

Compat shim; see ``backend/prompts/registry.py``.
"""
from backend.prompts.registry import load_template

instrument_prompt = load_template("instrument")
