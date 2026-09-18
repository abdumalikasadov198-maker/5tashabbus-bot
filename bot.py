import asyncio
import logging
import os
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


# CAPTCHA rasmini o'qish funksiyasi
async def solve_captcha(page) -> str:
    try:
        # CAPTCHA elementini topish va rasmga olish
        captcha_elem = page.locator(
            "img[src*='captcha'], div:has-text('F A C N') img"
        ).first
        if await captcha_elem.count() > 0:
            await captcha_elem.screenshot(path="captcha.png")
            img = Image.open("captcha.png")
            text = pytesseract.image_to_string(img).strip()
            # FAQAT lotin harflari va raqamlarni ajratib olish
            clean_text = "".join(filter(str.isalnum, text))
            return clean_text
    except Exception as e:
        logging.error(f"CAPTCHA o'qishda xatolik: {e}")
    return ""


@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 **Xush kelibsiz!**\n\n"
        "O'quvchilar Excel (`oquvchilar.xlsx`) faylini yuboring.\n"
        "Fayl ustunlari: `Guvohnoma_Raqam` (masalan: `I-SM 1234567`) va `Tugilgan_Sana` (`01.01.2008`)."
    )


@dp.message(F.document)
async def handle_document(message: types.Message):
    doc = message.document
    if doc.file_name.endswith((".xlsx", ".xls")):
        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, EXCEL_FILE)
        df = pd.read_excel(EXCEL_FILE)

        await message.answer(
            f"✅ **Excel qabul qilindi!**\n\n"
            f"📊 Jami o'quvchilar: **{len(df)} ta**\n\n"
            f"Boshlash uchun `/start_registration` buyrug'ini yuboring."
        )


@dp.message(Command("start_registration"))
async def start_mass_registration(message: types.Message):
    if not os.path.exists(EXCEL_FILE):
        await message.answer("❌ Excel fayl topilmadi!")
        return

    df = pd.read_excel(EXCEL_FILE)
    total = len(df)
    status_msg = await message.answer(f"⏳ **Boshlandi...** [0/{total}]")

    success_count = 0
    fail_count = 0

    # Sukut bo'yicha yuklanadigan namuna rasm (bo'lmasa avtomatik yaratiladi)
    sample_img_path = "sample_avatar.jpg"
    if not os.path.exists(sample_img_path):
        img = Image.new("RGB", (300, 400), color=(200, 200, 200))
        img.save(sample_img_path)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = await browser.new_context()
        page = await context.new_page()

        for idx, row in df.iterrows():
            guvohnoma = str(row["Guvohnoma_Raqam"]).strip()
            bdate = str(row["Tugilgan_Sana"]).strip()

            # Guvohnoma seriya va raqamini ajratish
            if " " in guvohnoma:
                seriya, raqam = guvohnoma.split(" ", 1)
            else:
                seriya, raqam = "", guvohnoma

            try:
                # 1. Bosh sahifaga kirish
                await page.goto(
                    "https://5tashabbus.uz/",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                await page.wait_for_timeout(2000)

                # 2. "Ro'yxatdan o`tish" tugmasini bosish
                reg_btn = page.locator("text=Ro'yxatdan o`tish")
                await reg_btn.first.click()
                await page.wait_for_timeout(1500)

                # Mobil raqam so'ralsa kiritib o'tish
                phone_input = page.locator(
                    "input[type='tel'], input[placeholder*='RAQAM']"
                )
                if await phone_input.count() > 0:
                    await phone_input.first.fill("998995498988")
                    await page.click("button:has-text('Ro`yxatdan o`tish')")
                    await page.wait_for_timeout(2000)

                # 3. Forma maydonlarini to'ldirish
                # Hujjat seriyasi va raqami
                inputs = page.locator(
                    "input[placeholder*='0000000'], input[placeholder*='seriya'], input[type='text']"
                )

                # Guvohnoma seriyasi
                await page.locator(
                    "input[placeholder*='Seriya'], input[placeholder*='I-SM']"
                ).first.fill(seriya)
                # Guvohnoma raqami
                await page.locator(
                    "input[placeholder*='0000000']"
                ).first.fill(raqam)
                # Tug'ilgan sana
                await page.locator(
                    "input[placeholder*='00.00.0000']"
                ).first.fill(bdate)

                # 4. CAPTCHA ni yechish
                captcha_code = await solve_captcha(page)
                if captcha_code:
                    await page.locator(
                        "input[placeholder*='AAAA'], input[placeholder*='TEKSTNI']"
                    ).first.fill(captcha_code)

                # 5. Qidirish tugmasi
                await page.click("button:has-text('Qidirish')")
                await page.wait_for_timeout(3000)

                # 6. Rasm yuklash (Fayl yuklash tugmasi orqali)
                file_input = page.locator("input[type='file']")
                if await file_input.count() > 0:
                    await file_input.set_input_files(sample_img_path)
                    await page.wait_for_timeout(1000)

                # 7. Saqlash / Yuborish tugmasi
                submit_btn = page.locator(
                    "button:has-text('Yuborish'), button:has-text('Saqlash')"
                )
                if await submit_btn.count() > 0:
                    await submit_btn.first.click()
                    await page.wait_for_timeout(2000)

                success_count += 1

            except Exception as e:
                logging.error(f"Xatolik ({guvohnoma}): {e}")
                fail_count += 1

            # Telegram'da holatni yangilash
            await status_msg.edit_text(
                f"🔄 **Jarayon:** [{idx+1}/{total}]\n"
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
    
