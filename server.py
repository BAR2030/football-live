import os, asyncio, logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager

import aiohttp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN=os.getenv("BOT_TOKEN","").strip()
FOOTBALL_DATA_TOKEN=os.getenv("FOOTBALL_DATA_TOKEN","").strip()
WEBAPP_URL=os.getenv("WEBAPP_URL","").strip()
PORT=int(os.getenv("PORT","8000"))
API_BASE="https://api.football-data.org/v4"
TZ=ZoneInfo("Asia/Tehran")
logging.basicConfig(level=logging.INFO)
dp=Dispatcher()
COMPETITIONS={"PL":"لیگ برتر انگلیس","PD":"لالیگا","BL1":"بوندس‌لیگا","SA":"سری‌آ ایتالیا","FL1":"لیگ یک فرانسه","CL":"لیگ قهرمانان اروپا","DED":"اردیویسه هلند","PPL":"لیگ پرتغال"}
bot_task=None

async def get_matches():
    if not FOOTBALL_DATA_TOKEN:
        raise HTTPException(status_code=503,detail="FOOTBALL_DATA_TOKEN تنظیم نشده است.")
    now=datetime.now(TZ)
    start=now.date()
    end=start+timedelta(days=6)
    headers={"X-Auth-Token":FOOTBALL_DATA_TOKEN}
    timeout=aiohttp.ClientTimeout(total=22)
    found=[]; errors=[]
    async with aiohttp.ClientSession(headers=headers,timeout=timeout) as session:
        for code, league in COMPETITIONS.items():
            try:
                async with session.get(f"{API_BASE}/competitions/{code}/matches",params={"dateFrom":start.isoformat(),"dateTo":end.isoformat()}) as resp:
                    if resp.status in (403,404):
                        errors.append(code); continue
                    if resp.status==429:
                        raise HTTPException(status_code=429,detail="سقف درخواست API پر شده؛ کمی بعد دوباره تلاش کن.")
                    if resp.status>=400:
                        errors.append(code);continue
                    data=await resp.json()
                    for m in data.get("matches",[]):
                        m["competition"]={"name":league}
                        found.append(m)
            except HTTPException: raise
            except Exception as e:
                logging.warning("API issue for %s: %s",code,e);errors.append(code)
    unique={m.get("id"):m for m in found if m.get("id") is not None}
    matches=list(unique.values())
    matches.sort(key=lambda x:x.get("utcDate",""))
    return {"matches":matches,"from":start.isoformat(),"to":end.isoformat(),"timezone":"Asia/Tehran","limited_competitions":errors}

@dp.message(CommandStart())
async def start(message:Message):
    keyboard=None
    if WEBAPP_URL.startswith("https://"):
        keyboard=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚽ مشاهده برنامه و نتایج فوتبال",web_app=WebAppInfo(url=WEBAPP_URL))]])
    text_msg=("سلام! به فوتبال‌لایو خوش اومدی ⚽\n\n"
              "برنامه بازی‌های ۷ روز آینده، روز و تاریخ، ساعت ایران و نتیجه مسابقات را در نسخه وب ببین.\n"
              "نتایج زنده به پوشش و زمان به‌روزرسانی منبع داده بستگی دارد.")
    await message.answer(text_msg,reply_markup=keyboard)

@dp.message()
async def fallback(message:Message):
    if message.text and message.text.startswith("/"):
        await message.answer("برای دیدن برنامه و نتایج فوتبال، دستور /start را بزن.")

@asynccontextmanager
async def lifespan(app:FastAPI):
    global bot_task
    if BOT_TOKEN:
        bot_task=asyncio.create_task(dp.start_polling(Bot(BOT_TOKEN)))
    else:
        logging.warning("BOT_TOKEN not set; website API can still run.")
    yield
    if bot_task:
        bot_task.cancel()
        try: await bot_task
        except asyncio.CancelledError: pass

app=FastAPI(title="Football Live Mini App",lifespan=lifespan)
@app.get("/")
async def index():
    return FileResponse("index.html")
@app.get("/health")
async def health():
    return {"ok":True}
@app.get("/api/matches")
async def matches():
    return await get_matches()
if __name__=="__main__":
    import uvicorn
    uvicorn.run("server:app",host="0.0.0.0",port=PORT)
