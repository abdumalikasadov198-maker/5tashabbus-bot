import asyncio
import logging
import os
import pandas as pd

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from PIL import Image
from playwright.async_api import async_playwright
import pytesseract

# Konfiguratsiyalar
BOT_TOKEN = "8735948987:AAFAktld-BCFSV2hoaEpxCHNwHAptqAsJPQ"  # BotFather'dan olingan token
ADMIN_ID = 1791376955  # O'zingizning Telegram ID'ingiz

EXCEL_FILE = "oquvchilar.xlsx"
DEFAULT_IMAGE = "default_photo.jpg"  # Bir xil standart rasm
PHOTOS_DIR = "downloaded_photos"

os.makedirs(PHOTOS_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# CAPTCHA yechish funksiyasi (Tesseract OCR)
async def solve_captcha(page) -> str:
    try:
        captcha_img = await page.query_selector("img[src*='captcha']")
        if captcha_img:
            await captcha_img.screenshot(path="captcha.png")
            img = Image.open("captcha.png")
            text = pytesseract.image_to_string(img).strip()
            return text
    except Exception as e:
        logging.error(f"CAPTCHA o'qishda xatolik: {e}")
    return ""


# /start buyrug'i
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 **Xush kelibsiz!**\n\n"
        "Barcha o'quvchilar ma'lumotlari jamlangan Excel (`oquvchilar.xlsx`) faylini yuboring.\n"
        "Fayl ustunlari: `Guvohnoma_Raqam` va `Tugilgan_Sana` bo'lishi kerak."
    )


# Excel faylni qabul qilish
@dp.message(F.document)
async def handle_document(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    doc = message.document
    if doc.file_name.endswith(".xlsx") or doc.file_name.endswith(".xls"):
        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, EXCEL_FILE)

        df = pd.read_excel(EXCEL_FILE)
        count = len(df)

        await message.answer(
            f"✅ **Excel fayli qabul qilindi!**\n\n"
            f"📊 Jami o'quvchilar soni: **{count} ta**\n\n"
            f"Ro'yxatdan o'tkazishni boshlash uchun `/start_registration` buyrug'ini yuboring."
        )
    else:
        await message.answer("❌ Iltimos, faqat `.xlsx` formatidagi Excel faylini yuboring!")


# ADMIN BUYRUG'I: Ommaviy ro'yxatdan o'tkazish
@dp.message(Command("start_registration"))
async def start_mass_registration(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    if not os.path.exists(EXCEL_FILE):
        await message.answer("❌ `oquvchilar.xlsx` fayli topilmadi! Avval Excel faylini yuboring.")
        return

    df = pd.read_excel(EXCEL_FILE)
    total = len(df)

    status_msg = await message.answer(
        f"⏳ **Ro'yxatdan o'tkazish boshlandi...**\nJami: {total} ta o'quvchi."
    )

    success_count = 0
    fail_count = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
            ],
        )
        context = await browser.new_context(permissions=["camera"])
        page = await context.new_page()

        for idx, row in df.iterrows():
            guvohnoma = str(row["Guvohnoma_Raqam"]).strip()
            bdate = str(row["Tugilgan_Sana"]).strip()

            try:
                # 1. Saytga kirish
                await page.goto("https://5tashabbus.uz/", timeout=60000)
                await page.wait_for_load_state("networkidle")

                # 2. Bo'limlarni tanlash
                await page.click("text=Ro'yxatdan o'tish")
                await page.wait_for_timeout(500)
                await page.click("text=Besh tashabbus")
                await page.click("text=Maktab")

                # 3. Hujjat turi va ma'lumotlar
                await page.select_option("select[name='document_type']", label="Guvohnoma")

                if " " in guvohnoma:
                    seriya, raqam = guvohnoma.split(" ", 1)
                else:
                    seriya, raqam = "", guvohnoma

                await page.fill("input[placeholder*='Seriya']", seriya)
                await page.fill("input[placeholder*='Raqam']", raqam)
                await page.fill("input[type='date']", bdate)

                # 4. CAPTCHA
                captcha_code = await solve_captcha(page)
                if captcha_code:
                    await page.fill("input[placeholder*='CAPTCHA']", captcha_code)

                # 5. Qidiruv
                await page.click("button:has-text('Qidirish')")
                await page.wait_for_timeout(2000)

                # 6. Rasm bosqichi (Standart rasm o'tiladi)
                await page.click("button:has-text('Rasmga olish')")
                await page.wait_for_timeout(1000)
                await page.click("button:has-text('Saqlash')")

                # 7. Yo'nalish
                await page.select_option("select[name='category']", label="Sport")
                await page.select_option("select[name='direction']", label="Yengil atletika")

                # 8. Yakunlash
                await page.click("button[type='submit']")
                await page.wait_for_timeout(2000)

                success_count += 1

            except Exception as e:
                logging.error(f"Xatolik ({guvohnoma}): {e}")
                fail_count += 1

            # Telegramda jarayonni yangilab turish (har 5 ta o'quvchida)
            if (idx + 1) % 5 == 0 or (idx + 1) == total:
                await status_msg.edit_text(
                    f"🔄 **Jarayon ketmoqda:** [{idx+1}/{total}]\n"
                    f"✅ Muvaffaqiyatli: {success_count}\n"
                    f"❌ Xatolik: {fail_count}"
                )

            await asyncio.sleep(2)

        await browser.close()

    await message.answer(
        f"🎉 **Barcha ishlar yakunlandi!**\n\n"
        f"✅ Muvaffaqiyatli o'tdi: {success_count} ta\n"
        f"❌ Xatolik berdi: {fail_count} ta"
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
