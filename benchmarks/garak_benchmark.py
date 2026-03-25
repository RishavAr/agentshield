"""
Run Agentiva against Garak's probe library (NVIDIA).

Two modes:
  subset — fixed list of 6 representative probes (fast, CI-friendly)
  full   — discover all concrete `Probe` subclasses under `garak.probes` (end-to-end Garak coverage)

Garak writes config/cache under XDG; we redirect into `benchmarks/tmp/garak_xdg/`.

Usage:
  python benchmarks/garak_benchmark.py
  python benchmarks/garak_benchmark.py --mode full --max-total-prompts 2500
  GARAK_MODE=full GARAK_MAX_TOTAL_PROMPTS=3000 python benchmarks/run_all_benchmarks.py
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import os
import pkgutil
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Type

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agentiva import __version__ as agentiva_version
from agentiva.interceptor.core import Agentiva


def _configure_garak_xdg() -> Dict[str, str]:
    base = os.path.join(_REPO_ROOT, "benchmarks", "tmp", "garak_xdg")
    cfg = os.path.join(base, "config")
    data = os.path.join(base, "data")
    cache = os.path.join(base, "cache")
    os.makedirs(cfg, exist_ok=True)
    os.makedirs(data, exist_ok=True)
    os.makedirs(cache, exist_ok=True)
    os.environ["XDG_CONFIG_HOME"] = cfg
    os.environ["XDG_DATA_HOME"] = data
    os.environ["XDG_CACHE_HOME"] = cache
    return {"XDG_CONFIG_HOME": cfg, "XDG_DATA_HOME": data, "XDG_CACHE_HOME": cache}


def _safe_prompt_format(prompt: str) -> str:
    return (
        prompt.replace("{generator.name}", "Agent")
        .replace("{generator.system_prompt}", "You are a helpful assistant.")
        .replace("{generator.purpose}", "customer support")
    )


def _discover_all_probe_classes() -> List[Tuple[str, Type[Any]]]:
    """Return (probe_id, class) for every non-abstract Garak Probe under garak.probes."""
    import garak.probes  # noqa: WPS433 — after XDG env

    from garak.probes.base import Probe

    out: List[Tuple[str, Type[Any]]] = []
    for modinfo in pkgutil.walk_packages(garak.probes.__path__, garak.probes.__name__ + "."):
        if modinfo.ispkg:
            continue
        try:
            mod = importlib.import_module(modinfo.name)
        except Exception:
            continue
        short = modinfo.name.rsplit(".", 1)[-1]
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if not (
                issubclass(obj, Probe)
                and obj is not Probe
                and getattr(obj, "__module__", None) == mod.__name__
            ):
                continue
            if inspect.isabstract(obj):
                continue
            probe_id = f"{short}.{name}"
            out.append((probe_id, obj))
    out.sort(key=lambda x: x[0])
    return out


def _subset_probe_specs() -> List[Tuple[str, Any]]:
    from garak.probes.dan import DanInTheWild, Dan_11_0, DUDE
    from garak.probes.encoding import InjectBase64
    from garak.probes.leakreplay import GuardianComplete
    from garak.probes.promptinject import HijackLongPrompt

    return [
        ("dan.Dan_11_0", Dan_11_0),
        ("dan.DUDE", DUDE),
        ("dan.DanInTheWild", DanInTheWild),
        ("encoding.InjectBase64", InjectBase64),
        ("promptinject.HijackLongPrompt", HijackLongPrompt),
        ("leakreplay.GuardianComplete", GuardianComplete),
    ]


async def run_garak_benchmark(
    *,
    mode: Optional[str] = None,
    max_prompts_per_probe: Optional[int] = None,
    max_probes: Optional[int] = None,
    max_total_prompts: Optional[int] = None,
) -> Dict[str, Any]:
    env = _defaults_from_env()
    mode_f = (mode or env["mode"]).strip().lower()
    if mode_f not in ("subset", "full"):
        mode_f = env["mode"]
    mpp = max_prompts_per_probe if max_prompts_per_probe is not None else env["max_prompts_per_probe"]
    mp = max_probes if max_probes is not None else env["max_probes"]
    mtp = max_total_prompts if max_total_prompts is not None else env["max_total_prompts"]

    xdg = _configure_garak_xdg()

    try:
        import garak  # noqa: F401, WPS433
    except Exception as e:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agentiva_version": agentiva_version,
            "framework": "garak",
            "status": "unavailable",
            "error": f"{type(e).__name__}: {e}",
            "xdg": xdg,
        }

    if mode_f == "full":
        probe_specs = _discover_all_probe_classes()
        if mp > 0:
            probe_specs = probe_specs[:mp]
    else:
        probe_specs = _subset_probe_specs()

    shield = Agentiva(mode="shadow")

    results: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agentiva_version": agentiva_version,
        "framework": "garak",
        "status": "ok",
        "mode": mode_f,
        "xdg": xdg,
        "max_prompts_per_probe": mpp,
        "max_probes": mp or None,
        "max_total_prompts": mtp,
        "probe_count_configured": len(probe_specs),
        "probes": [],
        "summary": {
            "total_prompts": 0,
            "blocked": 0,
            "shadow": 0,
            "allowed": 0,
            "avg_risk": 0.0,
            "probes_skipped": 0,
            "probes_no_prompts": 0,
        },
    }

    risk_sum = 0.0
    total_budget = 0

    for probe_id, probe_cls in probe_specs:
        if mtp is not None and total_budget >= mtp:
            break
        try:
            probe = probe_cls()
            prompts = list(getattr(probe, "prompts", []) or [])
        except Exception as e:
            results["summary"]["probes_skipped"] += 1
            results["probes"].append(
                {
                    "probe": probe_id,
                    "status": "error",
                    "error": f"{type(e).__name__}: {e}",
                    "tests": [],
                }
            )
            continue

        if not prompts:
            results["summary"]["probes_no_prompts"] += 1
            results["probes"].append({"probe": probe_id, "status": "no_prompts", "tests": []})
            continue

        tests = []
        cap = mpp
        for p in prompts[:cap]:
            if mtp is not None and total_budget >= mtp:
                break
            prompt = _safe_prompt_format(str(p))
            action = await shield.intercept(
                tool_name="process_user_request",
                arguments={"prompt": prompt, "content": prompt},
                agent_id="benchmark-agent",
            )
            decision = str(action.decision)
            risk = float(action.risk_score)
            risk_sum += risk
            total_budget += 1
            results["summary"]["total_prompts"] += 1
            if decision == "block":
                results["summary"]["blocked"] += 1
            elif decision == "shadow":
                results["summary"]["shadow"] += 1
            else:
                results["summary"]["allowed"] += 1

            tests.append(
                {
                    "probe": probe_id,
                    "decision": decision,
                    "risk_score": risk,
                    "prompt_preview": prompt[:180],
                    "action": action.to_dict(),
                }
            )

        results["probes"].append(
            {
                "probe": probe_id,
                "status": "ok",
                "prompt_count": len(prompts),
                "tested": len(tests),
                "tests": tests,
            }
        )

    total = results["summary"]["total_prompts"]
    results["summary"]["avg_risk"] = (risk_sum / total) if total else 0.0

    out_dir = os.path.join(_REPO_ROOT, "benchmarks", "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "garak_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return results


def _defaults_from_env() -> Dict[str, Any]:
    mode = os.getenv("GARAK_MODE", "subset").strip().lower()
    if mode not in ("subset", "full"):
        mode = "full"
    mpp = int(os.getenv("GARAK_MAX_PROMPTS_PER_PROBE", "32"))
    mp = int(os.getenv("GARAK_MAX_PROBES", "0"))
    mtp_raw = os.getenv("GARAK_MAX_TOTAL_PROMPTS", "2500").strip().lower()
    if mtp_raw in ("", "none", "unlimited"):
        max_total: Optional[int] = None
    else:
        try:
            v = int(mtp_raw)
            max_total = None if v == 0 else v
        except ValueError:
            max_total = 2500
    return {
        "mode": mode,
        "max_prompts_per_probe": max(1, mpp),
        "max_probes": max(0, mp),
        "max_total_prompts": max_total,
    }


def _print_summary(results: Dict[str, Any]) -> None:
    if results.get("status") != "ok":
        print(f"[garak] unavailable: {results.get('error')}")
        return
    s = results["summary"]
    total = s["total_prompts"]
    print("=" * 70)
    print("  GARAK BENCHMARK (NVIDIA) — Agentiva interception")
    print(f"  {results['timestamp']}")
    print("=" * 70)
    print(f"  Mode:          {results.get('mode', 'full')}")
    print(f"  Probes (cfg):  {results.get('probe_count_configured')}")
    print(f"  Total prompts: {total}")
    print(f"  Blocked:       {s['blocked']}")
    print(f"  Shadow:        {s['shadow']}")
    print(f"  Allowed:       {s['allowed']}")
    print(f"  Avg risk:      {s['avg_risk']:.2f}")
    print(f"  Skipped probes:{s.get('probes_skipped', 0)}")
    print(f"  No-prompt probes: {s.get('probes_no_prompts', 0)}")
    print("  Saved:         benchmarks/results/garak_results.json")


if __name__ == "__main__":
    env_defaults = _defaults_from_env()
    parser = argparse.ArgumentParser(description="Garak × Agentiva benchmark")
    parser.add_argument(
        "--mode",
        choices=("subset", "full"),
        default=env_defaults["mode"],
        help="subset=6 probes; full=discover all Garak probes (default: env GARAK_MODE or full)",
    )
    parser.add_argument(
        "--max-prompts-per-probe",
        type=int,
        default=env_defaults["max_prompts_per_probe"],
        metavar="N",
    )
    parser.add_argument(
        "--max-probes",
        type=int,
        default=env_defaults["max_probes"],
        metavar="N",
        help="Cap number of probes in full mode (0 = no cap)",
    )
    parser.add_argument(
        "--max-total-prompts",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N prompts (0 = unlimited). Default: env GARAK_MAX_TOTAL_PROMPTS or 2500",
    )
    args = parser.parse_args()
    mtp_arg = args.max_total_prompts
    if mtp_arg is None:
        mtp_resolved: Optional[int] = env_defaults["max_total_prompts"]
    else:
        mtp_resolved = None if mtp_arg == 0 else mtp_arg
    r = asyncio.run(
        run_garak_benchmark(
            mode=args.mode,
            max_prompts_per_probe=max(1, args.max_prompts_per_probe),
            max_probes=max(0, args.max_probes),
            max_total_prompts=mtp_resolved,
        )
    )
    _print_summary(r)
