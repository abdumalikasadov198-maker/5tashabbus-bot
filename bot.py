import asyncio
import logging
import os
import pandas as pd
import requests

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile

# 1. BOT SOZLAMALARI
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8735948987:AAFfSAMxlbYuz2zvgNgeJG2CogIzNTA18lk")
EXCEL_FILE = "oquvchilar.xlsx"
RESULT_FILE = "natija_oquvchilar.xlsx"

# 5tashabbus.uz API manzillari va sarlavhalari (Headers)
BASE_URL = "https://5tashabbus.uz"
CHECK_STUDENT_API = f"{BASE_URL}/api/v1/student/check"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/"
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# 2. TEZKOR API ORQALI RO'YXATDAN O'TKAZISH FUNKSIYASI (0.3 Soniya)
def register_student_via_api(guvohnoma: str, birth_date: str, phone: str = "998995498988") -> dict:
    guvohnoma = guvohnoma.strip()
    if " " in guvohnoma:
        seriya, raqam = guvohnoma.split(" ", 1)
    else:
        seriya, raqam = "", guvohnoma

    session = requests.Session()
    session.headers.update(HEADERS)

    payload = {
        "series": seriya.upper(),
        "number": raqam.strip(),
        "birth_date": birth_date.strip(),
        "phone": phone.strip()
    }

    try:
        response = session.post(CHECK_STUDENT_API, json=payload, timeout=10)
        
        if response.status_code == 200:
            res_data = response.json()
            
            # Agar o'quvchi topilgan bo'lsa
            student_name = res_data.get("full_name") or res_data.get("student_name") or res_data.get("name")
            
            if student_name:
                return {"success": True, "name": student_name, "msg": "Muvaffaqiyatli ro'yxatdan o'tdi"}
            elif res_data.get("success") or res_data.get("status") == "registered":
                return {"success": True, "name": "O'quvchi", "msg": "Ro'yxatdan o'tdi"}
            else:
                msg = res_data.get("message", "Bazada topilmadi")
                return {"success": False, "name": None, "msg": msg}
        else:
            return {"success": False, "name": None, "msg": f"Server xatosi ({response.status_code})"}

    except Exception as e:
        return {"success": False, "name": None, "msg": f"Ulanish xatosi: {str(e)}"}


# 3. TELEGRAM BOT HANDLER'LARI
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 **Xush kelibsiz!**\n\n"
        "O'quvchilar ro'yxati solingan Excel faylini yuboring.\n"
        "Fayl ustunlari: `Guvohnoma_Raqam` (masalan: `AE 4154273`), `Tugilgan_Sana` (`08.06.2009`)."
    )


@dp.message(F.document)
async def handle_document(message: types.Message):
    doc = message.document
    if doc.file_name.endswith((".xlsx", ".xls")):
        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, EXCEL_FILE)
        df = pd.read_excel(EXCEL_FILE)

        await message.answer(
            f"✅ **Excel fayl qabul qilindi!**\n\n"
            f"📊 Jami o'quvchilar soni: **{len(df)} ta**\n\n"
            f"Tezkor API orqali ro'yxatdan o'tkazishni boshlash uchun `/start_registration` buyrug'ini yuboring."
        )


@dp.message(Command("start_registration"))
async def start_mass_registration(message: types.Message):
    if not os.path.exists(EXCEL_FILE):
        await message.answer("❌ Excel fayl topilmadi! Avval faylni yuboring.")
        return

    df = pd.read_excel(EXCEL_FILE)
    total = len(df)
    status_msg = await message.answer(f"⏳ **API orqali ishlanmoqda...** [0/{total}]")

    successful_students = []
    failed_students = []
    
    statuses = []
    details = []

    # Har bir o'quvchini ketma-ket chaqmoqday tezlikda API orqali o'tkazish
    for idx, row in df.iterrows():
        guvohnoma = str(row["Guvohnoma_Raqam"]).strip()
        bdate = str(row["Tugilgan_Sana"]).strip()
        phone = str(row.get("Telefon", "998995498988")).replace("+", "").strip()

        # API so'rovi (0.3 soniya)
        res = register_student_via_api(guvohnoma, bdate, phone)

        if res["success"]:
            name = res["name"] if res["name"] else "O'quvchi"
            successful_students.append(f"• {name} ({guvohnoma})")
            statuses.append("Muvaffaqiyatli")
            details.append(name)
        else:
            failed_students.append(f"• {guvohnoma} ({res['msg']})")
            statuses.append("Xatolik")
            details.append(res['msg'])

        # Har 3 ta o'quvchida holatni yangilab turish
        if (idx + 1) % 3 == 0 or (idx + 1) == total:
            await status_msg.edit_text(
                f"⚡️ **Jarayon:** [{idx+1}/{total}]\n"
                f"✅ Muvaffaqiyatli: {len(successful_students)} ta\n"
                f"❌ Xatolik: {len(failed_students)} ta"
            )
        await asyncio.sleep(0.1)

    # Natijalarni yangi Excel fayliga saqlash
    df["Natija_Holati"] = statuses
    df["Tafsilot_Ism"] = details
    df.to_excel(RESULT_FILE, index=False)

    # YAKUNIY HISOBOT
    report = f"🎉 **Barcha ishlar yakunlandi!**\n\n"
    report += f"📊 Jami: **{total} ta**\n"
    report += f"✅ Muvaffaqiyatli: **{len(successful_students)} ta**\n"
    report += f"❌ Xatolik: **{len(failed_students)} ta**\n\n"

    if successful_students:
        report += "📋 **Ro'yxatdan o'tganlar:**\n"
        report += "\n".join(successful_students) + "\n\n"

    if failed_students:
        report += "⚠️ **O'tmaganlar:**\n"
        report += "\n".join(failed_students)

    await message.answer(report)
    
    # Natija Excel faylini Telegram'ga yuklash
    await message.answer_document(
        document=FSInputFile(RESULT_FILE),
        caption="📊 **To'liq ro'yxatdan o'tkazish natijalari (Excel)**"
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
    
