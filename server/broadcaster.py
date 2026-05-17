"""
broadcaster.py — Fan-out manager for SSE clients.

When a message is sent, publish() puts it into every connected client's queue.
Each /stream connection subscribes, reads from its own queue, and yields events.
"""

import asyncio
from typing import AsyncGenerator


class Broadcaster:
    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, username: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(username, []).append(q)
        return q

    def unsubscribe(self, username: str, q: asyncio.Queue) -> None:
        queues = self._subscribers.get(username, [])
        if q in queues:
            queues.remove(q)

    async def publish_to_users(self, message: dict, usernames: list[str]) -> None:
        """Send message to a specific list of users."""
        for username in usernames:
            for q in self._subscribers.get(username, []):
                await q.put(message)

    async def publish(self, message: dict) -> None:
        """Send message to sender and recipient queues."""
        targets = {message.get("sender"), message.get("recipient")}
        for username in targets:
            for q in self._subscribers.get(username, []):
                await q.put(message)

    def online_users(self) -> list[str]:
        return [u for u, qs in self._subscribers.items() if qs]

    async def stream(self, username: str) -> AsyncGenerator[dict, None]:
        q = self.subscribe(username)
        try:
            while True:
                msg = await q.get()
                yield msg
        finally:
            self.unsubscribe(username, q)


broadcaster = Broadcaster()
