import asyncio
import logging
import logging.handlers
import os
import re
import secrets
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)

import database as db
import messages as msg
from matrix_client import MatrixBot

load_dotenv()

LOG_FILE = os.getenv("LOG_FILE", "bot.log")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

_log_handlers = [logging.StreamHandler()]
if LOG_FILE:
    _log_handlers.append(
        logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
    )
logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.DEBUG if DEBUG else logging.INFO,
    handlers=_log_handlers
)
logger = logging.getLogger(__name__)

matrix_bot = MatrixBot()
_app: Application = None

MATRIX_DOMAIN = os.getenv("MATRIX_DOMAIN", "")
TOKEN_TTL = int(os.getenv("TOKEN_TTL_MINUTES", "60"))


def _require_env(key: str) -> str:
    v = os.getenv(key)
    if not v:
        raise EnvironmentError(f"{key} not set in .env")
    return v


def _matrix_id(login: str) -> str:
    clean = login.lstrip("@").split(":")[0]
    return f"@{clean}:{MATRIX_DOMAIN}"


def _valid_tg_login(v: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_]{4,32}$", v.lstrip("@")))


def _valid_matrix_login(v: str) -> bool:
    clean = v.lstrip("@").split(":")[0]
    return bool(re.match(r"^[a-zA-Z0-9._\-/=]+$", clean)) and len(clean) >= 1


async def send_tg(tg_id: int, text: str):
    try:
        await _app.bot.send_message(chat_id=tg_id, text=text)
    except Exception as e:
        logger.error(f"send_tg {tg_id}: {e}")


#tg part

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    tg_login = update.effective_user.username or ""

    await db.upsert_tg_user(tg_id, tg_login)
    if tg_login:
        await db.update_recipient_tg_id(tg_login, tg_id)

    user = await db.get_user_by_tg_id(tg_id)
    logger.debug(f"cmd_start: tg_id={tg_id} tg_login={tg_login} user={user}")

    if not user:
        await update.message.reply_text(msg.no_access)
        return

    role = user[4]
    if role == "tg_only":
        await update.message.reply_text(msg.start_tg_only)
        return

    #
    if user[3]:#matrix_id
        await update.message.reply_text(msg.start_authorized.format(matrix_id=user[3]))
    else:
        #no matrix_id
        await update.message.reply_text(msg.start_not_linked)
        context.user_data["waiting_matrix_login"] = True


async def cmd_adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    if not await db.is_matrix_authorized_or_admin(tg_id):
        await update.message.reply_text(msg.no_access)
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text(msg.adduser_usage)
        return

    tg_login = args[0].lstrip("@")
    matrix_login = args[1].lstrip("@").split(":")[0]

    if not _valid_tg_login(tg_login):
        await update.message.reply_text(msg.adduser_bad_tg)
        return
    if not _valid_matrix_login(matrix_login):
        await update.message.reply_text(msg.adduser_bad_matrix)
        return

    matrix_id = _matrix_id(matrix_login)

    #dublicate check
    existing = await db.get_user_by_matrix_id(matrix_id)
    if existing and existing[4] == "matrix_authorized":
        #already matrix_authorized
        await db.add_recipient(tg_id, tg_login, matrix_id)
        await update.message.reply_text(
            f"пользователь @{tg_login} уже существует\nдобавлен в ваш список получателей"
        )
        return

    known_tg_id = await db.create_matrix_authorized(tg_login, matrix_id)
    await db.add_recipient(tg_id, tg_login, matrix_id)

    if known_tg_id:
        await update.message.reply_text(msg.adduser_success.format(tg=tg_login, matrix_id=matrix_id))
    else:
        token = secrets.token_hex(8)
        await db.create_pending_link(0, matrix_id, token)
        await update.message.reply_text(
            msg.adduser_need_confirm.format(tg=tg_login, token=token)
        )


async def cmd_addrecipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    if not await db.is_matrix_authorized_or_admin(tg_id):
        await update.message.reply_text(msg.no_access)
        return

    args = context.args
    if len(args) != 1:
        await update.message.reply_text(msg.addrecipient_usage)
        return

    matrix_login = args[0].lstrip("@").split(":")[0]
    if not _valid_matrix_login(matrix_login):
        await update.message.reply_text(msg.addrecipient_bad)
        return

    matrix_id = _matrix_id(matrix_login)
    user = await db.get_user_by_matrix_id(matrix_id)
    if not user:
        await update.message.reply_text(msg.addrecipient_not_found.format(matrix_id=matrix_id))
        return

    tg_login = user[2] or ""
    await db.add_recipient(tg_id, tg_login, matrix_id)
    await update.message.reply_text(msg.addrecipient_success.format(matrix_id=matrix_id))


async def cmd_removerecipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    if not await db.is_matrix_authorized_or_admin(tg_id):
        await update.message.reply_text(msg.no_access)
        return

    args = context.args
    if len(args) != 1:
        await update.message.reply_text(msg.removerecipient_usage)
        return

    tg_login = args[0].lstrip("@")
    if not _valid_tg_login(tg_login):
        await update.message.reply_text(msg.removerecipient_bad)
        return

    recipients = await db.get_recipients(tg_id)
    if not any(r[3].lower() == tg_login.lower() for r in recipients):
        await update.message.reply_text(msg.removerecipient_not_found.format(tg=tg_login))
        return

    await db.remove_recipient(tg_id, tg_login)
    await update.message.reply_text(msg.removerecipient_success.format(tg=tg_login))


async def cmd_changerecipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    if not await db.has_access(tg_id):
        await update.message.reply_text(msg.no_access)
        return

    args = context.args
    if len(args) != 1:
        await update.message.reply_text(msg.change_usage)
        return

    matrix_login = args[0].lstrip("@").split(":")[0]
    if not _valid_matrix_login(matrix_login):
        await update.message.reply_text(msg.change_bad)
        return

    matrix_id = _matrix_id(matrix_login)
    user = await db.get_user_by_tg_id(tg_id)
    role = user[4] if user else None

    if role == "tg_only":
        owners = await db.get_matrix_owners_of_tg_user(tg_id)
        if not any(o[2] == matrix_id for o in owners):
            await update.message.reply_text(msg.change_not_in_list)
            return
    else:
        #matrix_authorized/admin
        recipients = await db.get_recipients(tg_id)
        if not any(r[1] == matrix_id for r in recipients):
            await update.message.reply_text(msg.change_not_in_list)
            return

    await db.set_active_recipient_matrix(tg_id, matrix_id)
    context.user_data["messaging_mode"] = True
    await update.message.reply_text(msg.change_success.format(matrix_id=matrix_id))


async def cmd_whorecipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    if not await db.has_access(tg_id):
        await update.message.reply_text(msg.no_access)
        return

    active = await db.get_active_recipient(tg_id)
    if not active or (not active[1] and not active[2]):
        await update.message.reply_text(msg.who_none)
    elif active[1]:
        await update.message.reply_text(msg.who_matrix.format(matrix_id=active[1]))
    else:
        user = await db.get_user_by_tg_id(active[2])
        login = user[2] if user else str(active[2])
        await update.message.reply_text(msg.who_tg.format(tg_login=login))


async def cmd_listrecipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    if not await db.has_access(tg_id):
        await update.message.reply_text(msg.no_access)
        return

    user = await db.get_user_by_tg_id(tg_id)
    role = user[4] if user else None

    if role == "tg_only":
        owners = await db.get_matrix_owners_of_tg_user(tg_id)
        if not owners:
            await update.message.reply_text(msg.list_empty)
            return
        lines = [msg.list_header]
        for o in owners:
            matrix_id = o[2] or "(без matrix)"
            lines.append(msg.list_item_full.format(tg=o[1] or str(o[0]), matrix_id=matrix_id))
        await update.message.reply_text("\n".join(lines))
    else:
        #matrix_authorized
        recipients = await db.get_recipients(tg_id)
        if not recipients:
            await update.message.reply_text(msg.list_empty)
            return
        lines = [msg.list_header]
        for r in recipients:
            tg_login = r[3]
            matrix_id = r[1]
            if matrix_id:
                lines.append(msg.list_item_full.format(tg=tg_login, matrix_id=matrix_id))
            else:
                lines.append(msg.list_item_tg_only.format(tg=tg_login))
        await update.message.reply_text("\n".join(lines))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    user = await db.get_user_by_tg_id(tg_id)
    if not user:
        await update.message.reply_text(msg.no_access)
        return
    role = user[4]
    if role in ("admin", "matrix_authorized"):
        await update.message.reply_text(msg.help_matrix_authorized)
    else:
        await update.message.reply_text(msg.help_tg_only)


#text msg

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    tg_login = update.effective_user.username or ""
    text = update.message.text

    user = await db.get_user_by_tg_id(tg_id)
    if not user:
        await update.message.reply_text(msg.no_access)
        return

    if context.user_data.get("waiting_matrix_login"):
        login = text.strip().lstrip("@").split(":")[0]
        if not _valid_matrix_login(login):
            await update.message.reply_text(msg.link_bad_login)
            return
        matrix_id = _matrix_id(login)

        existing = await db.get_user_by_matrix_id(matrix_id)
        if existing and existing[1] != tg_id:
            await update.message.reply_text(msg.link_taken)
            return

        token = secrets.token_hex(8)
        await db.create_pending_link(tg_id, matrix_id, token)
        context.user_data.pop("waiting_matrix_login")
        await update.message.reply_text(msg.link_instruction.format(domain=MATRIX_DOMAIN))
        await update.message.reply_text(msg.link_token.format(token=token))
        return

    # режим переписки
    if context.user_data.get("messaging_mode"):
        active = await db.get_active_recipient(tg_id)
        if not active or not active[1]:
            await update.message.reply_text(msg.who_none)
            context.user_data.pop("messaging_mode", None)
            return
        try:
            room_id = await matrix_bot.get_or_create_direct_room(active[1])
            sender_login = tg_login or update.effective_user.full_name or str(tg_id)
            await matrix_bot.send_message(room_id, f"@{sender_login}: {text}")
        except Exception as e:
            logger.error(f"matrix send error: {e}")
            await update.message.reply_text(msg.error_send.format(error=e))
        return

    await update.message.reply_text(
        "используйте /changeRecipient <matrixLogin> чтобы начать переписку"
    )


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(msg.only_text)


#matrix to telegram

async def on_matrix_message(sender_matrix_id: str, room_id: str, text: str):
    short_id = sender_matrix_id.split(":")[0].lstrip("@")
    sender = await db.get_user_by_matrix_id(sender_matrix_id)

    if sender and sender[1]:
        active = await db.get_active_recipient(sender[1])
        if active and active[2]:
            target_tg_id = active[2]
            await send_tg(target_tg_id, msg.incoming_from_matrix.format(
                matrix_id=short_id, text=text
            ))
            return

    owners = await db.get_owners_for_matrix(sender_matrix_id)
    if not owners:
        logger.debug(f"no recipients for {sender_matrix_id}")
        return

    formatted = msg.incoming_from_matrix.format(matrix_id=short_id, text=text)
    for row in owners:
        await send_tg(row[0], formatted)


#matrix

async def on_matrix_command(sender_matrix_id: str, room_id: str, text: str) -> bool:
    if not text.startswith("!"):
        return False

    parts = text.strip().split()
    cmd = parts[0].lower()
    sender = await db.get_user_by_matrix_id(sender_matrix_id)
    sender_tg_id = sender[1] if sender else None
    is_authorized = sender and sender[4] in ("admin", "matrix_authorized")

    logger.debug(f"matrix cmd: {cmd} from {sender_matrix_id} authorized={is_authorized}")

    if cmd == "!start":
        await matrix_bot.send_message(room_id, msg.matrix_start)
        return True

    if cmd == "!help":
        await matrix_bot.send_message(room_id, msg.matrix_help)
        return True

    if cmd == "!confirm" and len(parts) == 2:
        token = parts[1]
        await db.delete_expired_pending(TOKEN_TTL)

        pending = await db.get_pending_by_matrix(sender_matrix_id)
        if not pending or pending[2] != token:
            await matrix_bot.send_message(room_id, msg.matrix_bad_token)
            return True

        tg_id = pending[0]
        await db.confirm_matrix_link(tg_id, sender_matrix_id)
        await matrix_bot.send_message(room_id, msg.matrix_confirm_success)
        await send_tg(tg_id, msg.link_confirmed.format(matrix_id=sender_matrix_id))
        return True

    if not is_authorized:
        await matrix_bot.send_message(room_id, msg.matrix_no_access)
        return True

    if cmd == "!adduser":
        if len(parts) != 3:
            await matrix_bot.send_message(room_id, msg.matrix_adduser_usage)
            return True
        tg_login = parts[1].lstrip("@")
        matrix_login = parts[2].lstrip("@").split(":")[0]
        if not _valid_tg_login(tg_login):
            await matrix_bot.send_message(room_id, msg.matrix_adduser_bad_tg)
            return True
        if not _valid_matrix_login(matrix_login):
            await matrix_bot.send_message(room_id, msg.matrix_adduser_bad_matrix)
            return True
        matrix_id = _matrix_id(matrix_login)
        await db.create_matrix_authorized(tg_login, matrix_id)
        if sender_tg_id:
            await db.add_recipient(sender_tg_id, tg_login, matrix_id)
        token = secrets.token_hex(8)
        await db.create_pending_link(0, matrix_id, token)
        await matrix_bot.send_message(
            room_id,
            msg.matrix_adduser_success.format(tg=tg_login, matrix_id=matrix_id)
        )
        return True

    if cmd == "!addrecipient":
        if len(parts) != 2:
            await matrix_bot.send_message(room_id, msg.matrix_addrecipient_usage)
            return True
        tg_login = parts[1].lstrip("@")
        if not _valid_tg_login(tg_login):
            await matrix_bot.send_message(room_id, msg.matrix_addrecipient_bad)
            return True
        await db.create_tg_only(tg_login)
        if sender_tg_id:
            await db.add_tg_only_recipient(sender_tg_id, tg_login)
        await matrix_bot.send_message(room_id, msg.matrix_addrecipient_success.format(tg=tg_login))
        return True

    if cmd == "!changerecipient":
        if len(parts) != 2:
            await matrix_bot.send_message(room_id, msg.matrix_change_usage)
            return True
        tg_login = parts[1].lstrip("@")
        if not _valid_tg_login(tg_login):
            await matrix_bot.send_message(room_id, msg.matrix_change_bad)
            return True
        target = await db.get_user_by_tg_login(tg_login)
        if not target or not target[1]:
            await matrix_bot.send_message(room_id, msg.matrix_change_not_found.format(tg=tg_login))
            return True
        await db.set_active_recipient_tg(sender_matrix_id, target[1])
        await matrix_bot.send_message(room_id, msg.matrix_change_success.format(tg=tg_login))
        return True

    if cmd == "!whorecipient":
        if not sender_tg_id:
            await matrix_bot.send_message(room_id, msg.matrix_who_none)
            return True
        active = await db.get_active_recipient(sender_tg_id)
        if not active or not active[2]:
            await matrix_bot.send_message(room_id, msg.matrix_who_none)
        else:
            target = await db.get_user_by_tg_id(active[2])
            login = target[2] if target else str(active[2])
            await matrix_bot.send_message(room_id, msg.matrix_who.format(tg_login=login))
        return True

    if cmd == "!listrecipient":
        if not sender_tg_id:
            await matrix_bot.send_message(room_id, msg.matrix_list_empty)
            return True
        recipients = await db.get_recipients(sender_tg_id)
        if not recipients:
            await matrix_bot.send_message(room_id, msg.matrix_list_empty)
        else:
            lines = [msg.matrix_list_header]
            for r in recipients:
                lines.append(msg.matrix_list_item.format(tg=r[3]))
            await matrix_bot.send_message(room_id, "\n".join(lines))
        return True

    if cmd == "!removerecipient":
        if len(parts) != 2:
            await matrix_bot.send_message(room_id, msg.matrix_removerecipient_usage)
            return True
        tg_login = parts[1].lstrip("@")
        if not _valid_tg_login(tg_login):
            await matrix_bot.send_message(room_id, msg.removerecipient_bad)
            return True
        if not sender_tg_id:
            await matrix_bot.send_message(room_id, msg.matrix_no_access)
            return True
        recipients = await db.get_recipients(sender_tg_id)
        if not any(r[3].lower() == tg_login.lower() for r in recipients):
            await matrix_bot.send_message(room_id, msg.matrix_removerecipient_not_found.format(tg=tg_login))
        else:
            await db.remove_recipient(sender_tg_id, tg_login)
            await matrix_bot.send_message(room_id, msg.matrix_removerecipient_success.format(tg=tg_login))
        return True

    return False


async def matrix_handler(sender_matrix_id: str, room_id: str, text: str):
    logger.debug(f"matrix: {sender_matrix_id}: {repr(text)}")
    if await on_matrix_command(sender_matrix_id, room_id, text):
        return
    await on_matrix_message(sender_matrix_id, room_id, text)

async def _stop_messaging_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, handler):
    context.user_data.pop("messaging_mode", None)
    await handler(update, context)


#start

async def cleanup_loop():
    while True:
        await asyncio.sleep(300)
        await db.delete_expired_pending(TOKEN_TTL)


async def main():
    global _app

    if not MATRIX_DOMAIN:
        raise EnvironmentError("MATRIX_DOMAIN not set in .env")

    await db.init_db()
    await db.ensure_admin_from_env()

    proxy_url = f"socks5://{_require_env('PROXY_HOST')}:{_require_env('PROXY_PORT')}"
    logger.info(f"proxy: {proxy_url} | domain: {MATRIX_DOMAIN} | debug: {DEBUG}")

    _app = (
        Application.builder()
        .token(_require_env("TELEGRAM_BOT_TOKEN"))
        .proxy(proxy_url)
        .get_updates_proxy(proxy_url)
        .build()
    )

    for cmd, handler in [
        ("start", cmd_start),
        ("addUser", cmd_adduser),
        ("addRecipient", cmd_addrecipient),
        ("removeRecipient", cmd_removerecipient),
        ("changeRecipient", cmd_changerecipient),
        ("whoRecipient", cmd_whorecipient),
        ("listRecipient", cmd_listrecipient),
        ("help", cmd_help),
    ]:
        async def make_handler(h=handler):
            async def wrapped(update, context):
                context.user_data.pop("messaging_mode", None)
                context.user_data.pop("waiting_matrix_login", None)
                await h(update, context)
            return wrapped
        wrapped = await make_handler()
        _app.add_handler(CommandHandler(cmd, wrapped))

    _app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    _app.add_handler(MessageHandler(
        filters.PHOTO | filters.AUDIO | filters.VIDEO |
        filters.Document.ALL | filters.Sticker.ALL | filters.VOICE,
        handle_media
    ))

    await matrix_bot.start(matrix_handler)

    cleanup_task = asyncio.create_task(cleanup_loop())
    logger.info("bot started")

    await _app.initialize()
    await _app.start()
    await _app.updater.start_polling()

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass

    logger.info("shutdown...")
    cleanup_task.cancel()
    await _app.updater.stop()
    await _app.stop()
    await _app.shutdown()
    await matrix_bot.stop()
    logger.info("dead")


if __name__ == "__main__":
    asyncio.run(main())