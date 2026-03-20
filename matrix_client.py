import asyncio
import logging
import mimetypes
import os
from typing import Callable, Optional

from nio import (
    AsyncClient, MatrixRoom, RoomMessageText,
    RoomMessageImage, RoomMessageAudio, RoomMessageVideo, RoomMessageFile,
    LoginResponse, UploadResponse,
    InviteEvent
)

import database as db

logger = logging.getLogger(__name__)


class MatrixBot:
    def __init__(self):
        self.homeserver = os.getenv("MATRIX_HOMESERVER")
        self.user = os.getenv("MATRIX_USER")
        self.password = os.getenv("MATRIX_PASSWORD")
        self.client: Optional[AsyncClient] = None
        self._message_callback: Optional[Callable] = None
        self._sync_task: Optional[asyncio.Task] = None
        self._ready = False

    async def start(self, message_callback: Callable):
        if not all([self.homeserver, self.user, self.password]):
            raise EnvironmentError(
                "MATRIX_HOMESERVER, MATRIX_USER, MATRIX_PASSWORD must be set in .env"
            )

        self._message_callback = message_callback
        self.client = AsyncClient(self.homeserver, self.user)
        self.client.add_event_callback(self._on_invite, InviteEvent)

        for event_type in (
            RoomMessageText, RoomMessageImage,
            RoomMessageAudio, RoomMessageVideo, RoomMessageFile
        ):
            self.client.add_event_callback(self._on_message, event_type)

        response = await self.client.login(self.password)
        if not isinstance(response, LoginResponse):
            raise ConnectionError(f"matrix: connection error: {response}")

        logger.info(f"matrix: logged in as {self.user}")

        await self.client.sync(timeout=0, full_state=True)
        for room_id in list(self.client.invited_rooms.keys()):
            await self.client.join(room_id)
            logger.info(f"matrix: accepted invite {room_id}")

        await self.client.sync(timeout=0, full_state=True)

        self._ready = True
        logger.info("matrix: ready, listening for new messages")

        self._sync_task = asyncio.create_task(self._sync_loop())

    async def _sync_loop(self):
        while True:
            try:
                await self.client.sync(timeout=30000)
            except Exception as e:
                logger.error(f"matrix: sync error: {e}")
                await asyncio.sleep(5)

    async def _on_invite(self, room: MatrixRoom, event):
        logger.info(f"matrix: received invite {room.room_id}")
        await self.client.join(room.room_id)
        logger.info(f"matrix: accepted invite {room.room_id}")

    async def _on_message(self, room: MatrixRoom, event):
        if not self._ready:
            return

        if event.sender == self.user:
            return

        if getattr(room, "is_group", True):
            if len(room.users) > 2:
                return

        text = getattr(event, "body", None)
        if not text:
            return

        logger.debug(f"matrix: message from {event.sender}: {repr(text)}")

        if self._message_callback:
            await self._message_callback(
                sender_matrix_id=event.sender,
                room_id=room.room_id,
                text=text
            )

    async def send_message(self, room_id: str, text: str):
        if not self.client:
            raise RuntimeError("matrix client not running")
        await self.client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": text}
        )

    async def send_file(
        self,
        room_id: str,
        data: bytes,
        filename: str,
        mime_type: Optional[str] = None,
        caption: Optional[str] = None
    ):
        if not self.client:
            raise RuntimeError("matrix client not running")

        if not mime_type:
            mime_type, _ = mimetypes.guess_type(filename)
            mime_type = mime_type or "application/octet-stream"

        response = await self.client.upload(data, content_type=mime_type)
        if not isinstance(response, UploadResponse):
            raise RuntimeError(f"matrix: upload error: {response}")

        mxc_url = response.content_uri

        if mime_type.startswith("image/"):
            msgtype = "m.image"
        elif mime_type.startswith("audio/"):
            msgtype = "m.audio"
        elif mime_type.startswith("video/"):
            msgtype = "m.video"
        else:
            msgtype = "m.file"

        await self.client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={
                "msgtype": msgtype,
                "body": caption or filename,
                "url": mxc_url,
                "info": {"mimetype": mime_type}
            }
        )

    async def download_file(self, mxc_url: str) -> Optional[bytes]:
        if not self.client:
            raise RuntimeError("matrix client not running")
        response = await self.client.download(mxc_url)
        if hasattr(response, "body"):
            return response.body
        return None

    async def get_or_create_direct_room(self, matrix_id: str) -> str:
        cached = await db.get_cached_room(matrix_id)
        if cached:
            return cached

        for room_id, room in self.client.rooms.items():
            members = list(room.users.keys())
            if len(members) == 2 and matrix_id in members:
                await db.cache_room(matrix_id, room_id)
                logger.info(f"matrix: found existing room {room_id} with {matrix_id}")
                return room_id

        response = await self.client.room_create(
            invite=[matrix_id],
            is_direct=True
        )
        room_id = response.room_id
        await db.cache_room(matrix_id, room_id)
        logger.info(f"matrix: created new room {room_id} with {matrix_id}")
        return room_id

    async def stop(self):
        if self._sync_task:
            self._sync_task.cancel()
        if self.client:
            await self.client.close()
        logger.info("matrix: client stopped")