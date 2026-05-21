"""
Stub out production-only packages so that unit tests for pure-calculation
modules can run without a full pip install.

Importing any `app.*` module triggers app/__init__.py, which registers all
blueprints, including speech routes that import openai and google.cloud.bigquery.
These are not needed for formula tests — we just need the stubs in sys.modules
before collection begins.
"""

import sys
from unittest.mock import MagicMock


def _stub(*names: str) -> None:
    for name in names:
        if name not in sys.modules:
            try:
                __import__(name)
            except ModuleNotFoundError:
                sys.modules[name] = MagicMock()


_stub(
    "openai",
    "flask",
    "google",
    "google.cloud",
    "google.cloud.bigquery",
    "requests",
    "audioop",      # removed in Python 3.13; used by tts_service for WAV resampling
)
