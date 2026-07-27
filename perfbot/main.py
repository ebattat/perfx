import sys
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv
from perfbot.logger import setup_logging
from perfbot.client import Agent

_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="PerfBot — Gemini/Claude agent for GitHub and Jira")
    parser.add_argument(
        "--model", "-m",
        choices=["gemini", "claude"],
        default=None,
        help="Model backend to use: gemini (default) or claude. Overrides PERFBOT_MODEL env var.",
    )
    args = parser.parse_args()

    if args.model:
        os.environ["PERFBOT_MODEL"] = args.model

    model_name = os.environ.get("PERFBOT_MODEL", "gemini").lower()

    print(f"PerfBot Agent (powered by {model_name.capitalize()}). Type 'exit' or Ctrl-C to quit.")
    from perfbot.client import _parse_repos
    repos = _parse_repos()
    if repos:
        print(f"Configured repos: {', '.join(repos)}")
    print()

    agent = Agent()
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Bye!")
            sys.exit(0)

        try:
            response = agent.chat(user_input)
            print(f"\nAgent: {response}\n")
        except Exception as exc:
            print(f"\n[Error] {exc}\n")


if __name__ == "__main__":
    main()
