"""Telegram control bot: ideas -> pick -> angle -> preview -> approve / changes / reject.

Commands
  /ideas a      fresh topic ideas for Channel A (or b)
  /status       last 8 jobs
  /cancel       clear whatever the bot is waiting for
"""
import asyncio
import datetime as dt
import html
import logging
from functools import wraps
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaVideo, Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler,
                          filters)

import channels
import ideas
import pipeline
import store
from config import ENABLED_CHANNELS, LOCAL_TZ, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("yt")

RENDER_LOCK = asyncio.Lock()   # one render or upload at a time
BIG = {"read_timeout": 600, "write_timeout": 600, "connect_timeout": 60}


def owner_only(fn):
    @wraps(fn)
    async def inner(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        if not chat or chat.id != TELEGRAM_CHAT_ID:
            return
        return await fn(update, context)
    return inner


def kb(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows])


async def say(bot, text: str, **kw):
    return await bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode=ParseMode.HTML, **kw)


# ----------------------------------------------------------------------------- ideas
async def push_ideas(bot, ch_key: str):
    ch = channels.get(ch_key)
    await say(bot, f"Finding topics for <b>{html.escape(ch.name)}</b>...")
    try:
        found = await asyncio.to_thread(ideas.get_ideas, ch, store.recent_titles(ch_key))
    except Exception as e:  # noqa: BLE001
        log.exception("ideas failed")
        await say(bot, f"Idea search failed: <code>{html.escape(str(e)[:300])}</code>")
        return
    store.set_ideas(ch_key, found)
    lines = [f"<b>{html.escape(ch.name)}</b>: pick a topic\n"]
    for i, idea in enumerate(found, 1):
        lines.append(f"<b>{i}. {html.escape(idea['title'])}</b> [{idea['format']}]\n<i>{html.escape(idea['pitch'])}</i>\n")
    buttons = [[(str(i), f"pick|{ch_key}|{i - 1}") for i in range(1, len(found) + 1)], [("More ideas", f"more|{ch_key}")]]
    await say(bot, "\n".join(lines), reply_markup=kb(buttons))


async def scheduled_ideas(context: ContextTypes.DEFAULT_TYPE):
    await push_ideas(context.bot, context.job.data)


@owner_only
async def cmd_ideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = (context.args[0] if context.args else "A").upper()
    if key not in channels.CHANNELS:
        await update.message.reply_text("Use /ideas a or /ideas b")
        return
    await push_ideas(context.bot, key)


# ----------------------------------------------------------------------------- production
async def run_production(bot, job_id: str):
    async with RENDER_LOCK:
        job = store.get_job(job_id)
        await say(bot, f"Producing <b>{html.escape(job['idea']['title'])}</b> (rev {job['rev'] + 1}). "
                       "Script, voice, visuals and Shorts take roughly 5-15 minutes.")
        try:
            job = await asyncio.to_thread(pipeline.produce, job_id)
        except Exception as e:  # noqa: BLE001
            log.exception("produce failed")
            await say(bot, f"Production failed: <code>{html.escape(str(e)[:600])}</code>",
                      reply_markup=kb([[("Retry", f"retry|{job_id}"), ("Reject", f"rej|{job_id}")]]))
            return
    try:
        await send_review(bot, job)
    except Exception as e:  # noqa: BLE001
        log.exception("sending preview failed")
        jid = job["id"]
        await say(bot, f"Rendered, but sending the preview failed: <code>{html.escape(str(e)[:300])}</code>\n"
                       f"Title: {html.escape(job['script']['title'])}",
                  reply_markup=kb([[("Approve", f"ok|{jid}"), ("Changes", f"chg|{jid}"), ("Reject", f"rej|{jid}")]]))


async def send_review(bot, job: dict):
    s = job["script"]
    mins = job["long"]["duration"] / 60
    with open(job["long"]["preview"], "rb") as fh:
        await bot.send_video(TELEGRAM_CHAT_ID, fh, caption=f"Long video preview ({mins:.1f} min, 480p)",
                             supports_streaming=True, **BIG)
    with open(job["thumbnail"], "rb") as fh:
        await bot.send_photo(TELEGRAM_CHAT_ID, fh, caption="Thumbnail")
    if job["shorts"]:
        handles = [open(sh["preview"], "rb") for sh in job["shorts"][:10]]
        try:
            media = [InputMediaVideo(fh, caption=sh["title"][:200], supports_streaming=True)
                     for fh, sh in zip(handles, job["shorts"])]
            await bot.send_media_group(TELEGRAM_CHAT_ID, media, **BIG)
        finally:
            for fh in handles:
                fh.close()
    desc = html.escape(job["description"][:1500])
    text = (f"<b>Title:</b> {html.escape(s['title'])}\n<b>Shorts:</b> {len(job['shorts'])}\n\n"
            f"<b>Description:</b>\n{desc}")
    jid = job["id"]
    await say(bot, text, reply_markup=kb([[("Approve", f"ok|{jid}"), ("Changes", f"chg|{jid}"), ("Reject", f"rej|{jid}")]]))


async def run_publish(bot, job_id: str):
    async with RENDER_LOCK:
        await say(bot, "Uploading and scheduling...")
        try:
            results = await asyncio.to_thread(pipeline.publish, job_id)
        except Exception as e:  # noqa: BLE001
            log.exception("publish failed")
            await say(bot, f"Upload failed: <code>{html.escape(str(e)[:600])}</code>",
                      reply_markup=kb([[("Retry upload", f"ok|{job_id}")]]))
            return
    lines = ["<b>Scheduled</b>"]
    for r in results:
        when = pipeline.local_time(r["when"], LOCAL_TZ)
        lines.append(f"- {html.escape(r['title'])}\n  {when} IST · https://youtu.be/{r['id']}")
    await say(bot, "\n".join(lines), disable_web_page_preview=True)


# ----------------------------------------------------------------------------- buttons + text
@owner_only
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action, *rest = q.data.split("|")
    bot = context.bot

    if action == "more":
        await push_ideas(bot, rest[0])
    elif action == "pick":
        ch_key, idx = rest[0], int(rest[1])
        found = store.get_ideas(ch_key)
        if idx >= len(found):
            await say(bot, "Those ideas expired. Run /ideas again.")
            return
        store.set_awaiting({"kind": "angle", "ch": ch_key, "idx": idx})
        await say(bot, f"Picked: <b>{html.escape(found[idx]['title'])}</b>\n\n"
                       "Send your one-line angle: your take, the point you want viewers to leave with.")
    elif action == "ok":
        asyncio.create_task(run_publish(bot, rest[0]))
    elif action == "chg":
        store.set_awaiting({"kind": "changes", "job": rest[0]})
        await say(bot, "What should change? Send it in one message (script, tone, visuals, length...).")
    elif action == "rej":
        pipeline.reject(rest[0])
        await say(bot, "Rejected and cleaned up. Run /ideas when you want a new topic.")
    elif action == "retry":
        asyncio.create_task(run_production(bot, rest[0]))


@owner_only
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    waiting = store.get_awaiting()
    text = (update.message.text or "").strip()
    if not waiting:
        await update.message.reply_text("Nothing pending. Use /ideas a or /ideas b.")
        return
    if len(text) < 5:
        await update.message.reply_text("Please send at least a short sentence.")
        return
    store.set_awaiting(None)
    if waiting["kind"] == "angle":
        idea = store.get_ideas(waiting["ch"])[waiting["idx"]]
        job_id = pipeline.create_job(waiting["ch"], idea, text)
        asyncio.create_task(run_production(context.bot, job_id))
    elif waiting["kind"] == "changes":
        pipeline.add_note(waiting["job"], text)
        asyncio.create_task(run_production(context.bot, waiting["job"]))


@owner_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = sorted(store.read()["jobs"].values(), key=lambda j: j["created"], reverse=True)[:8]
    if not jobs:
        await update.message.reply_text("No jobs yet.")
        return
    lines = [f"{j['id']} · {j['channel']} · {j['status']} · {j['idea']['title'][:50]}" for j in jobs]
    await update.message.reply_text("\n".join(lines))


@owner_only
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store.set_awaiting(None)
    await update.message.reply_text("Cleared.")


@owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(__doc__)


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler("ideas", cmd_ideas))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    tz = ZoneInfo(LOCAL_TZ)
    for key in ENABLED_CHANNELS:
        ch = channels.get(key)
        h, m = map(int, ch.idea_time_local.split(":"))
        app.job_queue.run_daily(scheduled_ideas, time=dt.time(h, m, tzinfo=tz), days=ch.idea_days_ptb,
                                data=key, name=f"ideas_{key}")
        log.info("Scheduled ideas for %s on PTB days %s at %s %s", ch.name, ch.idea_days_ptb, ch.idea_time_local, LOCAL_TZ)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
