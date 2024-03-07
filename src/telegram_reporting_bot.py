import logging
from settings.conf import settings
from telegram import InlineQueryResultArticle, InputTextMessageContent, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, AIORateLimiter, InlineQueryHandler
from telegram.constants import ParseMode


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (f"Your Chat ID is: <b>{str(update.effective_chat.id)}</b>\n"
            "Please save this value and provide it to your Powerloom Node when prompted on startup.")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode=ParseMode.HTML)

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query:
        return
    else:
        # Create a button to start a private chat
        button = InlineKeyboardButton(text='Start private chat', url='https://t.me/PowerloomReportingBot')
        keyboard = InlineKeyboardMarkup([[button]])
        
        await update.inline_query.answer([
            InlineQueryResultArticle(
                id='1',
                title='Start a private chat',
                input_message_content=InputTextMessageContent(
                    message_text='Click the button below to start a private chat with me.'
                ),
                reply_markup=keyboard
            )
        ])
    

if __name__ == '__main__':
    application = ApplicationBuilder().token(settings.telegram.bot_token).rate_limiter(AIORateLimiter()).build()
    
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)
    application.add_handler(InlineQueryHandler(inline_query))
    
    application.run_polling()