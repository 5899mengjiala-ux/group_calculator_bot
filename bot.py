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

TZ = ZoneInfo("Asia/Shanghai")   # 北京时间
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


stats = load_stats()  # {chat_id: {...}}


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
    """每天第一次有事件或者查询时，如果日期变了，就重置日统计"""
    today = today_str()
    chat_stats = stats.get(cid)
    if chat_stats is None:
        return
    if chat_stats.get("last_reset_date") != today:
        if current_count is None:
            current_count = chat_stats.get("current_count", 0)
        chat_stats["midnight_count"] = current_count
        chat_stats["current_count"] = current_count
        chat_stats["joined_today"] = 0
        chat_stats["left_today"] = 0
        chat_stats["last_reset_date"] = today


async def daily_midnight_snapshot(context: ContextTypes.DEFAULT_TYPE):
    """每天 00:00 抓一下各群成员数，作为 '00:00人数' 基准"""
    for cid, chat_stats in stats.items():
        chat_id = int(cid)
        try:
            count = await context.bot.get_chat_member_count(chat_id)
        except Exception:
            # 可能被踢出群或者权限不足，跳过
            continue
        chat_stats["midnight_count"] = count
        chat_stats["current_count"] = count
        chat_stats["joined_today"] = 0
        chat_stats["left_today"] = 0
        chat_stats["last_reset_date"] = today_str()
    save_stats(stats)


def extract_change(old, new):
    """
    从 ChatMember 更新中判断是否有人进/退群
    返回: "join" / "leave" / None
    """
    if old is None or new is None:
        return None

    old_status = old.status
    new_status = new.status

    # 进群：from non-member to member
    joined_statuses = {"member", "administrator", "creator"}
    left_statuses = {"left", "kicked"}

    if old_status in left_statuses and new_status in joined_statuses:
        return "join"
    if old_status in joined_statuses and new_status in left_statuses:
        return "leave"
    return None


async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = update.chat_member
    if cmu is None:
        return

    chat = cmu.chat
    chat_id = chat.id
    title = chat.title or chat.full_name or str(chat_id)

    ensure_chat_entry(chat_id, title)
    cid = str(chat_id)

    change = extract_change(cmu.old_chat_member, cmu.new_chat_member)
    if change is None:
        return

    # 确保日期正确
    try:
        count = await context.bot.get_chat_member_count(chat_id)
    except Exception:
        count = stats[cid].get("current_count", 0)

    reset_if_new_day(cid, count)

    if change == "join":
        stats[cid]["joined_today"] += 1
        stats[cid]["current_count"] = stats[cid].get("current_count", 0) + 1
    elif change == "leave":
        stats[cid]["left_today"] += 1
        stats[cid]["current_count"] = max(
            0, stats[cid].get("current_count", 0) - 1
        )

    save_stats(stats)


async def cmd_ls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not stats:
        await update.effective_message.reply_text("我还没有见过任何群。")
        return

    lines = ["我见过的群："]
    for cid, chat_stats in stats.items():
        title = chat_stats.get("title") or cid
        lines.append(f"{title}\nID: `{cid}`")
    await update.effective_message.reply_text("\n\n".join(lines), parse_mode="Markdown")


def format_chat_report(cid: str, chat_stats: dict) -> str:
    title = chat_stats.get("title") or cid
    midnight = chat_stats.get("midnight_count")
    current = chat_stats.get("current_count")
    joined = chat_stats.get("joined_today", 0)
    left = chat_stats.get("left_today", 0)

    midnight_str = "未知" if midnight is None else str(midnight)
    current_str = "未知" if current is None else str(current)

    txt = []
    txt.append(f"群：{title}")
    txt.append(f"ID: `{cid}`")
    txt.append(f"00:00人数：{midnight_str} | 现在人数：{current_str}")
    txt.append(f"今日进：{joined}，退：{left}")
    return "\n".join(txt)


async def ensure_chat_stats(chat_id: int, title: str, bot) -> dict:
    cid = str(chat_id)
    ensure_chat_entry(chat_id, title)
    chat_stats = stats[cid]

    # 如果是新的一天，或者还没有记录当前人数，就刷新一下
    try:
        count = await bot.get_chat_member_count(chat_id)
    except Exception:
        count = chat_stats.get("current_count", 0)

    reset_if_new_day(cid, count)
    save_stats(stats)
    return chat_stats


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat

    # 优先使用参数中的群ID
    if context.args:
        try:
            target_cid = int(context.args[0])
        except ValueError:
            await msg.reply_text("群ID格式不对，请用 /today -100xxxx 这样的格式。")
            return
        chat_id = target_cid
        title = stats.get(str(chat_id), {}).get("title", str(chat_id))
    else:
        # 在群里直接用 /today：就查当前群
        if chat.type in ("group", "supergroup"):
            chat_id = chat.id
            title = chat.title or str(chat_id)
        else:
            await msg.reply_text("请在群里使用 /today，或加参数群ID。")
            return

    chat_stats = await ensure_chat_stats(chat_id, title, context.bot)

    header = f"[北京时间] {today_str()}"
    body = format_chat_report(str(chat_id), chat_stats)
    await msg.reply_text(f"{header}\n\n{body}", parse_mode="Markdown")


async def cmd_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    if not stats:
        await msg.reply_text("还没有任何群的统计数据。")
        return

    # 先更新所有群的当前人数 & 日期
    for cid in list(stats.keys()):
        chat_id = int(cid)
        title = stats[cid].get("title", cid)
        try:
            await ensure_chat_stats(chat_id, title, context.bot)
        except Exception:
            continue

    header = f"[北京时间] {today_str()}"
    bodies = []
    for cid, chat_stats in stats.items():
        bodies.append(format_chat_report(cid, chat_stats))

    text = header + "\n\n" + "\n\n".join(bodies)
    await msg.reply_text(text, parse_mode="Markdown")


async def start_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "已就绪（使用 chat_member 事件统计，建议把我设为群管理员）。\n\n"
        "/today [群ID] - 查看单个群今日统计\n"
        "/all - 查看我见过的所有群的今日统计\n"
        "/ls - 列出我见过的群名和群ID\n\n"
        "示例：\n"
        "/today -1001234567890"
    )
    await update.effective_message.reply_text(text)


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("请在环境变量 BOT_TOKEN 中设置机器人 Token。")

    app = Application.builder().token(token).build()

    # 每天 00:00 北京时间重置统计
    app.job_queue.run_daily(
        daily_midnight_snapshot,
        time=time(hour=0, minute=0, tzinfo=TZ),
        name="midnight_reset",
    )

    app.add_handler(CommandHandler("start", start_msg))
    app.add_handler(CommandHandler("ls", cmd_ls))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("all", cmd_all))

    # 监听成员变化
    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
