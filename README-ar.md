<div align="center">

# 📻 Quran Stream

### نظام بث مباشر للراديو القرآني وفيديوهات يوتيوب إلى Telegram

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688.svg)](https://fastapi.tiangolo.com/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Required-orange.svg)](https://ffmpeg.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

**بث صوتي ومرئي مباشر • بث يوتيوب المباشر والمسجّل • تكامل Telegram**

[المميزات](#-المميزات) • [التثبيت](#-التثبيت) • [الاستخدام](#-الاستخدام) • [المساهمة](#-المساهمة)

</div>

---

## 📋 جدول المحتويات

- [نظرة عامة](#-نظرة-عامة)
- [المميزات](#-المميزات)
- [المتطلبات](#-المتطلبات)
- [التثبيت](#-التثبيت)
- [الإعدادات](#-الإعدادات)
- [الاستخدام](#-الاستخدام)
- [هيكل المشروع](#-هيكل-المشروع)
- [التقنيات المستخدمة](#-التقنيات-المستخدمة)
- [المساهمة](#-المساهمة)

---

## 🎯 نظرة عامة

**Quran Stream** هو نظام بث مباشر إلى Telegram عبر RTMP. يدعم ثلاثة أنواع من المصادر:

| المصدر | المسار | الخرج |
|---|---|---|
| 🕌 **راديو قرآني** | محطة من ملف M3U ← FFmpeg | صوت AAC ← RTMP |
| 🔴 **بث يوتيوب مباشر** | رابط ← yt-dlp ← FFmpeg | H.264 + AAC ← RTMP |
| 🎬 **فيديو يوتيوب مسجّل** | رابط ← yt-dlp ← FFmpeg (مرة واحدة / تكرار) | H.264 + AAC ← RTMP |

### ✨ لماذا Quran Stream؟

- 📡 **بث مباشر عالي الجودة** - بث صوتي ومرئي واضح ومستقر
- 🔗 **تكامل سلس مع Telegram** - بث مباشر إلى قنواتك بسهولة
- ⚡ **نسخ مباشر للمقاطع (Stream Copy)** - إن كان مصدر يوتيوب متوافقاً أصلاً مع Telegram فلا يتم إعادة ترميزه، مما يوفّر المعالج ويقلّل زمن البدء
- 🎚 **مستويات جودة** - منخفض (480p) / متوسط (720p) / عالٍ (1080p) لمن لديه إنترنت بطيء
- 🔄 **إعادة اتصال تلقائية** - مع تأخير تصاعدي 2 ← 5 ← 10 ← 30 ثانية ودون تكرار عمليات FFmpeg
- 🌐 **واجهة ويب خفيفة** - صفحة واحدة بدون مكتبات خارجية تعمل حتى على اتصال ضعيف

---

## 🌟 المميزات

### 🚀 المميزات الرئيسية

| الميزة | الوصف |
|--------|-------|
| 📡 **بث مباشر** | بث صوتي مباشر للراديو القرآني |
| ▶️ **بث يوتيوب** | بث مباشر أو فيديو مسجّل من يوتيوب (صوت + صورة) |
| 🔁 **تكرار الفيديو** | تشغيل الفيديو المسجّل مرة واحدة أو إعادته تلقائياً |
| 🔗 **تكامل Telegram** | بث مباشر إلى قنوات Telegram عبر RTMP |
| 🎵 **معالجة الصوت والفيديو** | FFmpeg مع نسخ المقاطع المتوافقة دون إعادة ترميز |
| 🔒 **حماية مفتاح البث** | لا يظهر المفتاح في الواجهة ولا في السجلات ولا في ردود الـ API |
| 🌐 **واجهة ويب** | لوحة تحكم بسيطة وسريعة |
| 🐳 **دعم Docker** | نشر سهل باستخدام Docker |
| ⚡ **أداء عالي** | FastAPI لسرعة فائقة |

### 📻 المحطات المدعومة

- محطات mp3quran.net
- محطات راديو إسلامية أخرى
- إمكانية إضافة محطات مخصصة

---

## 📦 المتطلبات

قبل البدء، تأكد من تثبيت:

- **Python** 3.10 أو أحدث
- **FFmpeg** (مطلوب لمعالجة الصوت والفيديو)
- **yt-dlp** (مطلوب لمصادر يوتيوب - يُثبَّت تلقائياً من `requirements.txt`)
- **Telegram** account
- **Docker** (اختياري للنشر)

### تثبيت FFmpeg

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg

# Windows
# قم بتحميل FFmpeg من https://ffmpeg.org/download.html
```

---

## 🚀 التثبيت

### الطريقة الأولى: التثبيت العادي

```bash
# 1. استنسخ المستودع
git clone https://github.com/3bkader-gpt/quran-stream.git
cd quran-stream

# 2. أنشئ بيئة افتراضية
python -m venv venv
source venv/bin/activate  # على Windows: venv\Scripts\activate

# 3. ثبت المتطلبات
pip install -r requirements.txt

# 4. قم بتشغيل التطبيق
python main.py
```

### الطريقة الثانية: استخدام Docker

```bash
# استنسخ المستودع
git clone https://github.com/3bkader-gpt/quran-stream.git
cd quran-stream

# بناء الصورة
docker build -t quran-stream .

# تشغيل الحاوية
docker run -p 8000:8000 quran-stream
```

---

## ⚙️ الإعدادات

### إعداد Telegram RTMP

1. أنشئ قناة Telegram
2. احصل على RTMP URL من Telegram
3. أضف الرابط في الإعدادات

### تخصيص المحطات

قم بتعديل ملف `mp3quran_radios.m3u` لإضافة أو تعديل محطات الراديو:

```m3u
#EXTM3U
#EXTINF:-1,الراديو القرآني
http://stream.example.com/radio.mp3
```

---

## 📖 الاستخدام

### خطوات البث

1. ✅ **شغل التطبيق**
   ```bash
   python main.py
   ```

2. ✅ **افتح المتصفح**
   ```
   http://localhost:8000
   ```

3. ✅ **أدخل بيانات RTMP**
   - ضع رابط الخادم ومفتاح البث من Telegram ثم اضغط **Save**

4. ✅ **اختر المصدر**
   - **Quran Stations**: اختر محطة واضغط Play
   - **YouTube Live**: ألصق رابط البث المباشر واختر الجودة
   - **YouTube Video**: ألصق رابط الفيديو واختر «مرة واحدة» أو «تكرار» والجودة

5. ✅ **راقب البث**
   - تعرض لوحة «Now Streaming» الحالة والمدة ومعدل البث وجودة الاتصال
   - زر **Stop Stream** يوقف البث وينهي عملية FFmpeg تماماً

### واجهة المستخدم

- 📊 **لوحة التحكم** - عرض حالة البث الحالية
- 🎛️ **التحكم** - بدء/إيقاف البث
- 📡 **المحطات** - قائمة المحطات المتاحة
- 📈 **الإحصائيات** - إحصائيات البث

---

## 📁 هيكل المشروع

```
quran-stream/
├── 📂 templates/              # قوالب HTML
│   └── index.html            # لوحة التحكم (صفحة واحدة بدون مكتبات خارجية)
├── 📄 main.py                # واجهة FastAPI وقراءة ملف المحطات
├── 📄 streaming.py           # مدير البث وأنابيب FFmpeg وإعادة الاتصال
├── 📄 youtube.py             # التحقق من روابط يوتيوب واستخراج المقاطع عبر yt-dlp
├── 📄 test_stream.py         # فحوصات ذاتية (python test_stream.py)
├── 📄 mp3quran_radios.m3u    # قائمة محطات الراديو
├── 📄 requirements.txt       # المتطلبات
├── 🐳 Dockerfile             # ملف Docker
└── 📄 Procfile              # ملف النشر
```

---

## 🛠️ التقنيات المستخدمة

<div align="center">

| التقنية | الوصف |
|---------|-------|
| ![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white) | لغة البرمجة الأساسية |
| ![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?logo=fastapi&logoColor=white) | إطار عمل الويب |
| ![FFmpeg](https://img.shields.io/badge/FFmpeg-Required-007808?logo=ffmpeg&logoColor=white) | معالجة الصوت والفيديو |
| ![yt-dlp](https://img.shields.io/badge/yt--dlp-Required-FF0000?logo=youtube&logoColor=white) | استخراج روابط بث يوتيوب |
| ![RTMP](https://img.shields.io/badge/RTMP-Protocol-FF6B6B?logo=rtmp&logoColor=white) | بروتوكول البث المباشر |
| ![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white) | للحاويات |

</div>

---

## 🚀 النشر

### Render.com

المشروع جاهز للنشر على Render.com. راجع ملف `render.yaml` للإعدادات.

### Heroku

استخدم `Procfile` الموجود للنشر على Heroku.

---

## 🤝 المساهمة

نرحب بمساهماتك! 🎉

1. 🍴 Fork المشروع
2. 🌿 أنشئ فرع (`git checkout -b feature/AmazingFeature`)
3. 💾 Commit (`git commit -m 'Add some AmazingFeature'`)
4. 📤 Push (`git push origin feature/AmazingFeature`)
5. 🔄 افتح Pull Request

---

## ⚠️ ملاحظات مهمة

- ⚖️ تأكد من الحصول على إذن مناسب لاستخدام محتوى الراديو القرآني
- 🔒 احمِ معلومات الاتصال الخاصة بك
- 📊 راقب استخدام النطاق الترددي

---

## 📄 الترخيص

هذا المشروع مفتوح المصدر ومتاح للاستخدام الحر.

---

## 📞 التواصل والدعم

- 🐛 **الإبلاغ عن مشاكل**: [افتح Issue](https://github.com/3bkader-gpt/quran-stream/issues)
- 💡 **اقتراح ميزات**: [افتح Issue](https://github.com/3bkader-gpt/quran-stream/issues)
- 📧 **البريد الإلكتروني**: medo.omar.salama@gmail.com

---

<div align="center">

**صُنع بـ ❤️ بواسطة [Mohamed Omar](https://github.com/3bkader-gpt)**

⭐ إذا أعجبك المشروع، لا تنسى إعطائه نجمة!

[⬆ العودة للأعلى](#-quran-stream)

</div>