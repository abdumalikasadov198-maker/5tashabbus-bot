FROM python:3.10-slim

# Tesseract OCR va kerakli kutubxonalarni o'rnatish
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps

COPY . .

CMD ["python", "bot.py"]
