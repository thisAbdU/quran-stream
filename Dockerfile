# استخدام صورة بايثون خفيفة
FROM python:3.12-slim

# تحديث النظام وتثبيت FFmpeg (هذه هي الخطوة الأهم)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# إعداد مجلد العمل
WORKDIR /app

# نسخ ملف المتطلبات وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# فتح المنفذ (سيتم تحديده من Render)
EXPOSE 8000

# أمر التشغيل (يستخدم PORT من متغير البيئة أو 8000 كافتراضي)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
