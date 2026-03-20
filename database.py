import aiosqlite
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "bridge.db")

# admin             - are in .env, already linked
# matrix_authorized - added from addUser
# tg_only           - added from addRecipient
# users: id=0, telegram_id=1, telegram_username=2, matrix_id=3, role=4, added_at=5

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id       INTEGER UNIQUE,
    telegram_username TEXT,
    matrix_id         TEXT UNIQUE,
    role              TEXT NOT NULL DEFAULT 'tg_only',
    added_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recipients (
    owner_telegram_id   INTEGER NOT NULL,
    recipient_matrix_id TEXT NOT NULL,
    recipient_tg_id     INTEGER,
    recipient_tg_login  TEXT NOT NULL,
    PRIMARY KEY (owner_telegram_id, recipient_tg_login)
);

CREATE TABLE IF NOT EXISTS active_recipient (
    user_telegram_id    INTEGER PRIMARY KEY,
    target_matrix_id    TEXT,
    target_tg_id        INTEGER
);

CREATE TABLE IF NOT EXISTS pending_links (
    telegram_id INTEGER PRIMARY KEY,
    matrix_id   TEXT NOT NULL,
    token       TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS room_cache (
    matrix_id TEXT PRIMARY KEY,
    room_id   TEXT NOT NULL
);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
    logger.info("database initialized")

async def ensure_admin_from_env():
    tg_id = os.getenv("TELEGRAM_ADMIN_ID")
    tg_login = os.getenv("TELEGRAM_ADMIN_LOGIN")
    matrix_login = os.getenv("ADMIN_MATRIX_LOGIN")
    domain = os.getenv("MATRIX_DOMAIN", "")

    if not tg_id:
        raise EnvironmentError("TELEGRAM_ADMIN_ID not set in .env")

    matrix_id = f"@{matrix_login}:{domain}" if matrix_login and domain else None

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (telegram_id, telegram_username, matrix_id, role)
            VALUES (?, ?, ?, 'admin')
            ON CONFLICT(telegram_id) DO UPDATE SET
                telegram_username = excluded.telegram_username,
                matrix_id = excluded.matrix_id,
                role = 'admin'
        """, (int(tg_id), tg_login, matrix_id))
        await db.commit()

async def get_user_by_tg_id(tg_id: int) -> Optional[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (tg_id,))
        return await cur.fetchone()

async def get_user_by_tg_login(login: str) -> Optional[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT * FROM users WHERE LOWER(telegram_username) = LOWER(?)", (login,)
        )
        return await cur.fetchone()

async def get_user_by_matrix_id(matrix_id: str) -> Optional[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM users WHERE matrix_id = ?", (matrix_id,))
        return await cur.fetchone()

async def get_role(tg_id: int) -> Optional[str]:
    u = await get_user_by_tg_id(tg_id)
    return u[4] if u else None

async def has_access(tg_id: int) -> bool:
    return await get_role(tg_id) is not None


async def is_matrix_authorized_or_admin(tg_id: int) -> bool:
    role = await get_role(tg_id)
    return role in ("admin", "matrix_authorized")


async def upsert_tg_user(tg_id: int, tg_login: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT role FROM users WHERE telegram_id = ?", (tg_id,))
        existing = await cur.fetchone()
        if existing:
            await db.execute(
                "UPDATE users SET telegram_username = ? WHERE telegram_id = ?",
                (tg_login or None, tg_id)
            )
        else:
            cur2 = await db.execute(
                "SELECT id FROM users WHERE LOWER(telegram_username) = LOWER(?) AND telegram_id IS NULL",
                (tg_login,)
            )
            row = await cur2.fetchone()
            if row and tg_login:
                await db.execute(
                    "UPDATE users SET telegram_id = ? WHERE LOWER(telegram_username) = LOWER(?) AND telegram_id IS NULL",
                    (tg_id, tg_login)
                )
            else:
                await db.execute(
                    "INSERT INTO users (telegram_id, telegram_username, role) VALUES (?, ?, 'tg_only')",
                    (tg_id, tg_login or None)
                )
        await db.commit()


async def create_matrix_authorized(tg_login: str, matrix_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT telegram_id FROM users WHERE LOWER(telegram_username) = LOWER(?)", (tg_login,)
        )
        row = await cur.fetchone()
        if row:
            tg_id = row[0]
            await db.execute(
                "UPDATE users SET matrix_id = ?, role = 'matrix_authorized' WHERE LOWER(telegram_username) = LOWER(?)",
                (matrix_id, tg_login)
            )
        else:
            await db.execute(
                "INSERT INTO users (telegram_username, matrix_id, role) VALUES (?, ?, 'matrix_authorized')",
                (tg_login.lower(), matrix_id)
            )
            tg_id = None
        await db.commit()
        return tg_id or 0


async def create_tg_only(tg_login: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM users WHERE LOWER(telegram_username) = LOWER(?)", (tg_login,)
        )
        if await cur.fetchone():
            return  # уже есть
        await db.execute(
            "INSERT INTO users (telegram_username, role) VALUES (?, 'tg_only')",
            (tg_login.lower(),)
        )
        await db.commit()


async def confirm_matrix_link(tg_id: int, matrix_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET matrix_id = ?, role = 'matrix_authorized' WHERE telegram_id = ?",
            (matrix_id, tg_id)
        )
        await db.execute("DELETE FROM pending_links WHERE telegram_id = ?", (tg_id,))
        await db.commit()


async def create_pending_link(tg_id: int, matrix_id: str, token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO pending_links (telegram_id, matrix_id, token) VALUES (?, ?, ?)",
            (tg_id, matrix_id, token)
        )
        await db.commit()


async def get_pending_by_matrix(matrix_id: str) -> Optional[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT * FROM pending_links WHERE matrix_id = ?", (matrix_id,)
        )
        return await cur.fetchone()


async def get_pending_by_tg(tg_id: int) -> Optional[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT * FROM pending_links WHERE telegram_id = ?", (tg_id,)
        )
        return await cur.fetchone()


async def delete_expired_pending(max_minutes: int = 60):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM pending_links WHERE created_at < datetime('now', ? || ' minutes')",
            (f"-{max_minutes}",)
        )
        await db.commit()


async def add_recipient(owner_tg_id: int, recipient_tg_login: str, recipient_matrix_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        # ищем telegram_id получателя если уже известен
        cur = await db.execute(
            "SELECT telegram_id FROM users WHERE LOWER(telegram_username) = LOWER(?)",
            (recipient_tg_login,)
        )
        row = await cur.fetchone()
        tg_id = row[0] if row else None

        await db.execute("""
            INSERT INTO recipients (owner_telegram_id, recipient_matrix_id, recipient_tg_id, recipient_tg_login)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(owner_telegram_id, recipient_tg_login) DO UPDATE SET
                recipient_matrix_id = excluded.recipient_matrix_id,
                recipient_tg_id = excluded.recipient_tg_id
        """, (owner_tg_id, recipient_matrix_id, tg_id, recipient_tg_login.lower()))
        await db.commit()


async def add_tg_only_recipient(owner_tg_id: int, recipient_tg_login: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT telegram_id FROM users WHERE LOWER(telegram_username) = LOWER(?)",
            (recipient_tg_login,)
        )
        row = await cur.fetchone()
        tg_id = row[0] if row else None

        await db.execute("""
            INSERT INTO recipients (owner_telegram_id, recipient_matrix_id, recipient_tg_id, recipient_tg_login)
            VALUES (?, '', ?, ?)
            ON CONFLICT(owner_telegram_id, recipient_tg_login) DO UPDATE SET
                recipient_tg_id = COALESCE(excluded.recipient_tg_id, recipient_tg_id)
        """, (owner_tg_id, tg_id, recipient_tg_login.lower()))
        await db.commit()


async def get_recipients(owner_tg_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT * FROM recipients WHERE owner_telegram_id = ?", (owner_tg_id,)
        )
        return await cur.fetchall()


async def get_owners_for_matrix(matrix_id: str) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT owner_telegram_id FROM recipients WHERE recipient_matrix_id = ?",
            (matrix_id,)
        )
        return await cur.fetchall()


async def get_owners_for_tg(tg_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT owner_telegram_id FROM recipients WHERE recipient_tg_id = ?",
            (tg_id,)
        )
        return await cur.fetchall()


async def update_recipient_tg_id(tg_login: str, tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE recipients SET recipient_tg_id = ? WHERE LOWER(recipient_tg_login) = LOWER(?) AND recipient_tg_id IS NULL",
            (tg_id, tg_login)
        )
        await db.commit()





async def set_active_recipient_matrix(tg_id: int, target_matrix_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO active_recipient (user_telegram_id, target_matrix_id, target_tg_id)
            VALUES (?, ?, NULL)
            ON CONFLICT(user_telegram_id) DO UPDATE SET
                target_matrix_id = excluded.target_matrix_id,
                target_tg_id = NULL
        """, (tg_id, target_matrix_id))
        await db.commit()


async def set_active_recipient_tg(matrix_id: str, target_tg_id: int):
    user = await get_user_by_matrix_id(matrix_id)
    if not user or not user[1]:
        return
    owner_tg_id = user[1]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO active_recipient (user_telegram_id, target_matrix_id, target_tg_id)
            VALUES (?, NULL, ?)
            ON CONFLICT(user_telegram_id) DO UPDATE SET
                target_matrix_id = NULL,
                target_tg_id = excluded.target_tg_id
        """, (owner_tg_id, target_tg_id))
        await db.commit()


async def get_active_recipient(tg_id: int) -> Optional[tuple]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT * FROM active_recipient WHERE user_telegram_id = ?", (tg_id,)
        )
        return await cur.fetchone()


async def clear_active_recipient(tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM active_recipient WHERE user_telegram_id = ?", (tg_id,)
        )
        await db.commit()


async def get_cached_room(matrix_id: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT room_id FROM room_cache WHERE matrix_id = ?", (matrix_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def cache_room(matrix_id: str, room_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO room_cache (matrix_id, room_id) VALUES (?, ?)",
            (matrix_id, room_id)
        )
        await db.commit()


async def remove_recipient(owner_tg_id: int, recipient_tg_login: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM recipients WHERE owner_telegram_id = ? AND LOWER(recipient_tg_login) = LOWER(?)",
            (owner_tg_id, recipient_tg_login)
        )
        await db.commit()


async def get_matrix_owners_of_tg_user(tg_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT u.telegram_id, u.telegram_username, u.matrix_id
            FROM recipients r
            JOIN users u ON u.telegram_id = r.owner_telegram_id
            WHERE r.recipient_tg_id = ?
        """, (tg_id,))
        return await cur.fetchall()