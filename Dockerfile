FROM python:3.11-slim

# تثبيت ffmpeg والأدوات المطلوبة
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# إنشاء مجلد العمل
WORKDIR /app

# نسخ ملف المتطلبات أولاً للاستفادة من Docker cache
COPY requirements.txt .

# تثبيت المتطلبات
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# إنشاء مجلد التحميل
RUN mkdir -p downloads

# تشغيل البوت
CMD ["python", "main.py"]
