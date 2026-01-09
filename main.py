import asyncio
import logging
import os
import re
from datetime import date

import aiosqlite
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("ERROR: BOT_TOKEN not set!")
    exit(1)

bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_PATH = "workouts.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                exercise TEXT NOT NULL,
                sets INTEGER,
                reps TEXT,
                weight REAL
            )
        """)
        await db.commit()
    print("Database initialized")

def parse_line(line: str):
    line = line.strip().lower()
    if not line:
        return None

    # Пример: "жим лежа 3x8 75" или "присед 4x10 90кг" или "подтягивания 5xmax"
    match = re.match(r'^([а-яa-zё\s\-]+?)\s*(?:(\d+)\s*[xх]\s*([\d\-]+|max|до\s*отказа))?\s*([\d,.]+)?\s*(кг|kg|к)?$', line)
    if match:
        exercise = match.group(1).strip().title()
        sets = int(match.group(2)) if match.group(2) else None
        reps = match.group(3) if match.group(3) else None
        weight = float(match.group(4).replace(',', '.')) if match.group(4) else None
        return {"exercise": exercise, "sets": sets, "reps": reps, "weight": weight}
    return None

async def save_workout(user_id: int, text: str):
    today = date.today().isoformat()
    exercises = [parse_line(line) for line in text.split('\n') if parse_line(line)]
    if not exercises:
        return False, "Не распознана тренировка\nПример: Жим лежа 3x8 75кг"

    async with aiosqlite.connect(DB_PATH) as db:
        for ex in exercises:
            await db.execute("""
                INSERT INTO workouts (user_id, date, exercise, sets, reps, weight)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, today, ex["exercise"], ex["sets"], ex["reps"], ex["weight"]))
        await db.commit()

    return True, f"Сохранено {len(exercises)} упражнений за {today} ✅"

async def get_stats(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT exercise, SUM(sets * COALESCE(weight, 0)) as volume,
                   MAX(weight) as max_weight, COUNT(*) as count
            FROM workouts
            WHERE user_id = ?
            GROUP BY exercise
            ORDER BY volume DESC
            LIMIT 5
        """, (user_id,))
        rows = await cursor.fetchall()

    if not rows:
        return "Нет записей. Добавь тренировку!"

    lines = ["📊 Статистика (топ-5):"]
    for ex, vol, maxw, cnt in rows:
        lines.append(f"• {ex}: {vol:.0f} кг всего • макс {maxw or '?'} кг • {cnt} раз")
    return "\n".join(lines)

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Привет! 💪\nПиши тренировку (например: Жим лежа 3x8 75кг)\nКоманды:\n/stats — статистика")

@dp.message(Command("stats"))
async def stats(message: Message):
    text = await get_stats(message.from_user.id)
    await message.answer(text)

@dp.message()
async def handle_text(message: Message):
    success, resp = await save_workout(message.from_user.id, message.text)
    await message.answer(resp)

async def main():
    await init_db()
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
