import os
import logging
import sqlite3
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Update
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================== تنظیمات ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # بدون / آخر
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)

# ================== دیتابیس ==================
conn = sqlite3.connect("settings.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS config (
    id INTEGER PRIMARY KEY,
    source TEXT,
    destination TEXT,
    forward_active INTEGER DEFAULT 0
)
""")
cur.execute("INSERT OR IGNORE INTO config (id) VALUES (1)")
conn.commit()

def set_source(val): cur.execute("UPDATE config SET source=? WHERE id=1", (val,)); conn.commit()
def set_destination(val): cur.execute("UPDATE config SET destination=? WHERE id=1", (val,)); conn.commit()
def set_forward_status(status:int): cur.execute("UPDATE config SET forward_active=? WHERE id=1",(status,)); conn.commit()
def get_config(): cur.execute("SELECT source,destination,forward_active FROM config WHERE id=1"); return cur.fetchone()

# ================== FSM ==================
class ForwardState(StatesGroup):
    waiting_source = State()
    waiting_destination = State()

# ================== Bot & App ==================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# ================== Reply Keyboard ==================
def main_menu_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton("📤 فوروارد گروه به گروه"))
    keyboard.add(KeyboardButton("📡 فوروارد کانال به گروه"))
    return keyboard

def g2g_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton("🔹 گروه مبدا"))
    keyboard.add(KeyboardButton("🔸 گروه مقصد"))
    keyboard.add(KeyboardButton("▶️ شروع فوروارد"))
    keyboard.add(KeyboardButton("⏹ توقف فوروارد"))
    keyboard.add(KeyboardButton("🔙 بازگشت"))
    return keyboard

# ================== ابزار ==================
def is_admin(user_id:int): return user_id==ADMIN_ID
def is_valid_username(text:str): return text.startswith("@") and len(text)>1 and " " not in text

# ================== دستورات ==================
@dp.message(F.text.startswith("/start"))
async def start_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ شما دسترسی ندارید")
    await message.answer("پنل مدیریت ربات:", reply_markup=main_menu_keyboard())

# ================== دکمه‌ها ==================
@dp.message(F.text == "📡 فوروارد کانال به گروه")
async def c2g(message: types.Message):
    if not is_admin(message.from_user.id): return
    await message.answer("به زودی...")

@dp.message(F.text == "📤 فوروارد گروه به گروه")
async def g2g(message: types.Message):
    if not is_admin(message.from_user.id): return
    await message.answer("تنظیم فوروارد گروه به گروه:", reply_markup=g2g_keyboard())

@dp.message(F.text == "🔹 گروه مبدا")
async def ask_source(message: types.Message, state: FSMContext):
    await state.set_state(ForwardState.waiting_source)
    await message.answer("یوزرنیم گروه مبدا را با @ ارسال کن (مثال: @sourcegroup):")

@dp.message(F.text == "🔸 گروه مقصد")
async def ask_destination(message: types.Message, state: FSMContext):
    await state.set_state(ForwardState.waiting_destination)
    await message.answer("یوزرنیم گروه مقصد را با @ ارسال کن (مثال: @targetgroup):")

@dp.message(F.text == "▶️ شروع فوروارد")
async def start_forward(message: types.Message):
    set_forward_status(1)
    await message.answer("▶️ فوروارد فعال شد")

@dp.message(F.text == "⏹ توقف فوروارد")
async def stop_forward(message: types.Message):
    set_forward_status(0)
    await message.answer("⏹ فوروارد متوقف شد")

@dp.message(F.text == "🔙 بازگشت")
async def back(message: types.Message):
    await message.answer("پنل اصلی:", reply_markup=main_menu_keyboard())

# ================== ذخیره گروه‌ها با چک واقعی ==================
@dp.message(ForwardState.waiting_source)
async def save_source(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    if not is_valid_username(message.text):
        return await message.answer("❌ فرمت اشتباه است، فقط یوزرنیم با @ قبول می‌شود")
    try:
        await bot.get_chat(message.text)
    except:
        return await message.answer("❌ این گروه پیدا نشد. لطفاً یوزرنیم واقعی بده")
    set_source(message.text.lower())
    await state.clear()
    await message.answer("✅ گروه مبدا ثبت شد")

@dp.message(ForwardState.waiting_destination)
async def save_destination(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    if not is_valid_username(message.text):
        return await message.answer("❌ فرمت اشتباه است، فقط یوزرنیم با @ قبول می‌شود")
    try:
        await bot.get_chat(message.text)
    except:
        return await message.answer("❌ این گروه پیدا نشد. لطفاً یوزرنیم واقعی بده")
    set_destination(message.text.lower())
    await state.clear()
    await message.answer("✅ گروه مقصد ثبت شد")

# ================== فوروارد واقعی ==================
@dp.message()
async def auto_forward(message: types.Message):
    source, destination, forward_active = get_config()
    if not forward_active: return
    if not message.chat.username: return
    if f"@{message.chat.username.lower()}" == source:
        try:
            await message.copy_to(chat_id=destination)
        except Exception as e:
            logging.error(e)

# ================== Webhook ==================
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}")
    logging.info(f"Webhook set at {WEBHOOK_URL}/webhook/{BOT_TOKEN}")

@app.post(f"/webhook/{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
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
