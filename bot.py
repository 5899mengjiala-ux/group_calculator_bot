import json
import os
from datetime import datetime
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
    elif title and stats[cid]["title"] != title:
        stats[cid]["title"] = title


def today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d")


def reset_if_new_day(cid: str, current_count: int):
    today = today_str()
    chat_stats = stats[cid]
    if chat_stats.get("last_reset_date") != today:
        chat_stats["midnight_count"] = current_count
        chat_stats["current_count"] = current_count
        chat_stats["joined_today"] = 0
        chat_stats["left_today"] = 0
        chat_stats["last_reset_date"] = today


async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = update.chat_member
    if not cmu:
        return

    chat = cmu.chat
    cid = str(chat.id)
    ensure_chat_entry(chat.id, chat.title or cid)

    old_status = cmu.old_chat_member.status
    new_status = cmu.new_chat_member.status

    if old_status in {"left", "kicked"} and new_status in {"member", "administrator", "creator"}:
        change = "join"
    elif old_status in {"member", "administrator", "creator"} and new_status in {"left", "kicked"}:
        change = "leave"
    else:
        return

    try:
        count = await context.bot.get_chat_member_count(chat.id)
    except Exception:
        count = stats[cid]["current_count"]

    reset_if_new_day(cid, count)

    if change == "join":
        stats[cid]["joined_today"] += 1
        stats[cid]["current_count"] += 1
    else:
        stats[cid]["left_today"] += 1
        stats[cid]["current_count"] -= 1

    save_stats(stats)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)

    if cid not in stats:
        await update.message.reply_text("我还没有记录这个群。")
        return

    reset_if_new_day(cid, stats[cid]["current_count"])
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
        "🤖机器人已启动！\n"
        "使用：/today 查询今日进退人数"
    )


def main():
    token = os.getenv("BOT_TOKEN")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_msg))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    print("Bot running…")
    app.run_polling()


if __name__ == "__main__":
    main()
