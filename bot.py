import asyncio
import logging
import os
import pandas as pd
import requests

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile

# 1. BOT VA API SOZLAMALARI
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8735948987:AAFfSAMxlbYuz2zvgNgeJG2CogIzNTA18lk")
EXCEL_FILE = "oquvchilar.xlsx"
RESULT_FILE = "natija_oquvchilar.xlsx"

BASE_URL = "https://5tashabbus.uz"
CHECK_STUDENT_API = f"{BASE_URL}/api/v1/student/check"

# Server 403 bermasligi uchun to'liq brauzer header'lari
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "uz,ru;q=0.9,en;q=0.8",
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
    "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin"
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# 2. SEANS VA COOKIE BILAN ISHLAYDIGAN API FUNKSIYASI
def register_student_via_api(guvohnoma: str, birth_date: str, phone: str = "998995498988") -> dict:
    guvohnoma = guvohnoma.strip()
    if " " in guvohnoma:
        seriya, raqam = guvohnoma.split(" ", 1)
    else:
        seriya, raqam = "", guvohnoma

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        # 1. Bosh sahifaga kirib Cookie va Session'ni faollashtirish (403 xatoligining oldini oladi)
        session.get(BASE_URL, timeout=10)

        payload = {
            "series": seriya.upper(),
            "number": raqam.strip(),
            "birth_date": birth_date.strip(),
            "phone": phone.strip()
        }

        # 2. API'ga so'rov yuborish
        response = session.post(CHECK_STUDENT_API, json=payload, timeout=10)
        
        if response.status_code == 200:
            res_data = response.json()
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
            f"Ro'yxatdan o'tkazishni boshlash uchun `/start_registration` buyrug'ini yuboring."
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

    for idx, row in df.iterrows():
        guvohnoma = str(row["Guvohnoma_Raqam"]).strip()
        bdate = str(row["Tugilgan_Sana"]).strip()
        phone = str(row.get("Telefon", "998995498988")).replace("+", "").strip()

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

        if (idx + 1) % 3 == 0 or (idx + 1) == total:
            await status_msg.edit_text(
                f"⚡️ **Jarayon:** [{idx+1}/{total}]\n"
                f"✅ Muvaffaqiyatli: {len(successful_students)} ta\n"
                f"❌ Xatolik: {len(failed_students)} ta"
            )
        await asyncio.sleep(0.3)

    df["Natija_Holati"] = statuses
    df["Tafsilot_Ism"] = details
    df.to_excel(RESULT_FILE, index=False)

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
    
    await message.answer_document(
        document=FSInputFile(RESULT_FILE),
        caption="📊 **To'liq ro'yxatdan o'tkazish natijalari (Excel)**"
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
