import json
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ChatMemberHandler,
    ContextTypes,
)

TZ = ZoneInfo("Asia/Shanghai")
DATA_FILE = "stats.json"


def load_stats():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_stats(stats):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


stats = load_stats()


def ensure_chat_entry(chat_id: int, title: str):
    cid = str(chat_id)
    if cid not in stats:
        stats[cid] = {
            "title": title or "",
            "midnight_count": None,
            "current_count": 0,
            "joined_today": 0,
            "left_today": 0,
            "last_reset_date": None,
        }
    else:
        if title and stats[cid].get("title") != title:
            stats[cid]["title"] = title


def today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d")


def reset_if_new_day(cid: str, current_count: int | None = None):
    today = today_str()
    chat_stats = stats.get(cid)
    if chat_stats.get("last_reset_date") != today:
        if current_count is None:
            current_count = chat_stats.get("current_count", 0)
        chat_stats["midnight_count"] = current_count
        chat_stats["current_count"] = current_count
        chat_stats["joined_today"] = 0
        chat_stats["left_today"] = 0
        chat_stats["last_reset_date"] = today


async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = update.chat_member
    if cmu is None:
        return

    chat = cmu.chat
    chat_id = chat.id
    title = chat.title or str(chat_id)

    ensure_chat_entry(chat_id, title)
    cid = str(chat_id)

    old = cmu.old_chat_member
    new = cmu.new_chat_member

    joined_status = {"member", "administrator", "creator"}
    left_status = {"left", "kicked"}

    if old.status in left_status and new.status in joined_status:
        change = "join"
    elif old.status in joined_status and new.status in left_status:
        change = "leave"
    else:
        return

    try:
        count = await context.bot.get_chat_member_count(chat_id)
    except Exception:
        count = stats[cid].get("current_count", 0)

    reset_if_new_day(cid, count)

    if change == "join":
        stats[cid]["joined_today"] += 1
        stats[cid]["current_count"] += 1
    elif change == "leave":
        stats[cid]["left_today"] += 1
        stats[cid]["current_count"] -= 1

    save_stats(stats)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    cid = str(chat.id)

    if cid not in stats:
        await update.message.reply_text("我还没有记录这个群。")
        return

    reset_if_new_day(cid)
    save_stats(stats)

    s = stats[cid]
    msg = (
        f"📅 {today_str()}\n\n"
        f"群：{s['title']}\n"
        f"今日进：{s['joined_today']}\n"
        f"今日退：{s['left_today']}\n"
    )
    await update.message.reply_text(msg)


async def start_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖机器人已启动\n\n"
        "/today - 查询当前群今日进退人数"
    )


def main():
    token = os.getenv("BOT_TOKEN")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_msg))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
