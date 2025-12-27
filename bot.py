import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ChatMemberHandler,
    ContextTypes
)

TZ = ZoneInfo("Asia/Shanghai")
DATA_FILE = "stats.json"


def load_stats():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_stats():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


stats = load_stats()


def today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d")


def reset_if_new_day(cid, count):
    s = stats[cid]
    if s.get("date") != today_str():
        s["midnight"] = count
        s["joined"] = 0
        s["left"] = 0
        s["date"] = today_str()


async def on_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.chat_member
    chat = cm.chat
    cid = str(chat.id)

    if cid not in stats:
        stats[cid] = {"title": chat.title, "midnight": 0, "joined": 0, "left": 0, "date": None}

    try:
        count = await context.bot.get_chat_member_count(chat.id)
    except:
        return

    reset_if_new_day(cid, count)

    old = cm.old_chat_member.status
    new = cm.new_chat_member.status

    join_states = {"member", "administrator", "creator"}
    left_states = {"left", "kicked"}

    if old in left_states and new in join_states:
        stats[cid]["joined"] += 1
    elif old in join_states and new in left_states:
        stats[cid]["left"] += 1

    save_stats()


def fmt(cid, s):
    return (
        f"群：{s['title']} \n"
        f"ID: `{cid}`\n"
        f"00:00人数：{s.get('midnight', '?')} | 当前人数：{s.get('midnight', 0) + s.get('joined', 0) - s.get('left', 0)}\n"
        f"今日进：{s['joined']}，退：{s['left']}"
    )


async def cmd_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not stats:
        await update.message.reply_text("还没有任何统计数据")
        return

    text = f"[北京时间] {today_str()}\n\n"
    text += "\n\n".join(fmt(cid, s) for cid, s in stats.items())

    await update.message.reply_text(text, parse_mode="Markdown")


async def start(update: Update, context):
    await update.message.reply_text(
        "已上线！在这里私聊我即可：\n/all - 查看全部群今日数据"
    )


async def main():
    token = os.environ.get("BOT_TOKEN")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("all", cmd_all))
    app.add_handler(ChatMemberHandler(on_change, ChatMemberHandler.CHAT_MEMBER))

    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
