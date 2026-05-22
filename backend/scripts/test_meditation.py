"""Quick local check for the meditation agent — no running server needed.

Calls the agent directly and prints the generated session JSON, so you can see
the LLM-written script and its timings without deploying. If generation fails
(no key / API error) it prints the static-catalog fallback instead.

Run from backend/:
    python -m scripts.test_meditation            # default theme: calm
    python -m scripts.test_meditation sleep      # a specific theme
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")   # avoid cp1252 crashes on Windows
except Exception:
    pass

from app.services.meditation_agent import get_meditation, _THEMES


def main():
    theme  = sys.argv[1] if len(sys.argv) > 1 else "calm"
    config = {"OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "")}

    if not config["OPENAI_API_KEY"]:
        print("WARNING: OPENAI_API_KEY not set — expect the static fallback.\n")

    print("Available themes: {}".format(", ".join(_THEMES.keys())))
    print("Generating '{}' (fresh)...\n".format(theme))

    session = get_meditation(theme, config, fresh=True)
    if session is None:
        print("Unknown theme: {}".format(theme))
        sys.exit(1)

    print(json.dumps(session, indent=2, ensure_ascii=False))
    print("\nsource={}  prompts={}  duration={}s".format(
        session.get("source", "static"),
        len(session.get("prompts", [])),
        session.get("duration_s"),
    ))


if __name__ == "__main__":
    main()
