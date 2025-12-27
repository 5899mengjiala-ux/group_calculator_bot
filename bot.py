from telegram.ext import Application, CommandHandler, ContextTypes
import os

async def cmd_test(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("机器人正常运行！🎯")

def main():
    token = os.environ.get("BOT_TOKEN")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("test", cmd_test))
    print("Bot is running…")
    app.run_polling()

if __name__ == "__main__":
    main()
