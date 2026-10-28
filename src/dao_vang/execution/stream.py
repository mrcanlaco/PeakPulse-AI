"""User stream wakes the reconciler; REST remains the restart source of truth."""

from __future__ import annotations

import json
import threading
import time

from websockets.sync.client import connect

from .contracts import utc_now


class UserStream:
    def __init__(self, client, store):
        self.client, self.store = client, store
        self.changed = threading.Event()
        self.stopped = threading.Event()
        self.thread = threading.Thread(
            target=self.run, daemon=True, name="execution-user-stream"
        )

    def start(self):
        self.thread.start()

    def close(self):
        self.stopped.set()
        self.changed.set()
        self.thread.join(timeout=12)

    def run(self):
        while not self.stopped.is_set():
            try:
                key = self.client.listen_key("POST")["listenKey"]
                base = (
                    "wss://demo-fstream.binance.com/ws/"
                    if self.client.config.environment == "demo"
                    else "wss://fstream.binance.com/ws/"
                )
                with connect(base + key, open_timeout=10, close_timeout=2) as socket:
                    kept = time.monotonic()
                    while not self.stopped.is_set():
                        self.store.set(
                            "user_stream",
                            {"healthy": True, "at": utc_now().isoformat()},
                        )
                        if time.monotonic() - kept >= 25 * 60:
                            self.client.listen_key("PUT")
                            kept = time.monotonic()
                        try:
                            event = json.loads(socket.recv(timeout=10))
                        except TimeoutError:
                            continue
                        if event.get("e") == "listenKeyExpired":
                            raise ValueError("listen_key_expired")
                        self.store.record("user_stream_event", event)
                        self.changed.set()
            except Exception as exc:
                # Never log websocket URLs: listenKey is a credential.
                self.store.set(
                    "user_stream",
                    {
                        "healthy": False,
                        "at": utc_now().isoformat(),
                        "error": type(exc).__name__,
                    },
                )
                self.changed.set()
                self.stopped.wait(5)
