"""
Agentiva Security Benchmark Suite (Comprehensive)
=================================================
Runs Agentiva against recognized third-party benchmark frameworks when available.

Usage:
  python benchmarks/run_all_benchmarks.py

Optional environment (Garak defaults: subset=6 probes; set full for all probes):
  GARAK_MODE=subset|full
  GARAK_MAX_PROMPTS_PER_PROBE=32
  GARAK_MAX_PROBES=0
  GARAK_MAX_TOTAL_PROMPTS=2500  # 0 or none = unlimited (full mode only)

Frameworks:
1. Agentiva built-in benchmark (OWASP + MITRE ATLAS mapping + real incidents)
2. DeepTeam OWASP LLM Top 10 (Confident AI) — requires OPENAI_API_KEY to execute
3. Garak vulnerability probe library (NVIDIA) — runs prompt probes through Agentiva
4. PyRIT (Microsoft) — optional import + integration stub (targets require configuration)
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import importlib.util
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def module_available(module: str) -> bool:
    """Return True if module is present without importing it."""
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def install_if_missing(module: str, pip_name: Optional[str] = None) -> bool:
    # Do not import to detect availability: some frameworks (e.g. Garak/PyRIT) create
    # directories under HOME on import which can fail in sandboxed environments.
    if module_available(module):
        return True
    name = pip_name or module
    print(f"Installing {name}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", name, "--quiet"])
        return module_available(module)
    except Exception as e:
        print(f"  ⚠️  Could not install {name}: {e}")
        return False


def run_builtin_benchmark() -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("  BENCHMARK 1: Agentiva Built-in")
    print("  OWASP LLM Top 10 + MITRE ATLAS (mapping) + Real Incidents")
    print("=" * 60)
    from benchmarks.run_benchmark import run_benchmark

    return asyncio.run(run_benchmark())


def run_deepteam_benchmark() -> Optional[Dict[str, Any]]:
    print("\n" + "=" * 60)
    print("  BENCHMARK 2: DeepTeam OWASP LLM Top 10 (Confident AI)")
    print("=" * 60)
    if not install_if_missing("deepteam", "deepteam"):
        print("  ⚠️  DeepTeam not available; skipping.")
        return None
    from benchmarks.deepteam_benchmark import run_deepteam_benchmark

    return asyncio.run(run_deepteam_benchmark())


def run_garak_benchmark() -> Optional[Dict[str, Any]]:
    print("\n" + "=" * 60)
    print("  BENCHMARK 3: Garak Vulnerability Probes (NVIDIA)")
    print("=" * 60)
    # Garak import writes XDG dirs; our benchmark sets them to workspace paths.
    if not install_if_missing("garak", "garak"):
        print("  ⚠️  Garak not available; skipping.")
        return None
    from benchmarks.garak_benchmark import run_garak_benchmark

    return asyncio.run(run_garak_benchmark())


def run_pyrit_benchmark() -> Optional[Dict[str, Any]]:
    print("\n" + "=" * 60)
    print("  BENCHMARK 4: PyRIT (Microsoft)")
    print("=" * 60)
    # PyRIT may conflict with pinned deps; this stays optional and should never break the suite.
    ok = install_if_missing("pyrit", "pyrit")
    if not ok:
        print("  ⚠️  PyRIT not available; skipping.")
        return None
    from benchmarks.pyrit_benchmark import run_pyrit_benchmark

    return run_pyrit_benchmark()


def main() -> None:
    print("=" * 60)
    print("  AGENTIVA COMPREHENSIVE SECURITY BENCHMARK")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 60)
    print()
    print("  Running against recognized frameworks (when available):")
    print("  1. Agentiva built-in (OWASP + MITRE ATLAS + Real Incidents)")
    print("  2. DeepTeam OWASP LLM Top 10 (Confident AI)")
    print("  3. Garak Vulnerability Probes (NVIDIA)")
    print("  4. PyRIT Red Teaming (Microsoft)")

    results: Dict[str, Any] = {"timestamp": datetime.now(timezone.utc).isoformat()}

    results["builtin"] = run_builtin_benchmark()
    results["deepteam"] = run_deepteam_benchmark()
    results["garak"] = run_garak_benchmark()
    results["pyrit"] = run_pyrit_benchmark()

    out_dir = os.path.join(_REPO_ROOT, "benchmarks", "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "all_benchmarks_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print("  COMPREHENSIVE BENCHMARK SUMMARY")
    print("=" * 60)

    b = results.get("builtin")
    if b and isinstance(b, dict) and "summary" in b:
        s = b["summary"]
        total = s.get("total", 0) or 0
        passed = s.get("passed", 0) or 0
        pct = (passed / total * 100) if total else 0
        print(f"\n  Built-in:   {passed}/{total} passed ({pct:.0f}%)")

    d = results.get("deepteam") or {}
    if d:
        print(
            f"  DeepTeam:   {d.get('status','unknown')} — categories={len(d.get('deepteam_categories') or [])}, attacks={d.get('deepteam_attack_count', 0)}"
        )
        if d.get("status") == "skipped":
            print("             (Set OPENAI_API_KEY to execute DeepTeam red_team run.)")
    else:
        print("  DeepTeam:   not available")

    g = results.get("garak") or {}
    if g:
        s = g.get("summary") or {}
        mode = g.get("mode", "")
        mode_s = f", mode={mode}" if mode else ""
        print(
            f"  Garak:      {g.get('status','unknown')}{mode_s} — "
            f"prompts={s.get('total_prompts', 0)}, avg_risk={float(s.get('avg_risk', 0.0)):.2f}"
        )
    else:
        print("  Garak:      not available")

    p = results.get("pyrit") or {}
    if p:
        ps = p.get("summary") or {}
        if p.get("status") == "ok" and ps.get("total"):
            print(
                f"  PyRIT:      {p.get('status','unknown')} — "
                f"turns={ps.get('total', 0)} (blocked={ps.get('blocked',0)} "
                f"shadow={ps.get('shadow',0)} allowed={ps.get('allowed',0)} err={ps.get('errors',0)})"
            )
        else:
            print(f"  PyRIT:      {p.get('status','unknown')}")
    else:
        print("  PyRIT:      not available")

    print(f"\n  Full results saved to `benchmarks/results/`")
    print(f"  - all_benchmarks_results.json")
    print(f"  - benchmark_report.md / benchmark_results.json (built-in)")
    print(f"  - deepteam_results.json (if available)")
    print(f"  - garak_results.json (if available)")
    print(f"  - pyrit_results.json (if available)")


if __name__ == "__main__":
    main()

