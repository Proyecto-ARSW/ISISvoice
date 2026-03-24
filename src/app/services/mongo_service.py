from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.settings import settings


class MongoConversationStore:
    def __init__(self) -> None:
        self._client: AsyncIOMotorClient | None = None
        self._db = None

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    async def connect(self) -> None:
        if self._client is not None:
            return
        common_options = {
            "serverSelectionTimeoutMS": settings.mongo_server_selection_timeout_ms,
            "connectTimeoutMS": settings.mongo_connect_timeout_ms,
            "socketTimeoutMS": settings.mongo_socket_timeout_ms,
            "retryWrites": True,
        }
        if settings.mongodb_uri.startswith("mongodb+srv://"):
            self._client = AsyncIOMotorClient(
                settings.mongodb_uri,
                tls=True,
                tlsCAFile=certifi.where(),
                **common_options,
            )
        else:
            self._client = AsyncIOMotorClient(settings.mongodb_uri, **common_options)
        self._db = self._client[settings.mongodb_db]

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None

    async def _sessions(self):
        await self.connect()
        return self._db.sessions

    async def _messages(self):
        await self.connect()
        return self._db.messages

    async def ensure_session(self, session_id: str) -> None:
        sessions = await self._sessions()
        now = self._now()
        await sessions.update_one(
            {"_id": session_id},
            {
                "$setOnInsert": {
                    "_id": session_id,
                    "created_at": now,
                    "engine": "deterministic-rules",
                },
                "$set": {"updated_at": now},
            },
            upsert=True,
        )

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        messages = await self._messages()
        sessions = await self._sessions()
        now = self._now()

        await messages.insert_one(
            {
                "session_id": session_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "created_at": now,
            }
        )
        await sessions.update_one({"_id": session_id}, {"$set": {"updated_at": now}})

    async def get_history(self, session_id: str, limit: int | None = None) -> list[dict[str, str]]:
        messages = await self._messages()
        max_items = limit or settings.max_history_messages

        cursor = (
            messages.find({"session_id": session_id}, {"role": 1, "content": 1, "_id": 0})
            .sort("created_at", 1)
            .limit(max_items)
        )
        history = []
        async for item in cursor:
            history.append({"role": item["role"], "content": item["content"]})
        return history

    async def save_structured_data(self, session_id: str, data: dict[str, Any]) -> None:
        sessions = await self._sessions()
        await sessions.update_one(
            {"_id": session_id},
            {
                "$set": {
                    "structured_data": data,
                    "updated_at": self._now(),
                }
            },
            upsert=True,
        )

    async def finalize_session(self, session_id: str, final_record: dict[str, Any]) -> None:
        sessions = await self._sessions()
        now = self._now()
        await sessions.update_one(
            {"_id": session_id},
            {
                "$set": {
                    "final_clinical_history": final_record,
                    "session_status": "completed",
                    "finalized_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

    async def health(self) -> dict[str, Any]:
        try:
            await self.connect()
            await self._db.command("ping")
            return {"status": "up"}
        except Exception as exc:
            return {"status": "down", "error": str(exc)}


mongo_store = MongoConversationStore()
