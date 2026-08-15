from types import SimpleNamespace

import anthropic
import httpx
import pytest

from agent.agent import (
    ASK_ABOUT_LOCATION_SCHEMA,
    CHECK_INSURABILITY_SCHEMA,
    COMPARE_ADDRESSES_SCHEMA,
    InsurabilityAgent,
)
from tests.fixtures import LOW_RISK_CA_FETCH, PARADISE_CA_FETCH


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        InsurabilityAgent()


def test_check_insurability_schema_matches_signature():
    props = CHECK_INSURABILITY_SCHEMA["input_schema"]["properties"]
    assert "address" in props
    assert "overrides" in props
    assert CHECK_INSURABILITY_SCHEMA["input_schema"]["required"] == ["address"]
    override_props = props["overrides"]["properties"]
    assert "defensible_space_cleared" in override_props
    assert "home_hardened" in override_props


def test_compare_addresses_schema_matches_signature():
    props = COMPARE_ADDRESSES_SCHEMA["input_schema"]["properties"]
    assert "addresses" in props
    assert props["addresses"]["type"] == "array"
    assert COMPARE_ADDRESSES_SCHEMA["input_schema"]["required"] == ["addresses"]


def test_ask_about_location_schema_matches_signature():
    props = ASK_ABOUT_LOCATION_SCHEMA["input_schema"]["properties"]
    assert "address" in props
    assert "question" in props
    assert set(ASK_ABOUT_LOCATION_SCHEMA["input_schema"]["required"]) == {"address", "question"}


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, id_, input_, name="check_insurability"):
        self.id = id_
        self.input = input_
        self.name = name


class _FakeTextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


def test_agent_loop_calls_real_tool_then_returns_text(monkeypatch):
    """Fakes only the Anthropic API call — everything downstream (the tool
    call into _tool_check_insurability, scorer, mireye_client mocking) is
    the real code path, same as tests/test_mcp_server.py."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    import mcp_server.server as server_mod
    from mireye_client.client import GeocodeResult

    class FakeMireyeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            pass

        def geocode(self, address):
            return GeocodeResult(39.75, -121.63, 1.0, "rooftop", address, "geocodio")

        def fetch_with_retry(self, lat, lng, preset, max_retries=1):
            return PARADISE_CA_FETCH

    monkeypatch.setattr(server_mod, "MireyeClient", lambda: FakeMireyeClient())

    responses = iter(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    _FakeToolUseBlock(
                        "tool_1", {"address": "5555 Skyway, Paradise, CA 95969"}
                    )
                ],
            ),
            SimpleNamespace(
                stop_reason="end_turn",
                content=[_FakeTextBlock("This one's likely hard to place.")],
            ),
        ]
    )

    agent = InsurabilityAgent()
    agent._client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_kwargs: next(responses))
    )

    reply = agent.ask("Is this address hard to insure?")
    assert "hard to place" in reply


def test_agent_dispatches_compare_addresses_tool(monkeypatch):
    """The agent must route a compare_addresses tool_use block to
    _tool_compare_addresses, not to check_insurability — this is the
    generalized-dispatch path added alongside the second tool."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    import mcp_server.server as server_mod
    from mireye_client.client import GeocodeResult

    fixtures = {
        "5555 Skyway, Paradise, CA 95969": PARADISE_CA_FETCH,
        "1 Market St, San Francisco, CA 94105": LOW_RISK_CA_FETCH,
    }

    class FakeMireyeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            pass

        def geocode(self, address):
            data = fixtures[address]
            return GeocodeResult(data["lat"], data["lng"], 1.0, "rooftop", address, "geocodio")

        def fetch_with_retry(self, lat, lng, preset, max_retries=1):
            for data in fixtures.values():
                if data["lat"] == lat and data["lng"] == lng:
                    return data
            raise AssertionError("unexpected lat/lng in test")

    monkeypatch.setattr(server_mod, "MireyeClient", lambda: FakeMireyeClient())

    responses = iter(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    _FakeToolUseBlock(
                        "tool_1",
                        {"addresses": list(fixtures.keys())},
                        name="compare_addresses",
                    )
                ],
            ),
            SimpleNamespace(
                stop_reason="end_turn",
                content=[_FakeTextBlock("Paradise is riskier than San Francisco.")],
            ),
        ]
    )

    agent = InsurabilityAgent()
    agent._client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_kwargs: next(responses))
    )

    result = agent.ask_verbose("Compare these two addresses")
    assert result["reply"] == "Paradise is riskier than San Francisco."
    assert len(result["tool_calls"]) == 1
    trace = result["tool_calls"][0]
    assert trace["tool"] == "compare_addresses"
    assert len(trace["results"]) == 2
    assert trace["results"][0]["verdict"] == "likely_hard_to_place"  # ranked most severe first


def test_agent_dispatches_ask_about_location_tool(monkeypatch):
    """The agent must route an ask_about_location tool_use block to
    _tool_ask_about_location, not to the scorer — this is the guard that
    the two grounding paths (deterministic scorer vs. Mireye's /v1/ask)
    stay separate at the dispatch level, not just in the system prompt."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    import mcp_server.server as server_mod

    class FakeMireyeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            pass

        def ask(self, address, question):
            return {
                "answer": "Paradise Unified School District serves this area.",
                "confidence": "medium",
                "citations": [{"source": "OVERTURE_DIVISIONS"}],
                "data_gaps": [],
            }

    monkeypatch.setattr(server_mod, "MireyeClient", lambda: FakeMireyeClient())

    responses = iter(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    _FakeToolUseBlock(
                        "tool_1",
                        {
                            "address": "5555 Skyway, Paradise, CA 95969",
                            "question": "What school district is this in?",
                        },
                        name="ask_about_location",
                    )
                ],
            ),
            SimpleNamespace(
                stop_reason="end_turn",
                content=[_FakeTextBlock("It's in Paradise Unified School District.")],
            ),
        ]
    )

    agent = InsurabilityAgent()
    agent._client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_kwargs: next(responses))
    )

    result = agent.ask_verbose("What school district is this in?")
    assert "Paradise Unified" in result["reply"]
    trace = result["tool_calls"][0]
    assert trace["tool"] == "ask_about_location"
    assert trace["confidence"] == "medium"
    assert "verdict" not in trace


def test_max_tool_turns_cap_prevents_infinite_loop(monkeypatch):
    """A pathological model response that always wants another tool call
    must not loop forever — it should stop at max_tool_turns and degrade
    to a clear message instead of hanging."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    import mcp_server.server as server_mod
    from mireye_client.client import GeocodeResult

    class FakeMireyeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            pass

        def geocode(self, address):
            return GeocodeResult(39.75, -121.63, 1.0, "rooftop", address, "geocodio")

        def fetch_with_retry(self, lat, lng, preset, max_retries=1):
            return PARADISE_CA_FETCH

    monkeypatch.setattr(server_mod, "MireyeClient", lambda: FakeMireyeClient())

    call_count = 0

    def always_tool_use(**_kwargs):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[
                _FakeToolUseBlock(
                    f"tool_{call_count}",
                    {"address": "5555 Skyway, Paradise, CA 95969"},
                )
            ],
        )

    agent = InsurabilityAgent(max_tool_turns=3)
    agent._client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: always_tool_use(**kwargs))
    )

    result = agent.ask_verbose("Is this address hard to insure?")
    assert call_count == 3
    assert "couldn't reach a final answer" in result["reply"]
    assert len(result["tool_calls"]) == 3
    # History rolled back — no dangling half-finished turn left behind.
    assert agent._messages == []


def test_api_error_is_caught_and_returns_graceful_reply(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def raise_timeout(**_kwargs):
        raise anthropic.APITimeoutError(
            httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        )

    agent = InsurabilityAgent()
    agent._client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: raise_timeout(**kwargs))
    )

    result = agent.ask_verbose("Is this address hard to insure?")
    assert "error talking to the model" in result["reply"]
    assert result["tool_calls"] == []
    # History rolled back so the next call isn't sent with two consecutive
    # user-role messages.
    assert agent._messages == []


def test_history_rollback_allows_retry_after_failure(monkeypatch):
    """After an API failure, the next ask() call must succeed normally —
    proves the rollback didn't leave the conversation history corrupted."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    import mcp_server.server as server_mod
    from mireye_client.client import GeocodeResult

    class FakeMireyeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            pass

        def geocode(self, address):
            return GeocodeResult(39.75, -121.63, 1.0, "rooftop", address, "geocodio")

        def fetch_with_retry(self, lat, lng, preset, max_retries=1):
            return PARADISE_CA_FETCH

    monkeypatch.setattr(server_mod, "MireyeClient", lambda: FakeMireyeClient())

    responses = iter(
        [
            "FAIL",
            SimpleNamespace(
                stop_reason="end_turn",
                content=[_FakeTextBlock("All good now.")],
            ),
        ]
    )

    def maybe_fail(**_kwargs):
        r = next(responses)
        if r == "FAIL":
            raise anthropic.APITimeoutError(
                httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            )
        return r

    agent = InsurabilityAgent()
    agent._client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: maybe_fail(**kwargs))
    )

    first = agent.ask_verbose("first message")
    assert "error talking to the model" in first["reply"]

    second = agent.ask_verbose("second message")
    assert second["reply"] == "All good now."
