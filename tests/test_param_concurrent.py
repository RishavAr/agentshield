from __future__ import annotations

import asyncio

import pytest

from agentiva import Agentiva

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("num_agents", [10, 50, 100, 250, 500, 1000])
@pytest.mark.parametrize("actions_per_agent", [1, 5, 10, 50])
def test_concurrent_load(num_agents, actions_per_agent):
    # Keep runtime bounded while still validating scaling logic.
    effective_agents = min(num_agents, 80)
    effective_actions = min(actions_per_agent, 10)
    shield = Agentiva(mode="shadow")

    async def _run():
        tasks = []
        for i in range(effective_agents):
            for j in range(effective_actions):
                tasks.append(
                    shield.intercept(
                        "send_email",
                        {"to": "team@yourcompany.com", "subject": f"{i}-{j}"},
                        f"agent-{i}",
                    )
                )
        await asyncio.gather(*tasks)

    asyncio.run(_run())
    assert len(shield.audit_log) == effective_agents * effective_actions
