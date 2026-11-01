# ====================================================================
# FlenConvert Bot - Main Bot File
# Bot Telegram Konversi File dengan Reply Keyboard
#   - TXT <-> VCF
#   - Gabung TXT/VCF
#   - Potong VCF
#   - Rapikan TXT
#   - MSG to TXT
#   - XLS to TXT
#   - ADM & NVY Format
#
# Premium Features:
#   - Blue branding link (Markdown link)
#   - Bold/italic formatting
#   - Decorative separators
#   - Inline keyboard untuk multi-file ops
#
# Cara pakai di Termux:
#   1. Edit config.json, masukkan token dari @BotFather
#   2. pip install -r requirements.txt
#   3. python bot.py
# ====================================================================

import os
import re
import json
import sys
import asyncio
import logging
import tempfile
from datetime import datetime, timedelta
from typing import Optional

# ============================================================
# PYTHON 3.14+ COMPATIBILITY FIX
# Python 3.14 menghapus auto-create event loop di main thread.
# python-telegram-bot 21.x menggunakan asyncio.get_event_loop()
# yang akan raise RuntimeError di Python 3.14.
# Fix: buat event loop manual SEBELUM library dipanggil.
# ============================================================
def _fix_event_loop():
    """Pastikan event loop tersedia untuk Python 3.14+."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Loop closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop

# Panggil fix SEKARANG juga (sebelum import telegram),
# agar library tidak error saat inisialisasi.
_fix_event_loop()

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# Import modul konversi
from converters import (
    txt_to_vcf,
    vcf_to_txt,
    merge_txt,
    merge_vcf,
    split_vcf,
    clean_txt,
    msg_to_txt,
    xls_to_txt,
    to_adm_nvy_format,
    zip_directory,
    COUNTRY_CODES,
    list_supported_countries,
    parse_manual_numbers,
    manual_to_vcf,
    manual_to_txt,
    manual_to_adm_nvy,
)

# --------------------------------------------------------------------
# KONFIGURASI
# --------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

TOKEN = CONFIG['bot_token']
ADMIN_USERNAME = CONFIG.get('admin_username', 'AnggaOfficial')
BOT_NAME = CONFIG.get('bot_name', 'FlenConvert')
OWNER_ID = CONFIG.get('owner_id')
DEFAULT_CHUNK = CONFIG.get('default_vcf_chunk_size', 100)
MAX_MERGE = CONFIG.get('max_merge_files', 20)
NAME_PREFIX = CONFIG.get('contact_name_prefix', 'Contact')
ADM_FMT = CONFIG.get('adm_format', 'ADM-{num:03d}:{phone}')
NVY_FMT = CONFIG.get('nvy_format', 'NVY-{num:03d}:{phone}')
DEFAULT_COUNTRY_CODE = CONFIG.get('default_country_code', '+62')
DEFAULT_COUNTRY_NAME = CONFIG.get('default_country_name', 'Indonesia')

# Premium & QRIS configuration
QRIS_IMAGE_PATH = os.path.join(BASE_DIR, CONFIG.get('qris_image_path', 'qris_angga_official.png'))
QRIS_NMID = CONFIG.get('qris_nmid', 'ID1026593282423')
QRIS_MERCHANT = CONFIG.get('qris_merchant', 'Angga Official')
PREMIUM_PACKAGES = CONFIG.get('premium_packages', [])

# Database premium users (persistent storage)
PREMIUM_DB_PATH = os.path.join(BASE_DIR, 'premium_users.json')

# Daftar fitur yang HANYA bisa dipakai user premium.
# Owner bisa edit di config.json (key: "premium_only_features") untuk toggle.
# Default: fitur "power user" premium-only, fitur basic tetap free.
DEFAULT_PREMIUM_ONLY_FEATURES = [
    'adm_nvy',         # ADM & NVY format
    'split_vcf',       # POTONG VCF
    'merge_vcf',       # Gabung VCF
    'merge_txt',       # Gabung TXT
    'xls_to_txt',      # XLS to TXT
    'msg_to_txt',      # MSG to TXT
    'manual_input',    # Input Manual
]
PREMIUM_ONLY_FEATURES = set(CONFIG.get('premium_only_features', DEFAULT_PREMIUM_ONLY_FEATURES))

# Negara-negara populer untuk ditampilkan di inline keyboard (10 pertama)
# Sisanya bisa diakses via tombol "Lainnya"
POPULAR_COUNTRIES = [
    ("ID", "🇮🇩 Indonesia +62"),
    ("MY", "🇲🇾 Malaysia +60"),
    ("SG", "🇸🇬 Singapore +65"),
    ("TH", "🇹🇭 Thailand +66"),
    ("PH", "🇵🇭 Philippines +63"),
    ("US", "🇺🇸 United States +1"),
    ("GB", "🇬🇧 United Kingdom +44"),
    ("AU", "🇦🇺 Australia +61"),
    ("JP", "🇯🇵 Japan +81"),
    ("KR", "🇰🇷 South Korea +82"),
    ("CN", "🇨🇳 China +86"),
    ("IN", "🇮🇳 India +91"),
]

DEV_LINK = f"https://t.me/{ADMIN_USERNAME}"
# Branding blue link - ini yang muncul berwarna biru di Telegram
BRANDING_BLUE = f"[Bot Convert File By Angga Official]({DEV_LINK})"

# --------------------------------------------------------------------
# LOGGING
# --------------------------------------------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# Kurangi noise dari library
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)


# --------------------------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------------------------
def md_escape(text: str) -> str:
    """Escape karakter special Markdown (legacy mode)."""
    if not text:
        return ""
    return re.sub(r'([_*\[\]\(\)`])', r'\\\1', str(text))


def get_main_menu() -> ReplyKeyboardMarkup:
    """
    Susunan tombol Reply Keyboard utama.
    Layout mengikuti versi asli (6 baris) + tombol Premium + tombol Input Manual.
    """
    keyboard = [
        # Baris 1: Status (1 tombol, full width)
        [KeyboardButton("💎 Status 💎")],

        # Baris 2: ADM & NVY + Rapikan TXT
        [KeyboardButton("🗂️ ADM & NVY 🗂️"), KeyboardButton("📦 Rapikan TXT 📦")],

        # Baris 3: POTONG VCF + MSG to TXT
        [KeyboardButton("📊 POTONG VCF 📊"), KeyboardButton("📄 MSG to TXT 📄")],

        # Baris 4: TXT to VCF + BAGI VCF
        [KeyboardButton("📝 TXT to VCF 📝"), KeyboardButton("📁 BAGI VCF 📁")],

        # Baris 5: XLS to TXT + VCF to TXT
        [KeyboardButton("📈 XLS to TXT 📈"), KeyboardButton("♻️ VCF to TXT ♻️")],

        # Baris 6: Gabung TXT + Gabung VCF
        [KeyboardButton("📥 Gabung TXT 📥"), KeyboardButton("📥 Gabung VCF 📥")],

        # Baris 7: Input Manual + Premium
        [KeyboardButton("⌨️ Input Manual ⌨️"), KeyboardButton("💎 𝗣𝗥𝗘𝗠𝗜𝗨𝗠 💎")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_manual_format_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard untuk pilih format output Input Manual."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 ke VCF (kontak)", callback_data="manual_vcf"),
         InlineKeyboardButton("📄 ke TXT (rapikan)", callback_data="manual_txt")],
        [InlineKeyboardButton("🗂️ ke ADM Format", callback_data="manual_ADM"),
         InlineKeyboardButton("🗂️ ke NVY Format", callback_data="manual_NVY")],
        [InlineKeyboardButton("✨ REQ NAME (Custom)", callback_data="manual_CUSTOM")],
        [InlineKeyboardButton("❌ Batal", callback_data="manual_cancel")],
    ])


def get_finish_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard untuk tombol 'Selesai' pada mode multi-file."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Selesai & Proses", callback_data="finish_collect")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel_collect")],
    ])


def get_country_keyboard(action: str) -> InlineKeyboardMarkup:
    """
    Inline keyboard untuk pilih kode negara.
    Args:
        action: nama aksi yang akan dilakukan setelah pilih negara
                ('txt_to_vcf', 'clean_txt', 'adm_nvy_ADM', 'adm_nvy_NVY')
    """
    # 12 negara populer, dibagi 3 kolom x 4 baris
    rows = []
    for i in range(0, len(POPULAR_COUNTRIES), 3):
        row = []
        for code, label in POPULAR_COUNTRIES[i:i+3]:
            row.append(InlineKeyboardButton(label, callback_data=f"country_{action}_{code}"))
        rows.append(row)
    # Tombol "Lainnya" untuk lihat semua 89 negara
    rows.append([InlineKeyboardButton("🌍 Lihat Semua Negara", callback_data=f"country_more_{action}_0")])
    return InlineKeyboardMarkup(rows)


def get_all_countries_keyboard(action: str, page: int = 0) -> InlineKeyboardMarkup:
    """
    Inline keyboard paginasi untuk semua negara (89 negara).
    15 negara per halaman.
    """
    all_countries = list_supported_countries()  # [(code, dial, name), ...]
    per_page = 15
    total_pages = (len(all_countries) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    end = start + per_page
    page_items = all_countries[start:end]

    # 3 kolom x 5 baris
    rows = []
    for i in range(0, len(page_items), 3):
        row = []
        for code, dial, name in page_items[i:i+3]:
            label = f"{code} {dial}"
            row.append(InlineKeyboardButton(label, callback_data=f"country_{action}_{code}"))
        rows.append(row)

    # Tombol navigasi
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"country_more_{action}_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"country_more_{action}_{page+1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ Kembali ke Populer", callback_data=f"country_back_{action}")])
    return InlineKeyboardMarkup(rows)


def get_country_display(code: str) -> str:
    """Return string display untuk negara, misal '🇮🇩 Indonesia (+62)'."""
    code = code.upper()
    if code in COUNTRY_CODES:
        dial, name = COUNTRY_CODES[code]
        return f"{name} ({dial})"
    return f"Unknown ({code})"


def branding_footer() -> str:
    """Footer branding (warna biru karena link)."""
    return (
        f"\n\n━━━━━━━━━━━━━━━━━━\n"
        f"💎 {BRANDING_BLUE} 💎\n"
        f"━━━━━━━━━━━━━━━━━━"
    )


def safe_delete_message(func):
    """Decorator untuk handle error pada message edit/delete."""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Message operation failed: {e}")
    return wrapper


# --------------------------------------------------------------------
# PREMIUM USER DATABASE (persistent storage di premium_users.json)
# --------------------------------------------------------------------
def load_premium_db() -> dict:
    """Load database premium users dari JSON file."""
    try:
        if os.path.exists(PREMIUM_DB_PATH):
            with open(PREMIUM_DB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Gagal load premium DB: {e}")
    return {}


def save_premium_db(data: dict) -> bool:
    """Simpan database premium users ke JSON file."""
    try:
        with open(PREMIUM_DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Gagal save premium DB: {e}")
        return False


def add_premium_user(user_id: int, package_id: str, package_name: str,
                     duration_days: int, username: str = "") -> dict:
    """
    Tambah/upgrade user ke premium di database.

    Args:
        user_id: ID Telegram user
        package_id: ID paket (daily/weekly/monthly/lifetime)
        package_name: Nama paket
        duration_days: durasi premium dalam hari (9999 = lifetime)
        username: username Telegram user (optional)

    Returns: record premium user yang baru disimpan
    """
    db = load_premium_db()
    key = str(user_id)

    now = datetime.now()
    if duration_days >= 9999:
        # Lifetime - tidak ada expiry
        expires_at = None
        duration_str = "Lifetime"
    else:
        # Cek apakah user sudah premium - kalau ya, extend dari expiry lama
        existing = db.get(key, {})
        existing_expiry_str = existing.get('expires_at')
        if existing_expiry_str:
            try:
                existing_expiry = datetime.fromisoformat(existing_expiry_str)
                if existing_expiry > now:
                    # Extend dari expiry lama
                    expires_at = existing_expiry + timedelta(days=duration_days)
                else:
                    # Sudah expired, mulai dari sekarang
                    expires_at = now + timedelta(days=duration_days)
            except Exception:
                expires_at = now + timedelta(days=duration_days)
        else:
            expires_at = now + timedelta(days=duration_days)
        duration_str = f"{duration_days} hari"

    record = {
        'user_id': user_id,
        'username': username or '',
        'package': package_id,
        'package_name': package_name,
        'duration_days': duration_days,
        'activated_at': now.isoformat(),
        'expires_at': expires_at.isoformat() if expires_at else None,
    }
    db[key] = record
    save_premium_db(db)
    logger.info(f"Premium user added/updated: {user_id} ({package_name})")
    return record


def is_user_premium(user_id: int) -> bool:
    """
    Cek apakah user masih aktif premium (belum expired).
    Lifetime user selalu return True.
    """
    db = load_premium_db()
    record = db.get(str(user_id))
    if not record:
        return False

    expires_at_str = record.get('expires_at')
    if not expires_at_str:
        # Lifetime premium
        return True

    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        return datetime.now() < expires_at
    except Exception:
        return False


def get_premium_info(user_id: int) -> dict:
    """Ambil info premium user (paket, expiry, dll)."""
    db = load_premium_db()
    return db.get(str(user_id), {})


def remove_premium_user(user_id: int) -> bool:
    """Hapus user dari database premium."""
    db = load_premium_db()
    key = str(user_id)
    if key in db:
        del db[key]
        save_premium_db(db)
        return True
    return False


def is_feature_premium(feature_name: str) -> bool:
    """Cek apakah sebuah fitur butuh premium."""
    return feature_name in PREMIUM_ONLY_FEATURES


async def check_premium_access(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                feature_name: str) -> bool:
    """
    Cek apakah user boleh pakai fitur premium.
    Kalau TIDAK boleh, kirim pesan yang minta upgrade + return False.
    Kalau boleh, return True (handler lanjut).

    Args:
        update: Update object
        context: Context object
        feature_name: nama fitur (misal 'adm_nvy', 'manual_input')

    Returns:
        True jika user boleh pakai fitur, False kalau tidak.
    """
    user_id = update.effective_user.id

    # Kalau fitur bukan premium-only, lewati cek
    if not is_feature_premium(feature_name):
        return True

    # Owner selalu boleh pakai semua fitur
    if OWNER_ID and user_id == OWNER_ID:
        return True

    # Cek apakah user premium aktif
    if is_user_premium(user_id):
        return True

    # User belum premium - kirim pesan minta upgrade
    feature_labels = {
        'adm_nvy': '🗂️ ADM & NVY Format',
        'split_vcf': '📊 POTONG VCF',
        'merge_vcf': '📥 Gabung VCF',
        'merge_txt': '📥 Gabung TXT',
        'xls_to_txt': '📈 XLS to TXT',
        'msg_to_txt': '📄 MSG to TXT',
        'manual_input': '⌨️ Input Manual',
    }
    feature_label = feature_labels.get(feature_name, feature_name)

    # Cari paket termurah untuk ditampilkan
    cheapest = None
    if PREMIUM_PACKAGES:
        cheapest = min(PREMIUM_PACKAGES, key=lambda p: p.get('price', 0))
    price_hint = ""
    if cheapest:
        price = cheapest.get('price', 0)
        price_str = f"Rp{price:,}".replace(",", ".")
        price_hint = f"\n\n💰 Mulai dari *{price_str}* ({cheapest.get('name', '')})"

    # Inline keyboard untuk langsung ke menu premium
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Upgrade Premium Sekarang", callback_data="premium_show_menu")],
    ])

    message = (
        f"🔒 *Fitur Premium*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Maaf, fitur *{feature_label}* khusus member Premium.\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"\n🎁 *Keuntungan Premium:*"
        f"\n  • Akses semua fitur eksklusif"
        f"\n  • Konversi tanpa batas"
        f"\n  • Semua negara tersedia"
        f"\n  • Tanpa watermark"
        f"\n  • Prioritas support"
        f"{price_hint}"
        f"\n\nKlik tombol di bawah untuk lihat paket Premium 👇"
        f"{branding_footer()}"
    )

    try:
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )
    except Exception:
        # Kalau update.message tidak ada (misal dari callback), pakai effective_chat
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"Gagal kirim pesan premium gate: {e}")

    return False


# --------------------------------------------------------------------
# HELPER: Download file dengan retry & error handling
# --------------------------------------------------------------------
MAX_FILE_SIZE_MB = 20  # Batas Telegram Bot API (default)
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


async def download_telegram_file(document, save_path: str, max_retries: int = 3) -> bool:
    """
    Download file dari Telegram dengan retry logic dan error handling.

    Args:
        document: objek Document dari telegram
        save_path: path lokal untuk simpan file
        max_retries: jumlah percobaan ulang jika gagal

    Returns:
        True jika berhasil, False jika gagal

    Raises:
        RuntimeError dengan pesan user-friendly jika gagal total
    """
    # Cek ukuran file dulu
    file_size = document.file_size or 0
    if file_size > MAX_FILE_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        raise RuntimeError(
            f"File terlalu besar ({size_mb:.1f} MB). "
            f"Maksimal {MAX_FILE_SIZE_MB} MB (batas Telegram Bot API)."
        )

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            file = await document.get_file()
            await file.download_to_drive(save_path)
            return True
        except Exception as e:
            last_error = e
            error_type = type(e).__name__
            logger.warning(f"Download attempt {attempt}/{max_retries} failed: {error_type}: {e}")

            # Jangan retry kalau errornya permanent (BadRequest)
            if 'BadRequest' in error_type or 'file is too big' in str(e).lower():
                raise RuntimeError(
                    f"File tidak bisa didownload: {e}\n"
                    f"Mungkin file terlalu besar atau sudah expired."
                )

            if attempt < max_retries:
                import asyncio
                await asyncio.sleep(2 * attempt)  # exponential backoff
            else:
                # Last attempt juga gagal
                if 'TimedOut' in error_type or 'timeout' in str(e).lower():
                    raise RuntimeError(
                        "Download timeout - koneksi internet terlalu lambat.\n"
                        "Coba:\n"
                        "1. Gunakan koneksi WiFi yang stabil\n"
                        "2. Atau file yang lebih kecil\n"
                        "3. Atau coba lagi beberapa saat"
                    )
                elif 'NetworkError' in error_type or 'Connection' in str(e):
                    raise RuntimeError(
                        "Gagal terhubung ke server Telegram.\n"
                        "Cek koneksi internet Anda dan coba lagi."
                    )
                else:
                    raise RuntimeError(f"Gagal download file: {e}")

    raise RuntimeError(f"Download gagal setelah {max_retries} percobaan. Error: {last_error}")


# --------------------------------------------------------------------
# COMMAND HANDLERS
# --------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /start - menampilkan welcome + keyboard."""
    user = update.effective_user
    name = md_escape(user.first_name or "User")

    welcome = (
        f"👋 Hai, *{name}*!\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ *{BOT_NAME}* ⚡\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Saya dapat convert file secara instan 🚀\n\n"
        f"⚠️ *Note:* Order bot ini hanya melalui "
        f"[{ADMIN_USERNAME}]({DEV_LINK}), "
        f"selain itu dipastikan *SCAM*‼️\n"
        f"{branding_footer()}\n\n"
        f"Pilih menu di bawah untuk mulai 👇"
    )

    # Reset state user
    context.user_data.clear()

    await update.message.reply_text(
        welcome,
        reply_markup=get_main_menu(),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /help."""
    help_text = (
        f"📖 *Panduan Penggunaan*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📄 *TXT to VCF* - Convert daftar nomor ke kontak VCF\n"
        f"♻️ *VCF to TXT* - Ekstrak nomor dari VCF ke TXT\n"
        f"📥 *Gabung TXT/VCF* - Gabungkan beberapa file\n"
        f"📊 *Potong VCF* - Pecah VCF besar jadi kecil\n"
        f"📜 *Rapikan TXT* - Hapus duplikat & format nomor\n"
        f"📂 *MSG to TXT* - Simpan pesan ke file TXT\n"
        f"📈 *XLS to TXT* - Convert Excel ke TXT\n"
        f"🗂️ *ADM & NVY* - Format kontak khusus\n"
        f"   • ADM-001:+62xxx\n"
        f"   • NVY-001:+62xxx\n"
        f"   • ✨ REQ NAME: custom, misal ANGGA-001:+62xxx\n"
        f"💎 *Premium* - Upgrade ke fitur premium (bayar QRIS)\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Cukup klik tombol menu, lalu ikuti instruksi.\n"
        f"🌍 *Support 89 negara* (Indo, US, UK, AU, SG, dll)\n"
        f"{branding_footer()}"
    )
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_markup=get_main_menu(),
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /cancel - batalkan operasi saat ini."""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Operasi dibatalkan.\nKlik menu untuk mulai lagi 👇",
        reply_markup=get_main_menu(),
    )


# --------------------------------------------------------------------
# STATUS
# --------------------------------------------------------------------
async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan status bot & user, termasuk status premium."""
    user = update.effective_user
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Cek status premium user
    premium_info = get_premium_info(user.id)
    is_premium = is_user_premium(user.id)

    if is_premium:
        if premium_info.get('expires_at') is None:
            # Lifetime premium
            premium_status = "💎 *Premium (Lifetime)*"
            premium_detail = f"   • Paket: *{premium_info.get('package_name', 'Premium')}*\n"
            premium_detail += f"   • Status: *Aktif Selamanya* ✅\n"
            activated = premium_info.get('activated_at', '')[:10] if premium_info.get('activated_at') else '-'
            premium_detail += f"   • Aktif sejak: `{activated}`\n"
        else:
            # Premium berbatas waktu
            expires_str = premium_info.get('expires_at', '')
            try:
                expires_dt = datetime.fromisoformat(expires_str)
                days_left = (expires_dt - datetime.now()).days
                expires_display = expires_dt.strftime('%Y-%m-%d %H:%M')
                premium_status = f"💎 *Premium ({days_left} hari lagi)*"
                premium_detail = f"   • Paket: *{premium_info.get('package_name', 'Premium')}*\n"
                premium_detail += f"   • Expired: `{expires_display}`\n"
                premium_detail += f"   • Sisa: *{days_left} hari* ✅\n"
            except Exception:
                premium_status = "💎 *Premium*"
                premium_detail = ""
    else:
        premium_status = "🆓 *User Biasa (Free)*"
        premium_detail = "   • Akses fitur basic saja\n"
        premium_detail += "   • Upgrade untuk buka semua fitur 🔓\n"

    # Daftar fitur premium yang terkunci untuk user free
    locked_features = []
    feature_label_map = {
        'adm_nvy': '🗂️ ADM & NVY',
        'split_vcf': '📊 POTONG VCF',
        'merge_vcf': '📥 Gabung VCF',
        'merge_txt': '📥 Gabung TXT',
        'xls_to_txt': '📈 XLS to TXT',
        'msg_to_txt': '📄 MSG to TXT',
        'manual_input': '⌨️ Input Manual',
    }
    if not is_premium and not (OWNER_ID and user.id == OWNER_ID):
        for feat in PREMIUM_ONLY_FEATURES:
            label = feature_label_map.get(feat, feat)
            locked_features.append(f"🔒 {label}")

    locked_section = ""
    if locked_features:
        locked_section = (
            f"\n\n*Fitur Premium (terkunci):*\n"
            + "\n".join(locked_features)
            + f"\n\n💎 Upgrade untuk buka semua fitur!"
        )

    # Daftar fitur yang tersedia (free + premium)
    available_features = [
        "✅ TXT to VCF",
        "✅ VCF to TXT",
        "✅ Rapikan TXT",
    ]
    if is_premium or (OWNER_ID and user.id == OWNER_ID):
        available_features.extend([
            "✅ ADM & NVY",
            "✅ POTONG VCF",
            "✅ Gabung TXT/VCF",
            "✅ XLS to TXT",
            "✅ MSG to TXT",
            "✅ Input Manual",
        ])
    available_section = (
        f"\n\n*Fitur Tersedia:*"
        f"\n" + "\n".join(available_features)
    )

    status_text = (
        f"📊 *Status Bot*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Nama: {md_escape(user.first_name or '-')}\n"
        f"🆔 User ID: `{user.id}`\n"
        f"🤖 Bot: *{BOT_NAME}*\n"
        f"💎 Status: {premium_status}\n"
        f"{premium_detail}"
        f"⚡ Server: *Online*\n"
        f"🕐 Server Time: `{now}`\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"📞 Admin: [{ADMIN_USERNAME}]({DEV_LINK})"
        f"{available_section}"
        f"{locked_section}"
        f"{branding_footer()}"
    )

    # Tombol upgrade kalau belum premium
    reply_kb = get_main_menu()
    if not is_premium and not (OWNER_ID and user.id == OWNER_ID):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Upgrade ke Premium", callback_data="premium_show_menu")],
        ])
        await update.message.reply_text(
            status_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=get_main_menu(),
        )
        await update.message.reply_text(
            "👆 Klik tombol di bawah untuk upgrade:",
            reply_markup=reply_kb,
        )
    else:
        await update.message.reply_text(
            status_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=get_main_menu(),
        )


# --------------------------------------------------------------------
# 1. TXT -> VCF
# --------------------------------------------------------------------
async def start_txt_to_vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'txt_to_vcf_await_country'
    await update.message.reply_text(
        f"📄 *TXT to VCF Converter*\n\n"
        f"Pilih kode negara untuk nomor lokal Anda:\n"
        f"(Nomor dengan prefix `+` atau `00` akan otomatis dideteksi)",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_country_keyboard('txt_to_vcf'),
    )


async def handle_txt_to_vcf_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setelah user pilih negara, minta kirim file TXT."""
    query = update.callback_query
    await query.answer()

    country_code = query.data.split('_')[-1]
    dial, name = COUNTRY_CODES.get(country_code, ("+62", "Indonesia"))
    context.user_data['mode'] = 'txt_to_vcf'
    context.user_data['country_code'] = dial
    context.user_data['country_display'] = f"{name} ({dial})"

    await query.edit_message_text(
        f"✅ Negara: *{name} ({dial})*\n\n"
        f"Kirim file *TXT* berisi daftar nomor (satu nomor per baris).\n\n"
        f"Format yang didukung:\n"
        f"  • `0812xxx` (lokal) → {dial}812xxx\n"
        f"  • `{dial}812xxx` (tanpa +) → {dial}812xxx\n"
        f"  • `{dial}812xxx` (dengan +) → {dial}812xxx\n"
        f"  • `00{dial[1:]}812xxx` (00 prefix) → {dial}812xxx\n"
        f"  • Nomor negara lain dengan `+` prefix → otomatis\n\n"
        f"Kirim /cancel untuk batal.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def process_txt_to_vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith('.txt'):
        await update.message.reply_text("⚠️ File harus berformat *.txt*", parse_mode=ParseMode.MARKDOWN)
        return

    country_code = context.user_data.get('country_code', DEFAULT_COUNTRY_CODE)
    status_msg = await update.message.reply_text("⏳ Mengunduh & memproses...")
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, doc.file_name)
        output_path = os.path.join(tmp, 'output.vcf')

        try:
            await download_telegram_file(doc, input_path)

            await status_msg.edit_text("⏳ Konversi sedang berjalan...")
            success, total = txt_to_vcf(input_path, output_path, NAME_PREFIX, country_code)

            if success == 0:
                await status_msg.edit_text(
                    "❌ Tidak ada nomor valid ditemukan dalam file.\n"
                    f"Pastikan format: `0812xxx` atau `{country_code}812xxx`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            with open(output_path, 'rb') as f:
                country_display = context.user_data.get('country_display', DEFAULT_COUNTRY_NAME)
                await update.message.reply_document(
                    document=f,
                    filename=f"converted_{success}_contacts.vcf",
                    caption=(
                        f"✅ *Konversi Berhasil!*\n\n"
                        f"🌍 Country: *{country_display}*\n"
                        f"📊 Total baris: *{total}*\n"
                        f"✅ Nomor valid: *{success}*\n"
                        f"❌ Nomor invalid: *{total - success}*\n"
                        f"📦 Format: VCF v3.0\n"
                        f"{branding_footer()}"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            await status_msg.delete()
        except Exception as e:
            logger.exception("TXT to VCF error")
            await status_msg.edit_text(f"❌ Error: `{md_escape(str(e))}`", parse_mode=ParseMode.MARKDOWN)

    context.user_data['mode'] = None


# --------------------------------------------------------------------
# 2. VCF -> TXT
# --------------------------------------------------------------------
async def start_vcf_to_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'vcf_to_txt'
    await update.message.reply_text(
        f"♻️ *VCF to TXT Converter*\n\n"
        f"Kirim file *VCF* (kontak telepon).\n"
        f"Bot akan ekstrak semua nomor ke format TXT.\n\n"
        f"Kirim /cancel untuk batal.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu(),
    )


async def process_vcf_to_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(('.vcf', '.vcard')):
        await update.message.reply_text("⚠️ File harus berformat *.vcf*", parse_mode=ParseMode.MARKDOWN)
        return

    status_msg = await update.message.reply_text("⏳ Memproses...")
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, doc.file_name)
        output_path = os.path.join(tmp, 'extracted.txt')

        try:
            await download_telegram_file(doc, input_path)

            count = vcf_to_txt(input_path, output_path)

            if count == 0:
                await status_msg.edit_text("❌ Tidak ada nomor ditemukan dalam VCF.")
                return

            with open(output_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"extracted_{count}_numbers.txt",
                    caption=(
                        f"✅ *Ekstraksi Berhasil!*\n\n"
                        f"📊 Nomor diekstrak: *{count}*\n"
                        f"📦 Format: TXT (satu nomor per baris)\n"
                        f"{branding_footer()}"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            await status_msg.delete()
        except Exception as e:
            logger.exception("VCF to TXT error")
            await status_msg.edit_text(f"❌ Error: `{md_escape(str(e))}`", parse_mode=ParseMode.MARKDOWN)

    context.user_data['mode'] = None


# --------------------------------------------------------------------
# 3. Gabung TXT
# --------------------------------------------------------------------
async def start_merge_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Gating premium - cek apakah user boleh pakai fitur ini
    if not await check_premium_access(update, context, 'merge_txt'):
        return
    context.user_data['mode'] = 'merge_txt'
    context.user_data['files'] = []
    context.user_data['tmpdir'] = tempfile.mkdtemp(prefix='merge_txt_')
    await update.message.reply_text(
        f"📥 *Gabung TXT*\n\n"
        f"Kirim semua file *TXT* yang ingin digabung (maks {MAX_MERGE} file).\n"
        f"Duplikat akan otomatis dihapus.\n\n"
        f"Setelah selesai kirim semua file, klik tombol *Selesai* di bawah 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_finish_keyboard(),
    )


async def add_merge_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith('.txt'):
        await update.message.reply_text("⚠️ File harus *.txt*. Atau klik Selesai jika sudah selesai.")
        return

    files = context.user_data.get('files', [])
    if len(files) >= MAX_MERGE:
        await update.message.reply_text(f"⚠️ Maksimal {MAX_MERGE} file. Klik Selesai.")
        return

    tmpdir = context.user_data.get('tmpdir')
    if not tmpdir or not os.path.exists(tmpdir):
        tmpdir = tempfile.mkdtemp(prefix='merge_txt_')
        context.user_data['tmpdir'] = tmpdir

    save_path = os.path.join(tmpdir, f"file_{len(files)+1}_{doc.file_name}")
    await download_telegram_file(doc, save_path)
    files.append(save_path)
    context.user_data['files'] = files

    await update.message.reply_text(
        f"✅ File `{len(files)}` tersimpan: `{md_escape(doc.file_name)}`\n"
        f"Kirim file berikutnya atau klik *Selesai*.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_finish_keyboard(),
    )


async def finish_merge_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    files = context.user_data.get('files', [])
    if not files:
        await query.edit_message_text("❌ Tidak ada file dikumpulkan. Operasi dibatalkan.")
        context.user_data.clear()
        return

    status_msg = await query.edit_message_text("⏳ Menggabungkan file...")
    await context.bot.send_chat_action(query.message.chat.id, ChatAction.TYPING)

    tmpdir = context.user_data.get('tmpdir')
    output_path = os.path.join(tmpdir, 'merged.txt')

    try:
        final_count, original_count = merge_txt(files, output_path, dedupe=True)

        with open(output_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.message.chat.id,
                document=f,
                filename=f"merged_{final_count}_lines.txt",
                caption=(
                    f"✅ *Gabungan Berhasil!*\n\n"
                    f"📁 File digabung: *{len(files)}*\n"
                    f"📊 Total baris asli: *{original_count}*\n"
                    f"✅ Baris unik: *{final_count}*\n"
                    f"🗑️ Duplikat dihapus: *{original_count - final_count}*\n"
                    f"{branding_footer()}"
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        await status_msg.delete()
    except Exception as e:
        logger.exception("Merge TXT error")
        await status_msg.edit_text(f"❌ Error: `{md_escape(str(e))}`", parse_mode=ParseMode.MARKDOWN)
    finally:
        # Cleanup
        tmpdir = context.user_data.get('tmpdir')
        if tmpdir and os.path.exists(tmpdir):
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        context.user_data.clear()


# --------------------------------------------------------------------
# 4. Gabung VCF
# --------------------------------------------------------------------
async def start_merge_vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Gating premium - cek apakah user boleh pakai fitur ini
    if not await check_premium_access(update, context, 'merge_vcf'):
        return
    context.user_data['mode'] = 'merge_vcf'
    context.user_data['files'] = []
    context.user_data['tmpdir'] = tempfile.mkdtemp(prefix='merge_vcf_')
    await update.message.reply_text(
        f"📥 *Gabung VCF*\n\n"
        f"Kirim semua file *VCF* yang ingin digabung (maks {MAX_MERGE} file).\n\n"
        f"Setelah selesai, klik tombol *Selesai* di bawah 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_finish_keyboard(),
    )


async def add_merge_vcf_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(('.vcf', '.vcard')):
        await update.message.reply_text("⚠️ File harus *.vcf*. Atau klik Selesai jika sudah selesai.")
        return

    files = context.user_data.get('files', [])
    if len(files) >= MAX_MERGE:
        await update.message.reply_text(f"⚠️ Maksimal {MAX_MERGE} file. Klik Selesai.")
        return

    tmpdir = context.user_data.get('tmpdir')
    if not tmpdir or not os.path.exists(tmpdir):
        tmpdir = tempfile.mkdtemp(prefix='merge_vcf_')
        context.user_data['tmpdir'] = tmpdir

    save_path = os.path.join(tmpdir, f"file_{len(files)+1}_{doc.file_name}")
    try:
        await download_telegram_file(doc, save_path)
    except RuntimeError as e:
        await update.message.reply_text(
            f"❌ Gagal download file.\n\n`{md_escape(str(e))}`\n\n"
            f"Coba kirim ulang filenya, atau gunakan file yang lebih kecil.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_finish_keyboard(),
        )
        return
    except Exception as e:
        logger.exception("Merge TXT download error")
        await update.message.reply_text(
            f"❌ Error tidak terduga: `{md_escape(str(e))}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_finish_keyboard(),
        )
        return
    files.append(save_path)
    context.user_data['files'] = files

    await update.message.reply_text(
        f"✅ File `{len(files)}` tersimpan: `{md_escape(doc.file_name)}`\n"
        f"Kirim file berikutnya atau klik *Selesai*.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_finish_keyboard(),
    )


async def finish_merge_vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    files = context.user_data.get('files', [])
    if not files:
        await query.edit_message_text("❌ Tidak ada file dikumpulkan. Operasi dibatalkan.")
        context.user_data.clear()
        return

    status_msg = await query.edit_message_text("⏳ Menggabungkan VCF...")
    await context.bot.send_chat_action(query.message.chat.id, ChatAction.TYPING)

    tmpdir = context.user_data.get('tmpdir')
    output_path = os.path.join(tmpdir, 'merged.vcf')

    try:
        count = merge_vcf(files, output_path)

        with open(output_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.message.chat.id,
                document=f,
                filename=f"merged_{count}_contacts.vcf",
                caption=(
                    f"✅ *Gabungan VCF Berhasil!*\n\n"
                    f"📁 File digabung: *{len(files)}*\n"
                    f"👥 Total kontak: *{count}*\n"
                    f"{branding_footer()}"
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        await status_msg.delete()
    except Exception as e:
        logger.exception("Merge VCF error")
        await status_msg.edit_text(f"❌ Error: `{md_escape(str(e))}`", parse_mode=ParseMode.MARKDOWN)
    finally:
        tmpdir = context.user_data.get('tmpdir')
        if tmpdir and os.path.exists(tmpdir):
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        context.user_data.clear()


# --------------------------------------------------------------------
# 5. Potong VCF (Split VCF)
# --------------------------------------------------------------------
async def start_split_vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Gating premium - cek apakah user boleh pakai fitur ini
    if not await check_premium_access(update, context, 'split_vcf'):
        return
    context.user_data['mode'] = 'split_vcf'
    # Tampilkan pilihan ukuran chunk via inline keyboard
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("50 kontak", callback_data="split_50"),
            InlineKeyboardButton("100 kontak", callback_data="split_100"),
            InlineKeyboardButton("200 kontak", callback_data="split_200"),
        ],
        [InlineKeyboardButton("500 kontak", callback_data="split_500"),
         InlineKeyboardButton("1000 kontak", callback_data="split_1000")],
    ])
    await update.message.reply_text(
        f"📊 *Potong VCF*\n\n"
        f"Pilih jumlah kontak per file hasil pecahan:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )


async def handle_split_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chunk_size = int(query.data.split('_')[1])
    context.user_data['split_chunk'] = chunk_size
    context.user_data['mode'] = 'split_vcf'

    await query.edit_message_text(
        f"✅ Chunk size: *{chunk_size} kontak/file*\n\n"
        f"Sekarang kirim file *VCF* yang ingin dipecah.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def process_split_vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(('.vcf', '.vcard')):
        await update.message.reply_text("⚠️ File harus berformat *.vcf*", parse_mode=ParseMode.MARKDOWN)
        return

    chunk_size = context.user_data.get('split_chunk', DEFAULT_CHUNK)
    status_msg = await update.message.reply_text(f"⏳ Memecah VCF (chunk: {chunk_size})...")
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, doc.file_name)
        output_dir = os.path.join(tmp, 'output')
        os.makedirs(output_dir, exist_ok=True)
        zip_path = os.path.join(tmp, 'split_vcf.zip')

        try:
            await download_telegram_file(doc, input_path)

            file_count, total_contacts = split_vcf(input_path, output_dir, chunk_size)

            if file_count == 0:
                await status_msg.edit_text("❌ Tidak ada kontak ditemukan dalam VCF.")
                return

            # Zip semua file hasil pecahan
            zip_directory(output_dir, zip_path)

            with open(zip_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"split_{file_count}_files_{total_contacts}_contacts.zip",
                    caption=(
                        f"✅ *VCF Berhasil Dipecah!*\n\n"
                        f"📊 Total kontak: *{total_contacts}*\n"
                        f"📁 Jumlah file: *{file_count}*\n"
                        f"📦 Per file: *{chunk_size} kontak*\n"
                        f"🗜️ Format: ZIP (berisi semua file VCF)\n"
                        f"{branding_footer()}"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            await status_msg.delete()
        except Exception as e:
            logger.exception("Split VCF error")
            await status_msg.edit_text(f"❌ Error: `{md_escape(str(e))}`", parse_mode=ParseMode.MARKDOWN)

    context.user_data.clear()


# --------------------------------------------------------------------
# 6. Rapikan TXT
# --------------------------------------------------------------------
async def start_clean_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'clean_txt_await_country'
    await update.message.reply_text(
        f"📜 *Rapikan TXT*\n\n"
        f"Pilih kode negara untuk normalisasi nomor lokal:\n"
        f"(Nomor dengan prefix `+` atau `00` akan otomatis dideteksi)",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_country_keyboard('clean_txt'),
    )


async def handle_clean_txt_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setelah user pilih negara, minta kirim file TXT."""
    query = update.callback_query
    await query.answer()

    country_code = query.data.split('_')[-1]
    dial, name = COUNTRY_CODES.get(country_code, ("+62", "Indonesia"))
    context.user_data['mode'] = 'clean_txt'
    context.user_data['country_code'] = dial
    context.user_data['country_display'] = f"{name} ({dial})"

    await query.edit_message_text(
        f"✅ Negara: *{name} ({dial})*\n\n"
        f"Kirim file *TXT* berisi daftar nomor.\n"
        f"Bot akan:\n"
        f"  • Hapus duplikat\n"
        f"  • Normalisasi format (ke {dial}xxx)\n"
        f"  • Sortir secara alfabetis\n\n"
        f"Kirim /cancel untuk batal.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def process_clean_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith('.txt'):
        await update.message.reply_text("⚠️ File harus berformat *.txt*", parse_mode=ParseMode.MARKDOWN)
        return

    country_code = context.user_data.get('country_code', DEFAULT_COUNTRY_CODE)
    country_display = context.user_data.get('country_display', DEFAULT_COUNTRY_NAME)
    status_msg = await update.message.reply_text("⏳ Merapikan file...")
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, doc.file_name)
        output_path = os.path.join(tmp, 'cleaned.txt')

        try:
            await download_telegram_file(doc, input_path)

            final_count, original_count, duplicates = clean_txt(input_path, output_path, country_code)

            if final_count == 0:
                await status_msg.edit_text("❌ Tidak ada nomor valid ditemukan.")
                return

            with open(output_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"cleaned_{final_count}_unique.txt",
                    caption=(
                        f"✅ *File Dirapikan!*\n\n"
                        f"🌍 Country: *{country_display}*\n"
                        f"📊 Total baris asli: *{original_count}*\n"
                        f"✅ Nomor unik: *{final_count}*\n"
                        f"🗑️ Duplikat/invalid dihapus: *{duplicates}*\n"
                        f"🔧 Format: {country_code}xxx (sorted)\n"
                        f"{branding_footer()}"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            await status_msg.delete()
        except Exception as e:
            logger.exception("Clean TXT error")
            await status_msg.edit_text(f"❌ Error: `{md_escape(str(e))}`", parse_mode=ParseMode.MARKDOWN)

    context.user_data['mode'] = None


# --------------------------------------------------------------------
# 7. MSG to TXT
# --------------------------------------------------------------------
async def start_msg_to_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Gating premium - cek apakah user boleh pakai fitur ini
    if not await check_premium_access(update, context, 'msg_to_txt'):
        return
    context.user_data['mode'] = 'msg_to_txt'
    context.user_data['messages'] = []
    await update.message.reply_text(
        f"📂 *MSG to TXT Converter*\n\n"
        f"Kirim atau *forward* pesan-pesan yang ingin disimpan ke TXT.\n"
        f"Bot akan kumpulkan semua pesan, lalu simpan ke satu file.\n\n"
        f"Setelah selesai, klik *Selesai* di bawah 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_finish_keyboard(),
    )


async def collect_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kumpulkan pesan teks yang dikirim user."""
    msg = update.message
    text_parts = []

    # Ambil teks pesan
    if msg.text:
        text_parts.append(msg.text)
    elif msg.caption:
        text_parts.append(msg.caption)

    # Jika forward_date, tambahkan info pengirim asli
    if msg.forward_origin:
        try:
            origin = msg.forward_origin
            sender_name = getattr(origin, 'sender_user_name', None) or \
                          getattr(origin, 'hidden_sender_name', None) or \
                          getattr(origin, 'sender_chat_title', None) or "Unknown"
            text_parts.insert(0, f"[Forwarded from: {sender_name}]")
        except Exception:
            pass

    if not text_parts:
        await update.message.reply_text(
            "⚠️ Pesan tidak ada teks. Kirim pesan teks atau forward pesan.",
            reply_markup=get_finish_keyboard(),
        )
        return

    messages = context.user_data.get('messages', [])
    messages.append('\n'.join(text_parts))
    context.user_data['messages'] = messages

    await update.message.reply_text(
        f"✅ Pesan `{len(messages)}` tersimpan.\n"
        f"Kirim pesan berikutnya atau klik *Selesai*.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_finish_keyboard(),
    )


async def finish_msg_to_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    messages = context.user_data.get('messages', [])
    if not messages:
        await query.edit_message_text("❌ Tidak ada pesan dikumpulkan. Operasi dibatalkan.")
        context.user_data.clear()
        return

    status_msg = await query.edit_message_text("⏳ Menyusun file TXT...")

    with tempfile.TemporaryDirectory() as tmp:
        output_path = os.path.join(tmp, 'messages.txt')
        try:
            total_chars = msg_to_txt(messages, output_path)

            with open(output_path, 'rb') as f:
                await context.bot.send_document(
                    chat_id=query.message.chat.id,
                    document=f,
                    filename=f"messages_{len(messages)}_items.txt",
                    caption=(
                        f"✅ *Pesan Tersimpan!*\n\n"
                        f"📊 Jumlah pesan: *{len(messages)}*\n"
                        f"📝 Total karakter: *{total_chars}*\n"
                        f"📦 Format: TXT\n"
                        f"{branding_footer()}"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            await status_msg.delete()
        except Exception as e:
            logger.exception("MSG to TXT error")
            await status_msg.edit_text(f"❌ Error: `{md_escape(str(e))}`", parse_mode=ParseMode.MARKDOWN)

    context.user_data.clear()


# --------------------------------------------------------------------
# 8. XLS to TXT
# --------------------------------------------------------------------
async def start_xls_to_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Gating premium - cek apakah user boleh pakai fitur ini
    if not await check_premium_access(update, context, 'xls_to_txt'):
        return
    context.user_data['mode'] = 'xls_to_txt'
    await update.message.reply_text(
        f"📈 *XLS to TXT Converter*\n\n"
        f"Kirim file *Excel* (.xlsx atau .xls).\n"
        f"Bot akan convert semua sheet ke format TXT (tab-separated).\n\n"
        f"Kirim /cancel untuk batal.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu(),
    )


async def process_xls_to_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(('.xlsx', '.xls')):
        await update.message.reply_text("⚠️ File harus berformat *.xlsx* atau *.xls*", parse_mode=ParseMode.MARKDOWN)
        return

    status_msg = await update.message.reply_text("⏳ Mengonversi Excel...")
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, doc.file_name)
        output_path = os.path.join(tmp, 'output.txt')

        try:
            await download_telegram_file(doc, input_path)

            rows, sheets = xls_to_txt(input_path, output_path)

            if rows == 0:
                await status_msg.edit_text("❌ File Excel kosong atau tidak terbaca.")
                return

            with open(output_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"converted_{rows}_rows.txt",
                    caption=(
                        f"✅ *Konversi Excel Berhasil!*\n\n"
                        f"📊 Sheet diproses: *{sheets}*\n"
                        f"📋 Baris ditulis: *{rows}*\n"
                        f"📦 Format: TXT (tab-separated)\n"
                        f"{branding_footer()}"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            await status_msg.delete()
        except RuntimeError as e:
            # Error khusus: openpyxl belum terinstall
            logger.exception("XLS to TXT - openpyxl missing")
            await status_msg.edit_text(
                f"❌ *Module openpyxl belum terinstall*\n\n"
                f"Jalankan di Termux:\n"
                f"`pip install openpyxl`\n\n"
                f"Atau jalankan ulang `./setup.sh`",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.exception("XLS to TXT error")
            await status_msg.edit_text(
                f"❌ Error: `{md_escape(str(e))}`\n\n"
                f"Pastikan file Excel valid (.xlsx).",
                parse_mode=ParseMode.MARKDOWN
            )

    context.user_data['mode'] = None


# --------------------------------------------------------------------
# 9. ADM & NVY Format (dengan fitur REQ NAME custom prefix)
# --------------------------------------------------------------------
async def start_adm_nvy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu utama ADM & NVY - sekarang dengan opsi Custom Name."""
    # Gating premium - cek apakah user boleh pakai fitur ini
    if not await check_premium_access(update, context, 'adm_nvy'):
        return
    context.user_data['mode'] = 'adm_nvy_await'
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗂️ ADM Format", callback_data="fmt_ADM"),
         InlineKeyboardButton("🗂️ NVY Format", callback_data="fmt_NVY")],
        [InlineKeyboardButton("✨ REQ NAME (Custom)", callback_data="fmt_CUSTOM")],
    ])
    await update.message.reply_text(
        f"🗂️ *ADM & NVY Format Converter*\n\n"
        f"Pilih format output:\n\n"
        f"• *ADM* → format `ADM-001:+62xxx`\n"
        f"• *NVY* → format `NVY-001:+62xxx`\n"
        f"• *REQ NAME* → format custom, misal `ANGGA-001:+62xxx`\n\n"
        f"Pilih salah satu 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )


async def handle_adm_nvy_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setelah user pilih format ADM/NVY/CUSTOM, route ke handler yang sesuai."""
    query = update.callback_query
    await query.answer()

    fmt = query.data.split('_')[1]

    if fmt == 'CUSTOM':
        # Mode minta custom name dari user
        context.user_data['mode'] = 'adm_nvy_await_custom_name'
        context.user_data['format'] = 'CUSTOM'
        await query.edit_message_text(
            f"✨ *REQ NAME - Custom Prefix*\n\n"
            f"Ketik nama prefix yang Anda inginkan (3-35 karakter).\n\n"
            f"*Aturan:*\n"
            f"  • Hanya huruf besar/kecil dan angka\n"
            f"  • Tanpa spasi, simbol, atau karakter khusus\n"
            f"  • Contoh valid: `ANGGA`, `BOS`, `PREMIUM`, `VIP123`, `KONTAKPELANGGANBOS2024`\n\n"
            f"*Contoh output:* `ANGGA-001:+62xxx`\n\n"
            f"Kirim /cancel untuk batal.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ADM atau NVY - lanjut ke pilih negara
    context.user_data['mode'] = 'adm_nvy_await_country'
    context.user_data['format'] = fmt

    await query.edit_message_text(
        f"✅ Format: *{fmt}*\n\n"
        f"Sekarang pilih kode negara untuk nomor lokal:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_country_keyboard(f'adm_nvy_{fmt}'),
    )


async def handle_custom_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Capture custom name yang diketik user, lalu minta pilih negara."""
    text = update.message.text.strip()

    # Validasi: 3-35 karakter, alfanumerik saja
    if not text:
        await update.message.reply_text(
            "⚠️ Nama tidak boleh kosong. Ketik 3-35 karakter alfanumerik."
        )
        return

    if len(text) < 3 or len(text) > 35:
        await update.message.reply_text(
            f"⚠️ Panjang harus 3-35 karakter. Anda kirim: `{len(text)}` karakter.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not text.isalnum():
        await update.message.reply_text(
            "⚠️ Hanya boleh huruf dan angka (tanpa spasi/simbol). Coba lagi."
        )
        return

    # Normalize: huruf besar
    custom_prefix = text.upper()
    context.user_data['custom_prefix'] = custom_prefix
    context.user_data['mode'] = 'adm_nvy_await_country'
    context.user_data['format'] = custom_prefix  # pakai prefix sebagai format

    # Balas user + minta pilih negara
    await update.message.reply_text(
        f"✅ Custom prefix disimpan: *{custom_prefix}*\n\n"
        f"Contoh output: `{custom_prefix}-001:+62xxx`\n\n"
        f"Sekarang pilih kode negara untuk nomor lokal 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_country_keyboard(f'adm_nvy_{custom_prefix}'),
    )


async def handle_adm_nvy_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setelah user pilih negara, minta kirim file TXT."""
    query = update.callback_query
    await query.answer()

    # callback_data format: country_adm_nvy_{PREFIX}_{CODE}
    # PREFIX bisa ADM, NVY, atau custom (misal ANGGA)
    parts = query.data.split('_')
    # parts[0]='country', parts[1]='adm', parts[2]='nvy', parts[3]=PREFIX, parts[4]=CODE
    if len(parts) >= 5:
        fmt = parts[3]
        country_code = parts[4]
    else:
        # Fallback kalau parsing gagal
        fmt = context.user_data.get('format', 'ADM')
        country_code = parts[-1]

    dial, name = COUNTRY_CODES.get(country_code, ("+62", "Indonesia"))
    context.user_data['mode'] = 'adm_nvy'
    context.user_data['country_code'] = dial
    context.user_data['country_display'] = f"{name} ({dial})"
    context.user_data['format'] = fmt

    await query.edit_message_text(
        f"✅ Format: *{fmt}* | Negara: *{name} ({dial})*\n\n"
        f"Kirim file *TXT* berisi daftar nomor.\n"
        f"Output: `{fmt}-001:{dial}xxx` (per baris)\n\n"
        f"Kirim /cancel untuk batal.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def process_adm_nvy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith('.txt'):
        await update.message.reply_text("⚠️ File harus berformat *.txt*", parse_mode=ParseMode.MARKDOWN)
        return

    # fmt bisa: 'ADM', 'NVY', atau custom prefix (misal 'ANGGA')
    fmt = context.user_data.get('format', 'ADM')
    country_code = context.user_data.get('country_code', DEFAULT_COUNTRY_CODE)
    country_display = context.user_data.get('country_display', DEFAULT_COUNTRY_NAME)
    status_msg = await update.message.reply_text(f"⏳ Konversi ke format {fmt}...")
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, doc.file_name)
        output_path = os.path.join(tmp, f'output_{fmt.lower()}.txt')

        try:
            await download_telegram_file(doc, input_path)

            success, total = to_adm_nvy_format(input_path, output_path, fmt, country_code)

            if success == 0:
                await status_msg.edit_text("❌ Tidak ada nomor valid ditemukan.")
                return

            with open(output_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"{fmt.lower()}_{success}_numbers.txt",
                    caption=(
                        f"✅ *Konversi {fmt} Berhasil!*\n\n"
                        f"🌍 Country: *{country_display}*\n"
                        f"📊 Total baris: *{total}*\n"
                        f"✅ Nomor valid: *{success}*\n"
                        f"❌ Invalid: *{total - success}*\n"
                        f"📦 Format: `{fmt}-001:{country_code}xxx`\n"
                        f"{branding_footer()}"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
            await status_msg.delete()
        except Exception as e:
            logger.exception("ADM/NVY error")
            await status_msg.edit_text(f"❌ Error: `{md_escape(str(e))}`", parse_mode=ParseMode.MARKDOWN)

    context.user_data.clear()


# --------------------------------------------------------------------
# 10. PREMIUM (Pembayaran via QRIS)
# --------------------------------------------------------------------
def get_premium_packages_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard untuk pilih paket premium."""
    rows = []
    for pkg in PREMIUM_PACKAGES:
        price_str = f"Rp{pkg['price']:,}".replace(",", ".")
        label = f"{pkg['name']} - {price_str}"
        rows.append([InlineKeyboardButton(label, callback_data=f"premium_pkg_{pkg['id']}")])
    return InlineKeyboardMarkup(rows)


def get_premium_payment_keyboard(package_id: str) -> InlineKeyboardMarkup:
    """Inline keyboard setelah user pilih paket."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Saya Sudah Bayar", callback_data=f"premium_paid_{package_id}")],
        [InlineKeyboardButton("❌ Batal", callback_data="premium_cancel")],
    ])


def find_package(package_id: str) -> dict:
    """Cari paket berdasarkan ID."""
    for pkg in PREMIUM_PACKAGES:
        if pkg['id'] == package_id:
            return pkg
    return None


async def start_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu Premium - tampilkan daftar paket."""
    context.user_data['mode'] = 'premium'
    packages_text = "\n".join([
        f"💎 *{p['name']}* - Rp{p['price']:,}".replace(",", ".") +
        f" ({p['duration_days']} hari)" if p['duration_days'] < 9999 else " (Lifetime)"
        for p in PREMIUM_PACKAGES
    ])

    text = (
        f"💎 *Fitur Premium*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Keuntungan Premium:\n"
        f"  • Unlimited konversi file\n"
        f"  • Akses semua 89 negara\n"
        f"  • Tanpa watermark\n"
        f"  • Priority support\n"
        f"  • Custom branding\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Pilih paket di bawah 👇\n\n"
        f"{packages_text}\n"
        f"{branding_footer()}"
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_markup=get_premium_packages_keyboard(),
    )


async def handle_premium_show_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk callback 'premium_show_menu' dari tombol upgrade di pesan gate/status.

    Berbeda dari start_premium yang pakai update.message (text menu),
    callback ini dari inline button - pakai query.edit_message_text.
    """
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    context.user_data['mode'] = 'premium'
    packages_text = "\n".join([
        f"💎 *{p['name']}* - Rp{p['price']:,}".replace(",", ".") +
        f" ({p['duration_days']} hari)" if p['duration_days'] < 9999 else " (Lifetime)"
        for p in PREMIUM_PACKAGES
    ])

    text = (
        f"💎 *Fitur Premium*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Keuntungan Premium:\n"
        f"  • Unlimited konversi file\n"
        f"  • Akses semua 89 negara\n"
        f"  • Tanpa watermark\n"
        f"  • Priority support\n"
        f"  • Custom branding\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Pilih paket di bawah 👇\n\n"
        f"{packages_text}\n"
        f"{branding_footer()}"
    )

    try:
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=get_premium_packages_keyboard(),
        )
    except Exception:
        # Kalau edit gagal (misal pesan aslinya berbeda), kirim pesan baru
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=get_premium_packages_keyboard(),
        )


async def handle_premium_package_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setelah user pilih paket, tampilkan QRIS + instruksi bayar."""
    query = update.callback_query
    await query.answer()

    package_id = query.data.replace("premium_pkg_", "")
    pkg = find_package(package_id)
    if not pkg:
        await query.edit_message_text("❌ Paket tidak ditemukan.")
        return

    context.user_data['premium_package'] = package_id
    context.user_data['mode'] = 'premium_await_payment'

    price_str = f"Rp{pkg['price']:,}".replace(",", ".")
    duration_str = "Lifetime" if pkg['duration_days'] >= 9999 else f"{pkg['duration_days']} hari"

    features_text = "\n".join([f"  ✅ {f}" for f in pkg['features']])

    # Cek apakah file QRIS ada
    if os.path.exists(QRIS_IMAGE_PATH):
        with open(QRIS_IMAGE_PATH, 'rb') as qris_img:
            await query.message.reply_photo(
                photo=qris_img,
                caption=(
                    f"💎 *Pembayaran Premium*\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Paket: *{pkg['name']}*\n"
                    f"Harga: *{price_str}*\n"
                    f"Durasi: *{duration_str}*\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"Fitur:\n{features_text}\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🏪 Merchant: *{QRIS_MERCHANT}*\n"
                    f"🆔 NMID: `{QRIS_NMID}`\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"*Cara pembayaran:*\n"
                    f"1. Buka aplikasi e-wallet/banking\n"
                    f"   (DANA, OVO, GoPay, ShopeePay, LinkAja, dll)\n"
                    f"2. Scan QRIS di atas\n"
                    f"3. Bayar sesuai nominal: *{price_str}*\n"
                    f"4. Screenshot bukti pembayaran\n"
                    f"5. Klik *Saya Sudah Bayar* di bawah\n"
                    f"6. Kirim screenshot bukti bayar\n"
                    f"7. Admin akan verifikasi & aktifkan premium\n\n"
                    f"⚠️ *Penting:* Kirim bukti transfer ke admin "
                    f"[{ADMIN_USERNAME}]({DEV_LINK}) untuk verifikasi cepal."
                ),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
                reply_markup=get_premium_payment_keyboard(package_id),
            )
        await query.edit_message_text(f"✅ Paket dipilih: *{pkg['name']}* ({price_str})")
    else:
        # Fallback kalau gambar tidak ada
        await query.edit_message_text(
            f"💎 *Pembayaran Premium*\n\n"
            f"Paket: *{pkg['name']}*\n"
            f"Harga: *{price_str}*\n"
            f"Durasi: *{duration_str}*\n\n"
            f"⚠️ File QRIS tidak ditemukan.\n"
            f"Hubungi admin [{ADMIN_USERNAME}]({DEV_LINK}) untuk pembayaran manual.",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=get_premium_payment_keyboard(package_id),
        )


async def handle_premium_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setelah user klik 'Saya Sudah Bayar', minta upload bukti."""
    query = update.callback_query
    await query.answer()

    package_id = context.user_data.get('premium_package')
    pkg = find_package(package_id) if package_id else None
    if not pkg:
        await query.edit_message_text("❌ Sesi expired. Silakan pilih paket lagi.")
        context.user_data.clear()
        return

    context.user_data['mode'] = 'premium_await_proof'

    price_str = f"Rp{pkg['price']:,}".replace(",", ".")

    await query.edit_message_text(
        f"📤 *Upload Bukti Pembayaran*\n\n"
        f"Paket: *{pkg['name']}*\n"
        f"Nominal: *{price_str}*\n\n"
        f"Kirim *screenshot/photo bukti pembayaran* dari e-wallet/banking Anda.\n\n"
        f"Setelah upload, admin akan verifikasi dalam max 1x24 jam.\n"
        f"Untuk verifikasi cepat, kirim juga ke [{ADMIN_USERNAME}]({DEV_LINK}).",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def handle_premium_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle upload bukti pembayaran dari user."""
    package_id = context.user_data.get('premium_package')
    pkg = find_package(package_id) if package_id else None
    if not pkg:
        await update.message.reply_text(
            "❌ Sesi expired. Silakan mulai ulang dari menu Premium."
        )
        context.user_data.clear()
        return

    user = update.effective_user
    price_str = f"Rp{pkg['price']:,}".replace(",", ".")
    duration_str = "Lifetime" if pkg['duration_days'] >= 9999 else f"{pkg['duration_days']} hari"

    # Kirim notifikasi ke admin (jika owner_id diset)
    admin_msg = (
        f"🔔 *Permintaan Verifikasi Premium*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 User: {user.first_name} (`{user.id}`)\n"
        f"💎 Paket: *{pkg['name']}*\n"
        f"💰 Harga: *{price_str}*\n"
        f"⏱️ Durasi: *{duration_str}*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Verifikasi bukti pembayaran di atas.\n"
        f"Jika valid, aktifkan premium dengan perintah:\n"
        f"`/activate {user.id} {package_id}`\n\n"
        f"Atau klik tombol di bawah 👇"
    )

    # Inline keyboard untuk admin approve/reject
    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_{user.id}_{package_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_{user.id}_{package_id}"),
        ],
    ])

    # Simpan info user ke payment_records supaya pas approve bisa ambil username
    # (Untuk database premium_users.json)
    if not context.bot_data.get('payment_records'):
        context.bot_data['payment_records'] = {}
    context.bot_data['payment_records'][str(user.id)] = {
        'user_id': user.id,
        'username': user.username or '',
        'first_name': user.first_name or '',
        'package': package_id,
        'package_name': pkg['name'],
        'timestamp': datetime.now().isoformat(),
    }

    # Kirim ke admin (ke chat yang sama kalau owner_id tidak diset)
    target_chat = OWNER_ID if OWNER_ID else update.effective_chat.id
    try:
        # Forward bukti pembayaran ke admin
        if update.message.photo:
            # Ambil photo resolusi tertinggi
            photo = update.message.photo[-1]
            await context.bot.send_photo(
                chat_id=target_chat,
                photo=photo.file_id,
                caption=admin_msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=admin_keyboard,
            )
        elif update.message.document:
            await context.bot.send_document(
                chat_id=target_chat,
                document=update.message.document.file_id,
                caption=admin_msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=admin_keyboard,
            )
    except Exception as e:
        logger.warning(f"Gagal kirim notifikasi ke admin: {e}")

    # Balas user
    await update.message.reply_text(
        f"✅ *Bukti pembayaran diterima!*\n\n"
        f"Paket: *{pkg['name']}* ({price_str})\n\n"
        f"Admin akan verifikasi dalam max 1x24 jam.\n"
        f"Anda akan dapat notifikasi saat premium aktif.\n\n"
        f"Untuk verifikasi cepat, hubungi: "
        f"[{ADMIN_USERNAME}]({DEV_LINK})\n"
        f"{branding_footer()}",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_markup=get_main_menu(),
    )

    context.user_data.clear()


async def handle_admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin approve premium user."""
    query = update.callback_query
    await query.answer()

    # Hanya owner yang bisa approve
    if OWNER_ID and query.from_user.id != OWNER_ID:
        await query.answer("❌ Hanya admin yang bisa approve.", show_alert=True)
        return

    # Parse: admin_approve_{user_id}_{package_id}
    parts = query.data.split('_')
    if len(parts) < 4:
        await query.edit_message_caption("❌ Data invalid.")
        return

    user_id = int(parts[2])
    package_id = parts[3]
    pkg = find_package(package_id)
    if not pkg:
        await query.edit_message_caption("❌ Paket tidak ditemukan.")
        return

    duration_str = "Lifetime" if pkg['duration_days'] >= 9999 else f"{pkg['duration_days']} hari"
    price_str = f"Rp{pkg['price']:,}".replace(",", ".")

    # Update caption dengan status approved
    new_caption = (
        f"✅ *PREMIUM DISETUJUI*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 User ID: `{user_id}`\n"
        f"💎 Paket: *{pkg['name']}*\n"
        f"💰 Harga: *{price_str}*\n"
        f"⏱️ Durasi: *{duration_str}*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Admin: @{query.from_user.username}\n"
        f"Status: ✅ APPROVED"
    )

    try:
        await query.edit_message_caption(
            caption=new_caption,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        await query.edit_message_text(new_caption, parse_mode=ParseMode.MARKDOWN)

    # SIMPAN USER KE DATABASE PREMIUM (persistent)
    # Ini bagian kunci yang sebelumnya hilang - tanpa ini, status premium
    # tidak tersimpan dan user tetap dianggap user biasa.
    try:
        # Ambil info user dari payment_records (kalau ada) untuk dapatkan username
        username = ""
        payment_records = context.bot_data.get('payment_records', {})
        user_record = payment_records.get(str(user_id), {})
        username = user_record.get('username', '')

        record = add_premium_user(
            user_id=user_id,
            package_id=package_id,
            package_name=pkg['name'],
            duration_days=pkg['duration_days'],
            username=username,
        )
        logger.info(f"User {user_id} diset premium: {pkg['name']} (durasi: {duration_str})")
    except Exception as e:
        logger.error(f"Gagal simpan premium user {user_id} ke DB: {e}")

    # Kirim notifikasi ke user
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 *PREMIUM AKTIF!*\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💎 Paket: *{pkg['name']}*\n"
                f"⏱️ Durasi: *{duration_str}*\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"Selamat! Akun Anda sekarang Premium.\n"
                f"Semua fitur premium telah aktif.\n\n"
                f"Terima kasih atas pembayaran Anda!\n"
                f"{branding_footer()}"
            ),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=get_main_menu(),
        )
    except Exception as e:
        logger.warning(f"Gagal kirim notifikasi ke user {user_id}: {e}")


async def handle_admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin reject premium user."""
    query = update.callback_query
    await query.answer()

    if OWNER_ID and query.from_user.id != OWNER_ID:
        await query.answer("❌ Hanya admin yang bisa reject.", show_alert=True)
        return

    parts = query.data.split('_')
    if len(parts) < 4:
        await query.edit_message_caption("❌ Data invalid.")
        return

    user_id = int(parts[2])

    new_caption = (
        f"❌ *PREMIUM DITOLAK*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 User ID: `{user_id}`\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Admin: @{query.from_user.username}\n"
        f"Status: ❌ REJECTED"
    )

    try:
        await query.edit_message_caption(
            caption=new_caption,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        await query.edit_message_text(new_caption, parse_mode=ParseMode.MARKDOWN)

    # Kirim notifikasi ke user
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"❌ *Pembayaran Ditolak*\n\n"
                f"Mohon maaf, bukti pembayaran Anda tidak valid.\n"
                f"Silakan hubungi [{ADMIN_USERNAME}]({DEV_LINK}) untuk info lebih lanjut.\n"
                f"{branding_footer()}"
            ),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=get_main_menu(),
        )
    except Exception as e:
        logger.warning(f"Gagal kirim notifikasi ke user {user_id}: {e}")


async def handle_premium_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel premium flow."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(
        "❌ Pembayaran premium dibatalkan.\nKlik menu untuk mulai lagi."
    )


# --------------------------------------------------------------------
# 11. INPUT MANUAL (Ketik nomor langsung tanpa upload file)
# --------------------------------------------------------------------
async def start_manual_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu Input Manual - user ketik nomor langsung."""
    # Gating premium - cek apakah user boleh pakai fitur ini
    if not await check_premium_access(update, context, 'manual_input'):
        return
    context.user_data['mode'] = 'manual_await_format'
    await update.message.reply_text(
        f"⌨️ *Input Manual*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Pilih format output:\n\n"
        f"• *ke VCF* - Convert nomor ke kontak VCF\n"
        f"• *ke TXT* - Rapikan & normalisasi nomor\n"
        f"• *ke ADM/NVY* - Format khusus\n"
        f"• *REQ NAME* - Custom prefix\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Setelah pilih format, Anda akan diminta:\n"
        f"1. Pilih kode negara (untuk nomor lokal)\n"
        f"2. Ketik nomor langsung di chat\n"
        f"\nFormat input yang didukung:\n"
        f"  • Satu nomor per baris\n"
        f"  • Dipisah koma: `0812xxx, 0813xxx`\n"
        f"  • Dipisah titik koma: `0812xxx; 0813xxx`\n"
        f"{branding_footer()}",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_markup=get_manual_format_keyboard(),
    )


async def handle_manual_format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setelah user pilih format, minta pilih negara (atau custom name kalau CUSTOM)."""
    query = update.callback_query
    await query.answer()

    fmt = query.data.replace("manual_", "")
    if fmt == "cancel":
        context.user_data.clear()
        await query.edit_message_text(
            "❌ Input manual dibatalkan.\nKlik menu untuk mulai lagi."
        )
        return

    if fmt == "CUSTOM":
        # Mode minta custom name dulu
        context.user_data['mode'] = 'manual_await_custom_name'
        context.user_data['manual_format'] = 'CUSTOM'
        await query.edit_message_text(
            f"✨ *REQ NAME - Custom Prefix*\n\n"
            f"Ketik nama prefix yang Anda inginkan (3-35 karakter).\n\n"
            f"*Aturan:*\n"
            f"  • Hanya huruf besar/kecil dan angka\n"
            f"  • Tanpa spasi, simbol, atau karakter khusus\n"
            f"  • Contoh valid: `ANGGA`, `BOS`, `PREMIUM`, `VIP123`, `KONTAKPELANGGANBOS2024`\n\n"
            f"*Contoh output:* `ANGGA-001:+62xxx`\n\n"
            f"Kirim /cancel untuk batal.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Format: vcf, txt, ADM, NVY
    context.user_data['mode'] = 'manual_await_country'
    context.user_data['manual_format'] = fmt

    await query.edit_message_text(
        f"✅ Format: *{fmt.upper()}*\n\n"
        f"Sekarang pilih kode negara untuk nomor lokal:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_country_keyboard(f'manual_{fmt}'),
    )


async def handle_manual_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Capture custom name untuk Input Manual."""
    text = update.message.text.strip()

    if not text:
        await update.message.reply_text("⚠️ Nama tidak boleh kosong. Ketik 3-35 karakter alfanumerik.")
        return

    if len(text) < 3 or len(text) > 35:
        await update.message.reply_text(
            f"⚠️ Panjang harus 3-35 karakter. Anda kirim: `{len(text)}` karakter.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not text.isalnum():
        await update.message.reply_text("⚠️ Hanya boleh huruf dan angka (tanpa spasi/simbol). Coba lagi.")
        return

    custom_prefix = text.upper()
    context.user_data['manual_format'] = custom_prefix
    context.user_data['mode'] = 'manual_await_country'

    await update.message.reply_text(
        f"✅ Custom prefix: *{custom_prefix}*\n\n"
        f"Pilih kode negara untuk nomor lokal 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_country_keyboard(f'manual_{custom_prefix}'),
    )


async def handle_manual_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setelah user pilih negara, minta ketik nomor manual."""
    query = update.callback_query
    await query.answer()

    # callback_data format: country_manual_{FMT}_{CODE}
    parts = query.data.split('_')
    if len(parts) >= 4:
        fmt = parts[2]
        country_code = parts[3]
    else:
        fmt = context.user_data.get('manual_format', 'vcf')
        country_code = parts[-1]

    dial, name = COUNTRY_CODES.get(country_code, ("+62", "Indonesia"))
    context.user_data['mode'] = 'manual_await_numbers'
    context.user_data['country_code'] = dial
    context.user_data['country_display'] = f"{name} ({dial})"

    fmt_display = fmt.upper() if fmt in ('vcf', 'txt') else fmt
    await query.edit_message_text(
        f"✅ Format: *{fmt_display}* | Negara: *{name} ({dial})*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⌨️ *Ketik nomor sekarang*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Format yang didukung:\n"
        f"  • Satu nomor per baris\n"
        f"  • Dipisah koma: `0812xxx, 0813xxx`\n"
        f"  • Dipisah titik koma: `0812xxx; 0813xxx`\n\n"
        f"Contoh:\n"
        f"```\n"
        f"081234567890\n"
        f"081345678901\n"
        f"081456789012\n"
        f"```\n\n"
        f"Ketik nomor Anda di bawah 👇\n"
        f"Kirim /cancel untuk batal.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_manual_numbers_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert nomor yang diketik user."""
    text = update.message.text
    fmt = context.user_data.get('manual_format', 'vcf')
    country_code = context.user_data.get('country_code', DEFAULT_COUNTRY_CODE)
    country_display = context.user_data.get('country_display', DEFAULT_COUNTRY_NAME)

    # Parse nomor dari teks
    numbers = parse_manual_numbers(text)
    if not numbers:
        await update.message.reply_text(
            "⚠️ Tidak ada nomor terdeteksi. Ketik nomor dengan format yang benar.\n"
            "Contoh: `081234567890` atau `0812xxx, 0813xxx`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    status_msg = await update.message.reply_text(
        f"⏳ Memproses {len(numbers)} nomor..."
    )
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    with tempfile.TemporaryDirectory() as tmp:
        try:
            if fmt == 'vcf':
                # Convert ke VCF
                output_path = os.path.join(tmp, 'manual_output.vcf')
                success, total = manual_to_vcf(numbers, output_path, NAME_PREFIX, country_code)

                if success == 0:
                    await status_msg.edit_text(
                        "❌ Tidak ada nomor valid ditemukan.\n"
                        f"Pastikan format: `0812xxx` atau `{country_code}812xxx`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return

                filename = f"manual_{success}_contacts.vcf"
                caption = (
                    f"✅ *Konversi Manual Berhasil!*\n\n"
                    f"⌨️ Input: manual ({len(numbers)} nomor)\n"
                    f"🌍 Country: *{country_display}*\n"
                    f"✅ Nomor valid: *{success}*\n"
                    f"❌ Nomor invalid: *{total - success}*\n"
                    f"📦 Format: VCF v3.0\n"
                    f"{branding_footer()}"
                )

            elif fmt == 'txt':
                # Convert ke TXT (rapikan)
                output_path = os.path.join(tmp, 'manual_output.txt')
                final_count, original_count = manual_to_txt(
                    numbers, output_path, country_code, clean=True
                )

                if final_count == 0:
                    await status_msg.edit_text("❌ Tidak ada nomor valid ditemukan.")
                    return

                filename = f"manual_{final_count}_unique.txt"
                caption = (
                    f"✅ *Rapikan Manual Berhasil!*\n\n"
                    f"⌨️ Input: manual ({len(numbers)} nomor)\n"
                    f"🌍 Country: *{country_display}*\n"
                    f"✅ Nomor unik: *{final_count}*\n"
                    f"🗑️ Duplikat dihapus: *{original_count - final_count}*\n"
                    f"🔧 Format: {country_code}xxx (sorted)\n"
                    f"{branding_footer()}"
                )

            else:
                # ADM / NVY / Custom
                output_path = os.path.join(tmp, f'manual_{fmt.lower()}.txt')
                success, total = manual_to_adm_nvy(numbers, output_path, fmt, country_code)

                if success == 0:
                    await status_msg.edit_text("❌ Tidak ada nomor valid ditemukan.")
                    return

                filename = f"{fmt.lower()}_{success}_numbers.txt"
                caption = (
                    f"✅ *Konversi {fmt} Manual Berhasil!*\n\n"
                    f"⌨️ Input: manual ({len(numbers)} nomor)\n"
                    f"🌍 Country: *{country_display}*\n"
                    f"✅ Nomor valid: *{success}*\n"
                    f"❌ Invalid: *{total - success}*\n"
                    f"📦 Format: `{fmt}-001:{country_code}xxx`\n"
                    f"{branding_footer()}"
                )

            # Kirim file hasil
            with open(output_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                )
            await status_msg.delete()

        except Exception as e:
            logger.exception("Manual input error")
            await status_msg.edit_text(
                f"❌ Error: `{md_escape(str(e))}`",
                parse_mode=ParseMode.MARKDOWN
            )

    context.user_data.clear()


# --------------------------------------------------------------------
# ROUTING UTAMA
# --------------------------------------------------------------------
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routing pesan teks berdasarkan menu yang dipilih."""
    text = update.message.text
    mode = context.user_data.get('mode')

    # Jika sedang mode MSG to TXT, kumpulkan pesan
    if mode == 'msg_to_txt':
        await collect_msg(update, context)
        return

    # Jika sedang mode ADM/NVY await custom name, capture input user
    if mode == 'adm_nvy_await_custom_name':
        await handle_custom_name_input(update, context)
        return

    # Jika sedang mode Input Manual await custom name, capture input user
    if mode == 'manual_await_custom_name':
        await handle_manual_custom_name(update, context)
        return

    # Jika sedang mode Input Manual await numbers, capture nomor dari user
    if mode == 'manual_await_numbers':
        await handle_manual_numbers_input(update, context)
        return

    # Mapping menu ke handler.
    # Karena tombol sekarang pakai emoji berwarna + bold sans-serif (𝗦𝘁𝗮𝘁𝘂𝘀),
    # kita matching berdasarkan substring agar tidak terlalu sensitif terhadap perubahan emoji.
    # PENTING: urutan dict ini menentukan prioritas match.
    menu_map = {
        # Premium (CEK PALING AWAL karena "Premium" adalah kata unik)
        "PREMIUM": start_premium,
        "Premium": start_premium,
        # Input Manual
        "Input Manual": start_manual_input,
        "INPUT MANUAL": start_manual_input,
        # Status (merah)
        "Status": show_status,
        # ADM & NVY (abu-abu)
        "ADM": start_adm_nvy,
        "NVY": start_adm_nvy,
        # Rapikan TXT (biru)
        "Rapikan": start_clean_txt,
        # POTONG/BAGI VCF (hijau)
        "POTONG": start_split_vcf,
        "BAGI": start_split_vcf,
        # MSG to TXT (oranye)
        "MSG": start_msg_to_txt,
        # TXT to VCF (kuning)
        "TXT to VCF": start_txt_to_vcf,
        "TXT TO VCF": start_txt_to_vcf,
        # VCF to TXT (kuning)
        "VCF to TXT": start_vcf_to_txt,
        "VCF TO TXT": start_vcf_to_txt,
        # XLS to TXT (oranye)
        "XLS": start_xls_to_txt,
        # Gabung TXT (biru)
        "Gabung TXT": start_merge_txt,
        # Gabung VCF (ungu)
        "Gabung VCF": start_merge_vcf,
    }

    # Cari match berdasarkan substring (case-insensitive)
    handler = None
    text_lower = text.lower()
    for keyword, h in menu_map.items():
        if keyword.lower() in text_lower:
            handler = h
            break

    if handler:
        await handler(update, context)
    else:
        await update.message.reply_text(
            f"ℹ️ Pilih menu dari keyboard di bawah.\n"
            f"Ketik /help untuk panduan.",
            reply_markup=get_main_menu(),
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routing file yang dikirim berdasarkan mode aktif."""
    mode = context.user_data.get('mode')

    # Mode premium await proof - terima photo/document sebagai bukti bayar
    if mode == 'premium_await_proof':
        await handle_premium_proof(update, context)
        return

    if mode == 'txt_to_vcf':
        await process_txt_to_vcf(update, context)
    elif mode == 'vcf_to_txt':
        await process_vcf_to_txt(update, context)
    elif mode == 'merge_txt':
        await add_merge_txt_file(update, context)
    elif mode == 'merge_vcf':
        await add_merge_vcf_file(update, context)
    elif mode == 'split_vcf':
        await process_split_vcf(update, context)
    elif mode == 'clean_txt':
        await process_clean_txt(update, context)
    elif mode == 'xls_to_txt':
        await process_xls_to_txt(update, context)
    elif mode == 'adm_nvy':
        await process_adm_nvy(update, context)
    elif mode in ('txt_to_vcf_await_country', 'clean_txt_await_country', 'adm_nvy_await_country', 'adm_nvy_await_custom_name', 'adm_nvy_await', 'premium', 'premium_await_payment', 'manual_await_format', 'manual_await_country', 'manual_await_custom_name', 'manual_await_numbers'):
        # User belum selesai pilih opsi / belum kirim teks yang benar
        if mode == 'adm_nvy_await_custom_name':
            hint_msg = ("⚠️ Anda belum kirim nama custom.\n"
                       "Ketik 3-35 karakter alfanumerik (misal: ANGGA).\n"
                       "Atau kirim /cancel untuk batal.")
        elif mode == 'adm_nvy_await':
            hint_msg = ("⚠️ Pilih format di tombol di atas dulu (ADM / NVY / REQ NAME).\n"
                       "Atau kirim /cancel untuk batal.")
        elif mode == 'premium':
            hint_msg = ("⚠️ Pilih paket premium di tombol di atas dulu.\n"
                       "Atau kirim /cancel untuk batal.")
        elif mode == 'premium_await_payment':
            hint_msg = ("⚠️ Silakan klik tombol '✅ Saya Sudah Bayar' atau '❌ Batal' "
                       "di pesan QRIS di atas.")
        elif mode == 'manual_await_format':
            hint_msg = ("⚠️ Pilih format output di tombol di atas dulu "
                       "(VCF / TXT / ADM / NVY / REQ NAME).\n"
                       "Atau kirim /cancel untuk batal.")
        elif mode == 'manual_await_country':
            hint_msg = ("⚠️ Pilih kode negara di tombol di atas dulu.\n"
                       "Atau kirim /cancel untuk batal.")
        elif mode == 'manual_await_custom_name':
            hint_msg = ("⚠️ Anda belum kirim nama custom.\n"
                       "Ketik 3-35 karakter alfanumerik (misal: ANGGA).\n"
                       "Atau kirim /cancel untuk batal.")
        elif mode == 'manual_await_numbers':
            hint_msg = ("⚠️ Anda sedang di mode Input Manual.\n"
                       "Ketik nomor langsung di chat (bukan upload file).\n"
                       "Format: satu nomor per baris, atau dipisah koma.\n"
                       "Atau kirim /cancel untuk batal.")
        else:
            hint_msg = ("⚠️ Silakan pilih opsi di tombol di atas dulu.\n"
                       "Atau kirim /cancel untuk batal.")
        await update.message.reply_text(hint_msg)
    else:
        await update.message.reply_text(
            f"ℹ️ Pilih menu dulu sebelum kirim file.\n"
            f"Klik menu di keyboard bawah 👇",
            reply_markup=get_main_menu(),
        )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routing callback dari inline keyboard."""
    query = update.callback_query
    data = query.data

    if data == "finish_collect":
        mode = context.user_data.get('mode')
        if mode == 'merge_txt':
            await finish_merge_txt(update, context)
        elif mode == 'merge_vcf':
            await finish_merge_vcf(update, context)
        elif mode == 'msg_to_txt':
            await finish_msg_to_txt(update, context)
        else:
            await query.answer("Tidak ada operasi aktif.")
            await query.edit_message_text("ℹ️ Tidak ada operasi yang sedang berjalan.")
            context.user_data.clear()
    elif data == "cancel_collect":
        await query.answer("Dibatalkan")
        # Cleanup tmpdir jika ada
        tmpdir = context.user_data.get('tmpdir')
        if tmpdir and os.path.exists(tmpdir):
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        context.user_data.clear()
        await query.edit_message_text("❌ Operasi dibatalkan.")
    elif data == "noop":
        # Tombol info saja (page indicator), tidak melakukan apa-apa
        await query.answer(cache_time=1)
    elif data.startswith("split_"):
        await handle_split_choice(update, context)
    elif data.startswith("fmt_"):
        await handle_adm_nvy_choice(update, context)
    elif data == "manual_cancel":
        context.user_data.clear()
        await query.answer("Dibatalkan")
        await query.edit_message_text(
            "❌ Input manual dibatalkan.\nKlik menu untuk mulai lagi."
        )
    elif data.startswith("manual_vcf") or data.startswith("manual_txt") or \
         data.startswith("manual_ADM") or data.startswith("manual_NVY") or \
         data.startswith("manual_CUSTOM"):
        # User pilih format manual input
        await handle_manual_format_choice(update, context)
    elif data == "premium_cancel":
        await handle_premium_cancel(update, context)
    elif data == "premium_show_menu":
        # User klik tombol "Upgrade ke Premium" dari pesan status/gate
        await query.answer()
        # Simulasi klik tombol PREMIUM di keyboard utama
        # Pakai start_premium tapi perlu bypass karena biasanya pakai update.message
        await handle_premium_show_menu_callback(update, context)
    elif data.startswith("premium_pkg_"):
        # User pilih paket premium
        await handle_premium_package_choice(update, context)
    elif data.startswith("premium_paid_"):
        # User klik "Saya Sudah Bayar"
        await handle_premium_paid(update, context)
    elif data.startswith("admin_approve_"):
        # Admin approve pembayaran
        await handle_admin_approve(update, context)
    elif data.startswith("admin_reject_"):
        # Admin reject pembayaran
        await handle_admin_reject(update, context)
    elif data.startswith("country_txt_to_vcf_"):
        # User pilih negara untuk TXT->VCF
        await handle_txt_to_vcf_country(update, context)
    elif data.startswith("country_clean_txt_"):
        # User pilih negara untuk Clean TXT
        await handle_clean_txt_country(update, context)
    elif data.startswith("country_adm_nvy_"):
        # User pilih negara untuk ADM/NVY (format disimpan di parts)
        await handle_adm_nvy_country(update, context)
    elif data.startswith("country_manual_"):
        # User pilih negara untuk Input Manual
        await handle_manual_country(update, context)
    elif data.startswith("country_more_"):
        # Paginasi: tampilkan semua negara
        # Format: country_more_{action}_{page}
        parts = data.split('_')
        # parts[0]='country', parts[1]='more', parts[2:]=action_parts
        # Action bisa 'txt' 'to' 'vcf' atau 'adm' 'nvy' 'ADM' atau 'clean' 'txt'
        # Page adalah bagian terakhir
        page = int(parts[-1])
        action = '_'.join(parts[2:-1])
        await query.edit_message_text(
            f"🌍 *Pilih Negara (Halaman {page+1})*\n\n"
            f"Total 89 negara tersedia.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_all_countries_keyboard(action, page),
        )
    elif data.startswith("country_back_"):
        # Kembali dari "semua negara" ke "populer"
        # Format: country_back_{action}
        action = data[len("country_back_"):]
        await query.edit_message_text(
            f"🌍 *Pilih Negara Populer*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_country_keyboard(action),
        )
    else:
        await query.answer("Unknown action")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handler error global."""
    logger.error("Exception:", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                f"❌ Terjadi error internal. Coba lagi ya.\n"
                f"Jika persisten, hubungi [{ADMIN_USERNAME}]({DEV_LINK}).",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
                reply_markup=get_main_menu(),
            )
    except Exception:
        pass


# --------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------
def main():
    if TOKEN == "PASTE_TOKEN_DARI_BOTFATHER_DISINI" or not TOKEN:
        print("=" * 60)
        print("❌ ERROR: Token bot belum diisi!")
        print("=" * 60)
        print("Edit file config.json dan masukkan token dari @BotFather.")
        print("Format config.json:")
        print('  { "bot_token": "123456789:ABC...", ... }')
        print("=" * 60)
        return

    print("=" * 60)
    print(f"🤖 {BOT_NAME} Bot")
    print(f"👤 Admin: @{ADMIN_USERNAME}")
    print(f"💎 Premium features: blue branding link active")
    print("=" * 60)
    print("Bot sedang berjalan... Tekan Ctrl+C untuk berhenti.")
    print("=" * 60)

    # Build application dengan timeout configuration
    # read_timeout: waktu tunggu response dari server
    # write_timeout: waktu untuk send request
    # connect_timeout: waktu untuk establish connection
    # pool_timeout: waktu tunggu connection pool
    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .read_timeout(60)        # 60 detik untuk read (default 30, terlalu pendek)
        .write_timeout(60)       # 60 detik untuk write
        .connect_timeout(30)     # 30 detik untuk connect
        .pool_timeout(30)        # 30 detik untuk pool
        .get_updates_read_timeout(60)
        .build()
    )

    # Command handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("cancel", cmd_cancel))

    # Text message handler (route menu)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_message,
    ))

    # Document handler (route file ke processor, termasuk bukti pembayaran)
    application.add_handler(MessageHandler(
        filters.Document.ALL,
        handle_document,
    ))

    # Photo handler (untuk upload bukti pembayaran sebagai photo)
    application.add_handler(MessageHandler(
        filters.PHOTO,
        handle_document,  # route ke handler yang sama, mode premium_await_proof akan tangani
    ))

    # Inline callback handler
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Error handler
    application.add_error_handler(error_handler)

    # ============================================================
    # Run dengan Python 3.14+ compatibility
    # Coba run_polling() dulu. Kalau gagal (RuntimeError event loop),
    # gunakan fallback: jalankan via asyncio.run() dengan start/stop manual.
    # ============================================================
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except RuntimeError as e:
        if "event loop" in str(e).lower() or "no current event loop" in str(e).lower():
            print()
            print("⚠️  Terdeteksi Python 3.14+ - menggunakan fallback event loop...")
            print()
            _run_with_manual_event_loop(application)
        else:
            raise


def _run_with_manual_event_loop(application):
    """
    Fallback untuk Python 3.14+: jalankan bot dengan event loop manual.
    Menggunakan asyncio.run() yang membuat event loop baru di main thread.
    """
    import signal

    async def _run():
        # Initialize application
        await application.initialize()

        # Start updater (polling)
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
        )

        # Start application
        await application.start()

        print("✅ Bot berhasil start dengan manual event loop.")
        print("   Tekan Ctrl+C untuk berhenti.")
        print()

        # Tunggu sampai di-stop (Ctrl+C)
        stop_event = asyncio.Event()

        def _signal_handler(*_):
            stop_event.set()

        # Register signal handler untuk SIGINT/SIGTERM
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGINT, _signal_handler)
            loop.add_signal_handler(signal.SIGTERM, _signal_handler)
        except (NotImplementedError, RuntimeError):
            # Fallback untuk platform yang tidak support add_signal_handler
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)

        try:
            await stop_event.wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            print()
            print("🛑 Menghentikan bot...")
            try:
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
            except Exception:
                pass
            print("✅ Bot dihentikan dengan bersih.")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("\n🛑 Bot dihentikan oleh user.")


if __name__ == '__main__':
    main()
