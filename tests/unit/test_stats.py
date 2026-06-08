import pytest

from jules.cli.app import _compose_prompt, _estimate_tokens, calculate_cost


def test_estimate_tokens_counts_words() -> None:
    assert _estimate_tokens("") == 0
    assert _estimate_tokens("hello") == 1
    assert _estimate_tokens("hello world from jules") == 4


def test_compose_prompt_includes_personality_and_memory_refs() -> None:
    prompt = _compose_prompt("PERSONA", "hola", ["ep1", "ep2"])
    assert "PERSONA" in prompt
    assert "Relevant past context:\n- ep1\n- ep2" in prompt
    assert "User: hola" in prompt


def test_compose_prompt_without_personality_is_plain_user_message() -> None:
    assert _compose_prompt("", "hola") == "User: hola"


def test_compose_prompt_includes_chat_history() -> None:
    history = [("user", "primer mensaje"), ("jules", "primera respuesta")]
    prompt = _compose_prompt("PERSONA", "segundo mensaje", chat_history=history)
    assert "Conversation so far:" in prompt
    assert "User: primer mensaje" in prompt
    assert "Jules: primera respuesta" in prompt
    assert "User: segundo mensaje" in prompt


def test_compose_prompt_history_limit_keeps_last_n_turns() -> None:
    history = [(f"user", f"msg {i}") for i in range(20)]
    prompt = _compose_prompt("", "final", chat_history=history, history_limit=4)
    assert "msg 0" not in prompt
    assert "msg 16" in prompt
    assert "msg 19" in prompt


def test_compose_prompt_empty_history_omits_conversation_block() -> None:
    prompt = _compose_prompt("PERSONA", "hola", chat_history=[])
    assert "Conversation so far:" not in prompt


def test_calculate_cost_known_model() -> None:
    rates = {"gpt-4o": 0.000005, "claude-sonnet": 0.000003}
    assert calculate_cost(1000, "gpt-4o", rates) == pytest.approx(0.005)
    assert calculate_cost(1000, "claude-sonnet", rates) == pytest.approx(0.003)


def test_calculate_cost_unknown_model_returns_zero() -> None:
    assert calculate_cost(1000, "unknown-model", {"gpt-4o": 0.000005}) == 0.0


def test_calculate_cost_no_rates_returns_zero() -> None:
    assert calculate_cost(500, "gpt-4o", None) == 0.0
    assert calculate_cost(500, "gpt-4o", {}) == 0.0


def test_calculate_cost_zero_tokens_returns_zero() -> None:
    assert calculate_cost(0, "gpt-4o", {"gpt-4o": 0.000005}) == 0.0
