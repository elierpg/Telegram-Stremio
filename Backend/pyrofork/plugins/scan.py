from pyrogram import filters, Client, enums
from pyrogram.types import Message

from Backend.helper.custom_filter import CustomFilters
from Backend.helper.scan_manager import scan_manager
from Backend.helper.settings_manager import SettingsManager
from Backend.logger import LOGGER


@Client.on_message(filters.command('scan') & filters.private & CustomFilters.owner, group=9)
async def scan_command(client: Client, message: Message):
    status = scan_manager.get_status()
    if status["is_running"]:
        await message.reply_text(
            "⚠️ A scan is already running.\n"
            "Use /scanstatus to check progress or /cancelscan to stop it.",
            quote=True
        )
        return

    channels = list(SettingsManager.current().auth_channels)
    if not channels:
        await message.reply_text(
            "❌ No AUTH_CHANNEL configured. Add channels in /admin/config first.",
            quote=True
        )
        return

    result = await scan_manager.start(client, channels, mode="scan")
    if result.get("ok"):
        await message.reply_text(
            f"✅ Scan started across {len(channels)} channel(s).\n"
            f"Use /scanstatus to track progress.",
            quote=True
        )
    else:
        await message.reply_text(
            f"❌ {result.get('message', 'Could not start scan.')}",
            quote=True
        )


@Client.on_message(filters.command('rescan') & filters.private & CustomFilters.owner, group=9)
async def rescan_command(client: Client, message: Message):
    status = scan_manager.get_status()
    if status["is_running"]:
        await message.reply_text(
            "⚠️ A scan is already running.\n"
            "Use /cancelscan first, then /rescan.",
            quote=True
        )
        return

    channels = list(SettingsManager.current().auth_channels)
    if not channels:
        await message.reply_text(
            "❌ No AUTH_CHANNEL configured.",
            quote=True
        )
        return

    result = await scan_manager.start(client, channels, mode="rescan")
    if result.get("ok"):
        await message.reply_text(
            f"✅ Rescan started across {len(channels)} channel(s).\n"
            "All existing entries will be purged and re-indexed.\n"
            "Use /scanstatus to track progress.",
            quote=True
        )
    else:
        await message.reply_text(
            f"❌ {result.get('message', 'Could not start rescan.')}",
            quote=True
        )


@Client.on_message(filters.command('cancelscan') & filters.private & CustomFilters.owner, group=9)
async def cancelscan_command(client: Client, message: Message):
    result = await scan_manager.cancel()
    await message.reply_text(
        result.get("message", "Cancellation requested."),
        quote=True
    )


@Client.on_message(filters.command('scanstatus') & filters.private & CustomFilters.owner, group=9)
async def scanstatus_command(client: Client, message: Message):
    status = scan_manager.get_status()
    c = status["counters"]

    lines = [
        f"<b>Scan Status</b>",
        f"Status: <code>{status['status']}</code>",
        f"Mode: <code>{status['mode']}</code>",
        f"Elapsed: <code>{status['elapsed']}</code>",
        f"",
        f"<b>Counters</b>",
        f"  Total found: <code>{c['total_found']}</code>",
        f"  Processed:   <code>{c['processed']}</code>",
        f"  Indexed:     <code>{c['indexed']}</code>",
        f"  Skipped dup: <code>{c['skipped_dup']}</code>",
        f"  Skipped meta:<code>{c['skipped_meta']}</code>",
        f"  Skipped non-video: <code>{c['skipped_nonvid']}</code>",
        f"  Errors:      <code>{c['errors']}</code>",
    ]

    if status["current_channel_name"]:
        lines.append(f"\nCurrent channel: <code>{status['current_channel_name']}</code>")

    if status["error"]:
        lines.append(f"\n❌ Error: <code>{status['error']}</code>")

    lines.append(f"\nPending channels: <code>{len(status['pending'])}</code>")

    await message.reply_text(
        "\n".join(lines),
        parse_mode=enums.ParseMode.HTML,
        quote=True
    )
