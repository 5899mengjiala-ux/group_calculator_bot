def main():
    token = os.getenv("BOT_TOKEN")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_msg))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    print("Bot running…")
    app.run_polling()
