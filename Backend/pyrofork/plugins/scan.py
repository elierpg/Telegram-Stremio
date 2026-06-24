import asyncio
from pyrogram import filters, Client, enums
from pyrogram.types import Message

from Backend.helper.custom_filter import CustomFilters
from Backend.helper.scan_manager import scan_manager
from Backend.helper.settings_manager import SettingsManager
from Backend.logger import LOGGER


_status_msg: tuple[int, int] | None = None


def _format_status() -> str:
    s = scan_manager.get_status()
    c = s["counters"]

    icon = "🔄" if s["is_running"] else {"completed": "✅", "cancelled": "⏹", "error": "❌"}.get(s["status"], "")
    label = "Running" if s["is_running"] else {"completed": "Complete", "cancelled": "Cancelled", "error": "Failed"}.get(s["status"], s["status"].title())

    lines = [f"📡 Scan {icon} {label}", ""]

    if s["current_channel_name"]:
        current_id = s.get("current_id", 0)
        lines.append(f"📺 Channel: <code>{s['current_channel_name']}</code>")
        if current_id:
            lines.append(f"🔢 Scanning up to message ID: <code>{current_id:,}</code>")

    total = c["total_found"]
    indexed = c["indexed"]
    skipped_meta = c["skipped_meta"]
    skipped_nonvid = c["skipped_nonvid"]
    skipped_dup = c["skipped_dup"]
    errors = c["errors"]
    accounted = indexed + skipped_meta + skipped_nonvid + skipped_dup + errors

    lines.append(f"⏱ Duration: <code>{s['elapsed']}</code>")
    lines.append("")
    lines.append(f"📨 Total messages seen: <code>{total}</code>")
    lines.append(f"✅ Indexed: <code>{indexed}</code>")
    lines.append(f"⏭ Already in DB: <code>{skipped_dup}</code>")
    lines.append(f"⚠️ No metadata: <code>{skipped_meta}</code>")
    lines.append(f"📎 Non-video: <code>{skipped_nonvid}</code>")
    lines.append(f"❌ Errors: <code>{errors}</code>")

    if s["is_running"]:
        progress = (accounted / total * 100) if total > 0 else 0
        remaining = total - accounted
        if remaining > 0:
            lines.append(f"\n⏳ Processing: <code>{progress:.1f}%</code> ({remaining} remaining)")

    if s["pending"]:
        lines.append(f"\n⏳ Channels left: <code>{len(s['pending'])}</code>")

    if s["error"]:
        lines.append(f"\n❌ <code>{s['error']}</code>")

    return "\n".join(lines)


async def _poll_until_done(client: Client, chat_id: int, msg_id: int) -> None:
    global _status_msg
    try:
        while True:
            s = scan_manager.get_status()
            if not s["is_running"]:
                try:
                    await client.edit_message_text(
                        chat_id, msg_id, _format_status(),
                        parse_mode=enums.ParseMode.HTML
                    )
                except Exception:
                    pass
                break

            try:
                await client.edit_message_text(
                    chat_id, msg_id, _format_status(),
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception:
                pass

            await asyncio.sleep(2)
    finally:
        _status_msg = None


async def _start_and_track(client: Client, message: Message, mode: str) -> None:
    global _status_msg

    channels = list(SettingsManager.current().auth_channels)
    if not channels:
        await message.reply_text(
            "❌ No AUTH_CHANNEL configured. Add channels in /admin/config first.",
            quote=True
        )
        return

    msg = await message.reply_text("⏳ Starting scan...", quote=True)
    _status_msg = (msg.chat.id, msg.id)

    result = await scan_manager.start(client, channels, mode=mode)
    if not result.get("ok"):
        await msg.edit_text(f"❌ {result.get('message', 'Could not start scan.')}")
        _status_msg = None
        return

    await _poll_until_done(client, msg.chat.id, msg.id)


@Client.on_message(filters.command('scan') & filters.private & CustomFilters.owner, group=9)
async def scan_command(client: Client, message: Message):
    if scan_manager.get_status()["is_running"]:
        await message.reply_text(
            "⚠️ A scan is already running.\n"
            "Use /cancelscan to stop it.",
            quote=True
        )
        return
    await _start_and_track(client, message, mode="scan")


@Client.on_message(filters.command('rescan') & filters.private & CustomFilters.owner, group=9)
async def rescan_command(client: Client, message: Message):
    if scan_manager.get_status()["is_running"]:
        await message.reply_text(
            "⚠️ A scan is already running.\n"
            "Use /cancelscan first, then /rescan.",
            quote=True
        )
        return
    await _start_and_track(client, message, mode="rescan")


@Client.on_message(filters.command('cancelscan') & filters.private & CustomFilters.owner, group=9)
async def cancelscan_command(client: Client, message: Message):
    result = await scan_manager.cancel()
    reply = await message.reply_text(
        result.get("message", "Cancellation requested."),
        quote=True
    )

    global _status_msg
    if _status_msg is not None:
        chat_id, msg_id = _status_msg
        try:
            await asyncio.sleep(1)
            await client.edit_message_text(
                chat_id, msg_id, _format_status(),
                parse_mode=enums.ParseMode.HTML
            )
        except Exception:
            pass


@Client.on_message(filters.command('scanstatus') & filters.private & CustomFilters.owner, group=9)
async def scanstatus_command(client: Client, message: Message):
    await message.reply_text(
        _format_status(),
        parse_mode=enums.ParseMode.HTML,
        quote=True
    )
