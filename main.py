import os
import logging
import sqlite3
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================== تنظیمات ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)

# ================== دیتابیس ==================
conn = sqlite3.connect("settings.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS config (
    id INTEGER PRIMARY KEY,
    source TEXT,
    destination TEXT
)
""")
cur.execute("INSERT OR IGNORE INTO config (id) VALUES (1)")
conn.commit()

def set_source(val):
    cur.execute("UPDATE config SET source=? WHERE id=1", (val,))
    conn.commit()

def set_destination(val):
    cur.execute("UPDATE config SET destination=? WHERE id=1", (val,))
    conn.commit()

def get_config():
    cur.execute("SELECT source, destination FROM config WHERE id=1")
    return cur.fetchone()

# ================== FSM ==================
class ForwardState(StatesGroup):
    waiting_source = State()
    waiting_destination = State()

# ================== Bot & App ==================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# ================== کیبورد ==================
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 فوروارد گروه به گروه", callback_data="g2g")],
        [InlineKeyboardButton(text="📡 فوروارد کانال به گروه", callback_data="c2g")]
    ])

def g2g_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔹 گروه مبدا", callback_data="set_source")],
        [InlineKeyboardButton(text="🔸 گروه مقصد", callback_data="set_destination")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back")]
    ])

# ================== ابزار ==================
def is_admin(user_id: int):
    return user_id == ADMIN_ID

def is_valid_username(text: str):
    return text.startswith("@") and len(text) > 1 and " " not in text

# ================== دستورات ==================
@dp.message(F.text == "/start")
async def start_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ شما دسترسی ندارید")
    await message.answer("پنل مدیریت ربات:", reply_markup=main_menu())

# ================== دکمه‌ها ==================
@dp.callback_query(F.data == "c2g")
async def c2g(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("به زودی...", show_alert=True)

@dp.callback_query(F.data == "g2g")
async def g2g(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text("تنظیم فوروارد گروه به گروه:", reply_markup=g2g_menu())

@dp.callback_query(F.data == "set_source")
async def ask_source(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ForwardState.waiting_source)
    await callback.message.answer("یوزرنیم گروه مبدا را با @ ارسال کن (مثال: @sourcegroup):")
    await callback.answer()

@dp.callback_query(F.data == "set_destination")
async def ask_destination(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ForwardState.waiting_destination)
    await callback.message.answer("یوزرنیم گروه مقصد را با @ ارسال کن (مثال: @targetgroup):")
    await callback.answer()

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    await callback.message.edit_text("پنل اصلی:", reply_markup=main_menu())

# ================== ذخیره تنظیمات ==================
@dp.message(ForwardState.waiting_source)
async def save_source(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not is_valid_username(message.text):
        return await message.answer("❌ فرمت اشتباه است، فقط یوزرنیم با @ قبول می‌شود")
    set_source(message.text.lower())
    await state.clear()
    await message.answer("✅ گروه مبدا ثبت شد")

@dp.message(ForwardState.waiting_destination)
async def save_destination(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not is_valid_username(message.text):
        return await message.answer("❌ فرمت اشتباه است، فقط یوزرنیم با @ قبول می‌شود")
    set_destination(message.text.lower())
    await state.clear()
    await message.answer("✅ گروه مقصد ثبت شد")

# ================== فوروارد ==================
@dp.message()
async def auto_forward(message: types.Message):
    source, destination = get_config()
    if not source or not destination:
        return

    if not message.chat.username:
        return

    if f"@{message.chat.username.lower()}" == source:
        try:
            await message.copy_to(chat_id=destination)
        except Exception as e:
            logging.error(e)

# ================== Webhook ==================
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}")

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
async def health():
    return {"status": "Bot is running"}

# ================== Run ==================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
