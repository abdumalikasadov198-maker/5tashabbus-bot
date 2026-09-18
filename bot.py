import asyncio
import logging
import os
import re
import traceback
import pandas as pd

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from PIL import Image
from playwright.async_api import async_playwright
import pytesseract

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8735948987:AAFAktld-BCFSV2hoaEpxCHNwHAptqAsJPQ")
EXCEL_FILE = "oquvchilar.xlsx"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# CAPTCHA yechuvchi kuchaytirilgan funksiya
async def solve_captcha(page) -> str:
    try:
        captcha_elem = page.locator("img[src*='captcha']").first
        if await captcha_elem.count() > 0:
            await captcha_elem.screenshot(path="captcha.png")
            img = Image.open("captcha.png")
            text = pytesseract.image_to_string(img).strip()
            clean_text = re.sub(r"\W+", "", text)
            return clean_text
    except Exception as e:
        logging.error(f"CAPTCHA o'qishda xatolik: {e}")
    return ""


@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 **Xush kelibsiz!**\n\n"
        "O'quvchilar Excel (`oquvchilar.xlsx`) faylini yuboring.\n"
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
    status_msg = await message.answer(f"⏳ **Ro'yxatdan o'tkazish boshlandi...** [0/{total}]")

    successful_students = []
    failed_students = []

    # Standart rasm yaratish (bo'lmasa)
    sample_img_path = "sample_avatar.jpg"
    if not os.path.exists(sample_img_path):
        img = Image.new("RGB", (300, 400), color=(200, 200, 200))
        img.save(sample_img_path)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for idx, row in df.iterrows():
            guvohnoma = str(row["Guvohnoma_Raqam"]).strip()
            bdate = str(row["Tugilgan_Sana"]).strip()
            phone = str(row.get("Telefon", "998995498988")).replace("+", "").strip()

            if " " in guvohnoma:
                seriya, raqam = guvohnoma.split(" ", 1)
            else:
                seriya, raqam = "", guvohnoma

            is_registered = False
            student_name = "Noma'lum o'quvchi"

            # 2 marta qayta urinish imkoniyati
            for attempt in range(2):
                try:
                    # 1. Bosh sahifa
                    await page.goto("https://5tashabbus.uz/", wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(1500)

                    # 2. Ro'yxatdan o'tish tugmasi
                    reg_btn = page.locator("a, button, div").filter(has_text=re.compile(r"Ro.*yxatdan", re.I)).first
                    if await reg_btn.count() > 0:
                        await reg_btn.click(timeout=10000)
                        await page.wait_for_timeout(1500)

                    # 3. Telefon kiritish (agar so'ralsa)
                    phone_input = page.locator("input[type='tel'], input[placeholder*='998'], input[placeholder*='RAQAM']").first
                    if await phone_input.count() > 0 and await phone_input.is_visible():
                        await phone_input.fill(phone)
                        submit_phone = page.locator("button, a").filter(has_text=re.compile(r"Ro.*yxatdan", re.I)).first
                        await submit_phone.click()
                        await page.wait_for_timeout(2000)

                    # 4. Hujjat ma'lumotlarini kiritish
                    seriya_elem = page.locator("input[placeholder*='Seriya'], input[placeholder*='I-SM'], input[name*='series']").first
                    if await seriya_elem.count() > 0:
                        await seriya_elem.fill(seriya)

                    raqam_elem = page.locator("input[placeholder*='0000000'], input[placeholder*='Raqam'], input[name*='number']").first
                    if await raqam_elem.count() > 0:
                        await raqam_elem.fill(raqam)

                    sana_elem = page.locator("input[placeholder*='00.00.0000'], input[type='date'], input[name*='birth']").first
                    if await sana_elem.count() > 0:
                        await sana_elem.fill(bdate)

                    # 5. CAPTCHA
                    captcha_code = await solve_captcha(page)
                    if captcha_code:
                        captcha_input = page.locator("input[placeholder*='AAAA'], input[placeholder*='TEKSTNI']").first
                        if await captcha_input.count() > 0:
                            await captcha_input.fill(captcha_code)

                    # 6. Qidirish tugmasi
                    search_btn = page.locator("button, a").filter(has_text=re.compile(r"Qidirish", re.I)).first
                    if await search_btn.count() > 0:
                        await search_btn.click()
                        await page.wait_for_timeout(3000)

                    # 7. O'quvchi ism-familiyasini sahifadan o'qib olish
                    try:
                        name_elem = page.locator("input[placeholder*='FAMILIYA'], div:has-text('FAMILIYA'), h3, h4").first
                        if await name_elem.count() > 0:
                            val = await name_elem.input_value() if await name_elem.evaluate("node => node.tagName === 'INPUT'") else await name_elem.text_content()
                            if val and len(val.strip()) > 2:
                                student_name = val.strip()
                    except Exception:
                        pass

                    # 8. Rasm yuklash
                    file_input = page.locator("input[type='file']").first
                    if await file_input.count() > 0:
                        await file_input.set_input_files(sample_img_path)
                        await page.wait_for_timeout(1000)

                    # 9. Saqlash / Yuborish
                    submit_final = page.locator("button, a").filter(has_text=re.compile(r"Yuborish|Saqlash", re.I)).first
                    if await submit_final.count() > 0:
                        await submit_final.click()
                        await page.wait_for_timeout(2500)

                    is_registered = True
                    break

                except Exception as e:
                    logging.warning(f"Urinish {attempt+1} muvaffaqiyatsiz bo'ldi ({guvohnoma}): {e}")
                    await asyncio.sleep(2)

            if is_registered:
                successful_students.append(f"• {student_name} ({guvohnoma})")
            else:
                failed_students.append(f"• {guvohnoma}")

            # Telegram'da jonli holatni yangilash
            await status_msg.edit_text(
                f"🔄 **Jarayon:** [{idx+1}/{total}]\n"
                f"✅ Muvaffaqiyatli: {len(successful_students)} ta\n"
                f"❌ Xatolik: {len(failed_students)} ta"
            )
            await asyncio.sleep(1)

        await browser.close()

    # YAKUNIY HISOBOT
    report = f"🎉 **Barcha ishlar yakunlandi!**\n\n"
    report += f"📊 Jami: **{total} ta**\n"
    report += f"✅ Muvaffaqiyatli: **{len(successful_students)} ta**\n"
    report += f"❌ Xatolik: **{len(failed_students)} ta**\n\n"

    if successful_students:
        report += "📋 **Ro'yxatdan o'tgan o'quvchilar:**\n"
        report += "\n".join(successful_students) + "\n\n"

    if failed_students:
        report += "⚠️ **O'tmaganlar (Guvohnoma):**\n"
        report += "\n".join(failed_students)

    await message.answer(report)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
            
