"""Intent catalog loader for the speech agent.

Reads backend/app/data/intents.json once on import and exposes:
  - INTENTS         : the full list (used to render the system prompt)
  - intent_ids()    : list of valid intent ids (used as the JSON-schema enum)
  - prompt_block()  : compact human-readable description block for the system
                      prompt — keeps prompt size predictable.

The catalog is the single source of truth — adding a new intent means editing
intents.json and (if needed) wiring its data fetcher in agent_service.
"""

import json
import os
from typing import Any, Dict, List


_INTENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "intents.json"
)


def _load() -> Dict[str, Any]:
    with open(_INTENTS_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    if not isinstance(catalog.get("intents"), list) or not catalog["intents"]:
        raise ValueError(f"intents.json is malformed: missing 'intents' list")
    seen = set()
    for entry in catalog["intents"]:
        if "id" not in entry or "description" not in entry:
            raise ValueError(f"intents.json entry missing id/description: {entry}")
        if entry["id"] in seen:
            raise ValueError(f"duplicate intent id in intents.json: {entry['id']}")
        seen.add(entry["id"])
    return catalog


_CATALOG: Dict[str, Any] = _load()
INTENTS: List[Dict[str, Any]] = _CATALOG["intents"]


def intent_ids() -> List[str]:
    return [i["id"] for i in INTENTS]


def prompt_block() -> str:
    """Compact list — id then description, one per line. Examples are NOT
    included in the prompt; they're only for the test harness."""
    lines = ["Intents (pick exactly one — the id whose description best fits the question):"]
    for i in INTENTS:
        lines.append(f"- {i['id']}: {i['description']}")
    return "\n".join(lines)
