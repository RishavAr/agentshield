"""
Run Agentiva against DeepTeam's OWASP LLM Top 10 (Confident AI).

DeepTeam is a recognized third-party red-teaming framework. This harness:
- Imports DeepTeam's OWASPTop10 framework definition.
- (Optionally) runs DeepTeam's `red_team` pipeline if a compatible OpenAI key is present.
- Always produces a reproducible JSON report indicating what was run vs. skipped.

Usage:
  python benchmarks/deepteam_benchmark.py

Important:
DeepTeam uses `deepeval` and requires `OPENAI_API_KEY` to generate + evaluate attacks.
If `OPENAI_API_KEY` is not set, we still verify that the framework is importable and
report its categories/attack count, but we skip executing the red-team run.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agentiva import __version__ as agentiva_version
from agentiva.interceptor.core import Agentiva


async def run_deepteam_benchmark(attacks_per_category: int = 1) -> Dict[str, Any]:
    try:
        from deepteam.frameworks import OWASPTop10
        from deepteam import red_team
        from deepteam.test_case.test_case import RTTurn

        has_deepteam = True
    except Exception as e:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agentiva_version": agentiva_version,
            "framework": "deepteam",
            "status": "unavailable",
            "error": f"{type(e).__name__}: {e}",
        }

    owasp = OWASPTop10()
    categories: List[str] = list(getattr(owasp, "categories", []) or [])
    attacks = list(getattr(owasp, "attacks", []) or [])

    results: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agentiva_version": agentiva_version,
        "framework": "deepteam",
        "deepteam_framework": "OWASPTop10",
        "status": "ok" if has_deepteam else "unavailable",
        "deepteam_categories": categories,
        "deepteam_attack_count": len(attacks),
        "ran_red_team": False,
        "red_team_error": None,
        "notes": [],
    }

    # DeepTeam requires an OpenAI key through deepeval. If missing, we skip execution.
    if not os.getenv("OPENAI_API_KEY", "").strip():
        results["status"] = "skipped"
        results["notes"].append("DeepTeam is importable, but OPENAI_API_KEY is not set; skipping `red_team()` execution.")
    else:
        shield = Agentiva(mode="shadow")

        async def agentiva_callback(prompt: str, history: Optional[List["RTTurn"]] = None) -> "RTTurn":
            action = await shield.intercept(
                tool_name="process_user_request",
                arguments={"prompt": prompt, "content": prompt},
                agent_id="benchmark-agent",
            )
            decision = str(action.decision)
            risk = float(action.risk_score)
            if decision == "block":
                content = f"[BLOCKED by Agentiva — risk {risk:.2f}]"
            else:
                content = f"[{decision.upper()} — risk {risk:.2f}]"
            # DeepTeam expects RTTurn(role='assistant', content=...).
            return RTTurn(role="assistant", content=content, additional_metadata={"agentiva": action.to_dict()})

        try:
            # DeepTeam will synthesize attacks per category using its simulator/evaluator models.
            report = red_team(
                model_callback=agentiva_callback,
                framework=owasp,
                attacks_per_vulnerability_type=attacks_per_category,
                ignore_errors=True,
                async_mode=True,
                max_concurrent=10,
            )
            results["ran_red_team"] = True
            # Report object can be complex; serialize best-effort.
            try:
                results["deepteam_report"] = report if isinstance(report, (dict, list, str, int, float, bool)) else str(report)
            except Exception:
                results["deepteam_report"] = str(report)
        except Exception as e:
            results["ran_red_team"] = False
            results["red_team_error"] = f"{type(e).__name__}: {e}"
            results["notes"].append(
                "DeepTeam execution requires a working OpenAI-compatible key and network access for deepeval."
            )

    out_dir = os.path.join(_REPO_ROOT, "benchmarks", "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "deepteam_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return results


def _print_summary(results: Dict[str, Any]) -> None:
    print("=" * 70)
    print("  DEEPTEAM BENCHMARK (Confident AI) — OWASP LLM Top 10")
    print(f"  {results.get('timestamp')}")
    print("=" * 70)
    print(f"  Status:     {results.get('status')}")
    print(f"  Categories: {len(results.get('deepteam_categories') or [])}")
    print(f"  Attacks:    {results.get('deepteam_attack_count')}")
    if results.get("ran_red_team"):
        print("  red_team:   executed")
    else:
        if results.get("red_team_error"):
            print(f"  red_team:   error — {results.get('red_team_error')}")
        else:
            print("  red_team:   skipped")
    print("  Saved:      benchmarks/results/deepteam_results.json")


if __name__ == "__main__":
    r = asyncio.run(run_deepteam_benchmark())
    _print_summary(r)
