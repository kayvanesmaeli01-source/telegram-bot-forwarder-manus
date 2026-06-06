import asyncio
import logging
import sys
import json
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

# اطلاعات ربات
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
SETTINGS_FILE = 'settings.json'

# Webhook settings
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST') # Render will provide this
WEBHOOK_PATH = f'/webhook/{API_TOKEN}'
WEB_SERVER_PORT = int(os.getenv('PORT', 8080)) # Render will provide this

# تنظیمات پیش‌فرض
DEFAULT_SETTINGS = {
    "welcome_message": "سلام! پیام خود را بفرستید تا به دست مدیر برسد.",
    "confirmation_message": "✅ پیام شما دریافت شد و برای مدیر ارسال گردید."
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()

def save_settings(settings_data):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings_data, f, ensure_ascii=False, indent=4)

class AdminStates(StatesGroup):
    waiting_for_new_welcome = State()
    waiting_for_new_confirmation = State()

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
current_settings = load_settings()

def get_admin_kb():
    buttons = [
        [InlineKeyboardButton(text="👋 تغییر متن خوش‌آمدگویی", callback_data="set_welcome")],
        [InlineKeyboardButton(text="✅ تغییر متن تایید ارسال", callback_data="set_confirm")],
        [InlineKeyboardButton(text="📝 مشاهده تنظیمات فعلی", callback_data="view_all_settings")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    if message.from_user.id == ADMIN_ID:
        await message.answer("سلام مدیر! برای مدیریت ربات از دستور /admin استفاده کنید.")
    else:
        welcome = current_settings.get("welcome_message", DEFAULT_SETTINGS["welcome_message"])
        await message.answer(welcome)

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🛠 پنل مدیریت ربات:", reply_markup=get_admin_kb())

@dp.callback_query(F.data == "set_welcome")
async def start_set_welcome(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("لطفاً متن جدید **خوش‌آمدگویی** را ارسال کنید:")
    await state.set_state(AdminStates.waiting_for_new_welcome)
    await callback.answer()

@dp.callback_query(F.data == "set_confirm")
async def start_set_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("لطفاً متن جدید **تایید ارسال پیام** را ارسال کنید:")
    await state.set_state(AdminStates.waiting_for_new_confirmation)
    await callback.answer()

@dp.callback_query(F.data == "view_all_settings")
async def view_settings(callback: CallbackQuery):
    welcome = current_settings.get("welcome_message", "تعریف نشده")
    confirm = current_settings.get("confirmation_message", "تعریف نشده")
    text = f"📋 تنظیمات فعلی:\n\n1️⃣ متن خوش‌آمدگویی:\n{welcome}\n\n2️⃣ متن تایید ارسال:\n{confirm}"
    await callback.message.answer(text)
    await callback.answer()

@dp.message(AdminStates.waiting_for_new_welcome)
async def process_new_welcome(message: Message, state: FSMContext):
    current_settings["welcome_message"] = message.text
    save_settings(current_settings)
    await message.answer("✅ متن خوش‌آمدگویی آپدیت شد.", reply_markup=get_admin_kb())
    await state.clear()

@dp.message(AdminStates.waiting_for_new_confirmation)
async def process_new_confirm(message: Message, state: FSMContext):
    current_settings["confirmation_message"] = message.text
    save_settings(current_settings)
    await message.answer("✅ متن تایید ارسال آپدیت شد.", reply_markup=get_admin_kb())
    await state.clear()

@dp.message()
async def main_handler(message: Message):
    # بخش مدیریت پاسخ‌های مدیر
    if message.from_user.id == ADMIN_ID:
        if message.reply_to_message:
            try:
                # چک کردن متن یا کپشن برای پیدا کردن آیدی
                content = ""
                if message.reply_to_message.text:
                    content = message.reply_to_message.text
                elif message.reply_to_message.caption:
                    content = message.reply_to_message.caption
                
                if "🔢 ID:" in content:
                    target_id = int(content.split("🔢 ID:")[1].split("\n")[0].strip())
                    await bot.copy_message(chat_id=target_id, from_chat_id=ADMIN_ID, message_id=message.message_id)
                    await message.answer("✔️ پاسخ شما برای کاربر ارسال شد.")
                else:
                    await message.answer("❌ آیدی کاربر در این پیام یافت نشد. لطفاً روی پیامی که حاوی اطلاعات کاربر است ریپلای کنید.")
            except Exception as e:
                await message.answer(f"❌ خطا در ارسال: {e}")
        return

    # بخش دریافت پیام از کاربران
    user = message.from_user
    info_text = (
        f"📩 پیام جدید از:\n"
        f"👤 نام: {user.full_name}\n"
        f"🆔 یوزرنیم: @{user.username if user.username else 'ندارد'}\n"
        f"🔢 ID: {user.id}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
    )
    
    try:
        # اگر پیام فقط متن بود
        if message.text:
            await bot.send_message(chat_id=ADMIN_ID, text=info_text + f"📝 متن:\n{message.text}")
        
        # اگر پیام مدیا (عکس، فیلم و ...) بود
        else:
            # کپی کردن پیام برای مدیر با اضافه کردن اطلاعات کاربر در کپشن
            await bot.copy_message(
                chat_id=ADMIN_ID,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                caption=info_text + (f"📎 کپشن: {message.caption}" if message.caption else "")
            )
        
        # ارسال تاییدیه به کاربر
        confirm_text = current_settings.get("confirmation_message", DEFAULT_SETTINGS["confirmation_message"])
        await message.answer(confirm_text)
        
    except Exception as e:
        logging.error(f"Error forwarding: {e}")

async def on_startup(bot: Bot):
    if WEBHOOK_HOST:
        webhook_url = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
        await bot.set_webhook(webhook_url)
        logging.info(f"Webhook set to: {webhook_url}")
    else:
        logging.warning("WEBHOOK_HOST not set, bot will run in long-polling mode.")

async def on_shutdown(bot: Bot):
    if WEBHOOK_HOST:
        await bot.delete_webhook()
        logging.info("Webhook deleted.")

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Create aiohttp application
    app = web.Application()
    
    # Register request handler
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)

    # Start webhook server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=WEB_SERVER_PORT)
    await site.start()

    # Keep the main task running indefinitely
    await asyncio.Event().wait()

if __name__ == "__main__":
    logging.info("Starting bot")
    asyncio.run(main())
