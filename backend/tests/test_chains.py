"""Chain tests (Plan 3 D2).

Cover the chains that are pure-Python (similarity, llm_factory routing,
prompt formatting). LLM-invoking paths are mocked so tests stay hermetic.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# similarity_chain (no LLM)
# ---------------------------------------------------------------------------


class TestSimilarity:
    def test_embed_progression_is_normalized(self):
        from backend.chains.similarity_chain import embed_progression

        vec = embed_progression(["C", "G", "Am", "F"])
        norm = sum(v * v for v in vec) ** 0.5
        assert vec is not None and len(vec) == 12
        assert 0.99 <= norm <= 1.01, f"vector should be L2-normalized; got {norm}"

    def test_embed_empty_returns_zero_vector(self):
        from backend.chains.similarity_chain import embed_progression

        assert embed_progression([]) == [0.0] * 12

    def test_embed_v2_is_36_dim(self):
        from backend.chains.similarity_chain import embed_progression_v2

        vec = embed_progression_v2(["C", "G", "Am", "F"])
        assert len(vec) == 36, "v2 = 12 pitch + 12 transitions + 12 qualities"

    def test_embed_v2_key_invariance(self):
        """I-V-vi-IV in C and the same progression in G should embed nearly identically."""
        from backend.chains.similarity_chain import embed_progression_v2

        c_vec = embed_progression_v2(["C", "G", "Am", "F"], key="C major")
        g_vec = embed_progression_v2(["G", "D", "Em", "C"], key="G major")
        # Cosine similarity
        dot = sum(a * b for a, b in zip(c_vec, g_vec))
        n_c = sum(a * a for a in c_vec) ** 0.5
        n_g = sum(a * a for a in g_vec) ** 0.5
        sim = dot / (n_c * n_g)
        assert sim > 0.99, f"key-rotated progressions should match closely; got {sim}"

    def test_find_similar_returns_top_k(self):
        from backend.chains.similarity_chain import find_similar

        results = find_similar(["C", "G", "Am", "F"], k=2)
        assert len(results) == 2
        for r in results:
            assert {"title", "artist", "progression", "score"} <= r.keys()
        # Scores should be sorted descending
        assert results[0]["score"] >= results[1]["score"]

    def test_find_similar_handles_unknown_chord(self):
        from backend.chains.similarity_chain import find_similar

        # ``N.C.`` and empty strings shouldn't crash
        results = find_similar(["N.C.", "", "Cmaj7"], k=3)
        assert len(results) <= 3


# ---------------------------------------------------------------------------
# llm_factory (provider routing, no real API calls)
# ---------------------------------------------------------------------------


class TestLLMFactory:
    def test_unknown_provider_raises(self):
        from backend.chains.llm_factory import _build_provider_llm

        with pytest.raises(ValueError, match="Unknown LLM provider"):
            _build_provider_llm("not-a-provider", model="x", temperature=0.0, api_key="x")

    def test_openai_requires_key(self):
        from backend.chains.llm_factory import _build_provider_llm

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            _build_provider_llm("openai", model="gpt-x", temperature=0.0, api_key="")

    def test_fallback_observer_wraps_runnable(self):
        from langchain_core.runnables import RunnableLambda

        from backend.chains.llm_factory import (
            _wrap_with_observable_fallback,
            get_fallback_stats,
            reset_fallback_stats,
        )

        # Primary always fails, fallback always succeeds.
        primary = RunnableLambda(lambda _x: (_ for _ in ()).throw(RuntimeError("boom")))
        fallback = RunnableLambda(lambda x: f"recovered:{x}")
        reset_fallback_stats()
        wrapped = _wrap_with_observable_fallback(
            primary,
            fallback,
            primary_name="alpha",
            fallback_name="beta",
        )
        assert wrapped.invoke("test") == "recovered:test"
        assert get_fallback_stats() == {"alpha->beta": 1}

    def test_build_chat_llm_provider_override_uses_given_provider(self, monkeypatch):
        """Bug-2 fix: build_chat_llm(provider='anthropic', model='claude-x') must
        call _build_provider_llm with provider='anthropic', not the global
        LLM_PROVIDER setting.  Patch _build_provider_llm to capture the call."""
        from backend.chains import llm_factory

        captured: dict = {}

        def _fake_build_provider_llm(provider, model, temperature, api_key=""):
            captured["provider"] = provider
            captured["model"] = model
            # Return a minimal mock that won't blow up when bind_tools is called.
            from unittest.mock import MagicMock
            m = MagicMock()
            m.bind_tools = lambda tools, **kw: m
            return m

        monkeypatch.setattr(llm_factory, "_build_provider_llm", _fake_build_provider_llm)

        llm_factory.build_chat_llm(temperature=0.7, provider="anthropic", model="claude-x")
        assert captured.get("provider") == "anthropic", (
            f"Expected provider='anthropic', got {captured.get('provider')!r}"
        )
        assert captured.get("model") == "claude-x"

    def test_build_chat_llm_no_override_uses_global_provider(self, monkeypatch):
        """Bug-2 backward-compat: when provider/model are omitted, the global
        LLM_PROVIDER / MODEL_NAME settings are used (unchanged behavior).
        We call _resolve_primary_and_fallback directly (no network) and assert
        the resolved provider matches the global setting."""
        import os

        from backend.chains import llm_factory

        # Force the global provider to a known value via env var.
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        # Clear the settings cache so our env var takes effect.
        from backend.config import get_settings as _gs
        _gs.cache_clear()

        captured: dict = {}
        original_build_provider = llm_factory._build_provider_llm

        def _fake_build_provider_llm(provider, model, temperature, api_key=""):
            captured["provider"] = provider
            from unittest.mock import MagicMock
            m = MagicMock()
            m.bind_tools = lambda tools, **kw: m
            return m

        monkeypatch.setattr(llm_factory, "_build_provider_llm", _fake_build_provider_llm)

        try:
            llm_factory.build_chat_llm(temperature=0.7)
        finally:
            _gs.cache_clear()

        assert captured.get("provider") == "ollama", (
            f"Expected provider='ollama' (global default), got {captured.get('provider')!r}"
        )

    def test_build_aura_agent_passes_effective_chat_provider_to_build_chat_llm(self, monkeypatch):
        """Bug-2 fix: build_aura_agent must forward effective_chat_provider /
        effective_chat_model to build_chat_llm, so CHAT_PROVIDER/CHAT_MODEL env
        vars actually affect the chat path."""
        from backend.chains import aura_agent

        captured: dict = {}

        def _fake_build_chat_llm(temperature=0.7, tools=None, provider=None, model=None):
            captured["provider"] = provider
            captured["model"] = model
            from unittest.mock import MagicMock
            return MagicMock()

        fake_settings = type("S", (), {
            "creative_temperature": 0.7,
            "effective_chat_provider": "anthropic",
            "effective_chat_model": "claude-sentinel",
            "chat_max_tool_iters": 4,
            "chat_tools_enabled": True,
        })()

        monkeypatch.setattr(aura_agent, "build_chat_llm", _fake_build_chat_llm)
        monkeypatch.setattr(aura_agent, "get_settings", lambda: fake_settings)

        try:
            aura_agent.build_aura_agent(tools=[], tutor_mode=False)
        except Exception:
            pass  # agent construction may fail on the mock model — we only care about the call args

        assert captured.get("provider") == "anthropic", (
            f"Expected build_chat_llm called with provider='anthropic'; got {captured!r}"
        )
        assert captured.get("model") == "claude-sentinel"


# ---------------------------------------------------------------------------
# chat_chain context injection (no LLM)
# ---------------------------------------------------------------------------


class TestChatContext:
    def test_context_renders_with_key_tempo_progression(self):
        from backend.chains.chat_chain import _format_analysis_context

        analysis = {
            "title": "Synthetic",
            "key": "C major",
            "tempo": 120,
            "chords": [{"chord": "C"}, {"chord": "G"}, {"chord": "Am"}, {"chord": "F"}],
            "roman": {"progression": ["I", "V", "vi", "IV"]},
        }
        ctx = _format_analysis_context(analysis)
        assert ctx is not None
        assert "C major" in ctx
        assert "120" in ctx
        assert "I → V → vi → IV" in ctx
        assert "Synthetic" in ctx

    def test_context_none_when_analysis_missing(self):
        from backend.chains.chat_chain import _format_analysis_context

        # Empty dict is falsy and treated as "no analysis" — matches None case.
        assert _format_analysis_context(None) is None
        assert _format_analysis_context({}) is None

    def test_context_uses_unknown_key_when_only_partial_data(self):
        from backend.chains.chat_chain import _format_analysis_context

        # A populated dict missing ``key`` should still render with a fallback.
        ctx = _format_analysis_context({"tempo": 100})
        assert ctx is not None
        assert "Unknown" in ctx

    def test_build_history_prepends_system_when_analysis_given(self):
        from langchain_core.messages import SystemMessage

        from backend.chains.chat_chain import _build_history

        msgs = _build_history(
            [{"role": "user", "content": "hi"}],
            analysis={"key": "A minor", "tempo": 90, "chords": [{"chord": "Am"}]},
        )
        assert isinstance(msgs[0], SystemMessage)
        assert "A minor" in msgs[0].content

    def test_get_chat_response_falls_back_on_llm_error(self):
        from backend.chains import chat_chain

        # Force build_llm to raise so the chain hits its except branch.
        with patch.object(chat_chain, "build_llm", side_effect=RuntimeError("no api key")):
            reply = chat_chain.get_chat_response("test", [])
        assert "AURA Transmission Offline" in reply


# ---------------------------------------------------------------------------
# instrument_chain auto-capo helper
# ---------------------------------------------------------------------------


class TestAutoCapo:
    def test_open_chords_pick_no_capo_or_better(self):
        """C-G-Am-F: open shapes are fine but capo 5 turns F→C so might rank higher."""
        from backend.chains.instrument_chain import _auto_capo

        result = _auto_capo(["C", "G", "Am", "F"])
        # Either the function says no capo or a fret that yields easier shapes.
        assert result is None or 1 <= result <= 7

    def test_tricky_keys_picks_capo_2(self):
        from backend.chains.instrument_chain import _auto_capo

        # F#m-D-A-E with capo 2 -> Em-C-G-D (all open).
        assert _auto_capo(["F#m", "D", "A", "E"]) == 2

    def test_empty_list_returns_none(self):
        from backend.chains.instrument_chain import _auto_capo

        assert _auto_capo([]) is None


# ---------------------------------------------------------------------------
# theory_chain TheoryExplanation flattener
# ---------------------------------------------------------------------------


class TestTheoryFlattener:
    def test_required_only(self):
        from backend.chains.theory_chain import TheoryExplanation, _flatten

        te = TheoryExplanation(
            key_summary="The song is in C major.",
            function_explanation="C tonic, G dominant.",
        )
        out = _flatten(te)
        assert "C major" in out
        assert "G dominant" in out

    def test_full_render_includes_pattern_and_similar(self):
        from backend.chains.theory_chain import TheoryExplanation, _flatten

        te = TheoryExplanation(
            key_summary="Key: G.",
            function_explanation="Tonic, dominant, …",
            pattern_name="I-V-vi-IV",
            notable_techniques=["modal mixture"],
            similar_song="Let It Be — Beatles",
        )
        out = _flatten(te)
        assert "**Pattern:**" in out
        assert "modal mixture" in out
        assert "Let It Be" in out


# ---------------------------------------------------------------------------
# llm_factory provider-agnostic binding (Group 1)
# ---------------------------------------------------------------------------


class TestBindBeforeFallback:
    def test_transform_applied_to_each_model_then_composed(self):
        """transform must hit BOTH primary and fallback bare models, and the
        result must still be a fallback-routing Runnable (primary fails ->
        fallback rescues)."""
        from langchain_core.runnables import RunnableLambda

        from backend.chains.llm_factory import (
            _bind_before_fallback,
            reset_fallback_stats,
        )

        seen: list[str] = []

        def _make_primary():
            return RunnableLambda(
                lambda _x: (_ for _ in ()).throw(RuntimeError("primary down"))
            )

        def _make_fallback():
            return RunnableLambda(lambda x: f"fb:{x}")

        def _transform(model):
            # Tag every model the transform touches so we can assert both ran.
            seen.append(id(model))
            return model | RunnableLambda(lambda v: v)

        reset_fallback_stats()
        runnable = _bind_before_fallback(
            _make_primary,
            _make_fallback,
            transform=_transform,
        )
        # transform ran on primary AND fallback => two calls on two DISTINCT objects.
        assert len(seen) == 2
        assert seen[0] != seen[1]
        # Fallback routing still works.
        assert runnable.invoke("hi") == "fb:hi"

    def test_no_fallback_returns_transformed_primary_only(self):
        from langchain_core.runnables import RunnableLambda

        from backend.chains.llm_factory import _bind_before_fallback

        calls: list[int] = []

        def _transform(model):
            calls.append(1)
            return model

        runnable = _bind_before_fallback(
            lambda: RunnableLambda(lambda x: f"ok:{x}"),
            None,  # no fallback configured
            transform=_transform,
        )
        assert len(calls) == 1  # only the primary was transformed
        assert runnable.invoke("z") == "ok:z"


class TestPublicBinders:
    """build_chat_llm / build_structured_llm route through _bind_before_fallback
    so bind_tools and with_structured_output survive a fallback chain — even
    when the primary and fallback are DIFFERENT providers (the live P1 bug)."""

    def test_build_structured_llm_survives_cross_provider_fallback(self):
        from unittest.mock import MagicMock

        from langchain_core.runnables import RunnableLambda
        from pydantic import BaseModel

        from backend.chains import llm_factory

        class _Schema(BaseModel):
            answer: str

        structured_calls: list[object] = []

        def _fake_model(tag: str):
            # A stand-in bare model: only the binding methods chains use.
            m = MagicMock(name=tag)

            def _wso(schema):
                structured_calls.append(schema)
                return RunnableLambda(lambda _x: _Schema(answer=tag))

            m.with_structured_output.side_effect = _wso
            return m

        # provider != fallback_provider => exercises the cross-provider path.
        settings = MagicMock()
        settings.llm_provider = "openai"
        settings.llm_fallback_provider = "anthropic"
        settings.llm_fallback_model = "claude-x"
        settings.model_name = "gpt-x"

        with (
            patch.object(llm_factory, "get_settings", return_value=settings),
            patch.object(
                llm_factory,
                "_build_provider_llm",
                side_effect=lambda provider, **kw: _fake_model(provider),
            ),
        ):
            runnable = llm_factory.build_structured_llm(_Schema, temperature=0.2)

        # with_structured_output was applied to BOTH bare models.
        assert structured_calls == [_Schema, _Schema]
        # Primary path returns the structured object (no AttributeError).
        assert runnable.invoke("q").answer == "openai"

    def test_build_chat_llm_binds_tools_on_bare_model(self):
        from unittest.mock import MagicMock

        from langchain_core.runnables import RunnableLambda

        from backend.chains import llm_factory

        bound_tools: list[object] = []

        def _fake_model(tag: str):
            m = MagicMock(name=tag)

            def _bt(tools):
                bound_tools.append(tools)
                return RunnableLambda(lambda x: f"{tag}:{x}")

            m.bind_tools.side_effect = _bt
            return m

        settings = MagicMock()
        settings.llm_provider = "openai"
        settings.llm_fallback_provider = ""  # no fallback
        settings.llm_fallback_model = ""
        settings.model_name = "gpt-x"

        sentinel_tools = [object()]
        with (
            patch.object(llm_factory, "get_settings", return_value=settings),
            patch.object(
                llm_factory,
                "_build_provider_llm",
                side_effect=lambda provider, **kw: _fake_model(provider),
            ),
        ):
            runnable = llm_factory.build_chat_llm(temperature=0.7, tools=sentinel_tools)

        assert bound_tools == [sentinel_tools]
        assert runnable.invoke("hi") == "openai:hi"

    def test_build_chat_llm_without_tools_returns_plain_model(self):
        from unittest.mock import MagicMock

        from langchain_core.runnables import RunnableLambda

        from backend.chains import llm_factory

        def _fake_model(tag: str):
            m = MagicMock(name=tag)
            # If bind_tools is wrongly called, the test would see it.
            m.bind_tools.side_effect = AssertionError("bind_tools should not run")
            return m

        settings = MagicMock()
        settings.llm_provider = "openai"
        settings.llm_fallback_provider = ""
        settings.llm_fallback_model = ""
        settings.model_name = "gpt-x"

        with (
            patch.object(llm_factory, "get_settings", return_value=settings),
            patch.object(
                llm_factory,
                "_build_provider_llm",
                side_effect=lambda provider, **kw: RunnableLambda(lambda x: f"plain:{x}"),
            ),
        ):
            runnable = llm_factory.build_chat_llm(temperature=0.7)

        assert runnable.invoke("hi") == "plain:hi"


class TestTheoryChainFallbackSafe:
    """Regression: build_theory_chain must build cleanly when a DIFFERENT
    fallback provider is configured. Before the fix it raised AttributeError
    because .with_structured_output was called on RunnableWithFallbacks."""

    def test_build_theory_chain_with_cross_provider_fallback(self):
        from langchain_core.runnables import RunnableLambda

        from backend.chains import theory_chain

        captured: list[object] = []

        def _fake_structured(schema, temperature=0.2):
            captured.append(schema)
            return RunnableLambda(lambda _x: _x)

        # If theory_chain still imports build_llm and calls
        # .with_structured_output itself, this patch wouldn't be consulted and
        # captured would stay empty.
        with patch.object(
            theory_chain, "build_structured_llm", side_effect=_fake_structured
        ):
            chain = theory_chain.build_theory_chain()

        assert chain is not None
        # Schema passed is the chain-local TheoryExplanation.
        assert captured == [theory_chain.TheoryExplanation]


class TestInstrumentChainFallbackSafe:
    """Regression: build_instrument_chain must build cleanly with a different
    fallback provider configured (was AttributeError on
    RunnableWithFallbacks.with_structured_output)."""

    def test_build_instrument_chain_with_cross_provider_fallback(self):
        from langchain_core.runnables import RunnableLambda

        from backend.chains import instrument_chain

        captured: list[object] = []

        def _fake_structured(schema, temperature=0.2):
            captured.append(schema)
            return RunnableLambda(lambda _x: _x)

        with patch.object(
            instrument_chain, "build_structured_llm", side_effect=_fake_structured
        ):
            chain = instrument_chain.build_instrument_chain()

        assert chain is not None
        assert captured == [instrument_chain.LLMInstrumentTips]


class TestBindingsSurviveFallback:
    """Spec (e): with a primary + DIFFERENT fallback provider, both bind_tools
    and with_structured_output must survive .with_fallbacks() and remain active
    on the fallback path when the primary fails."""

    def _settings(self):
        from unittest.mock import MagicMock

        s = MagicMock()
        s.llm_provider = "openai"
        s.llm_fallback_provider = "anthropic"
        s.llm_fallback_model = "claude-x"
        s.model_name = "gpt-x"
        return s

    def test_structured_output_active_on_fallback_path(self):
        from unittest.mock import MagicMock

        from langchain_core.runnables import RunnableLambda
        from pydantic import BaseModel

        from backend.chains import llm_factory

        class _Out(BaseModel):
            who: str

        def _fake_model(provider: str):
            m = MagicMock(name=provider)
            if provider == "openai":
                # Primary's structured runnable explodes -> fallback rescues.
                m.with_structured_output.return_value = RunnableLambda(
                    lambda _x: (_ for _ in ()).throw(RuntimeError("primary 500"))
                )
            else:
                m.with_structured_output.return_value = RunnableLambda(
                    lambda _x: _Out(who=provider)
                )
            return m

        llm_factory.reset_fallback_stats()
        with (
            patch.object(llm_factory, "get_settings", return_value=self._settings()),
            patch.object(
                llm_factory,
                "_build_provider_llm",
                side_effect=lambda provider, **kw: _fake_model(provider),
            ),
        ):
            runnable = llm_factory.build_structured_llm(_Out, temperature=0.2)
            result = runnable.invoke("prompt")

        # Fallback produced a structured object -> binding survived composition.
        assert result.who == "anthropic"
        # Observable-fallback logging/counter still fired (preserved behavior).
        assert llm_factory.get_fallback_stats() == {"openai->anthropic": 1}

    def test_bind_tools_active_on_fallback_path(self):
        from unittest.mock import MagicMock

        from langchain_core.runnables import RunnableLambda

        from backend.chains import llm_factory

        tool_bindings: dict[str, object] = {}

        def _fake_model(provider: str):
            m = MagicMock(name=provider)

            def _bt(tools, _p=provider):
                tool_bindings[_p] = tools
                if _p == "openai":
                    return RunnableLambda(
                        lambda _x: (_ for _ in ()).throw(RuntimeError("primary down"))
                    )
                return RunnableLambda(lambda x: f"{_p}-tooled:{x}")

            m.bind_tools.side_effect = _bt
            return m

        sentinel_tools = [object()]
        llm_factory.reset_fallback_stats()
        with (
            patch.object(llm_factory, "get_settings", return_value=self._settings()),
            patch.object(
                llm_factory,
                "_build_provider_llm",
                side_effect=lambda provider, **kw: _fake_model(provider),
            ),
        ):
            runnable = llm_factory.build_chat_llm(temperature=0.7, tools=sentinel_tools)
            result = runnable.invoke("hi")

        # bind_tools ran on BOTH providers with the same tool list.
        assert tool_bindings == {"openai": sentinel_tools, "anthropic": sentinel_tools}
        # Fallback (tool-aware) produced the answer.
        assert result == "anthropic-tooled:hi"
        assert llm_factory.get_fallback_stats() == {"openai->anthropic": 1}
