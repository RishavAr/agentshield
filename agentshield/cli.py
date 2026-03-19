import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from agentshield.api.server import run_server
from agentshield.interceptor.core import AgentShield


def _cmd_serve(args: argparse.Namespace) -> None:
    os.environ["AGENTSHIELD_MODE"] = args.mode
    run_server(host=args.host, port=args.port)


def _cmd_demo(_: argparse.Namespace) -> None:
    from examples.live_demo import run_demo

    asyncio.run(run_demo())


def _cmd_test(args: argparse.Namespace) -> None:
    cmd = [sys.executable, "-m", "pytest"]
    if args.verbose:
        cmd.append("-v")
    if args.path:
        cmd.append(args.path)
    else:
        cmd.append("tests")
    result = subprocess.run(cmd, check=False)
    raise SystemExit(result.returncode)


def _cmd_init(args: argparse.Namespace) -> None:
    source = Path(args.template_policy).resolve()
    destination = Path.cwd() / args.output
    if not source.exists():
        raise SystemExit(f"Template policy not found: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    print(f"Created policy file at {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="agentshield")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Start API server")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--mode", default="shadow", choices=["shadow", "live", "approval"])
    serve.set_defaults(func=_cmd_serve)

    demo = sub.add_parser("demo", help="Run the live demo scenarios")
    demo.set_defaults(func=_cmd_demo)

    test_cmd = sub.add_parser("test", help="Run test suite")
    test_cmd.add_argument("--path", default="tests")
    test_cmd.add_argument("--verbose", action="store_true")
    test_cmd.set_defaults(func=_cmd_test)

    init_cmd = sub.add_parser("init", help="Create default policy file in current directory")
    init_cmd.add_argument("--output", default="policies/default.yaml")
    init_cmd.add_argument("--template-policy", default="policies/default.yaml")
    init_cmd.set_defaults(func=_cmd_init)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
