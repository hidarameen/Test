
import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
import yt_dlp
import re
import math
import time

# إعداد البوت
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("youtube_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# قاموس لحفظ معلومات الفيديوهات مؤقتاً
video_info_cache = {}

def get_youtube_info(url):
    """استخراج معلومات الفيديو من YouTube"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            return None

def check_ffmpeg():
    """التحقق من وجود ffmpeg وعرض معلوماته"""
    import subprocess
    try:
        result = subprocess.run(['/home/runner/.nix-profile/bin/ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ تم العثور على ffmpeg بنجاح")
            print(f"📍 المسار: /home/runner/.nix-profile/bin/ffmpeg")
            return True
        else:
            print("❌ ffmpeg غير متاح")
            return False
    except Exception as e:
        print(f"❌ خطأ في التحقق من ffmpeg: {e}")
        return False

def progress_hook(d):
    """عرض تقدم التحميل"""
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', 'N/A')
        speed = d.get('_speed_str', 'N/A')
        print(f"التحميل: {percent} - السرعة: {speed}")

async def download_and_merge_video_audio(url, video_format_id, video_dir, title):
    """تحميل ودمج الفيديو مع الصوت"""
    try:
        # تحديد مسار ffmpeg
        ffmpeg_path = '/home/runner/.nix-profile/bin/ffmpeg'
        
        # خيارات تحميل الفيديو والصوت منفصلين ثم دمجهما
        ydl_opts = {
            'format': f'{video_format_id}+bestaudio[ext=m4a]/best',
            'outtmpl': f'{video_dir}/%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'progress_hooks': [progress_hook],
            'concurrent_fragments': 4,
            'buffersize': 16384,
            'http_chunk_size': 10485760,
            # تحديد مسار ffmpeg
            'ffmpeg_location': ffmpeg_path,
            # إعدادات الدمج المحسنة
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'merge_output_format': 'mp4',
            # إجبار استخدام ffmpeg للدمج
            'prefer_ffmpeg': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        return True
        
    except Exception as e:
        print(f"خطأ في دمج الفيديو والصوت: {e}")
        # محاولة بصيغة مختلفة
        try:
            print("محاولة الدمج بطريقة مختلفة...")
            ydl_opts_alt = {
                'format': f'{video_format_id}+bestaudio',
                'outtmpl': f'{video_dir}/%(title)s.%(ext)s',
                'quiet': False,
                'progress_hooks': [progress_hook],
                'ffmpeg_location': ffmpeg_path,
                'prefer_ffmpeg': True,
                'merge_output_format': 'mp4',
            }
            
            with yt_dlp.YoutubeDL(ydl_opts_alt) as ydl:
                ydl.download([url])
            return True
            
        except Exception as e2:
            print(f"فشل في الطريقة البديلة: {e2}")
            # محاولة تحميل الفيديو فقط كحل أخير
            try:
                print("تحميل الفيديو فقط كحل أخير...")
                ydl_opts_fallback = {
                    'format': video_format_id,
                    'outtmpl': f'{video_dir}/%(title)s.%(ext)s',
                    'quiet': False,
                    'progress_hooks': [progress_hook],
                    'ffmpeg_location': ffmpeg_path,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts_fallback) as ydl:
                    ydl.download([url])
                return True
                
            except Exception as e3:
                print(f"فشل في التحميل الاحتياطي: {e3}")
                return False

async def upload_with_progress(client, chat_id, file_path, caption="", thumb=None, is_audio=False):
    """رفع الملف مع عرض تقدم الرفع - يدعم ملفات حتى 2GB"""
    file_size = os.path.getsize(file_path)
    
    # Bot API الجديد يدعم ملفات حتى 2GB
    if file_size <= 2 * 1024 * 1024 * 1024:  # 2GB
        try:
            if is_audio:
                return await client.send_audio(
                    chat_id=chat_id,
                    audio=file_path,
                    caption=caption,
                    thumb=thumb,
                    progress=upload_progress
                )
            else:
                # استخدام send_document للملفات الكبيرة للحصول على أفضل دعم
                return await client.send_document(
                    chat_id=chat_id,
                    document=file_path,
                    caption=caption,
                    thumb=thumb,
                    progress=upload_progress
                )
        except Exception as e:
            # في حالة فشل الرفع المباشر، نحاول التقسيم كحل احتياطي
            print(f"فشل الرفع المباشر: {e}")
            return await upload_large_file(client, chat_id, file_path, caption)
    
    # إذا كان الملف أكبر من 2GB، قسمه
    return await upload_large_file(client, chat_id, file_path, caption)

async def upload_progress(current, total):
    """عرض تقدم الرفع"""
    percent = (current / total) * 100
    print(f"رفع: {percent:.1f}% ({current}/{total})")

async def upload_large_file(client, chat_id, file_path, caption):
    """رفع الملفات الكبيرة مقسمة إلى أجزاء"""
    file_size = os.path.getsize(file_path)
    chunk_size = 50 * 1024 * 1024  # 50MB per chunk
    total_chunks = math.ceil(file_size / chunk_size)
    
    file_name = os.path.basename(file_path)
    base_name, ext = os.path.splitext(file_name)
    
    chunks = []
    
    with open(file_path, 'rb') as f:
        for i in range(total_chunks):
            chunk_data = f.read(chunk_size)
            if not chunk_data:
                break
                
            chunk_filename = f"{base_name}.part{i+1:03d}{ext}"
            chunk_path = os.path.join(os.path.dirname(file_path), chunk_filename)
            
            with open(chunk_path, 'wb') as chunk_file:
                chunk_file.write(chunk_data)
            
            chunks.append(chunk_path)
    
    # رفع كل جزء
    uploaded_messages = []
    for i, chunk_path in enumerate(chunks, 1):
        chunk_caption = f"{caption}\n📦 الجزء {i}/{total_chunks}"
        
        message = await client.send_document(
            chat_id=chat_id,
            document=chunk_path,
            caption=chunk_caption,
            progress=upload_progress
        )
        uploaded_messages.append(message)
        
        # حذف الجزء بعد الرفع
        os.remove(chunk_path)
        
        # انتظار قصير بين الأجزاء
        await asyncio.sleep(0.5)
    
    return uploaded_messages

def get_quality_name(height):
    """تحويل رقم الدقة إلى اسم معروف"""
    quality_map = {
        144: "144p",
        240: "240p", 
        360: "360p",
        480: "480p",
        720: "720p HD",
        1080: "1080p Full HD",
        1440: "1440p 2K",
        2160: "2160p 4K",
        4320: "4320p 8K"
    }
    return quality_map.get(height, f"{height}p")

def calculate_total_filesize(video_format, best_audio_format):
    """حساب الحجم الإجمالي للفيديو + الصوت"""
    video_size = video_format.get('filesize', 0) or 0
    audio_size = best_audio_format.get('filesize', 0) or 0 if best_audio_format else 0
    return video_size + audio_size

def create_format_keyboard(formats, video_id):
    """إنشاء لوحة مفاتيح لاختيار صيغة الفيديو مع منطق فلترة محدث"""
    keyboard = []
    
    # تصنيف الصيغ
    mp4_formats = []
    mp4_video_only = []
    other_video_formats = []
    mp3_formats = []
    mp4a_formats = []
    
    # العثور على أفضل صيغة صوت لدمجها مع الفيديوهات بدون صوت
    best_audio_format = None
    for f in formats:
        if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
            if not best_audio_format or (f.get('abr', 0) or 0) > (best_audio_format.get('abr', 0) or 0):
                best_audio_format = f
    
    # فلترة وتصنيف الصيغ
    for f in formats:
        format_id = f.get('format_id', '')
        height = f.get('height')
        ext = f.get('ext', 'unknown')
        filesize = f.get('filesize', 0)
        vcodec = f.get('vcodec', 'none')
        acodec = f.get('acodec', 'none')
        abr = f.get('abr', 0)
        
        # تجاهل الصيغ غير المفيدة
        if not height and acodec == 'none':
            continue
            
        if ext == 'mp4' and vcodec != 'none':
            # صيغ MP4
            if acodec != 'none':
                # MP4 مع صوت
                total_size = filesize or 0
                size_text = f" - {round(total_size / (1024 * 1024), 1)}MB" if total_size > 0 else ""
                quality_name = get_quality_name(height)
                
                mp4_formats.append({
                    'text': f"🎬 {quality_name}{size_text}",
                    'callback': f"video_{video_id}_{format_id}",
                    'height': height or 0,
                    'needs_audio': False
                })
            else:
                # MP4 بدون صوت - سيتم دمج الصوت
                total_size = calculate_total_filesize(f, best_audio_format)
                size_text = f" - {round(total_size / (1024 * 1024), 1)}MB" if total_size > 0 else ""
                quality_name = get_quality_name(height)
                
                mp4_video_only.append({
                    'text': f"🎬 {quality_name}{size_text}",
                    'callback': f"video_{video_id}_{format_id}",
                    'height': height or 0,
                    'needs_audio': True
                })
                
        elif vcodec != 'none' and height and ext not in ['mp4']:
            # صيغ فيديو أخرى - أفضل واحدة فقط
            total_size = calculate_total_filesize(f, best_audio_format) if acodec == 'none' else (filesize or 0)
            size_text = f" - {round(total_size / (1024 * 1024), 1)}MB" if total_size > 0 else ""
            
            other_video_formats.append({
                'format': f,
                'text': f"📹 {height}p ({ext.upper()}){size_text}",
                'callback': f"video_{video_id}_{format_id}",
                'height': height or 0,
                'needs_audio': acodec == 'none'
            })
            
        elif ext == 'mp3' or (acodec != 'none' and vcodec == 'none' and 'mp3' in format_id.lower()):
            # صيغ MP3
            size_text = f" - {round(filesize / (1024 * 1024), 1)}MB" if filesize and filesize > 0 else ""
            bitrate_text = f" {abr}kbps" if abr else ""
            
            mp3_formats.append({
                'text': f"🎵 MP3{bitrate_text}{size_text}",
                'callback': f"audio_{video_id}_{format_id}",
                'abr': abr or 0
            })
            
        elif ext == 'm4a' or 'mp4a' in str(acodec).lower():
            # صيغ MP4A
            size_text = f" - {round(filesize / (1024 * 1024), 1)}MB" if filesize and filesize > 0 else ""
            bitrate_text = f" {abr}kbps" if abr else ""
            
            mp4a_formats.append({
                'text': f"🎶 M4A{bitrate_text}{size_text}",
                'callback': f"audio_{video_id}_{format_id}",
                'abr': abr or 0
            })
    
    # ترتيب الصيغ
    # MP4 - ترتيب حسب الجودة (من الأعلى للأقل)
    all_mp4 = mp4_formats + mp4_video_only
    all_mp4.sort(key=lambda x: x['height'], reverse=True)
    
    # إضافة جميع صيغ MP4
    for fmt in all_mp4:
        keyboard.append([InlineKeyboardButton(fmt['text'], callback_data=fmt['callback'])])
    
    # أفضل صيغة فيديو أخرى (غير MP4)
    if other_video_formats:
        best_other = max(other_video_formats, key=lambda x: x['height'])
        keyboard.append([InlineKeyboardButton(best_other['text'], callback_data=best_other['callback'])])
    
    # أفضل صيغتين MP3
    mp3_formats.sort(key=lambda x: x['abr'], reverse=True)
    for fmt in mp3_formats[:2]:
        keyboard.append([InlineKeyboardButton(fmt['text'], callback_data=fmt['callback'])])
    
    # أفضل صيغة MP4A
    if mp4a_formats:
        best_mp4a = max(mp4a_formats, key=lambda x: x['abr'])
        keyboard.append([InlineKeyboardButton(best_mp4a['text'], callback_data=best_mp4a['callback'])])
    
    # إضافة زر صوت فقط MP3 العام إذا لم تكن هناك صيغ MP3 محددة
    if not mp3_formats:
        keyboard.append([InlineKeyboardButton("🎵 صوت فقط (MP3)", callback_data=f"audio_{video_id}")])
    
    return InlineKeyboardMarkup(keyboard)

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "مرحباً! 🎬\n\n"
        "أرسل لي رابط فيديو من YouTube وسأقوم بتحميله لك\n"
        "يمكنك اختيار الصيغة والجودة التي تريدها\n\n"
        "✨ مميزات البوت:\n"
        "• دعم الملفات الكبيرة حتى 2GB بدون تقسيم\n"
        "• تحميل متوازي وسريع من YouTube\n"
        "• رفع مُحسَّن باستخدام Bot API الجديد\n"
        "• عرض تقدم التحميل والرفع\n"
        "• صيغ متعددة للفيديو والصوت\n\n"
        "مثال: https://youtube.com/watch?v=..."
    )

@app.on_message(filters.text & ~filters.command(["start"]))
async def handle_url(client, message):
    url = message.text.strip()
    
    # التحقق من صحة رابط YouTube
    youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/'
    if not re.search(youtube_regex, url):
        await message.reply_text("❌ يرجى إرسال رابط صحيح من YouTube")
        return
    
    status_msg = await message.reply_text("⏳ جاري تحليل الفيديو...")
    
    try:
        # استخراج معلومات الفيديو
        info = get_youtube_info(url)
        if not info:
            await status_msg.edit_text("❌ لا يمكن الوصول إلى الفيديو")
            return
        
        video_id = info['id']
        title = info.get('title', 'فيديو بدون عنوان')
        duration = info.get('duration', 0)
        uploader = info.get('uploader', 'غير معروف')
        view_count = info.get('view_count', 0)
        
        # حفظ معلومات الفيديو
        video_info_cache[video_id] = {
            'url': url,
            'info': info,
            'title': title,
            'formats': info['formats']  # حفظ الصيغ للوصول السريع
        }
        
        # تنسيق المدة والمشاهدات
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "غير محدد"
        views_str = f"{view_count:,}" if view_count else "غير محدد"
        
        # إنشاء لوحة اختيار الصيغ
        keyboard = create_format_keyboard(info['formats'], video_id)
        
        await status_msg.edit_text(
            f"📹 **{title}**\n\n"
            f"👤 **القناة:** {uploader}\n"
            f"⏱️ **المدة:** {duration_str}\n"
            f"👀 **المشاهدات:** {views_str}\n\n"
            f"اختر الصيغة والجودة:",
            reply_markup=keyboard
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ خطأ: {str(e)}")

@app.on_callback_query()
async def handle_download(client, callback_query: CallbackQuery):
    data = callback_query.data
    
    try:
        if data.startswith("video_"):
            # تحميل فيديو
            parts = data.split("_")
            video_id = parts[1]
            format_id = parts[2]
            
            if video_id not in video_info_cache:
                await callback_query.answer("❌ انتهت صلاحية الرابط", show_alert=True)
                return
                
            await callback_query.answer("⏳ جاري التحميل...")
            
            # إنشاء مجلد خاص لهذا الفيديو
            video_dir = f"downloads/{video_id}"
            os.makedirs(video_dir, exist_ok=True)
            
            cache_data = video_info_cache[video_id]
            
            # التحقق من حاجة الفيديو للصوت
            selected_format = None
            for f in cache_data['info']['formats']:
                if f.get('format_id') == format_id:
                    selected_format = f
                    break
            
            needs_audio = selected_format and selected_format.get('acodec') == 'none'
            
            if needs_audio:
                status_msg = await callback_query.message.edit_text("⏳ جاري تحميل الفيديو ودمج الصوت...")
                
                # استخدام دالة الدمج
                success = await download_and_merge_video_audio(
                    cache_data['url'], 
                    format_id, 
                    video_dir, 
                    cache_data['title']
                )
                
                if not success:
                    await status_msg.edit_text("❌ فشل في تحميل أو دمج الفيديو")
                    return
                    
            else:
                status_msg = await callback_query.message.edit_text("⏳ جاري تحميل الفيديو من YouTube...")
                
                # خيارات التحميل العادية
                ydl_opts = {
                    'format': format_id,
                    'outtmpl': f'{video_dir}/%(title)s.%(ext)s',
                    'quiet': False,
                    'no_warnings': False,
                    'progress_hooks': [progress_hook],
                    'concurrent_fragments': 4,
                    'buffersize': 16384,
                    'http_chunk_size': 10485760,
                    'ffmpeg_location': '/home/runner/.nix-profile/bin/ffmpeg',
                }
                
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([cache_data['url']])
                except Exception as download_error:
                    await status_msg.edit_text(f"❌ فشل في التحميل: {str(download_error)}")
                    return
            
        elif data.startswith("best_"):
            # تحميل أفضل جودة متاحة
            video_id = data.split("_")[1]
            
            if video_id not in video_info_cache:
                await callback_query.answer("❌ انتهت صلاحية الرابط", show_alert=True)
                return
                
            await callback_query.answer("⏳ جاري التحميل...")
            
            # إنشاء مجلد خاص لهذا الفيديو
            video_dir = f"downloads/{video_id}"
            os.makedirs(video_dir, exist_ok=True)
            
            status_msg = await callback_query.message.edit_text("⏳ جاري تحميل أفضل جودة متاحة...")
            
            # خيارات التحميل لأفضل جودة
            ydl_opts = {
                'format': 'best[height<=1080]/best',  # أفضل جودة حتى 1080p
                'outtmpl': f'{video_dir}/%(title)s.%(ext)s',
                'quiet': False,
                'no_warnings': False,
                'progress_hooks': [progress_hook],
                'concurrent_fragments': 4,
                'buffersize': 16384,
                'http_chunk_size': 10485760,
                'ffmpeg_location': '/home/runner/.nix-profile/bin/ffmpeg',
            }
            
        elif data.startswith("audio_"):
            # تحميل صوت فقط
            parts = data.split("_")
            video_id = parts[1]
            format_id = parts[2] if len(parts) > 2 else None
            
            if video_id not in video_info_cache:
                await callback_query.answer("❌ انتهت صلاحية الرابط", show_alert=True)
                return
                
            await callback_query.answer("⏳ جاري التحميل...")
            
            # إنشاء مجلد خاص لهذا الفيديو
            video_dir = f"downloads/{video_id}"
            os.makedirs(video_dir, exist_ok=True)
            
            status_msg = await callback_query.message.edit_text("⏳ جاري تحميل الصوت من YouTube...")
            
            # خيارات التحميل للصوت
            if format_id:
                # صيغة محددة
                ydl_opts = {
                    'format': format_id,
                    'outtmpl': f'{video_dir}/%(title)s.%(ext)s',
                    'quiet': False,
                    'progress_hooks': [progress_hook],
                    'concurrent_fragments': 4,
                    'buffersize': 16384,
                    'http_chunk_size': 10485760,
                    'ffmpeg_location': '/home/runner/.nix-profile/bin/ffmpeg',
                }
            else:
                # أفضل صوت وتحويل لMP3
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': f'{video_dir}/%(title)s.%(ext)s',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'quiet': False,
                    'progress_hooks': [progress_hook],
                    'concurrent_fragments': 4,
                    'buffersize': 16384,
                    'http_chunk_size': 10485760,
                    'ffmpeg_location': '/home/runner/.nix-profile/bin/ffmpeg',
                }
                
            cache_data = video_info_cache[video_id]
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([cache_data['url']])
            except Exception as download_error:
                await status_msg.edit_text(f"❌ فشل في التحميل: {str(download_error)}")
                return
        
        # لا حاجة لتحميل إضافي هنا حيث تم التحميل أعلاه حسب النوع
        
        # البحث عن الملف المحمل
        import glob
        downloaded_files = glob.glob(f'{video_dir}/*')
        
        if not downloaded_files:
            await status_msg.edit_text("❌ لم يتم العثور على الملف المحمل")
            return
        
        file_path = downloaded_files[0]
        file_size = os.path.getsize(file_path)
        
        # التحقق من حجم الملف
        if file_size > 2 * 1024 * 1024 * 1024:  # 2GB
            await status_msg.edit_text("❌ حجم الملف كبير جداً (أكثر من 2GB)")
            # حذف الملف والمجلد
            os.remove(file_path)
            os.rmdir(video_dir)
            return
        
        # عرض معلومات الملف
        file_size_mb = round(file_size / (1024 * 1024), 2)
        await status_msg.edit_text(
            f"📁 **تم التحميل بنجاح!**\n\n"
            f"📊 **حجم الملف:** {file_size_mb} MB\n"
            f"📤 **جاري رفع الملف إلى Telegram...**"
        )
        
        # رفع الملف مع progress
        try:
            caption = f"🎬 **{cache_data['title']}**\n📊 الحجم: {file_size_mb} MB"
            
            if data.startswith("audio_"):
                await upload_with_progress(
                    client, 
                    callback_query.message.chat.id, 
                    file_path, 
                    caption, 
                    is_audio=True
                )
            else:
                await upload_with_progress(
                    client, 
                    callback_query.message.chat.id, 
                    file_path, 
                    caption, 
                    is_audio=False
                )
            
            await status_msg.edit_text("✅ تم الرفع بنجاح!")
            
        except Exception as upload_error:
            await status_msg.edit_text(f"❌ فشل في رفع الملف: {str(upload_error)}")
        
        # حذف الملف والمجلد بعد الرفع
        try:
            os.remove(file_path)
            os.rmdir(video_dir)
        except:
            pass
        
        # حذف البيانات من الذاكرة المؤقتة
        del video_info_cache[video_id]
        
    except Exception as e:
        await callback_query.message.edit_text(f"❌ خطأ عام: {str(e)}")

if __name__ == "__main__":
    # إنشاء مجلد التحميل
    os.makedirs("downloads", exist_ok=True)
    
    print("🤖 بدء تشغيل البوت...")
    print("🔍 التحقق من المتطلبات...")
    
    # التحقق من ffmpeg
    ffmpeg_ok = check_ffmpeg()
    if not ffmpeg_ok:
        print("⚠️ تحذير: قد تواجه مشاكل في دمج الصوت مع الفيديو")
    
    print("✨ المميزات:")
    print("   • دعم الملفات الكبيرة حتى 2GB باستخدام Bot API الجديد")
    print("   • تحميل متوازي مع concurrent fragments")
    print("   • رفع مُحسَّن بدون تقسيم للملفات تحت 2GB")
    print("   • عرض تقدم التحميل والرفع")
    print("   • تقسيم تلقائي فقط للملفات الأكبر من 2GB")
    print("   • دمج تلقائي للصوت مع الفيديو")
    
    app.run()
