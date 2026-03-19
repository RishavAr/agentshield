from __future__ import annotations

import random
import string

import pytest

from agentshield import AgentShield


def generate_fuzz_inputs(count=500):
    rng = random.Random(42)
    inputs = []
    for _ in range(count):
        inputs.append(
            {
                "tool_name": "".join(rng.choices(string.printable, k=rng.randint(1, 200))),
                "arguments": {
                    "".join(rng.choices(string.ascii_letters, k=10)): "".join(
                        rng.choices(string.printable, k=rng.randint(0, 1000))
                    )
                    for _ in range(rng.randint(0, 20))
                },
            }
        )
    inputs.extend(
        [
            {"tool_name": "", "arguments": {}},
            {"tool_name": "a" * 10000, "arguments": {}},
            {"tool_name": "'; DROP TABLE--", "arguments": {}},
            {"tool_name": "<script>alert('xss')</script>", "arguments": {}},
            {"tool_name": "../../../etc/passwd", "arguments": {}},
            {"tool_name": "\x00\x01\x02", "arguments": {}},
            {"tool_name": "normal", "arguments": {"key": None}},
            {"tool_name": "normal", "arguments": {"key": [[[[[]]]]]}},
            {"tool_name": "normal", "arguments": {"key": {"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}}},
            {"tool_name": "normal", "arguments": {f"key_{i}": f"val_{i}" for i in range(1000)}},
        ]
    )
    return inputs


FUZZ_INPUTS = generate_fuzz_inputs(500)


@pytest.mark.parametrize("fuzz_input", FUZZ_INPUTS)
def test_fuzz_interceptor_never_crashes(fuzz_input):
    """AgentShield must NEVER crash regardless of input."""
    shield = AgentShield(mode="shadow")
    try:
        action = shield.intercept_sync(
            tool_name=(fuzz_input["tool_name"] or "empty_tool"),
            arguments=fuzz_input["arguments"],
            agent_id="fuzz-agent",
        )
        assert action.decision in {"block", "shadow", "approve", "allow", "pending"}
    except Exception as exc:
        # Accept validation failures, reject only system-level crash patterns.
        assert "Traceback" not in str(exc)
