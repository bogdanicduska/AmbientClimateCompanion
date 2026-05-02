"""
Per-device pending audio queue.

Holds short audio clips (WAV bytes) that the device should play on its next
proactive poll. Used to decouple ASK answers from the device-side mic→speaker
handoff: the /speech/ask endpoint synthesizes the answer audio and enqueues
it here; /speech/proactive drains the queue first, before evaluating triggers.

In-memory + per-device deque with maxlen=3. Survives only within a single
process (Cloud Run instance). On instance restart the queue is dropped — that
is acceptable because answers are ephemeral; if a user's question is lost in a
cold-start, they re-ask. We deliberately do not persist this in BigQuery to
keep the round-trip latency small.
"""

import threading
from collections import deque
from typing import Any, Dict, Optional

_lock = threading.Lock()
_queues: Dict[str, "deque[Dict[str, Any]]"] = {}
_MAX_PER_DEVICE = 3


def enqueue(device_id: str, item: Dict[str, Any]) -> None:
    with _lock:
        q = _queues.get(device_id)
        if q is None:
            q = deque(maxlen=_MAX_PER_DEVICE)
            _queues[device_id] = q
        q.append(item)


def dequeue(device_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        q = _queues.get(device_id)
        if not q:
            return None
        try:
            return q.popleft()
        except IndexError:
            return None


def peek_size(device_id: str) -> int:
    with _lock:
        q = _queues.get(device_id)
        return len(q) if q else 0
