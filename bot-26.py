#!/usr/bin/env python3
"""
ThermoCrafts Biznes Bot v3.0
21 Modul | IAS 2 | ABC/XYZ CV | Katalog | Kafolat | Marketing
"""
import os, json, sqlite3, logging, math, re, requests, base64, asyncio, time
import threading, hashlib, tempfile, secrets, zipfile, io, difflib, calendar
import xml.etree.ElementTree as ET
import html as _html
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict

# ── Vaqt zonasi: Railway serveri UTC da ishlaydi. Sana/vaqt Toshkent bo'yicha bo'lsin,
#    aks holda 00:00–05:00 oralig'idagi sotuv oldingi kunga (va oy boshida — oldingi oyga) yoziladi.
try:
    _TZH = int(os.getenv('TZ_OFFSET', '5'))
    os.environ['TZ'] = f"<{'+' if _TZH >= 0 else '-'}{abs(_TZH):02d}>{-_TZH}"
    if hasattr(time, 'tzset'):
        time.tzset()
except Exception:
    pass
from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup,
                       InputMediaPhoto, InputMediaVideo, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove)
from telegram.ext import (Application, CommandHandler, MessageHandler,
                           CallbackQueryHandler, ConversationHandler,
                           filters, ContextTypes, TypeHandler, ApplicationHandlerStop)
from telegram.error import BadRequest
import anthropic

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
log = logging.getLogger(__name__)
# httpx har so'rovni INFO darajada URL bilan yozadi — URL ichida BOT_TOKEN bor (Railway loglarida token ochiq turardi)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)      # Instagram so'rovlari URL'ida token bo'lishi mumkin

# ── CONFIG ────────────────────────────────────────────────────────
BOT_TOKEN     = os.getenv('BOT_TOKEN', '')
ANTHROPIC_KEY = os.getenv('ANTHROPIC_KEY', '')
OWNER_ID      = int(os.getenv('OWNER_ID', '0'))
CHANNEL_ID    = os.getenv('CHANNEL_ID', '')   # @ThermoCrafts

def get_channel_id():
    return os.getenv('CHANNEL_ID', '')
# Baza joyi: Railway'da Volume ulangan bo'lsa (RAILWAY_VOLUME_MOUNT_PATH avtomatik beriladi) —
# baza o'sha doimiy diskda turadi va qayta deploy/restartda yo'qolmaydi. Aks holda — eski joy.
VOLUME_PATH   = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '').strip()
_DBP_ENV      = os.getenv('DB_PATH', '').strip()
if VOLUME_PATH and (not _DBP_ENV or not os.path.isabs(_DBP_ENV)):
    DB_PATH = os.path.join(VOLUME_PATH, os.path.basename(_DBP_ENV) if _DBP_ENV else 'thermocraft.db')
else:
    DB_PATH = _DBP_ENV or 'thermocraft.db'

def db_on_volume():
    return bool(VOLUME_PATH) and os.path.abspath(DB_PATH).startswith(os.path.abspath(VOLUME_PATH) + os.sep)
ai = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# Conversation states
(S_NAME, S_CAT, S_SUP, S_COST, S_PRICE, S_QTY,
 S_SPECS, S_PHOTOS, S_DONE) = range(9)

# ── INITIAL PRODUCTS ──────────────────────────────────────────────
INIT_P = [
    # ID, name, cat, supplier, qty, cost(haqiqiy sebest), price(sotish narxi), factory_price
    # ── TWO TREES ────────────────────────────────────────────────────
    # qoldi: 1ta + yangi 1ta = 2 ta (sebest: avg $117)
    (1, 'TTS 55 Pro',           'Lazer', 'Two Trees', 2,  117,  250, 110),
    # qoldi: 1ta + yangi 3ta = 4 ta (sebest: avg $154)
    (2, 'TTS 10 Pro',           'Lazer', 'Two Trees', 4,  154,  290, 145),
    # qoldi: 2ta + yangi 1ta = 3 ta (sebest: avg $296)
    (3, 'TTS 20 Pro',           'Lazer', 'Two Trees', 3,  296,  490, 280),
    (4, 'Laser head 10W',       'Lazer', 'Two Trees', 2,   87,  120,  80),
    # qoldi: 2ta + yangi 3ta = 5 ta (sebest: avg $98)
    (5, 'CNC3018 Pro',          'CNC',   'Two Trees', 5,   98,  185,  95),
    (6, '4th Axis Rotary',      'CNC',   'Two Trees', 1,   91,  180,  70),
    (7, '500W Spindle',         'CNC',   'Two Trees', 1,   91,  180,  70),
    (8, 'Milling Cutter',       'CNC',   'Two Trees', 1,   65,  100,  50),
    (9, 'Extension Kit 600x600','CNC',   'Two Trees', 1,   65,  110,  55),
    (10,'Honeycomb 400x400',    'CNC',   'Two Trees', 2,   23,   35,  20),
    (11,'Honeycomb 500x500',    'CNC',   'Two Trees', 1,   23,   70,  18),
    (12,'Rotary Blue',          'CNC',   'Two Trees', 2,   21,   45,  18),
    (13,'Air Assist Pump',      'CNC',   'Two Trees', 2,   41,   45,  35),
    # ── FREESUB ──────────────────────────────────────────────────────
    (14,'15 in 1 (SB400)',      'Press', 'Freesub',   2,  300,  360, 198),
    (15,'P8100 (11 in 1)',      'Press', 'Freesub',   2,  160,  335, 140),
    (16,'F1130 (2 in 1)',       'Press', 'Freesub',   2,  100,  190,  88),
    (17,'PD150',                'Press', 'Freesub',   1,   88,  130,  80),
    (18,'ST210 kepka',          'Press', 'Freesub',   1,   89,  190,  82),
    (19,'F270',                 'Press', 'Freesub',   1,   85,  190,  79),
    (20,"Hc12E qorong'i",     "Qog'oz",'Freesub',  2,   53,   65,  45),
    (21,"Hc12g-B och",         "Qog\'oz", 'Freesub',  1,   15,   18,  12),
    # ── OLDIN SOTILGAN (qty=0, tarix uchun) ─────────────────────────
    (22,'F3880',                'Press', 'Freesub',   0,  145, 350, 130),
    (23,'TTC450 PRO',          'CNC',   'Two Trees',  0,  540, 610, 480),
    (24,'CNC vacuum cleaner',  'CNC',   'Two Trees',  0,  120, 150, 110),
    (25,'F910-W220V8',         'Press', 'Freesub',   0,  260, 310, 240),
    (26,'P4060',               'Press', 'Freesub',   0,  350, 410, 320),
    (27,'ST210A5-B220VA',      'Press', 'Freesub',   0,  200, 250, 185),
    (28,'P1210ZJ-R',           'Press', 'Freesub',   0,  155, 190, 140),
    (29,'P1210-R220V5',        'Press', 'Freesub',   0,  200, 250, 185),
    (30,'F136-3',              'Press', 'Freesub',   0,  155, 190, 140),
    (31,'F1130 kepka',         'Press', 'Freesub',   0,   88, 130,  80),
]

# Texnik ma'lumotlar (saytdan olingan)
INIT_SPECS = {
    'TTS 20 Pro': [
        ('🟢 Quvvat','20W (22W peak) — professional daraja'),
        ('🟢 Lazer dog\'i','0.13 × 0.145 mm (eng aniq)'),
        ('🟢 Ishchi maydon','418 × 418 mm (TTS 10/55 dan 40% katta!)'),
        ('🟢 Kesish','20mm yog\'och 1 o\'tishda, 5mm akrilik 1 o\'tishda'),
        ('🟢 Air Assist','✅ O\'z ichida bepul (10-30L/min)'),
        ('─── Umumiy xususiyatlar ───',''),
        ('Tezlik','30,000 mm/min'),
        ('Og\'irlik','3.2 kg (lazer boshi)'),
        ('Ulanish','WiFi + USB + TF karta'),
        ('Dastur','LightBurn, LaserGRBL'),
        ('Materiallar','Yog\'och, akrilik, teri, metall, bambu, tosh, shisha'),
    ],
    'TTS 10 Pro': [
        ('🟡 Quvvat','10W — o\'rta daraja'),
        ('🟡 Lazer dog\'i','0.08 mm (yuqori aniqlik)'),
        ('🟡 Ishchi maydon','300 × 300 mm (kengaytiriladi 600×600mm)'),
        ('🟡 Kesish','10mm yog\'och, 3mm akrilik'),
        ('🟡 Air Assist','❌ Yo\'q (alohida)'),
        ('─── Umumiy xususiyatlar ───',''),
        ('Tezlik','30,000 mm/min'),
        ('Og\'irlik','3.6 kg'),
        ('Ulanish','WiFi + USB + TF karta'),
        ('Dastur','LightBurn, LaserGRBL'),
        ('Materiallar','Yog\'och, plastik, qog\'oz, teri, po\'lat (bo\'yalgan)'),
    ],
    'TTS 55 Pro': [
        ('🔴 Quvvat','5.5W — boshlang\'ich daraja'),
        ('🔴 Lazer dog\'i','0.15 mm'),
        ('🔴 Ishchi maydon','300 × 300 mm (kengaytiriladi 600×600mm)'),
        ('🔴 Kesish','3mm yog\'och, 2mm akrilik'),
        ('🔴 Air Assist','❌ Yo\'q (alohida)'),
        ('─── Umumiy xususiyatlar ───',''),
        ('Tezlik','30,000 mm/min'),
        ('Og\'irlik','3.2 kg'),
        ('Ulanish','WiFi + USB + TF karta'),
        ('Dastur','LightBurn, LaserGRBL'),
        ('Materiallar','Yog\'och, plastik, qog\'oz, teri, po\'lat (bo\'yalgan)'),
    ],
    'CNC3018 Pro': [
        ('Ishchi maydon','300 × 180 × 45 mm'),('Boshqaruv','GRBL'),
        ('Spindle','775 motor, 24V'),('Maks tezlik','2500 mm/min'),
        ('Aniqlik','0.1 mm'),('Ulanish','USB'),
        ('Dastur','Candle, Universal Gcode Sender'),
        ('Materiallar','Yog\'och, MDF, akrilik, PCB, alyuminiy'),
        ('Kuchlanish','24V DC'),('Kafolat','3 oy'),
    ],
    'P8100 (11 in 1)': [
        ('Quvvat','1000W'),('Kuchlanish','220V/110V'),
        ('Harorat','0-250°C'),('Vaqt','0-999 son'),
        ('Plita o\'lchami','29 × 38 cm'),('Og\'irlik','22.6 kg'),
        ('Sertifikat','CE, FCC'),('Kafolat','1 yil'),
        ('Elementlar','Krus 6/9/12/17oz, kepka, taxta, butilka'),
    ],
    '15 in 1 (SB400)': [
        ('Quvvat','1400W'),('Kuchlanish','220V'),
        ('Harorat','0-250°C'),('Vaqt','0-999 son'),
        ('Plita o\'lchami','29 × 38 cm'),('Sertifikat','CE'),
        ('Kafolat','1 yil'),
        ('Elementlar','Futbolka, krus, kepka, taflon, qoshiq, ruchka, krossovka'),
    ],
}

# ── DATABASE ──────────────────────────────────────────────────────
def db():
    # timeout: zaxira (backup) oqimi bazani o'qiyotgan paytda yozuv darhol "database is locked" bilan yiqilmasin
    return sqlite3.connect(DB_PATH, timeout=15)

def init_db():
    conn = db(); c = conn.cursor()

    # Mahsulotlar (zavod narxi ham saqlangan)
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY, name TEXT UNIQUE, cat TEXT,
        supplier TEXT, qty INTEGER, cost REAL, price REAL,
        factory_price REAL DEFAULT 0, warranty_days INTEGER DEFAULT 90,
        active INTEGER DEFAULT 1
    )''')

    # Mahsulot texnik ma'lumotlari
    c.execute('''CREATE TABLE IF NOT EXISTS product_specs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER, spec_name TEXT, spec_value TEXT,
        FOREIGN KEY(product_id) REFERENCES products(id)
    )''')

    # Mahsulot rasmlari (Telegram file_id)
    c.execute('''CREATE TABLE IF NOT EXISTS product_photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER, file_id TEXT, order_num INTEGER DEFAULT 0,
        FOREIGN KEY(product_id) REFERENCES products(id)
    )''')

    # Sotuvlar (IAS 2 mos: COGS alohida)
    c.execute('''CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, time TEXT, product TEXT,
        qty INTEGER, unit_cost REAL, revenue REAL, profit REAL,
        discount REAL DEFAULT 0, customer TEXT DEFAULT '',
        customer_type TEXT DEFAULT 'B2C',
        bank_cost REAL DEFAULT 0, delivery_cost REAL DEFAULT 0,
        reversed INTEGER DEFAULT 0
    )''')

    # Xarajatlar (3 tur: cogs_bank | cogs_delivery | period)
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, amount REAL, category TEXT,
        expense_type TEXT DEFAULT 'period',
        note TEXT, reversed INTEGER DEFAULT 0
    )''')

    # Yo'ldagi tovarlar
    c.execute('''CREATE TABLE IF NOT EXISTS transit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, supplier TEXT, product TEXT,
        qty INTEGER, unit_cost REAL, total_cost REAL,
        deposit REAL DEFAULT 0, remaining REAL,
        bank_fee REAL DEFAULT 0, delivery_fee REAL DEFAULT 0,
        real_cost REAL, status TEXT DEFAULT 'yolda',
        arrived_date TEXT, note TEXT
    )''')

    # Mijozlar
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, phone TEXT, type TEXT DEFAULT 'B2C',
        total_purchases REAL DEFAULT 0, notes TEXT,
        created TEXT, last_purchase TEXT
    )''')

    # Zakazlar (yetkazuvchiga)
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, supplier TEXT, product TEXT,
        qty INTEGER, cost REAL, total REAL,
        status TEXT DEFAULT 'kutilmoqda', note TEXT
    )''')

    # Shaxsiy qarzlar
    c.execute('''CREATE TABLE IF NOT EXISTS debts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, person TEXT, amount REAL,
        type TEXT, note TEXT, paid INTEGER DEFAULT 0
    )''')

    _qarz_turlarini_birxillash(c)   # eski 'berildi'/'olindi' → debitorlik/kreditorlik (idempotent)

    # Operatsiyalar logi (undo uchun)
    c.execute('''CREATE TABLE IF NOT EXISTS op_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, time TEXT, op_type TEXT,
        data_json TEXT, reversed INTEGER DEFAULT 0
    )''')

    # Oylik maqsadlar
    c.execute('''CREATE TABLE IF NOT EXISTS targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year INTEGER, month INTEGER,
        target_revenue REAL, target_profit REAL,
        UNIQUE(year, month)
    )''')

    # Kafolat kuzatish
    c.execute('''CREATE TABLE IF NOT EXISTS warranties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER, product TEXT, customer TEXT,
        start_date TEXT, end_date TEXT,
        status TEXT DEFAULT 'active', note TEXT
    )''')

    # Raqobatchi narxlar
    c.execute('''CREATE TABLE IF NOT EXISTS competitors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, competitor TEXT, product TEXT,
        their_price REAL, our_price REAL, note TEXT
    )''')

    # OLX e'lonlar kuzatish
    c.execute('''CREATE TABLE IF NOT EXISTS olx_listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product TEXT UNIQUE, last_updated TEXT,
        calls_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active'
    )''')

    # Valyuta kurslari
    c.execute('''CREATE TABLE IF NOT EXISTS exchange_rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT UNIQUE, usd_uzs REAL, usd_rub REAL DEFAULT 0
    )''')

    # Boshlang'ich ma'lumotlar
    c.execute('SELECT COUNT(*) FROM products')
    if c.fetchone()[0] == 0:
        for p in INIT_P:
            c.execute('INSERT INTO products VALUES (?,?,?,?,?,?,?,?,90,1)', p)
        # Texnik ma'lumotlar
        for pname, specs in INIT_SPECS.items():
            c.execute('SELECT id FROM products WHERE name=?', (pname,))
            row = c.fetchone()
            if row:
                for sname, sval in specs:
                    c.execute('INSERT INTO product_specs (product_id,spec_name,spec_value) VALUES (?,?,?)',
                              (row[0], sname, sval))


    c.execute('''CREATE TABLE IF NOT EXISTS cash_box (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, time TEXT,
        type TEXT, amount REAL,
        category TEXT, note TEXT,
        payment_method TEXT DEFAULT 'naqd'
    )''')
    # Boshlang'ich kassa qoldig'i
    c.execute('SELECT COUNT(*) FROM cash_box')
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO cash_box (date,time,type,amount,category,note) VALUES (?,?,?,?,?,?)",
                  ('2026-09-01','00:00','kirim',1080,'boshlangich','September boshlangich qoldiq'))

    # ── TARIXIY SOTUVLAR (Yan-Avg 2026) ─────────────────────────────
    c.execute('SELECT COUNT(*) FROM sales')
    if c.fetchone()[0] == 0:
        HIST = [
            # Yanvar 2026 (~$1,987)
            ('2026-01-10','TTS 20 Pro',1,300,470,170),
            ('2026-01-12','TTS 10 Pro',2,170,520,180),
            ('2026-01-15','15 in 1 (SB400)',1,300,355,55),
            ('2026-01-18','CNC3018 Pro',1,115,182,67),
            ('2026-01-20','Air Assist Pump',2,41,94,12),
            ('2026-01-25','Rotary Blue',2,21,94,52),
            ('2026-01-28','F1130 (2 in 1)',1,100,187,87),
            ('2026-01-30',"Hc12E qorong'i",1,53,65,12),
            # Fevral 2026 (~$2,680)
            ('2026-02-05','TTS 20 Pro',2,300,940,340),
            ('2026-02-08','P8100 (11 in 1)',2,160,664,344),
            ('2026-02-12','TTS 10 Pro',1,170,260,90),
            ('2026-02-15','CNC3018 Pro',1,115,182,67),
            ('2026-02-20','Air Assist Pump',1,41,47,6),
            ('2026-02-22','Rotary Blue',1,21,47,26),
            ('2026-02-25','Honeycomb 400x400',2,23,70,24),
            ('2026-02-28',"Hc12g-B och",1,15,18,3),
            # Mart 2026 (~$2,185)
            ('2026-03-05','TTS 20 Pro',2,300,940,340),
            ('2026-03-08','CNC3018 Pro',1,115,182,67),
            ('2026-03-10','P8100 (11 in 1)',1,160,332,172),
            ('2026-03-12','ST210 kepka',1,89,190,101),
            ('2026-03-15','PD150',1,88,140,52),
            ('2026-03-18','Extension Kit 600x600',1,65,110,45),
            ('2026-03-22','Milling Cutter',1,65,100,35),
            ('2026-03-25',"Hc12E qorong'i",2,53,130,24),
            # Aprel 2026 (~$3,190)
            ('2026-04-03','TTS 20 Pro',2,300,940,340),
            ('2026-04-05','TTS 10 Pro',1,170,260,90),
            ('2026-04-08','CNC3018 Pro',1,115,182,67),
            ('2026-04-10','P8100 (11 in 1)',2,160,664,344),
            ('2026-04-12','15 in 1 (SB400)',1,300,355,55),
            ('2026-04-15','4th Axis Rotary',1,91,180,89),
            ('2026-04-18','Milling Cutter',1,65,100,35),
            ('2026-04-20','Air Assist Pump',1,41,47,6),
            ('2026-04-22','Rotary Blue',1,21,47,26),
            ('2026-04-25',"Hc12E qorong'i",1,53,65,12),
            ('2026-04-28','F270',1,85,190,105),
            ('2026-04-30','Honeycomb 400x400',1,23,35,12),
            # May 2026 (~$1,515)
            ('2026-05-05','TTS 20 Pro',1,300,470,170),
            ('2026-05-08','15 in 1 (SB400)',1,300,355,55),
            ('2026-05-12','P8100 (11 in 1)',1,160,332,172),
            ('2026-05-15','Honeycomb 500x500',1,23,70,47),
            ('2026-05-18','Air Assist Pump',1,41,47,6),
            ('2026-05-22','Extension Kit 600x600',1,65,110,45),
            ('2026-05-25',"Hc12g-B och",1,15,18,3),
            # Iyun 2026 (~$1,500)
            ('2026-06-05','TTS 20 Pro',2,300,940,340),
            ('2026-06-08','Air Assist Pump',1,41,47,6),
            ('2026-06-12','CNC3018 Pro',1,115,182,67),
            ('2026-06-15','F270',1,85,190,105),
            ('2026-06-20',"Hc12E qorong'i",1,53,65,12),
            ('2026-06-25','Rotary Blue',1,21,47,26),
            # Iyul 2026 (~$525)
            ('2026-07-05','TTS 10 Pro',1,170,260,90),
            ('2026-07-10','TTS 55 Pro',1,130,195,65),
            ('2026-07-15','CNC3018 Pro',1,115,182,67),
            # Avgust 2026 (~$1,993)
            ('2026-08-05','TTS 10 Pro',2,170,520,180),
            ('2026-08-08','TTS 20 Pro',1,300,470,170),
            ('2026-08-10','P8100 (11 in 1)',1,160,332,172),
            ('2026-08-12','ST210 kepka',1,89,190,101),
            ('2026-08-15','F1130 (2 in 1)',1,100,187,87),
            ('2026-08-18','15 in 1 (SB400)',1,300,355,55),
        ]
        for h in HIST:
            c.execute(
                "INSERT INTO sales (date,time,product,qty,unit_cost,revenue,profit) VALUES (?,?,?,?,?,?,?)",
                (h[0], '12:00', h[1], h[2], h[3], h[4], h[5]))
        log.info(f"Tarixiy {len(HIST)} ta sotuv yuklandi!")

    # Two Trees boshlang'ich qarzi $805
    c.execute("SELECT COUNT(*) FROM transit WHERE supplier='Two Trees' AND note='boshlangich_qarz'")
    if c.fetchone()[0] == 0:
        c.execute("""INSERT INTO transit
            (date,supplier,product,qty,unit_cost,total_cost,deposit,remaining,status,note)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            ('2026-09-01','Two Trees','Oldingi partiya qoldighi',1,805,805,0,805,'qarz','boshlangich_qarz'))

    conn.commit(); conn.close()
    init_stock_tables()          # ombor jurnali + boshlang'ich qoldiq (idempotent)
    init_po_tables()             # zavod buyurtmalari (8-bosqich, idempotent)
    init_marketing_tables()      # marketing: postlar, so'rovlar, sozlamalar, sayt keshi (9-bosqich, idempotent)
    init_b10_tables()            # zaxira, qaytarish, smena, serial/kafolat, shtrix-kod (10-bosqich, idempotent)
    log.info("DB tayyor!")


# ── DB HELPERS ────────────────────────────────────────────────────
def get_products(active_only=True):
    conn = db(); c = conn.cursor()
    q = 'SELECT id,name,cat,supplier,qty,cost,price,factory_price,warranty_days FROM products'
    if active_only: q += ' WHERE active=1'
    q += ' ORDER BY cat,name'
    rows = c.fetchall() if not c.execute(q) else c.fetchall()
    conn.close()
    return [{'id':r[0],'name':r[1],'cat':r[2],'sup':r[3],'qty':r[4],
             'cost':r[5],'price':r[6],'factory':r[7],'warranty':r[8]} for r in rows]

def _nrm(s):
    """Nomni solishtirish uchun: kichik harf, '*'/'×' → 'x', faqat harf va raqam"""
    s = str(s or '').lower().replace('*', 'x').replace('×', 'x')
    return re.sub(r'[^a-z0-9]', '', s)

def _cand(p):
    return {"name": p['name'], "qty": p['qty'], "price": p['price']}

def match_product(q, prefer_stock=False, prods=None):
    """Mahsulotni topadi. Qaytaradi: (mahsulot | None, variantlar).
    Bir nechta mos kelsa — taxmin qilmaydi, variantlar ro'yxatini qaytaradi.
    prefer_stock=True (sotuvda): bir nechtasidan faqat bittasida tovar bo'lsa — o'shani oladi."""
    prods = prods if prods is not None else get_products()
    ql = str(q or '').lower().strip()
    if not ql: return None, []
    for p in prods:
        if p['name'].lower() == ql: return p, []
    nq = _nrm(q)
    def pick(lst):
        if len(lst) == 1: return lst[0], []
        if prefer_stock:
            bor = [p for p in lst if p['qty'] > 0]
            if len(bor) == 1: return bor[0], []
        return None, [_cand(p) for p in lst[:8]]
    if nq:
        ex = [p for p in prods if _nrm(p['name']) == nq]
        if ex: return pick(ex)
        sub = [p for p in prods if nq in _nrm(p['name']) or (len(_nrm(p['name'])) >= 3 and _nrm(p['name']) in nq)]
        if sub: return pick(sub)
    words = [w for w in re.split(r'[\s\-_/+,()]+', ql) if len(w) > 2]
    if words:
        sc = []
        for p in prods:
            pl, pn = p['name'].lower(), _nrm(p['name'])
            k = sum(1 for w in words if w in pl or (_nrm(w) and _nrm(w) in pn))
            if k: sc.append((k, p))
        if sc:
            best = max(k for k, _ in sc)
            return pick([p for k, p in sc if k == best])
    return None, []

def find_product(q):
    p, _ = match_product(q)
    if p: return p
    # Eski (yumshoq) qidiruv — hisobot/raqobat kabi o'qish amallari uchun
    prods = get_products(); ql = (q or '').lower().strip()
    if not ql: return None
    for p in prods:
        if ql in p['name'].lower() or p['name'].lower() in ql: return p
    words = [w for w in ql.split() if len(w) > 2]
    for p in prods:
        if any(w in p['name'].lower() for w in words): return p
    return None

def _to_usd(usd=None, uzs=None, rate=None):
    """Summani dollarga: so'm berilsa yoki 'dollar' 5000 dan katta bo'lsa — kurs bo'yicha o'giradi"""
    try: usd = float(usd or 0)
    except (TypeError, ValueError): usd = 0.0
    try: uzs = float(uzs or 0)
    except (TypeError, ValueError): uzs = 0.0
    if uzs > 0 or usd >= 5000:
        rate = rate or get_exchange_rate()
        return round((uzs or usd) / rate, 2)
    return usd

def _taqsimla(total, weights):
    """total ($) ni og'irliklar bo'yicha SENTGACHA aniq taqsimlaydi (yig'indi = total)"""
    cents = int(round(float(total) * 100))
    w = [max(0.0, float(x)) for x in weights]
    if sum(w) <= 0: w = [1.0] * len(w)
    W = sum(w)
    raw = [cents * x / W for x in w]
    base = [int(math.floor(x)) for x in raw]
    rem = cents - sum(base)
    for i in sorted(range(len(raw)), key=lambda i: -(raw[i] - base[i]))[:max(0, rem)]:
        base[i] += 1
    return [b / 100 for b in base]

def get_product_specs(product_id):
    conn = db(); c = conn.cursor()
    c.execute('SELECT spec_name,spec_value FROM product_specs WHERE product_id=? ORDER BY id', (product_id,))
    rows = c.fetchall(); conn.close()
    return rows

def get_product_photos(product_id):
    conn = db(); c = conn.cursor()
    c.execute('SELECT file_id FROM product_photos WHERE product_id=? ORDER BY order_num', (product_id,))
    rows = [r[0] for r in c.fetchall()]; conn.close()
    return rows

def add_product(name, cat, sup, qty, cost, price, factory_price=0, warranty_days=90):
    conn = db(); c = conn.cursor()
    try:
        c.execute('INSERT INTO products (name,cat,supplier,qty,cost,price,factory_price,warranty_days) VALUES (?,?,?,?,?,?,?,?)',
                  (name, cat, sup, qty, cost, price, factory_price, warranty_days))
        pid = c.lastrowid
        if qty: _sm_yoz(c, pid, name, int(qty), int(qty), 'yangi_tovar', cost)
        conn.commit(); conn.close()
        log_op('add_product', {'name':name,'cat':cat,'qty':qty,'cost':cost,'price':price})
        return pid
    except sqlite3.IntegrityError:      # shu nomli mahsulot allaqachon bor
        conn.close(); return None
    except Exception:
        log.exception("add_product"); conn.close(); return None

def update_product(pid, **kwargs):
    conn = db(); c = conn.cursor()
    for k, v in kwargs.items():
        if k == 'qty':
            stock_set(c, pid, int(v), 'tuzatish', 'update_product')
        elif k in ('name','cat','supplier','cost','price','factory_price','warranty_days','active'):
            c.execute(f'UPDATE products SET {k}=? WHERE id=?', (v, pid))
    conn.commit(); conn.close()

def add_spec(product_id, spec_name, spec_value):
    conn = db(); c = conn.cursor()
    c.execute('INSERT INTO product_specs (product_id,spec_name,spec_value) VALUES (?,?,?)',
              (product_id, spec_name, spec_value))
    conn.commit(); conn.close()

def add_photo(product_id, file_id):
    conn = db(); c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM product_photos WHERE product_id=?', (product_id,))
    order = c.fetchone()[0]
    c.execute('INSERT INTO product_photos (product_id,file_id,order_num) VALUES (?,?,?)',
              (product_id, file_id, order))
    conn.commit(); conn.close()

def _sotuv_tx(c, now, pid, pname, qty, price, cost, discount=0, customer='', ctype='B2C',
              cash=True, method='naqd', seller_id=0, seller_name='', serials=None):
    """Bitta sotuv qatori — CHAQIRUVCHINING tranzaksiyasi ichida (commit/rollback chaqiruvchida).
    Astatka yetmasa None qaytaradi (hech narsa yozilmaydi). Aks holda (sale_id, revenue, profit)."""
    revenue = round(price * qty, 2)              # pul — sentgacha (313.3333*3 = 939.9999 bo'lib qolmasin)
    profit = round(revenue - (cost or 0) * qty, 2)
    d, t = now.strftime('%Y-%m-%d'), now.strftime('%H:%M')
    c.execute('INSERT INTO sales (date,time,product,qty,unit_cost,revenue,profit,discount,customer,customer_type) VALUES (?,?,?,?,?,?,?,?,?,?)',
              (d, t, pname, qty, cost, revenue, profit, discount, customer, ctype))
    sale_id = c.lastrowid
    if stock_move(c, pid, -qty, 'sotuv', ref=f's{sale_id}', user=(seller_id, seller_name), unit_cost=cost, now=now) is None:
        return None                              # astatka yetmadi — chaqiruvchi rollback qiladi (sotuv ham yozilmaydi)
    if seller_id or seller_name:
        c.execute('UPDATE sales SET seller_id=?, seller_name=? WHERE id=?', (int(seller_id or 0), seller_name or '', sale_id))
    # Kafolat
    c.execute('SELECT COALESCE(warranty_days,0) FROM products WHERE id=?', (pid,))
    w = c.fetchone(); wdays = (w[0] or 0) if w else 0
    end = (now + timedelta(days=wdays)).strftime('%Y-%m-%d') if wdays > 0 else ''
    if serials:                                  # 10-bosqich: har serialga alohida kafolat; band serial → _SerialXato
        c.execute("SELECT id, serial FROM serials WHERE id IN (%s)" % ",".join("?" * len(serials)), [int(x) for x in serials])
        _snom = dict(c.fetchall())
        _sotuv_seriallar(c, sale_id, pid, serials, d, customer, end, (seller_id, seller_name))
        if wdays > 0:
            for _sr in serials:
                c.execute('INSERT INTO warranties (sale_id,product,customer,start_date,end_date,serial) VALUES (?,?,?,?,?,?)',
                          (sale_id, pname, customer, d, end, _snom.get(int(_sr), '')))
    elif wdays > 0:
        c.execute('INSERT INTO warranties (sale_id,product,customer,start_date,end_date) VALUES (?,?,?,?,?)',
                  (sale_id, pname, customer, d, end))
    # Kassa — shu tranzaksiya ichida (sotuv bor-u kassa yo'q holati bo'lmasin)
    if cash:
        c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                  (d, t, 'kirim', revenue, 'sotuv', f'{pname} x{qty} (#{sale_id})', method or 'naqd'))
    return sale_id, revenue, profit

def save_sale(pid, pname, qty, price, cost, discount=0, customer='', ctype='B2C', cash=True, method='naqd',
              seller_id=0, seller_name=''):
    """Sotuv BITTA tranzaksiyada: astatka kamayadi + sotuv yoziladi + kassaga kirim + kafolat.
    Astatka yetmasa hech narsa yozilmaydi (avval sotuv yozilib, astatka/kassa o'zgarmay qolardi)."""
    now = datetime.now()
    conn = db(); c = conn.cursor()
    try:
        r = _sotuv_tx(c, now, pid, pname, qty, price, cost, discount, customer, ctype, cash, method,
                      seller_id, seller_name)
        if r is None:
            conn.rollback(); conn.close()
            return False, None
        sale_id, revenue, profit = r
        conn.commit()
    except Exception:
        conn.rollback(); conn.close()
        raise
    conn.close()
    ok = True
    # Mijozga bog'lash (aniq moslik bo'yicha, yo'q bo'lsa yaratadi)
    if ok and customer:
        try:
            cid = mijoz_id(customer, create=True, ctype=ctype)
            if cid:
                conn = db(); c = conn.cursor()
                c.execute('UPDATE sales SET customer_id=? WHERE id=?', (cid, sale_id))
                conn.commit(); conn.close()
                yangila_jami(cid)
                reorder_yangila(cid, pname, now.strftime('%Y-%m-%d'))
        except Exception as e:
            log.warning(f'mijozga boglash: {e}')
    if ok:
        log_op('sale', {'sale_id':sale_id,'product':pname,'qty':qty,'price':price,'profit':profit})
    return ok, sale_id

class _AstatkaYetmadi(Exception):
    pass

def pos_saqlash(qatorlar, mijoz='', cid=0, method='naqd', seller_id=0, seller_name='', ctype='B2C'):
    """Savatni BITTA tranzaksiyada saqlaydi (hammasi yoki hech narsa).
    qatorlar: [{'pid','name','qty','unit','disc'}] — unit: chegirmadan keyingi dona narxi ($).
    Tannarx savatdan emas, bazadan olinadi. Nasiya: kassaga tushmaydi, mijozga bitta debitorlik yoziladi.
    Qaytaradi: {'ok':True,'sales':[...],'jami','foyda','debt_id'} yoki {'ok':False,'error':...}."""
    if not qatorlar:
        return {'ok': False, 'error': "Savat bo'sh"}
    if is_closed(today()):
        return {'ok': False, 'error': f"{today()[:7]} davri yopilgan — sotuv yozib bo'lmaydi (/och)"}
    nasiya = method == 'nasiya'
    mijoz = (mijoz or '').strip()
    if nasiya and not (mijoz and cid):
        return {'ok': False, 'error': "Nasiya uchun mijoz tanlanishi kerak"}
    if not nasiya and method not in TOLOV_USULLARI:
        return {'ok': False, 'error': f"To'lov usuli noma'lum: {method}"}
    now = datetime.now()
    d, t = now.strftime('%Y-%m-%d'), now.strftime('%H:%M')
    conn = db(); c = conn.cursor()
    done = []; debt_id = None
    try:
        for q in qatorlar:
            qty = int(q['qty'])
            if qty <= 0: raise ValueError("Soni noto'g'ri")
            c.execute('SELECT name, cost FROM products WHERE id=?', (q['pid'],))
            row = c.fetchone()
            if not row: raise _AstatkaYetmadi(q.get('name') or str(q['pid']))
            r = _sotuv_tx(c, now, q['pid'], row[0], qty, float(q['unit']), row[1] or 0, round(float(q.get('disc') or 0), 1),
                          mijoz, ctype, cash=not nasiya, method=(method if not nasiya else 'naqd'),
                          seller_id=seller_id, seller_name=seller_name, serials=(q.get('serials') or None))
            if r is None: raise _AstatkaYetmadi(row[0])
            sid, rev, prof = r
            if cid:
                c.execute('UPDATE sales SET customer_id=? WHERE id=?', (cid, sid))
                if q.get('serials'): c.execute('UPDATE serials SET customer_id=? WHERE sale_id=?', (cid, sid))
            # Bekor qilish (undo) ro'yxati uchun — o'sha tranzaksiyada
            c.execute('INSERT INTO op_log (date,time,op_type,data_json) VALUES (?,?,?,?)',
                      (d, t, 'sale', json.dumps({'sale_id': sid, 'product': row[0], 'qty': qty,
                                                  'price': float(q['unit']), 'profit': prof}, ensure_ascii=False)))
            done.append({'sale_id': sid, 'product': row[0], 'qty': qty, 'summa': rev, 'foyda': prof})
        jami = round(sum(x['summa'] for x in done), 2)
        if nasiya:
            izoh = ("nasiya: " + ", ".join(f"{x['product']} x{x['qty']}" for x in done)
                    + " (" + ",".join(f"#s{x['sale_id']}" for x in done) + ")")
            c.execute('INSERT INTO debts (date,person,amount,type,note) VALUES (?,?,?,?,?)',
                      (d, mijoz, jami, DEBITOR, izoh))
            debt_id = c.lastrowid
            try:
                c.execute('UPDATE debts SET customer_id=? WHERE id=?', (cid, debt_id))
            except sqlite3.OperationalError:
                pass
        conn.commit()
    except _AstatkaYetmadi as e:
        conn.rollback(); conn.close()
        return {'ok': False, 'error': f"Astatka yetmadi: {e}. Savat saqlanmadi — hech narsa yozilmadi."}
    except _SerialXato as e:
        conn.rollback(); conn.close()
        return {'ok': False, 'error': f"Serial {e} band yoki topilmadi. Savat saqlanmadi — serialni qayta tanlang."}
    except Exception:
        conn.rollback(); conn.close()
        raise
    conn.close()
    # Muhim bo'lmagan yangilashlar (xato bo'lsa ham sotuv saqlangan)
    if cid:
        try:
            yangila_jami(cid)
            for x in done: reorder_yangila(cid, x['product'], d)
        except Exception as e:
            log.warning(f'pos mijoz yangilash: {e}')
    return {'ok': True, 'sales': done, 'jami': jami,
            'foyda': round(sum(x['foyda'] for x in done), 2), 'debt_id': debt_id}

def reverse_sale(sale_id):
    """Sotuvni bekor qiladi: sotuv belgisi + astatka + kafolat + kassa qaytimi BITTA tranzaksiyada
    (avval kassa qaytimi alohida yozilardi — o'rtada xato bo'lsa astatka qaytib, pul qaytmay qolardi)."""
    conn = db(); c = conn.cursor()
    cid = 0
    try:
        c.execute('SELECT * FROM sales WHERE id=? AND reversed=0', (sale_id,))
        row = c.fetchone()
        if not row: conn.close(); return False
        try:                                     # 10-bosqich: qisman qaytarilgan sotuv yoki qaytarish qatori → 📥 Qaytarish / undo
            c.execute("SELECT COALESCE(return_of,0) FROM sales WHERE id=?", (sale_id,)); _ro = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM sales WHERE return_of=? AND reversed=0", (sale_id,)); _rn = c.fetchone()[0]
        except sqlite3.OperationalError:
            _ro = _rn = 0
        if _ro or _rn: conn.close(); return False
        product, qty, revenue = row[3], row[4], row[6]
        c.execute('UPDATE sales SET reversed=1 WHERE id=? AND reversed=0', (sale_id,))
        if c.rowcount == 0:
            conn.rollback(); conn.close(); return False
        c.execute("SELECT product_id FROM stock_moves WHERE kind='sotuv' AND ref=? ORDER BY id DESC LIMIT 1", (f's{sale_id}',))
        pr = c.fetchone()
        if not pr:
            c.execute('SELECT id FROM products WHERE name=?', (product,)); pr = c.fetchone()
        if pr:
            stock_move(c, pr[0], qty, 'qaytish', reason='sotuv bekor', ref=f's{sale_id}', unit_cost=row[5], allow_negative=True)
        c.execute("UPDATE warranties SET status='cancelled' WHERE sale_id=?", (sale_id,))
        try:
            c.execute("UPDATE serials SET status='omborda', sale_id=0, sold_date='', customer='', customer_id=0, warranty_end='' "
                      "WHERE sale_id=? AND status='sotilgan'", (sale_id,))
        except sqlite3.OperationalError:
            pass
        c.execute("SELECT COUNT(*) FROM cash_box WHERE type='kirim' AND note LIKE ?", (f'%(#{sale_id})',))
        if c.fetchone()[0] > 0:
            now = datetime.now()
            c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                      (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'), 'chiqim', revenue, 'qaytarish',
                       f'{product} bekor (#{sale_id})', 'naqd'))
        else:
            # Kassaga tushmagan = nasiya sotuv: mijozning debitorligi ham kamayadi/yopiladi
            _nasiya_qaytar(c, sale_id, row)
        try:
            c.execute('SELECT COALESCE(customer_id,0) FROM sales WHERE id=?', (sale_id,))
            cid = (c.fetchone() or [0])[0] or 0
        except sqlite3.OperationalError:     # customer_id ustuni hali yo'q (eski baza)
            cid = 0
        conn.commit()
    except Exception:
        conn.rollback(); conn.close()
        raise
    conn.close()
    if cid:
        try: yangila_jami(cid)               # mijoz kartasidagi jami xarid ham kamaysin
        except Exception as e: log.warning(f'yangila_jami: {e}')
    return True

def add_expense(amount, category, expense_type='period', note='', cash=True, date=None):
    d = date or datetime.now().strftime('%Y-%m-%d')
    conn = db(); c = conn.cursor()
    c.execute('INSERT INTO expenses (date,amount,category,expense_type,note) VALUES (?,?,?,?,?)',
              (d, amount, category, expense_type, note))
    eid = c.lastrowid
    conn.commit(); conn.close()
    log_op('expense', {'id':eid,'amount':amount,'type':expense_type,'note':note,'cash':cash})
    if cash:
        add_cash(amount, 'chiqim', category, f'{note} (#x{eid})')
    return eid

def add_transit(supplier, product, qty, unit_cost, deposit=0, bank_fee=0, delivery_fee=0, note='', cash_method=None):
    """cash_method berilsa — avans ('zavod_qarz') va bank/yetkazish ('zavod_xarajat') kassadan chiqim bo'lib
    shu tranzaksiyada yoziladi (🏭 Zavod buyurtmasi bilan bir xil). Berilmasa — avvalgidek kassaga tegmaydi."""
    total = qty * unit_cost
    real_cost = unit_cost + (bank_fee + delivery_fee) / qty if qty else unit_cost
    remaining = total - deposit
    now = datetime.now()
    conn = db(); c = conn.cursor()
    c.execute('''INSERT INTO transit
        (date,supplier,product,qty,unit_cost,total_cost,deposit,remaining,
         bank_fee,delivery_fee,real_cost,note)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        (now.strftime('%Y-%m-%d'), supplier, product, qty, unit_cost,
         total, deposit, remaining, bank_fee, delivery_fee, real_cost, note))
    tid = c.lastrowid
    try: c.execute("UPDATE transit SET bs_usul='toliq' WHERE id=?", (tid,))
    except sqlite3.OperationalError: pass          # ustun hali yo'q (init dan oldin) — keyingi init belgilaydi
    if cash_method:
        d_, t_ = now.strftime('%Y-%m-%d'), now.strftime('%H:%M')
        if deposit > 0:
            c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                      (d_, t_, 'chiqim', round(deposit, 2), 'zavod_qarz', f"{supplier} zakaz #{tid} avans", cash_method))
        if (bank_fee or 0) + (delivery_fee or 0) > 0:
            c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                      (d_, t_, 'chiqim', round((bank_fee or 0) + (delivery_fee or 0), 2), 'zavod_xarajat',
                       f"{supplier} zakaz #{tid} bank/yetkazish", cash_method))
    conn.commit(); conn.close()
    log_op('transit', {'id':tid,'supplier':supplier,'product':product,'qty':qty,'total':total,'deposit':deposit})
    return tid

def arrive_transit(tid):
    """Yo'ldagi tovar keldi: astatkaga qo'shadi, sebestni O'RTACHA tortilgan usulda yangilaydi (IAS 2)."""
    conn = db(); c = conn.cursor()
    c.execute('SELECT * FROM transit WHERE id=? AND status=?', (tid, 'yolda'))
    row = c.fetchone()
    if not row: conn.close(); return None
    # transit ustunlari: 0 id,1 date,2 supplier,3 product,4 qty,5 unit_cost,6 total_cost,7 deposit,
    # 8 remaining,9 bank_fee,10 delivery_fee,11 real_cost (avval row[10] — DOSTAVKA summasi — sebest deb yozilardi)
    product, qty, real_cost = row[3], row[4] or 0, row[11]
    if real_cost is None: real_cost = row[5] or 0
    c.execute('SELECT COALESCE(received_qty,0), COALESCE(po_id,0) FROM transit WHERE id=?', (tid,))
    _rq, _po = c.fetchone()
    qty = max(0, qty - _rq)                  # 8-bosqich: qisman kelgan bo'lsa — faqat qolgani
    # Mahsulot: avval aniq nom, keyin yagona moslik, oxirida eski LIKE usuli
    c.execute('SELECT id, qty, cost FROM products WHERE name=?', (product,))
    pid_row = c.fetchone()
    if not pid_row:
        p, _ = match_product(product, prods=get_products(active_only=False))
        if p: pid_row = (p['id'], p['qty'], p['cost'])
    if not pid_row:
        c.execute('SELECT id, qty, cost FROM products WHERE name LIKE ?', (f'%{product}%',))
        pid_row = c.fetchone()
    now = datetime.now().strftime('%Y-%m-%d')
    c.execute("UPDATE transit SET status='keldi', arrived_date=?, received_qty=qty WHERE id=?", (now, tid))
    if pid_row and qty > 0:
        pid, old_q, old_c = pid_row[0], max(0, pid_row[1] or 0), pid_row[2] or 0
        jami_q = old_q + qty
        new_cost = round((old_q * old_c + qty * real_cost) / jami_q, 2) if jami_q > 0 else real_cost
        stock_move(c, pid, qty, 'zavod_kirim', reason=f"zakaz #{tid}", ref=f't{tid}', unit_cost=real_cost,
                   new_cost=new_cost, supplier=row[2] or '', allow_negative=True)
    if _po:
        _po_holat_avto(c, _po)
    conn.commit(); conn.close()
    return {'product': product, 'qty': qty, 'real_cost': real_cost, 'found': bool(pid_row)}

def pay_transit_deposit(tid, amount, c=None):
    """c berilsa — chaqiruvchining tranzaksiyasi ichida (commit qilmaydi), aks holda o'zi ochib yopadi."""
    sql = 'UPDATE transit SET deposit=deposit+?, remaining=MAX(0,remaining-?) WHERE id=?'
    if c is not None:
        c.execute(sql, (amount, amount, tid)); return c.rowcount
    conn = db(); cc = conn.cursor()
    cc.execute(sql, (amount, amount, tid)); n = cc.rowcount
    conn.commit(); conn.close(); return n

def add_customer(name, phone='', ctype='', notes=''):
    """Mijoz qo'shadi. Ism bir xil bo'lsa yangi ma'lumot bilan to'ldiradi.
       Qaytaradi: ('qoshildi'|'yangilandi'|'xato', mijoz_id)"""
    name = (name or '').strip()
    if not name: return ('xato', None)
    conn = db(); c = conn.cursor()
    c.execute('SELECT id,phone,type,notes FROM customers WHERE lower(trim(name))=lower(?)', (name,))
    row = c.fetchone()
    if row:
        cid, old_ph, old_t, old_n = row
        c.execute('UPDATE customers SET phone=?, type=?, notes=? WHERE id=?',
                  (phone or old_ph or '', ctype or old_t or 'B2C', notes or old_n or '', cid))
        conn.commit(); conn.close()
        return ('yangilandi', cid)
    now = datetime.now().strftime('%Y-%m-%d')
    c.execute('INSERT INTO customers (name,phone,type,notes,created,total_purchases) VALUES (?,?,?,?,?,0)',
              (name, phone, ctype or 'B2C', notes, now))
    cid = c.lastrowid
    conn.commit(); conn.close()
    return ('qoshildi', cid)

def find_customers(q=''):
    conn = db(); c = conn.cursor()
    if q:
        c.execute("SELECT id,name,phone,type,total_purchases,notes,created FROM customers WHERE name LIKE ? ORDER BY total_purchases DESC", (f'%{q}%',))
    else:
        c.execute("SELECT id,name,phone,type,total_purchases,notes,created FROM customers ORDER BY total_purchases DESC")
    rows = c.fetchall(); conn.close(); return rows

def delete_customer(name):
    conn = db(); c = conn.cursor()
    c.execute("DELETE FROM customers WHERE lower(trim(name))=lower(?)", ((name or '').strip(),))
    n = c.rowcount; conn.commit(); conn.close(); return n

# ── QARZ MODELI: faqat IKKI tur ───────────────────────────────────
#   DEBITORLIK  — mijoz BIZGA qarz (bizdan qarz / nasiya)     → kutilayotgan KIRIM
#   KREDITORLIK — BIZ zavod/yetkazuvchiga qarzmiz (zavoddan qarz) → kutilayotgan CHIQIM
# Avval bir xil qiymat kodning turli joyida teskari ma'noda ishlatilardi: eski matn rejimi 'olindi'ni
# "biz berdik" (debitor) deb, AI agent/balans/nasiya esa 'berildi'ni debitor deb hisoblardi.
# Endi bazaga faqat 'debitorlik'/'kreditorlik' yoziladi; eski qiymatlar init_db da bir marta
# shu turlarga o'tkaziladi (asl qiymat debts.type_old ustunida saqlanadi).
DEBITOR, KREDITOR = 'debitorlik', 'kreditorlik'
_DEBITOR_ALIAS = ('debitorlik', 'debitor', 'receivable', 'berildi', 'bizga')
_KREDITOR_ALIAS = ('kreditorlik', 'kreditor', 'payable', 'olindi', 'bizdan')
# SQL uchun doimiy ro'yxat (foydalanuvchi matni emas). Eski qiymatlar ham o'qiladi —
# migratsiyagacha bo'lgan zaxira tiklansa ham hisob to'g'ri chiqsin.
DEBITOR_SQL = "(" + ",".join(f"'{a}'" for a in _DEBITOR_ALIAS) + ")"
KREDITOR_SQL = "(" + ",".join(f"'{a}'" for a in _KREDITOR_ALIAS) + ")"

def debt_turi(v):
    """Har qanday (eski/yangi) qarz turini 'debitorlik' | 'kreditorlik' | None ga keltiradi."""
    s = str(v or '').strip().lower()
    if s in _DEBITOR_ALIAS: return DEBITOR
    if s in _KREDITOR_ALIAS: return KREDITOR
    return None

# ── Mijozni o'chirish: egasining tasdig'i bilan ──────────────────
_DEL_PENDING = {}            # token -> {'name', 'ts'}
_DEL_TTL = 600               # 10 daqiqa

def _mijoz_topish_aniq(name):
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, name FROM customers WHERE lower(trim(name))=lower(?)", ((name or '').strip(),))
    rows = c.fetchall(); conn.close(); return rows

async def _mijoz_ochirish_sorovi(name, ctx):
    """AI agent delete_customer so'raganda: o'chirmaydi, egasiga Ha/Yo'q tugmalarini yuboradi."""
    name = (name or '').strip()
    rows = _mijoz_topish_aniq(name) if name else []
    if not rows:
        return {"ok": False, "error": f"Mijoz topilmadi (aniq ism kerak): {name!r}"}
    if ctx is None or not getattr(ctx, 'bot', None):
        return {"ok": False, "error": "Tasdiqlash tugmalarini yuborib bo'lmadi — o'chirilmadi."}
    now = time.time()
    for k in [k for k, v in _DEL_PENDING.items() if now - v['ts'] > _DEL_TTL]:
        _DEL_PENDING.pop(k, None)
    tok = secrets.token_hex(4)
    _DEL_PENDING[tok] = {'name': rows[0][1], 'ts': now}
    conn = db(); c = conn.cursor()
    c.execute("SELECT COUNT(*), COALESCE(SUM(revenue),0) FROM sales WHERE reversed=0 AND COALESCE(customer_id,0)=?", (rows[0][0],))
    ns, sm = c.fetchone(); conn.close()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ha, o'chir", callback_data=f"delcust_yes_{tok}"),
                                InlineKeyboardButton("❌ Yo'q", callback_data=f"delcust_no_{tok}")]])
    await ctx.bot.send_message(
        chat_id=OWNER_ID,
        text=(f"🗑 Mijozni o'chirishni tasdiqlaysizmi?\n\n👤 {rows[0][1]}\n"
              f"Sotuvlar: {ns} ta · {fmt(sm)}\n\n(Sotuv va qarz yozuvlari o'chmaydi, faqat mijoz kartasi.)"),
        reply_markup=kb)
    return {"ok": False, "pending_confirmation": True,
            "message": "O'CHIRILMADI hali: egasiga 'Ha, o'chir / Yo'q' tugmalari yuborildi. Tugma bosilgandan keyin bajariladi."}

async def _mijoz_ochirish_callback(q, data):
    """delcust_yes_<token> / delcust_no_<token> (faqat egasi — on_callback da tekshiriladi)."""
    try: _, javob, tok = data.split('_', 2)
    except ValueError: return
    p = _DEL_PENDING.pop(tok, None)
    if not p or time.time() - p['ts'] > _DEL_TTL:
        await q.edit_message_text("⏰ Tasdiq muddati o'tgan yoki allaqachon bajarilgan. Mijoz o'chirilmadi.")
        return
    if javob != 'yes':
        await q.edit_message_text(f"❎ Bekor qilindi. {p['name']} o'chirilmadi.")
        return
    n = await asyncio.to_thread(delete_customer, p['name'])
    await q.edit_message_text(f"🗑 {p['name']} o'chirildi." if n else f"❌ {p['name']} topilmadi (allaqachon o'chirilgan bo'lishi mumkin).")

def add_debt(person, amount, dtype, note=''):
    """dtype: 'debitorlik' (mijoz bizga qarz) yoki 'kreditorlik' (biz qarzmiz). Qaytaradi: debt id."""
    turi = debt_turi(dtype)
    if not turi:
        raise ValueError(f"Qarz turi noma'lum: {dtype!r} — 'debitorlik' yoki 'kreditorlik' bo'lishi kerak")
    now = datetime.now()
    conn = db(); c = conn.cursor()
    c.execute('INSERT INTO debts (date,person,amount,type,note) VALUES (?,?,?,?,?)',
              (now.strftime('%Y-%m-%d'), person, round(float(amount or 0), 2), turi, note))
    did = c.lastrowid
    conn.commit(); conn.close()
    return did

def _qarz_turlarini_birxillash(c):
    """Eski qarz turlarini 2 turga o'tkazadi. Idempotent (har ishga tushishda xavfsiz), hech narsa o'chirilmaydi:
    asl qiymat type_old ustuniga bir marta yoziladi. Xarita: berildi→debitorlik, olindi→kreditorlik,
    'nasiya:' izohli yozuvlar → doim debitorlik."""
    try:
        c.execute("ALTER TABLE debts ADD COLUMN type_old TEXT")
    except sqlite3.OperationalError:
        pass                                   # ustun allaqachon bor
    for canon, aliases in ((DEBITOR, _DEBITOR_ALIAS), (KREDITOR, _KREDITOR_ALIAS)):
        eski = [a for a in aliases if a != canon]
        q = ",".join("?" * len(eski))
        c.execute(f"UPDATE debts SET type_old=type WHERE type_old IS NULL AND lower(trim(type)) IN ({q})", eski)
        c.execute(f"UPDATE debts SET type=? WHERE lower(trim(type)) IN ({q})", [canon] + eski)
    c.execute("UPDATE debts SET type_old=type WHERE type_old IS NULL AND note LIKE 'nasiya:%' AND type IS NOT ?", (DEBITOR,))
    c.execute("UPDATE debts SET type=? WHERE note LIKE 'nasiya:%' AND type IS NOT ?", (DEBITOR, DEBITOR))
    c.execute("SELECT type, COUNT(*) FROM debts WHERE type IS NULL OR type NOT IN (?,?) GROUP BY type", (DEBITOR, KREDITOR))
    for t, n in c.fetchall():
        log.warning("debts: %s ta yozuvning turi noma'lum (%r) — /qarzlar da alohida ko'rsatiladi", n, t)

def _nasiya_qaytar(c, sale_id, row):
    """reverse_sale ichida, o'sha tranzaksiyada: nasiya sotuvga mos debitorlikni kamaytiradi yoki yopadi.
    Avval '#s<id>' belgisi bo'yicha; eski yozuvlarda — mijoz + sana + 'nasiya: <mahsulot> x<son>' izohi bo'yicha."""
    summa = round(row[6] or 0, 2)
    if summa <= 0: return 0
    c.execute(f"SELECT id, amount, note FROM debts WHERE paid=0 AND type IN {DEBITOR_SQL} AND note LIKE ? "
              "ORDER BY id DESC", (f'%#s{sale_id}%',))
    tag = re.compile(rf"#s{int(sale_id)}(?!\d)")
    hit = next((r for r in c.fetchall() if tag.search(r[2] or '')), None)
    if not hit and (row[9] or '').strip():
        c.execute(f"SELECT id, amount, note FROM debts WHERE paid=0 AND type IN {DEBITOR_SQL} "
                  "AND person=? AND date=? AND note LIKE ? AND note NOT LIKE '%#s%' ORDER BY id DESC LIMIT 1",
                  (row[9], row[1], f'nasiya:%{row[3]} x{row[4]}%'))
        hit = c.fetchone()
    if not hit: return 0
    did, amt, note = hit[0], round(hit[1] or 0, 2), hit[2] or ''
    qoldiq = round(amt - summa, 2)
    if qoldiq <= 0.01:
        c.execute("UPDATE debts SET paid=1, note=? WHERE id=?", (f"{note} | yopildi: sotuv #s{sale_id} bekor", did))
        return amt
    c.execute("UPDATE debts SET amount=?, note=? WHERE id=?",
              (qoldiq, f"{note} | -{summa:.2f}: sotuv #s{sale_id} bekor", did))
    return summa

# ── QARZ TO'LOVI ──────────────────────────────────────────────────
TOLOV_USULLARI = ('naqd', 'karta', 'payme', 'click', 'otkazma')
_USUL_ALIAS = {'naqd': 'naqd', 'cash': 'naqd', 'karta': 'karta', 'plastik': 'karta', 'card': 'karta',
               'humo': 'karta', 'uzcard': 'karta', 'payme': 'payme', 'click': 'click',
               'otkazma': 'otkazma', "o'tkazma": 'otkazma', 'bank': 'otkazma'}

def tolov_usuli(v):
    s = str(v or '').strip().lower()
    for ch in ('ʻ', '’', '‘', '`', 'ʼ'): s = s.replace(ch, "'")
    return _USUL_ALIAS.get(s)

def _usd2(v): return f"${v:,.2f}"

def _nom_tanla(q, nomlar):
    """Ism bo'yicha tanlash: aniq → boshi ('Ali' ↔ 'Ali Valiyev') → ichida → o'xshash.
    Qaytaradi: (tanlangan_nom | None, nomzodlar). Bir nechtasi mos kelsa — taxmin qilmaydi."""
    n = norm_ism(q)
    uniq = {}
    for nm in nomlar:
        k = norm_ism(nm)
        if k: uniq.setdefault(k, nm)
    if not n: return None, list(uniq.values())
    if n in uniq: return uniq[n], []
    for mos in (lambda k: k.startswith(n + ' ') or n.startswith(k + ' '),
                lambda k: (len(n) >= 3 and n in k) or (len(k) >= 3 and k in n)):
        hits = [k for k in uniq if mos(k)]
        if len(hits) == 1: return uniq[hits[0]], []
        if hits: return None, [uniq[k] for k in hits]
    close = difflib.get_close_matches(n, list(uniq), n=3, cutoff=0.8)
    if len(close) == 1: return uniq[close[0]], []
    return None, [uniq[k] for k in close]

def ochiq_qarzlar(turi):
    """{ism: jami} — ochiq debitorlik yoki kreditorlik (kreditorlikka zavod qoldig'i ham kiradi)."""
    sql = DEBITOR_SQL if turi == DEBITOR else KREDITOR_SQL
    conn = db(); c = conn.cursor()
    c.execute(f"SELECT person, COALESCE(SUM(amount),0) FROM debts WHERE paid=0 AND amount>0 AND type IN {sql} GROUP BY person")
    out = defaultdict(float)
    for p, s in c.fetchall(): out[p or '?'] += s
    if turi == KREDITOR:
        c.execute("SELECT supplier, COALESCE(SUM(remaining),0) FROM transit WHERE remaining>0 GROUP BY supplier")
        for p, s in c.fetchall(): out[p or '?'] += s
    conn.close()
    return {k: round(v, 2) for k, v in out.items()}

def pay_debt(kind, person, amount, method='naqd', note='', transit_ids=None):
    """Qarz to'lovi BITTA tranzaksiyada.
    debitorlik — mijoz bizga to'ladi: kassaga KIRIM, mijozning ochiq debitorligi eng eskisidan (FIFO) kamayadi.
    kreditorlik — biz to'ladik: kassadan CHIQIM, zavod qoldig'i (transit.remaining) va boshqa kreditorlik FIFO kamayadi.
    Ortiqcha summa qabul qilinmaydi (qarz hech qachon manfiy bo'lmaydi). op_log ga 'debt_payment' yoziladi (/undo)."""
    turi = debt_turi(kind)
    if not turi:
        return {'ok': False, 'error': "Tur 'debitorlik' (mijoz to'ladi) yoki 'kreditorlik' (biz to'ladik) bo'lishi kerak"}
    usul = tolov_usuli(method or 'naqd')
    if not usul:
        return {'ok': False, 'error': f"To'lov usuli noma'lum: {method}. Mumkin: {', '.join(TOLOV_USULLARI)}"}
    try: amount = round(float(amount), 2)
    except (TypeError, ValueError): amount = 0.0
    if amount <= 0:
        return {'ok': False, 'error': "Summa 0 dan katta bo'lishi kerak"}
    sana = today()
    if is_closed(sana):
        return {'ok': False, 'error': f"{sana[:7]} davri yopilgan — to'lov yozib bo'lmaydi. Ochish: /och {sana[:7]}"}
    sql = DEBITOR_SQL if turi == DEBITOR else KREDITOR_SQL
    conn = db(); c = conn.cursor()
    try:
        c.execute(f"SELECT id, date, person, amount, COALESCE(customer_id,0) FROM debts "
                  f"WHERE paid=0 AND amount>0 AND type IN {sql}")
        debts = c.fetchall()
        tr = []
        if turi == KREDITOR:
            c.execute("SELECT id, date, supplier, remaining FROM transit WHERE remaining>0")
            tr = c.fetchall()
        nomlar = [d[2] for d in debts] + [t[2] for t in tr]
        if transit_ids is not None:
            # Faqat ko'rsatilgan zavod buyurtmasi qatorlari (🏭 Zavod → To'lov); boshqa qarzlarga tegmaydi
            ids_ = {int(i) for i in transit_ids}
            tr = [t for t in tr if t[0] in ids_] if turi == KREDITOR else []
            debts = []
            if not tr:
                conn.close()
                return {'ok': False, 'error': "Bu buyurtma bo'yicha ochiq qarz topilmadi"}
            person = tr[0][2] or person
            nomlar = [t[2] for t in tr]
        tanlangan, nomzod = _nom_tanla(person, nomlar)
        if not tanlangan:
            conn.close()
            if nomzod:
                return {'ok': False, 'error': f"'{person}' aniq emas — qaysi biri?", 'variantlar': nomzod}
            return {'ok': False, 'error': f"'{person}' bo'yicha ochiq {turi} topilmadi",
                    'variantlar': sorted({n for n in nomlar if n})[:10]}
        tn = norm_ism(tanlangan)
        cids = {d[4] for d in debts if norm_ism(d[2]) == tn and d[4]}
        items = [('debt', d[0], d[1] or '', round(d[3] or 0, 2)) for d in debts
                 if norm_ism(d[2]) == tn or (d[4] and d[4] in cids)]
        items += [('transit', t[0], t[1] or '', round(t[3] or 0, 2)) for t in tr if norm_ism(t[2]) == tn]
        items.sort(key=lambda i: (i[2], 0 if i[0] == 'transit' else 1, i[1]))     # FIFO: eng eskisi birinchi
        jami = round(sum(i[3] for i in items), 2)
        if amount > jami + 0.005:
            conn.close()
            return {'ok': False, 'qarz': jami,
                    'error': f"Ortiqcha to'lov: {tanlangan} bo'yicha ochiq {turi} faqat {_usd2(jami)}. "
                             f"{_usd2(amount)} qabul qilinmadi — summani tekshiring."}
        amount = min(amount, jami)
        now = datetime.now(); d_, t_ = now.strftime('%Y-%m-%d'), now.strftime('%H:%M')
        c.execute('INSERT INTO op_log (date,time,op_type,data_json) VALUES (?,?,?,?)', (d_, t_, 'debt_payment', '{}'))
        op_id = c.lastrowid
        left = amount; done = []
        for src, iid, _sana, qoldiq in items:
            if left <= 0.004: break
            part = round(min(left, qoldiq), 2)
            yopildi = part >= qoldiq - 0.005
            if src == 'debt':
                # qoldiq kamayadi; 0 bo'lsa yopiladi (qaytarishda aynan shu summa qo'shiladi — tartibdan qat'i nazar to'g'ri)
                c.execute("UPDATE debts SET amount=ROUND(MAX(0, amount-?),2), paid=CASE WHEN amount-?<=0.005 THEN 1 ELSE 0 END "
                          "WHERE id=? AND paid=0", (part, part, iid))
                n = c.rowcount
            else:
                n = pay_transit_deposit(iid, part, c)
            if n != 1:
                raise RuntimeError(f"qarz yozuvi o'zgarib qoldi ({src} #{iid})")
            done.append({'src': src, 'id': iid, 'part': part, 'yopildi': yopildi})
            left = round(left - part, 2)
        # Kassa: zavod qismi 'zavod_qarz' (Excel import shu toifani hisobga oladi), qolgani alohida toifa
        cash_type = 'kirim' if turi == DEBITOR else 'chiqim'
        bo_lak = defaultdict(float)
        for it in done:
            cat = 'qarz_qaytdi' if turi == DEBITOR else ('zavod_qarz' if it['src'] == 'transit' else 'qarz_tolov')
            bo_lak[cat] += it['part']
        cash_ids = []
        for cat, s in bo_lak.items():
            izoh = (f"{tanlangan} qarz to'lovi (#p{op_id})" if turi == DEBITOR else f"{tanlangan} qarziga to'lov (#p{op_id})")
            if note: izoh += f" — {note}"
            c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                      (d_, t_, cash_type, round(s, 2), cat, izoh, usul))
            cash_ids.append(c.lastrowid)
        data = {'kind': turi, 'person': tanlangan, 'amount': amount, 'method': usul,
                'cash_ids': cash_ids, 'items': done, 'date': d_}
        c.execute('UPDATE op_log SET data_json=? WHERE id=?', (json.dumps(data, ensure_ascii=False), op_id))
        conn.commit()
    except Exception:
        conn.rollback(); conn.close()
        raise
    conn.close()
    return {'ok': True, 'op_id': op_id, 'kind': turi, 'person': tanlangan, 'paid': amount, 'method': usul,
            'qoldiq': max(0.0, round(jami - amount, 2)),
            'yopildi': sum(1 for i in done if i['yopildi']), 'qisman': sum(1 for i in done if not i['yopildi']),
            'items': done, 'kassa': round(get_cash_balance(), 2)}

def reverse_debt_payment(op_id):
    """Qarz to'lovini BITTA tranzaksiyada bekor qiladi: qarz qoldig'i qaytadi, kassaga teskari yozuv, op_log reversed=1."""
    conn = db(); c = conn.cursor()
    try:
        c.execute("SELECT date, data_json FROM op_log WHERE id=? AND op_type='debt_payment' AND reversed=0", (op_id,))
        r = c.fetchone()
        if not r:
            conn.close(); return False, "Topilmadi yoki allaqachon qaytarilgan"
        for s in (r[0], today()):
            if is_closed(s):
                conn.close(); return False, f"{s[:7]} davri yopilgan — to'lovni qaytarib bo'lmaydi (/och {s[:7]})"
        d = json.loads(r[1] or '{}')
        c.execute("UPDATE op_log SET reversed=1 WHERE id=? AND reversed=0", (op_id,))
        if c.rowcount != 1:
            conn.rollback(); conn.close(); return False, "Topilmadi yoki allaqachon qaytarilgan"
        for it in d.get('items', []):
            if it['src'] == 'debt':
                c.execute("UPDATE debts SET amount=ROUND(amount+?,2), paid=0 WHERE id=?", (it['part'], it['id']))
            else:
                c.execute("UPDATE transit SET deposit=deposit-?, remaining=remaining+? WHERE id=?",
                          (it['part'], it['part'], it['id']))
        now = datetime.now()
        c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                  (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'),
                   'chiqim' if d.get('kind') == DEBITOR else 'kirim', d.get('amount', 0), 'qaytarish',
                   f"qarz to'lovi bekor: {d.get('person', '')} (#p{op_id})", d.get('method') or 'naqd'))
        conn.commit()
    except Exception:
        conn.rollback(); conn.close()
        raise
    conn.close()
    return True, "qaytarildi"

def set_target(year, month, revenue, profit):
    conn = db(); c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO targets (year,month,target_revenue,target_profit) VALUES (?,?,?,?)',
              (year, month, revenue, profit))
    conn.commit(); conn.close()

def add_competitor(competitor, product, price, note=''):
    now = datetime.now()
    conn = db(); c = conn.cursor()
    our = find_product(product)
    our_price = our['price'] if our else 0
    c.execute('INSERT INTO competitors (date,competitor,product,their_price,our_price,note) VALUES (?,?,?,?,?,?)',
              (now.strftime('%Y-%m-%d'), competitor, product, price, our_price, note))
    conn.commit(); conn.close()

def update_olx(product, calls=0):
    now = datetime.now().strftime('%Y-%m-%d')
    conn = db(); c = conn.cursor()
    c.execute('SELECT id FROM olx_listings WHERE product=?', (product,))
    if c.fetchone():
        c.execute('UPDATE olx_listings SET last_updated=?, calls_count=calls_count+? WHERE product=?',
                  (now, calls, product))
    else:
        c.execute('INSERT INTO olx_listings (product,last_updated,calls_count) VALUES (?,?,?)',
                  (product, now, calls))
    conn.commit(); conn.close()

_RATE = {'date': None, 'rate': None, 'retry_at': 0.0}

def _last_known_rate():
    try:
        conn = db(); c = conn.cursor()
        c.execute('SELECT usd_uzs FROM exchange_rates WHERE usd_uzs>0 ORDER BY date DESC LIMIT 1')
        r = c.fetchone(); conn.close()
        return float(r[0]) if r and r[0] else None
    except Exception:
        return None

def get_exchange_rate():
    """CBU kursi. Kunlik kesh; cbu.uz ishlamasa 10 daqiqa qayta urinmaydi (har xabarda bot 5 soniya
    qotib qolmasin) va oxirgi ma'lum kursni qaytaradi (avval darhol 12500 qaytarardi)."""
    today = datetime.now().strftime('%Y-%m-%d')
    if _RATE['date'] == today and _RATE['rate']:
        return _RATE['rate']
    conn = db(); c = conn.cursor()
    c.execute('SELECT usd_uzs FROM exchange_rates WHERE date=?', (today,))
    row = c.fetchone()
    conn.close()
    if row and row[0] and row[0] > 0:
        _RATE.update(date=today, rate=float(row[0]))
        return _RATE['rate']
    if time.time() >= _RATE['retry_at']:
        try:
            r = requests.get('https://cbu.uz/uz/arkhiv-kursov-valyut/json/', timeout=5)
            data = r.json()
            for item in data:
                if item.get('Ccy') == 'USD':
                    rate = float(item['Rate'])
                    if rate <= 0: break
                    conn2 = db(); c2 = conn2.cursor()
                    c2.execute('INSERT OR REPLACE INTO exchange_rates (date,usd_uzs) VALUES (?,?)',
                               (today, rate))
                    conn2.commit(); conn2.close()
                    _RATE.update(date=today, rate=rate, retry_at=0.0)
                    return rate
        except Exception as e:
            log.warning("CBU kursini olib bo'lmadi: %s", e)
        _RATE['retry_at'] = time.time() + 600
    return _last_known_rate() or 12500.0  # fallback

def get_sales(date_filter):
    conn = db(); c = conn.cursor()
    c.execute('SELECT * FROM sales WHERE date LIKE ? AND reversed=0 ORDER BY id DESC',
              (date_filter + '%',))
    rows = c.fetchall(); conn.close(); return rows

def get_expenses(date_filter, expense_type=None):
    conn = db(); c = conn.cursor()
    if expense_type:
        c.execute('SELECT * FROM expenses WHERE date LIKE ? AND expense_type=? AND reversed=0',
                  (date_filter + '%', expense_type))
    else:
        c.execute('SELECT * FROM expenses WHERE date LIKE ? AND reversed=0',
                  (date_filter + '%',))
    rows = c.fetchall(); conn.close(); return rows

def log_op(op_type, data):
    now = datetime.now()
    conn = db(); c = conn.cursor()
    c.execute('INSERT INTO op_log (date,time,op_type,data_json) VALUES (?,?,?,?)',
              (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'),
               op_type, json.dumps(data, ensure_ascii=False)))
    conn.commit(); conn.close()

def get_last_ops(n=10):
    conn = db(); c = conn.cursor()
    c.execute('SELECT * FROM op_log WHERE reversed=0 ORDER BY id DESC LIMIT ?', (n,))
    rows = c.fetchall(); conn.close(); return rows

def add_qty(pid, delta, kind=None, reason='', user=None):
    """Astatkaga qo'shadi/ayiradi (avvalgidek 0 dan pastga tushmaydi) — ombor jurnali orqali."""
    conn = db(); c = conn.cursor()
    try:
        c.execute('SELECT COALESCE(qty,0) FROM products WHERE id=?', (pid,))
        r = c.fetchone()
        if r:
            d = max(int(delta), -max(0, r[0]))
            stock_move(c, pid, d, kind or ('kirim' if d >= 0 else 'tuzatish'), reason, user=user, allow_negative=True)
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()

# ── OMBOR JURNALI (stock ledger) ──────────────────────────────────
# Har bir astatka o'zgarishi stock_moves ga yoziladi — o'sha tranzaksiyada (stock_move orqali).
# Qoida: SUM(stock_moves.qty) == products.qty (har mahsulot uchun). Ishga tushishda ombor_moslash() tekshiradi.
OMBOR_TURLARI = {
    'boshlangich': "Boshlang'ich qoldiq", 'sotuv': 'Sotuv', 'qaytish': 'Sotuv bekor / qaytish',
    'kirim': 'Kirim', 'zavod_kirim': 'Zavoddan keldi', 'chiqim': 'Chiqim (spisanie)',
    'inventar': 'Inventarizatsiya', 'tuzatish': 'Tuzatish', 'yangi_tovar': 'Yangi tovar',
}
CHIQIM_SABABLARI = (('brak', 'Brak'), ('yoqoldi', "Yo'qoldi"), ('namuna', 'Namuna'), ('ichki', 'Ichki ishlatish'))
CHIQIM_SABAB_NOMI = dict(CHIQIM_SABABLARI)

def init_stock_tables():
    """Additiv: stock_moves jadvali, products.min_qty; har mahsulot uchun boshlang'ich qoldiq (idempotent)."""
    conn = db(); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stock_moves (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, time TEXT,
        product_id INTEGER, product TEXT, kind TEXT, qty INTEGER, balance INTEGER,
        unit_cost REAL DEFAULT 0, reason TEXT DEFAULT '', ref TEXT DEFAULT '',
        user_id INTEGER DEFAULT 0, user_name TEXT DEFAULT '', supplier TEXT DEFAULT ''
    )''')
    try: c.execute("CREATE INDEX IF NOT EXISTS ix_sm_pid ON stock_moves(product_id, id)")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE products ADD COLUMN min_qty INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    ombor_moslash(c)
    conn.commit(); conn.close()

def ombor_moslash(c):
    """Jurnal yig'indisi products.qty ga teng bo'lmasa — farqni bitta yozuv bilan tenglashtiradi.
    Jurnali yo'q mahsulot: 'boshlangich'; aks holda (jurnalsiz o'zgarish bo'lgan) 'tuzatish'. Qaytaradi: yozuvlar soni."""
    c.execute("SELECT p.id, p.name, COALESCE(p.qty,0), COALESCE(p.cost,0), "
              "(SELECT COALESCE(SUM(m.qty),0) FROM stock_moves m WHERE m.product_id=p.id), "
              "(SELECT COUNT(*) FROM stock_moves m WHERE m.product_id=p.id) FROM products p")
    n = 0
    for pid, name, q, cost, s, cnt in c.fetchall():
        if q != s:
            _sm_yoz(c, pid, name, q - s, q, 'boshlangich' if cnt == 0 else 'tuzatish', cost,
                    reason='' if cnt == 0 else "avtomatik tenglash (jurnalsiz o'zgarish)")
            n += 1
    return n

def _sm_yoz(c, pid, name, delta, balance, kind, unit_cost=0, reason='', ref='', user=None, supplier='', now=None):
    now = now or datetime.now()
    uid, uname = (user or (0, ''))[:2]
    c.execute("INSERT INTO stock_moves (date,time,product_id,product,kind,qty,balance,unit_cost,reason,ref,user_id,user_name,supplier) "
              "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'), pid, name, kind, int(delta), int(balance),
               round(float(unit_cost or 0), 4), reason or '', ref or '', int(uid or 0), uname or '', supplier or ''))
    return c.lastrowid

def stock_move(c, pid, delta, kind, reason='', ref='', user=None, unit_cost=None, new_cost=None,
               supplier='', allow_negative=False, now=None):
    """YAGONA astatka o'zgartirish nuqtasi (chaqiruvchining tranzaksiyasi ichida).
    delta<0 va astatka yetmasa (allow_negative=False) — hech narsa qilmaydi, None qaytaradi.
    Qaytaradi: (move_id, yangi_qoldiq)."""
    c.execute('SELECT name, COALESCE(qty,0), COALESCE(cost,0) FROM products WHERE id=?', (pid,))
    r = c.fetchone()
    if not r: return None
    name, q, cost = r
    delta = int(delta)
    if delta < 0 and not allow_negative:
        c.execute('UPDATE products SET qty=qty+? WHERE id=? AND qty>=?', (delta, pid, -delta))
        if c.rowcount == 0: return None
    elif delta != 0:
        c.execute('UPDATE products SET qty=qty+? WHERE id=?', (delta, pid))
    if new_cost is not None:
        c.execute('UPDATE products SET cost=? WHERE id=?', (round(float(new_cost), 2), pid))
    bal = q + delta
    if delta == 0: return (0, bal)
    mid = _sm_yoz(c, pid, name, delta, bal, kind, cost if unit_cost is None else unit_cost,
                  reason, ref, user, supplier, now)
    return (mid, bal)

def stock_set(c, pid, new_qty, kind='tuzatish', reason='', ref='', user=None, new_cost=None):
    """Astatkani aniq songa o'rnatadi (farq jurnalga yoziladi)."""
    c.execute('SELECT COALESCE(qty,0) FROM products WHERE id=?', (pid,))
    r = c.fetchone()
    if not r: return None
    return stock_move(c, pid, int(new_qty) - r[0], kind, reason, ref, user, new_cost=new_cost, allow_negative=True)

def ombor_tarix(pid, limit=8, offset=0):
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, date, time, kind, qty, balance, unit_cost, reason, ref, user_name, supplier "
              "FROM stock_moves WHERE product_id=? ORDER BY id DESC LIMIT ? OFFSET ?", (pid, limit, offset))
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM stock_moves WHERE product_id=?", (pid,))
    n = c.fetchone()[0]; conn.close()
    return rows, n

def ombor_tekshir():
    """[(pid, nom, qty, jurnal_yigindisi)] — mos kelmaganlar (bo'sh bo'lishi kerak)."""
    conn = db(); c = conn.cursor()
    c.execute("SELECT p.id, p.name, COALESCE(p.qty,0), (SELECT COALESCE(SUM(m.qty),0) FROM stock_moves m WHERE m.product_id=p.id) "
              "FROM products p")
    rows = [r for r in c.fetchall() if r[2] != r[3]]; conn.close()
    return rows

def _ombor_davr_tekshir():
    if is_closed(today()):
        return f"{today()[:7]} davri yopilgan — yozib bo'lmaydi (/och {today()[:7]})"
    return None

def ombor_kirim(pid, qty, unit_cost, supplier='', pay='none', user=None, note=''):
    """Qo'lda kirim: astatka +qty, tannarx o'rtacha tortilgan (IAS 2).
    pay: 'cash' — kassadan chiqim; 'debt' — yetkazuvchiga kreditorlik; 'none' — pulsiz (faqat astatka)."""
    xato = _ombor_davr_tekshir()
    if xato: return {'ok': False, 'error': xato}
    try: qty = int(qty); unit_cost = round(float(unit_cost), 2)
    except (TypeError, ValueError): return {'ok': False, 'error': "Son yoki narx noto'g'ri"}
    if qty <= 0 or unit_cost < 0: return {'ok': False, 'error': "Son musbat, narx manfiy bo'lmasin"}
    if pay == 'debt' and not (supplier or '').strip():
        return {'ok': False, 'error': "Qarzga kirim uchun yetkazuvchi kerak"}
    now = datetime.now(); d, t = now.strftime('%Y-%m-%d'), now.strftime('%H:%M')
    conn = db(); c = conn.cursor()
    try:
        c.execute('SELECT name, COALESCE(qty,0), COALESCE(cost,0) FROM products WHERE id=?', (pid,))
        r = c.fetchone()
        if not r: conn.close(); return {'ok': False, 'error': 'Mahsulot topilmadi'}
        name, q, cost = r
        baza = max(0, q)
        new_cost = round((baza * cost + qty * unit_cost) / (baza + qty), 2) if baza + qty > 0 else unit_cost
        c.execute('INSERT INTO op_log (date,time,op_type,data_json) VALUES (?,?,?,?)', (d, t, 'stock', '{}'))
        op_id = c.lastrowid
        mid, bal = stock_move(c, pid, qty, 'kirim', note, f'op{op_id}', user, unit_cost, new_cost, supplier)
        summa = round(qty * unit_cost, 2); cash_id = debt_id = None
        if pay == 'cash' and summa > 0:
            c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                      (d, t, 'chiqim', summa, 'tovar_xarid', f"{name} x{qty} kirim (#m{op_id})", 'naqd'))
            cash_id = c.lastrowid
        elif pay == 'debt' and summa > 0:
            c.execute('INSERT INTO debts (date,person,amount,type,note) VALUES (?,?,?,?,?)',
                      (d, supplier.strip(), summa, KREDITOR, f"tovar kirim: {name} x{qty} (#m{op_id})"))
            debt_id = c.lastrowid
        data = {'kind': 'kirim', 'pid': pid, 'product': name, 'qty': qty, 'unit_cost': unit_cost,
                'old_cost': cost, 'move_ids': [mid], 'cash_id': cash_id, 'debt_id': debt_id, 'supplier': supplier,
                'summa': summa, 'pay': pay}
        c.execute('UPDATE op_log SET data_json=? WHERE id=?', (json.dumps(data, ensure_ascii=False), op_id))
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return {'ok': True, 'op_id': op_id, 'product': name, 'balance': bal, 'new_cost': new_cost, 'summa': summa}

def ombor_chiqim(pid, qty, sabab, user=None, note=''):
    """Chiqim / spisanie: astatka −qty, tannarx bo'yicha XARAJAT yoziladi (kassaga tegmaydi)."""
    xato = _ombor_davr_tekshir()
    if xato: return {'ok': False, 'error': xato}
    if sabab not in CHIQIM_SABAB_NOMI: return {'ok': False, 'error': "Sabab noma'lum"}
    try: qty = int(qty)
    except (TypeError, ValueError): qty = 0
    if qty <= 0: return {'ok': False, 'error': "Son musbat bo'lsin"}
    now = datetime.now(); d, t = now.strftime('%Y-%m-%d'), now.strftime('%H:%M')
    conn = db(); c = conn.cursor()
    try:
        c.execute('SELECT name, COALESCE(cost,0) FROM products WHERE id=?', (pid,))
        r = c.fetchone()
        if not r: conn.close(); return {'ok': False, 'error': 'Mahsulot topilmadi'}
        name, cost = r
        c.execute('INSERT INTO op_log (date,time,op_type,data_json) VALUES (?,?,?,?)', (d, t, 'stock', '{}'))
        op_id = c.lastrowid
        res = stock_move(c, pid, -qty, 'chiqim', CHIQIM_SABAB_NOMI[sabab] + (f": {note}" if note else ''),
                         f'op{op_id}', user, cost)
        if res is None:
            conn.rollback(); conn.close(); return {'ok': False, 'error': "Astatka yetmaydi"}
        summa = round(qty * cost, 2); eid = None
        if summa > 0:
            c.execute('INSERT INTO expenses (date,amount,category,expense_type,note) VALUES (?,?,?,?,?)',
                      (d, summa, 'spisanie', 'period', f"{CHIQIM_SABAB_NOMI[sabab]}: {name} x{qty} (#m{op_id})"))
            eid = c.lastrowid
        data = {'kind': 'chiqim', 'pid': pid, 'product': name, 'qty': qty, 'sabab': sabab,
                'move_ids': [res[0]], 'expense_id': eid, 'summa': summa}
        c.execute('UPDATE op_log SET data_json=? WHERE id=?', (json.dumps(data, ensure_ascii=False), op_id))
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return {'ok': True, 'op_id': op_id, 'product': name, 'balance': res[1], 'summa': summa}

def ombor_inventar(sanoq, user=None):
    """sanoq: {pid: (tizimdagi_son_sanash_paytida, sanalgan_son)}. Farq = sanalgan − tizimdagi
    (sanash paytidan keyingi sotuvlar saqlanadi). Kamomad tannarx bo'yicha xarajat ('inventar_kamomad').
    Ortiqcha — faqat astatka (foyda sifatida yozilmaydi)."""
    xato = _ombor_davr_tekshir()
    if xato: return {'ok': False, 'error': xato}
    now = datetime.now(); d, t = now.strftime('%Y-%m-%d'), now.strftime('%H:%M')
    conn = db(); c = conn.cursor()
    try:
        c.execute('INSERT INTO op_log (date,time,op_type,data_json) VALUES (?,?,?,?)', (d, t, 'stock', '{}'))
        op_id = c.lastrowid
        moves = []; kamomad = 0.0; qatorlar = []
        for pid, (tizim, sanalgan) in sanoq.items():
            farq = int(sanalgan) - int(tizim)
            if farq == 0: continue
            c.execute('SELECT name, COALESCE(qty,0), COALESCE(cost,0) FROM products WHERE id=?', (pid,))
            r = c.fetchone()
            if not r: continue
            farq = max(farq, -r[1])                 # astatka manfiy bo'lmasin
            if farq == 0: continue
            mid, bal = stock_move(c, pid, farq, 'inventar', f"sanoq: tizim {tizim} → {sanalgan}", f'op{op_id}', user,
                                  r[2], allow_negative=True)
            moves.append(mid)
            if farq < 0: kamomad += -farq * r[2]
            qatorlar.append({'pid': pid, 'product': r[0], 'farq': farq, 'qoldiq': bal, 'summa': round(farq * r[2], 2)})
        eid = None
        kamomad = round(kamomad, 2)
        if kamomad > 0:
            c.execute('INSERT INTO expenses (date,amount,category,expense_type,note) VALUES (?,?,?,?,?)',
                      (d, kamomad, 'inventar_kamomad', 'period', f"inventarizatsiya kamomadi (#m{op_id})"))
            eid = c.lastrowid
        if not moves:
            conn.rollback(); conn.close()
            return {'ok': True, 'op_id': None, 'qatorlar': [], 'kamomad': 0.0}
        c.execute('UPDATE op_log SET data_json=? WHERE id=?',
                  (json.dumps({'kind': 'inventar', 'move_ids': moves, 'expense_id': eid, 'qatorlar': qatorlar,
                               'kamomad': kamomad}, ensure_ascii=False), op_id))
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return {'ok': True, 'op_id': op_id, 'qatorlar': qatorlar, 'kamomad': kamomad}

def ombor_undo(op_id):
    """Ombor operatsiyasini bekor qiladi (teskari harakatlar + xarajat/kassa/qarz) — bitta tranzaksiyada."""
    conn = db(); c = conn.cursor()
    try:
        c.execute("SELECT date, data_json FROM op_log WHERE id=? AND op_type='stock' AND reversed=0", (op_id,))
        r = c.fetchone()
        if not r: conn.close(); return False, "Topilmadi yoki allaqachon qaytarilgan"
        for s in (r[0], today()):
            if is_closed(s):
                conn.close(); return False, f"{s[:7]} davri yopilgan (/och {s[:7]})"
        d = json.loads(r[1] or '{}')
        for mid in d.get('move_ids', []):
            c.execute("SELECT product_id, qty FROM stock_moves WHERE id=?", (mid,))
            m = c.fetchone()
            if not m: continue
            res = stock_move(c, m[0], -m[1], 'tuzatish', f"bekor: op #{op_id}", f'op{op_id}u')
            if res is None:
                conn.rollback(); conn.close()
                return False, "Astatka yetmaydi — kirim qilingan tovar allaqachon sotilgan"
        if d.get('kind') == 'kirim' and d.get('old_cost') is not None:
            c.execute('UPDATE products SET cost=? WHERE id=?', (d['old_cost'], d['pid']))
        if d.get('expense_id'):
            c.execute('UPDATE expenses SET reversed=1 WHERE id=?', (d['expense_id'],))
        if d.get('cash_id'):
            now = datetime.now()
            c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                      (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'), 'kirim', d.get('summa', 0), 'qaytarish',
                       f"kirim bekor (#m{op_id})", 'naqd'))
        if d.get('debt_id'):
            c.execute('UPDATE debts SET paid=1, note=note || ? WHERE id=?', (f" | bekor (#m{op_id})", d['debt_id']))
        c.execute('UPDATE op_log SET reversed=1 WHERE id=?', (op_id,))
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return True, "qaytarildi"

def kam_qolganlar():
    """min_qty belgilangan va qoldig'i shundan oshmagan faol mahsulotlar."""
    conn = db(); c = conn.cursor()
    try:
        c.execute("SELECT id, name, cat, COALESCE(qty,0), COALESCE(min_qty,0), price FROM products "
                  "WHERE active=1 AND COALESCE(min_qty,0)>0 AND COALESCE(qty,0)<=min_qty ORDER BY qty, name")
        rows = c.fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return [{'id': r[0], 'name': r[1], 'cat': r[2], 'qty': r[3], 'min': r[4], 'price': r[5]} for r in rows]

def set_min_qty(pid, n):
    conn = db(); c = conn.cursor()
    c.execute('UPDATE products SET min_qty=? WHERE id=?', (max(0, int(n)), pid))
    ok = c.rowcount > 0; conn.commit(); conn.close()
    return ok

def ombor_qiymati():
    """Tannarx bo'yicha ombor qiymati: {'jami','dona','kat':{cat:(dona, qiymat)}}"""
    kat = defaultdict(lambda: [0, 0.0]); jami = 0.0; dona = 0
    for p in get_products():
        q = max(0, p['qty'] or 0); v = q * (p['cost'] or 0)
        kat[p['cat'] or 'Boshqa'][0] += q; kat[p['cat'] or 'Boshqa'][1] += v
        jami += v; dona += q
    return {'jami': round(jami, 2), 'dona': dona, 'kat': {k: (v[0], round(v[1], 2)) for k, v in kat.items()}}


# ── ABC/XYZ TAHLIL (IAS 2 + CV formula) ──────────────────────────

# ── KASSA FUNKSIYALARI ────────────────────────────────────────────
def get_cash_balance():
    conn = db(); c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(CASE WHEN type=\'kirim\' THEN amount ELSE -amount END),0) FROM cash_box")
    balance = c.fetchone()[0] or 0
    conn.close()
    return balance

def add_cash(amount, cash_type, category='sotuv', note='', method='naqd'):
    now = datetime.now()
    conn = db(); c = conn.cursor()
    c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
              (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'),
               cash_type, amount, category, note, method))
    conn.commit(); conn.close()

def get_cash_history(date_filter=None):
    conn = db(); c = conn.cursor()
    if date_filter:
        c.execute("SELECT * FROM cash_box WHERE date LIKE ? ORDER BY id DESC", (date_filter+'%',))
    else:
        c.execute("SELECT * FROM cash_box ORDER BY id DESC LIMIT 30")
    rows = c.fetchall(); conn.close()
    return rows

def get_nelikvid(days=60):
    prods = get_products()
    conn = db(); c = conn.cursor()
    nelikvid = []
    for p in prods:
        if p['qty'] <= 0: continue
        c.execute("SELECT MAX(date) FROM sales WHERE product=? AND reversed=0", (p['name'],))
        last_sale = c.fetchone()[0]
        days_since = 999 if not last_sale else (datetime.now() - datetime.strptime(last_sale, '%Y-%m-%d')).days
        if days_since >= days:
            nelikvid.append({
                'name': p['name'], 'qty': p['qty'],
                'price': p['price'], 'cost': p['cost'],
                'days_since': days_since,
                'last_sale': last_sale or 'Hech sotilmagan'
            })
    conn.close()
    return sorted(nelikvid, key=lambda x: -x['days_since'])

def _oylar_orqaga(n):
    """Joriy oy bilan birga oxirgi n oy, eskidan yangiga: ['2026-03', ..., '2026-10'].
    (Avval 'bugun - 30*i kun' ishlatilardi: 31-sanada joriy oy ikki marta chiqib, oldingi oy tushib qolardi,
    1-2 martda esa fevral umuman ko'rinmasdi.)"""
    now = datetime.now(); y, m = now.year, now.month
    out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0: y, m = y - 1, 12
    return out[::-1]

def calc_cv(monthly_data):
    n = len(monthly_data)
    if n < 2: return 999.0
    mean = sum(monthly_data) / n
    if mean == 0: return 999.0
    variance = sum((x - mean) ** 2 for x in monthly_data) / n
    return round(math.sqrt(variance) / mean, 2)

def abc_xyz_analysis():
    prods = get_products()
    conn = db(); c = conn.cursor()
    c.execute('SELECT product,SUM(revenue),SUM(qty),COUNT(*) FROM sales WHERE reversed=0 GROUP BY product')
    sd = {r[0]: {'rev':r[1] or 0,'qty':r[2] or 0,'cnt':r[3]} for r in c.fetchall()}
    months = _oylar_orqaga(8)

    items = []
    for p in prods:
        s = sd.get(p['name'], {'rev':0,'qty':0,'cnt':0})
        monthly = []
        for m in months:
            c.execute('SELECT COALESCE(SUM(qty),0) FROM sales WHERE product=? AND date LIKE ? AND reversed=0',
                      (p['name'], m+'%'))
            monthly.append(float(c.fetchone()[0]))
        cv = calc_cv(monthly)
        items.append({
            'name': p['name'], 'cat': p['cat'],
            'rev': s['rev'], 'cnt': s['cnt'],
            'qty': p['qty'], 'cost': p['cost'],
            'price': p['price'], 'total_sold': sum(monthly),
            'cv': cv,
            'xyz': 'X' if cv < 0.5 else ('Y' if cv <= 1.0 else 'Z'),
            'monthly': monthly
        })

    conn.close()
    items.sort(key=lambda x: x['rev'], reverse=True)
    total_rev = sum(i['rev'] for i in items) or 1
    cumulative = 0
    for item in items:
        cumulative += item['rev']
        pct = cumulative / total_rev * 100
        item['abc'] = 'A' if pct <= 80 else ('B' if pct <= 95 else 'C')
        item['pct'] = round(item['rev'] / total_rev * 100, 1)
    return items

# ── HELPERS ───────────────────────────────────────────────────────
def fmt(n): return f"${n:,.0f}"
def fmtuzs(n, rate=12500): return f"{n*rate:,.0f} so'm"
def today(): return datetime.now().strftime('%Y-%m-%d')
def this_month(): return datetime.now().strftime('%Y-%m')
def now_t(): return datetime.now().strftime('%d.%m.%Y %H:%M')

# ── ROLLAR (owner / admin / sotuvchi) ─────────────────────────────
# Egasi — OWNER_ID (bazada saqlanmaydi, uni o'zgartirib/o'chirib bo'lmaydi).
# Xodimlar — `users` jadvalida. Rol har chaqiriqda bazadan o'qiladi: o'zgarish darhol kuchga kiradi.
ROLLAR = ('admin', 'sotuvchi')
ROL_NOMI = {'owner': 'egasi', 'admin': 'admin', 'sotuvchi': 'sotuvchi'}
# Sotuvchi faqat shularni qila oladi (tannarx/foyda, hisobot, o'chirish, kassa, sozlama — yo'q)
_SOTUVCHI_RUXSAT = frozenset({'pos', 'stock_view', 'customer_add', 'own_sales',
                              'qaytarish_sorov', 'smena'})       # 10-bosqich: qaytarish so'rovi, smena ochish/yopish
# Faqat egasi: xodimlarni boshqarish va tizim (kod yangilash, bazani tiklash, astatkani nollash)
_FAQAT_EGA = frozenset({'roles', 'system', 'zaxira'})         # 'zaxira' — 💾 Zaxira bo'limi (10-bosqich)
try:
    SOTUVCHI_MAX_CHEGIRMA = max(0.0, float(os.getenv('SELLER_MAX_DISCOUNT', '5') or 5))  # ixtiyoriy, majburiy emas
except ValueError:
    SOTUVCHI_MAX_CHEGIRMA = 5.0

def init_users_table():
    """Additiv: users jadvali + sotuvga sotuvchi ustunlari. Idempotent."""
    conn = db(); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY, name TEXT DEFAULT '',
        role TEXT DEFAULT 'sotuvchi', active INTEGER DEFAULT 1,
        max_discount_pct REAL, created_at TEXT DEFAULT ''
    )''')
    for ddl in ("ALTER TABLE sales ADD COLUMN seller_id INTEGER DEFAULT 0",
                "ALTER TABLE sales ADD COLUMN seller_name TEXT DEFAULT ''"):
        try: c.execute(ddl)
        except sqlite3.OperationalError: pass       # ustun allaqachon bor
    conn.commit(); conn.close()

def _uid(u):
    if isinstance(u, int): return u
    us = getattr(u, 'effective_user', None) or getattr(u, 'from_user', None)
    return getattr(us, 'id', None)

def xodim(u):
    """Foydalanuvchi ma'lumoti: {'id','name','role','active','max_discount'} yoki None (ro'yxatda yo'q / nofaol)."""
    uid = _uid(u)
    if uid is None: return None
    if uid == OWNER_ID:
        return {'id': uid, 'name': 'Egasi', 'role': 'owner', 'active': 1, 'max_discount': 100.0}
    try:
        conn = db(); c = conn.cursor()
        c.execute('SELECT name, role, active, max_discount_pct FROM users WHERE telegram_id=?', (uid,))
        r = c.fetchone(); conn.close()
    except sqlite3.OperationalError:
        return None                                  # jadval hali yaratilmagan
    if not r or not r[2] or r[1] not in ROLLAR: return None
    md = r[3] if r[3] is not None else (SOTUVCHI_MAX_CHEGIRMA if r[1] == 'sotuvchi' else 100.0)
    return {'id': uid, 'name': r[0] or str(uid), 'role': r[1], 'active': 1, 'max_discount': float(md)}

def user_role(u):
    x = xodim(u)
    return x['role'] if x else None

def can(u, perm):
    """Markaziy ruxsat tekshiruvi. 'boshqaruv' — egasi/admin uchun umumiy boshqaruv (oldingi is_owner joylari)."""
    rol = user_role(u)
    if rol == 'owner': return True
    if rol == 'admin': return perm not in _FAQAT_EGA
    if rol == 'sotuvchi': return perm in _SOTUVCHI_RUXSAT
    return False

def is_owner(u): return _uid(u) == OWNER_ID      # faqat egasi (eski nom saqlandi)

def xodim_saqla(tid, name, role, max_pct=None):
    """Qo'shadi yoki yangilaydi (faollashtiradi). Qaytaradi: 'qoshildi' | 'yangilandi'."""
    if role not in ROLLAR: raise ValueError(f"Rol noma'lum: {role}")
    if int(tid) == OWNER_ID: raise ValueError("Egasi xodim sifatida qo'shilmaydi")
    conn = db(); c = conn.cursor()
    c.execute('SELECT 1 FROM users WHERE telegram_id=?', (int(tid),))
    bor = c.fetchone() is not None
    if bor:
        c.execute('UPDATE users SET name=?, role=?, active=1, max_discount_pct=COALESCE(?, max_discount_pct) '
                  'WHERE telegram_id=?', (name, role, max_pct, int(tid)))
    else:
        c.execute('INSERT INTO users (telegram_id,name,role,active,max_discount_pct,created_at) VALUES (?,?,?,1,?,?)',
                  (int(tid), name, role, max_pct, datetime.now().strftime('%Y-%m-%d %H:%M')))
    conn.commit(); conn.close()
    return 'yangilandi' if bor else 'qoshildi'

def xodimlar_royxati():
    conn = db(); c = conn.cursor()
    c.execute('SELECT telegram_id, name, role, active, max_discount_pct, created_at FROM users ORDER BY active DESC, name')
    rows = c.fetchall(); conn.close()
    return [{'id': r[0], 'name': r[1] or str(r[0]), 'role': r[2], 'active': r[3],
             'max_discount': (r[4] if r[4] is not None else (SOTUVCHI_MAX_CHEGIRMA if r[2] == 'sotuvchi' else 100.0)),
             'created': r[5]} for r in rows]

def xodim_ozgartir(tid, **kv):
    """kv: role / active / max_discount_pct"""
    ruxsat = {'role', 'active', 'max_discount_pct'}
    sets = [(k, v) for k, v in kv.items() if k in ruxsat]
    if not sets: return False
    conn = db(); c = conn.cursor()
    c.execute('UPDATE users SET ' + ', '.join(f'{k}=?' for k, _ in sets) + ' WHERE telegram_id=?',
              [v for _, v in sets] + [int(tid)])
    ok = c.rowcount > 0
    conn.commit(); conn.close()
    return ok

def cash_flow_forecast():
    """30 kunlik cash flow prognozi"""
    conn = db(); c = conn.cursor()
    # O'rtacha oylik sotuv (oxirgi 3 oy)
    months = _oylar_orqaga(3)
    monthly_revs = []
    for m in months:
        c.execute('SELECT COALESCE(SUM(revenue),0) FROM sales WHERE date LIKE ? AND reversed=0', (m+'%',))
        monthly_revs.append(c.fetchone()[0])
    avg_monthly = sum(monthly_revs) / 3 if monthly_revs else 0

    # KREDITORLIK — zavod: to'lanmagan qoldiq (yo'lda yoki kelgan bo'lsa ham; balans bilan bir xil ta'rif)
    c.execute("SELECT COALESCE(SUM(remaining),0) FROM transit WHERE remaining>0")
    transit_remaining = c.fetchone()[0] or 0

    # Qarzlar: DEBITORLIK = kutilayotgan kirim (+), KREDITORLIK = kutilayotgan chiqim (−)
    # (avval eski matn rejimi ma'nosida teskari olinardi: mijoz qarzi chiqim bo'lib ketardi)
    c.execute(f"SELECT COALESCE(SUM(amount),0) FROM debts WHERE paid=0 AND type IN {DEBITOR_SQL}")
    debt_in = c.fetchone()[0] or 0
    c.execute(f"SELECT COALESCE(SUM(amount),0) FROM debts WHERE paid=0 AND type IN {KREDITOR_SQL}")
    debt_out = c.fetchone()[0] or 0

    conn.close()
    return {
        'avg_monthly_revenue': avg_monthly,
        'expected_30day': avg_monthly,
        'transit_to_pay': transit_remaining,
        'debts_to_receive': debt_in,
        'debts_to_pay': debt_out,
        'debitorlik': debt_in,
        'kreditorlik': round(transit_remaining + debt_out, 2),
        'net_forecast': avg_monthly + debt_in - transit_remaining - debt_out
    }

def get_sales_trend():
    """Oxirgi 3 oy trendi"""
    months = []
    for m in _oylar_orqaga(3):
        conn = db(); c = conn.cursor()
        c.execute('SELECT COALESCE(SUM(revenue),0), COALESCE(SUM(profit),0) FROM sales WHERE date LIKE ? AND reversed=0', (m+'%',))
        row = c.fetchone(); conn.close()
        months.append({'month': m, 'rev': row[0], 'profit': row[1]})
    if len(months) >= 2 and months[-2]['rev'] > 0:
        change = (months[-1]['rev'] - months[-2]['rev']) / months[-2]['rev'] * 100
    else:
        change = 0
    return months, change


# ── CLAUDE AI PARSER ──────────────────────────────────────────────
def ai_parse(user_msg, prods):
    plist = '\n'.join([f"- {p['name']} (qty:{p['qty']}, narx:${p['price']})" for p in prods])
    system = f"""Siz ThermoCrafts biznes botining AI qismi. FAQAT JSON qaytaring.

MAHSULOTLAR:
{plist}

AMALLAR (to'liq ro'yxat):
Sotish: {{"action":"sell","product":"nom","qty":1,"price":260,"currency":"USD","discount":0,"customer":"","type":"B2C"}}
MUHIM VALYUTA QOIDASI: narx DOIM dollarda beriladi. Agar foydalanuvchi som da aytsa (masalan "3 884 000", "3.8 mln", "5 mln som") -> "currency":"UZS" qoy va raqamni somda qoldir. Dollar belgisi yoki 5000 dan kichik son -> "currency":"USD".
Tovar qoshish (keldi): {{"action":"add","product":"nom","qty":2}}
Yangi tovar: {{"action":"new_product"}}
Astatka: {{"action":"stock","cat":"Barchasi"}}
Hisobot bugun: {{"action":"report","period":"today"}}
Hisobot oy: {{"action":"report","period":"month","month":"2026-07"}}
Hisobot yil: {{"action":"report","period":"year","year":"2026"}}
Narx jadvali: {{"action":"prices"}}
Yoldagi tovar: {{"action":"transit_add","supplier":"Two Trees","product":"nom","qty":2,"unit_cost":280,"deposit":200,"bank_fee":45,"delivery_fee":110}}
Tovar keldi: {{"action":"transit_arrive","id":1}}
Deposit toldim: {{"action":"transit_pay","id":1,"amount":200}}
Yolda royxat: {{"action":"transit_list"}}
Zavod qarz: {{"action":"supplier_debt"}}
Xarajat: {{"action":"expense","amount":50,"category":"OLX reklama","type":"period","note":""}}
Bank tolov: {{"action":"expense","amount":45,"category":"bank","type":"cogs_bank","note":""}}
Dostavka: {{"action":"expense","amount":110,"category":"dostavka","type":"cogs_delivery","note":""}}
Mijoz qosh: {{"action":"add_customer","name":"ism","phone":"","ctype":"B2C"}}
Mijozlar: {{"action":"customers"}}
Mijoz bizga qarz: {{"action":"debt","person":"ism","amount":100,"type":"debitorlik"}}
Biz qarzmiz: {{"action":"debt","person":"ism","amount":100,"type":"kreditorlik"}}
Qarz to'landi: {{"action":"debt_pay","kind":"debitorlik","person":"ism","amount":100,"method":"naqd"}}
Qarzlar: {{"action":"debts"}}
ABC XYZ: {{"action":"analiz"}}
Maqsad: {{"action":"set_target","revenue":3000,"profit":800}}
Kafolat: {{"action":"warranties"}}
Prognoz: {{"action":"cashflow"}}
Trend: {{"action":"trend"}}
Katalog: {{"action":"catalog","product":"nom"}}
OLX yangilandi: {{"action":"olx_update","product":"nom","calls":2}}
Raqobatchi: {{"action":"competitor","competitor":"apexmach","product":"nom","price":490}}
Valyuta: {{"action":"rate"}}
Qayt et: {{"action":"undo","id":0}}
Kafolat: {{"action":"warranties"}}
Tushunarsiz: {{"action":"unknown","reply":"..."}}

QOIDALAR:
- "sotdim/ketdi/sotildi/soting/sotib yubording" = sell
- "kanalga post/e'lon" = channel_post
- "kassa/pul/naqd kirim/chiqim" = kassa_op
- "nelikvid/sotilmagan/muzlatilgan" = nelikvid
- "oylik tafsil/batafsil/mahsulot nima sotildi" = oy_tafsil
- "eslatma/xabar/reminder" = eslatmalar
- "reklama/xabar yuborish mijozlarga" = send_ads
- "sotilmadi/sotolmadim/ketmadi/olmadi" = unknown (xato tushunma, faqat savol bo'lsa javob ber)
- "keldi/qoshildi/kirdi" = add
- MUHIM: "sotilmadi", "ketmadi", "olmadi" kabi INKOR shakllar = sell EMAS!
- "xarajat/sarf berdim" = expense (type=period)
- "bank tolov" = expense (type=cogs_bank)
- "dostavka/yolkira" = expense (type=cogs_delivery)
- "zakaz berdim/yo'lga tushdi" = transit_add
- QARZ faqat 2 tur. type="debitorlik" = u BIZGA qarz ("Alibek 200 qarz oldi", "Alibekka qarz berdim", nasiya).
  type="kreditorlik" = BIZ unga qarzmiz ("Alibekdan qarz oldim", "Alibek bizga qarz berdi", zavodga qarz)
- QARZ TO'LOVI = debt_pay: "Alibek qarzini qaytardi/to'ladi 100" → kind="debitorlik"; "Alibekka qarzimizni to'ladim" → kind="kreditorlik".
  Zavodga to'lov: zakaz raqami (#3) aytilsa — transit_pay, raqamsiz ("Two Trees ga 300 to'ladim") — debt_pay kind="kreditorlik".
  method: naqd/karta/payme/click/otkazma (aytilmasa naqd)
- product maydonida MAVJUD ro'yxatdan nom yozing"""

    try:
        resp = ai.messages.create(
            model='claude-haiku-4-5-20251001', max_tokens=400,
            system=system,
            messages=[{'role':'user','content':user_msg}])
        raw = resp.content[0].text.strip()
        s, e = raw.find('{'), raw.rfind('}')+1
        if s >= 0 and e > s: return json.loads(raw[s:e])
    except Exception as ex: log.error(f'AI: {ex}')
    return {'action':'unknown','reply':'Tushunmadim 🤔\n/yordam buyrug\'ini ko\'ring'}



# ══════════════════════════════════════════════════════════════════
# AI AGENT — to'liq sun'iy intellekt rejimi (tool-use)
# ══════════════════════════════════════════════════════════════════
AI_MODE  = os.getenv('AI_MODE', 'agent')          # 'agent' yoki 'parse'
AI_MODEL = os.getenv('AI_MODEL', 'claude-sonnet-5')
AI_HISTORY = {}          # user_id -> [messages]
AI_HISTORY_MAX = 20      # 10 ta savol-javob

def _j(obj):
    """Tool natijasini ixcham JSON ga aylantiradi"""
    return json.dumps(obj, ensure_ascii=False, default=str)

def _undo_op(op_id: int):
    conn = db(); c = conn.cursor()
    c.execute('SELECT * FROM op_log WHERE id=? AND reversed=0', (op_id,))
    op = c.fetchone()
    conn.close()          # o'qish ulanishi yopiladi — quyidagi yozuvlar boshqa ulanishda bo'ladi
    if not op:
        return False, "Topilmadi yoki allaqachon qaytarilgan"
    if op[3] == 'debt_payment':
        return reverse_debt_payment(op_id)
    if op[3] == 'stock':
        return ombor_undo(op_id)
    if op[3] == 'return':
        return reverse_return(op_id)             # 📥 qaytarish — atomik                 # kirim / chiqim / inventarizatsiya — atomik       # o'zi atomik: qarz + kassa + op_log bitta tranzaksiyada
    d = json.loads(op[4]); ok = False
    if op[3] == 'sale':
        ok = reverse_sale(d.get('sale_id', 0))
    elif op[3] == 'expense':
        c2 = db(); cc = c2.cursor()
        cc.execute('UPDATE expenses SET reversed=1 WHERE id=?', (d.get('id', 0),))
        ok = cc.rowcount > 0; c2.commit(); c2.close()
        if ok: add_cash(d.get('amount', 0), 'kirim', 'qaytarish', f"xarajat bekor (#x{d.get('id')})")
    if ok:
        conn = db()
        conn.execute('UPDATE op_log SET reversed=1 WHERE id=?', (op_id,)); conn.commit()
        conn.close()
    return ok, ("qaytarildi" if ok else "qaytarib bo'lmadi")

# ── Asboblar ro'yxati ────────────────────────────────────────────
AI_TOOLS = [
    {"name": "get_stock",
     "description": "Astatka: barcha mahsulotlar, soni, sebest, narx, yetkazuvchi. Nomi bo'yicha qidirish uchun ham ishlatiladi.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Ixtiyoriy: nom yoki kategoriya bo'yicha filtr"}}}},
    {"name": "record_sale",
     "description": "BITTA mahsulot sotuvini qayd qiladi: astatkani kamaytiradi, kassaga kirim yozadi, foyda hisoblaydi. "
                    "Mijoz ismi va to'lov usuli ixtiyoriy (aytilmasa: naqd, mijozsiz). Bir nechta mahsulot birga sotilsa — record_sale_multi.",
     "input_schema": {"type": "object", "required": ["product", "qty"], "properties": {
         "product": {"type": "string", "description": "Mahsulot nomi (astatkadagi kabi)"},
         "qty": {"type": "integer"},
         "price_usd": {"type": "number", "description": "DONA narxi dollarda. 0 bo'lsa ro'yxat narxi olinadi"},
         "price_uzs": {"type": "number", "description": "Agar so'mda aytilgan bo'lsa — dona narxi so'mda"},
         "total_usd": {"type": "number", "description": "Hamma dona uchun UMUMIY summa dollarda (masalan '2 ta 940$ ga' → qty=2, total_usd=940)"},
         "total_uzs": {"type": "number", "description": "Umumiy summa so'mda"},
         "discount_pct": {"type": "number", "default": 0},
         "customer": {"type": "string", "default": ""},
         "customer_type": {"type": "string", "enum": ["B2C", "B2B"], "default": "B2C"},
         "on_credit": {"type": "boolean", "default": False, "description": "Nasiya bo'lsa true — kassaga tushmaydi, debitor yoziladi (mijoz ismi shart)"},
         "payment_method": {"type": "string", "enum": ["naqd", "karta", "payme", "click", "otkazma"], "default": "naqd"}}}},
    {"name": "record_sale_multi",
     "description": "Bir nechta mahsulot BIRGA sotilganda (komplekt), masalan 'TTS 20 Pro + honeycomb + pump 470$ ga'. "
                    "Har mahsulot astatkadan kamayadi, kassaga jami summa kirim bo'ladi. Umumiy summa (total_usd) berilsa — "
                    "narxi alohida aytilmagan mahsulotlarga ro'yxat narxi ulushiga qarab taqsimlanadi. "
                    "Biror mahsulot aniqlanmasa yoki yetmasa — hech narsa yozilmaydi.",
     "input_schema": {"type": "object", "required": ["items"], "properties": {
         "items": {"type": "array", "description": "Sotilgan mahsulotlar",
                   "items": {"type": "object", "required": ["product"], "properties": {
                       "product": {"type": "string", "description": "Mahsulot nomi (astatkadagi kabi)"},
                       "qty": {"type": "integer", "default": 1},
                       "price_usd": {"type": "number", "description": "Faqat shu mahsulotga alohida narx aytilgan bo'lsa — dona narxi"},
                       "price_uzs": {"type": "number"}}}},
         "total_usd": {"type": "number", "description": "Hammasi uchun umumiy summa dollarda"},
         "total_uzs": {"type": "number", "description": "Umumiy summa so'mda"},
         "discount_pct": {"type": "number", "default": 0},
         "customer": {"type": "string", "default": ""},
         "customer_type": {"type": "string", "enum": ["B2C", "B2B"], "default": "B2C"},
         "on_credit": {"type": "boolean", "default": False},
         "payment_method": {"type": "string", "enum": ["naqd", "karta", "payme", "click", "otkazma"], "default": "naqd"}}}},
    {"name": "add_stock",
     "description": "Tovar keldi — astatkaga qo'shadi.",
     "input_schema": {"type": "object", "required": ["product", "qty"], "properties": {
         "product": {"type": "string"}, "qty": {"type": "integer"}}}},
    {"name": "record_expense",
     "description": "Xarajat yozadi VA kassadan chiqim qiladi. Pul allaqachon kassadan chiqib bo'lgan bo'lsa (masalan ilgari record_cash orqali yozilgan) — from_cash=false qo'ying, aks holda kassa ikki marta kamayadi.",
     "input_schema": {"type": "object", "required": ["amount_usd", "category"], "properties": {
         "amount_usd": {"type": "number"},
         "category": {"type": "string", "description": "reklama, transport, bank, ijara, ai_xizmat, boshqa..."},
         "expense_type": {"type": "string", "enum": ["period", "cogs_bank", "cogs_delivery"], "default": "period"},
         "from_cash": {"type": "boolean", "default": True, "description": "Kassadan chiqim yozilsinmi. Eski yozuvni to'g'irlash bo'lsa false"},
         "date": {"type": "string", "description": "YYYY-MM-DD. Bo'sh = bugun. O'tgan kun xarajatini yozish uchun"},
         "note": {"type": "string", "default": ""}}}},
    {"name": "record_cash",
     "description": "Kassaga kirim yoki chiqim (sotuv/xarajat/qarz to'lovidan tashqari: shaxsiy oldi, kassa to'g'irlash va h.k.). Mijoz qarzini qaytarsa — pay_debt.",
     "input_schema": {"type": "object", "required": ["amount_usd", "direction"], "properties": {
         "amount_usd": {"type": "number"},
         "direction": {"type": "string", "enum": ["kirim", "chiqim"]},
         "method": {"type": "string", "default": "naqd"},
         "note": {"type": "string", "default": ""}}}},
    {"name": "get_cash",
     "description": "Kassa qoldig'i va oxirgi operatsiyalar.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_report",
     "description": "Hisobot: tushum, tannarx, foyda, sotilgan mahsulotlar. period: today | month | year",
     "input_schema": {"type": "object", "required": ["period"], "properties": {
         "period": {"type": "string", "enum": ["today", "month", "year"]},
         "month": {"type": "string", "description": "YYYY-MM (period=month bo'lsa)"},
         "year": {"type": "string", "description": "YYYY (period=year bo'lsa)"}}}},
    {"name": "get_sales_list",
     "description": "Oxirgi sotuvlar ro'yxati (sana, mahsulot, narx, mijoz).",
     "input_schema": {"type": "object", "properties": {
         "days": {"type": "integer", "default": 7},
         "product": {"type": "string", "description": "Ixtiyoriy filtr"}}}},
    {"name": "get_expenses_list",
     "description": "Xarajatlar ro'yxati (oy bo'yicha).",
     "input_schema": {"type": "object", "properties": {
         "month": {"type": "string", "description": "YYYY-MM, bo'sh bo'lsa joriy oy"}}}},
    {"name": "get_last_operations",
     "description": "Oxirgi operatsiyalar (bekor qilish uchun id lar bilan).",
     "input_schema": {"type": "object", "properties": {"n": {"type": "integer", "default": 8}}}},
    {"name": "undo_operation",
     "description": "Operatsiyani bekor qiladi (sotuv, xarajat yoki qarz to'lovi). get_last_operations dan id oling.",
     "input_schema": {"type": "object", "required": ["op_id"], "properties": {"op_id": {"type": "integer"}}}},
    {"name": "get_debts",
     "description": "Qarzlar 2 tur: debitorlik (mijozlar bizga qarz) va kreditorlik (biz zavod/yetkazuvchiga qarzmiz, zavod qarzi ham shu).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "add_debt",
     "description": "Qarz yozish. type: 'debitorlik' = u BIZGA qarz (mijoz qarzi), 'kreditorlik' = BIZ unga qarzmiz. Nasiya sotuv uchun bu emas — record_sale on_credit=true. Zavodga zakaz qarzi transit orqali yuritiladi.",
     "input_schema": {"type": "object", "required": ["person", "amount_usd", "type"], "properties": {
         "person": {"type": "string"}, "amount_usd": {"type": "number"},
         "type": {"type": "string", "enum": ["debitorlik", "kreditorlik"]},
         "note": {"type": "string", "default": ""}}}},
    {"name": "get_transit",
     "description": "Yo'ldagi tovarlar va zavod qarzi (id lar bilan).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "pay_debt",
     "description": "Qarz TO'LOVI. kind='debitorlik' — mijoz bizga qarzini to'ladi/qaytardi: kassaga kirim, mijoz qarzi eng eskisidan "
                    "kamayadi/yopiladi (record_cash EMAS). kind='kreditorlik' — biz zavod/yetkazuvchiga qarzimizni to'ladik: kassadan chiqim, "
                    "zavod qoldig'i va boshqa kreditorlik eng eskisidan kamayadi. Qarzdan ortiq summa qabul qilinmaydi. /undo bilan qaytadi.",
     "input_schema": {"type": "object", "required": ["kind", "person"], "properties": {
         "kind": {"type": "string", "enum": ["debitorlik", "kreditorlik"]},
         "person": {"type": "string", "description": "Mijoz yoki zavod/yetkazuvchi nomi (taxminiy bo'lsa ham bo'ladi)"},
         "amount_usd": {"type": "number", "description": "To'langan summa dollarda"},
         "amount_uzs": {"type": "number", "description": "So'mda aytilgan bo'lsa"},
         "method": {"type": "string", "enum": ["naqd", "karta", "payme", "click", "otkazma"], "default": "naqd"},
         "note": {"type": "string", "default": ""}}}},
    {"name": "pay_factory_debt",
     "description": "Zavod qarzini to'laydi: qarz kamayadi va kassadan chiqim yoziladi. transit_id bermasa — supplier bo'yicha eng eski qarzdan boshlab yopadi. amount_usd bermasa — o'sha yetkazuvchiga bo'lgan butun qarz yopiladi.",
     "input_schema": {"type": "object", "properties": {
         "supplier": {"type": "string", "description": "Two Trees / Freesub / AlgoLaser"},
         "transit_id": {"type": "integer", "description": "Aniq yozuv id (get_transit dan)"},
         "amount_usd": {"type": "number", "description": "To'langan summa. Bo'sh = butun qarz"},
         "from_cash": {"type": "boolean", "default": True, "description": "Kassadan chiqim yozilsinmi. Qarz ilgari to'langan bo'lib faqat tizimda ochiq qolgan bo'lsa — false"},
         "note": {"type": "string", "default": ""}}}},
    {"name": "get_financial_statements",
     "description": "Moliyaviy hisobot: P&L (tushum, tannarx, yalpi va sof foyda), Balans (aktiv/passiv/kapital), Cash Flow. Egasi 'moliyaviy hisobot', 'balans', 'foyda qancha', 'biznes qiymati' desa ishlating.",
     "input_schema": {"type": "object", "properties": {
         "period": {"type": "string", "description": "YYYY-MM yoki YYYY. Bo'sh = joriy oy"}}}},
    {"name": "get_aging",
     "description": "Qarzdorlik yoshi: kim necha kundan beri qarzdor (0-30/31-60/61-90/90+), biz kimga qarzdormiz, zavod qarzi.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_inventory_turnover",
     "description": "Tovar aylanishi: har mahsulot uchun band kapital, zaxira necha kunga yetadi, qaysi tovar harakatsiz, qaysisiga qayta buyurtma kerak.",
     "input_schema": {"type": "object", "properties": {
         "days": {"type": "integer", "default": 90}}}},
    {"name": "close_period",
     "description": "Oyni yopadi \u2014 o'sha oyga yangi yozuv kiritib bo'lmaydi. Egasidan tasdiq oling.",
     "input_schema": {"type": "object", "required": ["period"], "properties": {
         "period": {"type": "string", "description": "YYYY-MM"},
         "reopen": {"type": "boolean", "default": False, "description": "true \u2014 yopilgan oyni qayta ochadi"}}}},
    {"name": "create_document",
     "description": "Mijozga hisob-faktura yoki chek yaratib yuboradi (PDF).",
     "input_schema": {"type": "object", "required": ["customer", "lines"], "properties": {
         "doc_type": {"type": "string", "enum": ["faktura", "chek"], "default": "faktura"},
         "customer": {"type": "string"},
         "lines": {"type": "array", "description": "Mahsulotlar",
                   "items": {"type": "object", "required": ["product", "qty"], "properties": {
                       "product": {"type": "string"}, "qty": {"type": "integer"},
                       "price_usd": {"type": "number", "description": "Bo'sh = ro'yxat narxi"}}}},
         "note": {"type": "string", "default": ""}}}},
    {"name": "get_customer_card",
     "description": "Mijoz kartasi: barcha xaridlari, jami tushum va foyda, qarzi, kanali, qayta buyurtma vaqti kelgan rasxodniklari, aloqa tarixi. 'Alisher kim', 'Alisher nima olgan', 'Alisher qancha olib bergan' kabi savollarga shuni ishlating.",
     "input_schema": {"type": "object", "required": ["name"], "properties": {
         "name": {"type": "string", "description": "Mijoz ismi"}}}},
    {"name": "link_customers",
     "description": "Eski sotuv va qarz yozuvlaridagi ism-matnlarni mijoz kartalariga bog'laydi, dublikatlarni ko'rsatadi. Mijoz tarixi bo'sh chiqsa shuni ishlating.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "merge_customers",
     "description": "Ikki mijoz kartasini birlashtiradi (dublikat). Birinchisi ikkinchisiga qo'shilib o'chadi. Avval egasidan tasdiq oling.",
     "input_schema": {"type": "object", "required": ["from_name", "to_name"], "properties": {
         "from_name": {"type": "string", "description": "O'chadigan (eski/noto'liq ism)"},
         "to_name": {"type": "string", "description": "Qoladigan (to'g'ri ism)"}}}},
    {"name": "set_customer_channel",
     "description": "Mijoz qaysi kanaldan kelganini belgilaydi: olx, instagram, telegram, tavsiya, b2b, boshqa. Yangi mijoz qo'shganda albatta so'rang.",
     "input_schema": {"type": "object", "required": ["name", "channel"], "properties": {
         "name": {"type": "string"},
         "channel": {"type": "string", "enum": ["olx", "instagram", "telegram", "tavsiya", "b2b", "boshqa"]}}}},
    {"name": "get_channel_report",
     "description": "Qaysi kanal qancha foyda keltirgani: OLX, Instagram, tavsiya va hokazo. Reklamaga qayerga pul sarflashni hal qilishda ishlating.",
     "input_schema": {"type": "object", "properties": {
         "period": {"type": "string", "description": "YYYY-MM yoki YYYY. Bo'sh = hamma vaqt"}}}},
    {"name": "get_reorders",
     "description": "Qayta buyurtma vaqti kelgan mijozlar: kim qaysi rasxodnikni qachon olgan va tugagan bo'lishi kerak. Takroriy savdo uchun asosiy asbob.",
     "input_schema": {"type": "object", "properties": {
         "days_ahead": {"type": "integer", "default": 5, "description": "Necha kun oldindan ogohlantirish"}}}},
    {"name": "set_consumable",
     "description": "Mahsulotni rasxodnik deb belgilaydi: necha kunda tugaydi. Masalan sublimatsiya qog'ozi 30 kun. Shundan keyin uni olgan mijozlarga avtomat eslatma chiqadi. days=0 kuzatuvdan chiqaradi.",
     "input_schema": {"type": "object", "required": ["product", "days"], "properties": {
         "product": {"type": "string"},
         "days": {"type": "integer", "description": "Necha kunda tugaydi. 0 = rasxodnik emas"}}}},
    {"name": "log_contact",
     "description": "Mijoz bilan bo'lgan suhbat yoki kelishuvni yozib qo'yadi. Egasi 'Alisherga aytdim', 'Sardor qo'ng'iroq qildi' desa ishlating.",
     "input_schema": {"type": "object", "required": ["name", "text"], "properties": {
         "name": {"type": "string"},
         "text": {"type": "string", "description": "Nima gaplashildi"},
         "kind": {"type": "string", "default": "suhbat", "description": "suhbat | qongiroq | taklif | shikoyat"}}}},
    {"name": "create_statement",
     "description": "Solishtirish dalolatnomasi: mijozning barcha xaridlari va qarz qoldig'i PDF holida. B2B mijoz imzolashi uchun.",
     "input_schema": {"type": "object", "required": ["name"], "properties": {
         "name": {"type": "string"}}}},
    {"name": "send_dashboard",
     "description": "Biznes holatini chiroyli HTML dashboard fayl qilib yuboradi: kassa, astatka, oylik savdo grafigi, xarajatlar, nelikvid, raqobat. Egasi 'dashboard', 'umumiy holat', 'hisobot fayl' desa ishlating.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "broadcast_customers",
     "description": "Botga obuna bo'lgan mijozlarga xabar yuboradi. Faqat egasi aniq so'raganda ishlating. Avval matnni ko'rsatib tasdiq oling.",
     "input_schema": {"type": "object", "required": ["text"], "properties": {
         "text": {"type": "string", "description": "Xabar matni"},
         "confirmed": {"type": "boolean", "default": False, "description": "Egasi tasdiqladimi. false bo'lsa faqat obunachilar soni qaytadi"}}}},
    {"name": "record_competitor_price",
     "description": "Raqobatchining narxini yozib qo'yadi. Foydalanuvchi aytsa ham, web_search bilan o'zingiz topsangiz ham ishlating. Bir mahsulot uchun bir necha sotuvchi bo'lishi mumkin.",
     "input_schema": {"type": "object", "required": ["competitor", "product", "their_price_usd"], "properties": {
         "competitor": {"type": "string", "description": "Sotuvchi nomi yoki OLX profili, masalan apexmach"},
         "product": {"type": "string", "description": "Mahsulot nomi (bizning astatkadagi kabi)"},
         "their_price_usd": {"type": "number"},
         "note": {"type": "string", "default": "", "description": "Havola, holati (yangi/b-u), izoh"}}}},
    {"name": "get_competitor_analysis",
     "description": "Raqobat tahlili: har mahsulot bo'yicha bizning narx, raqobatchi narxlari, o'rin (arzon/qimmat), marja zaxirasi. product bersangiz faqat o'shani.",
     "input_schema": {"type": "object", "properties": {
         "product": {"type": "string", "description": "Ixtiyoriy: bitta mahsulot"},
         "days": {"type": "integer", "default": 90, "description": "Necha kunlik ma'lumot"}}}},
    {"name": "get_analytics",
     "description": "Tahlil: abc_xyz | nelikvid | trend | cashflow",
     "input_schema": {"type": "object", "required": ["kind"], "properties": {
         "kind": {"type": "string", "enum": ["abc_xyz", "nelikvid", "trend", "cashflow"]}}}},
    {"name": "get_customers",
     "description": "Mijozlar ro'yxati.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "delete_customer",
     "description": "Mijozni o'chirish SO'ROVI (ism bo'yicha aniq moslik). Darhol o'chirmaydi: egasiga 'Ha, o'chir / Yo'q' "
                    "tugmalari yuboriladi, o'chirish faqat egasi 'Ha' ni bosganda bajariladi. Egasiga tugmani bosishini ayting.",
     "input_schema": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}},
    {"name": "add_customer",
     "description": "Mijoz qo'shadi. Shu ismli mijoz bor bo'lsa ma'lumotini yangilaydi (telefon, tur, izoh).",
     "input_schema": {"type": "object", "required": ["name"], "properties": {
         "name": {"type": "string"}, "phone": {"type": "string", "default": ""},
         "customer_type": {"type": "string", "enum": ["B2C", "B2B"], "description": "Faqat aniq bilsangiz bering. Bo'sh qoldirilsa eski tur saqlanadi, yangi mijozga B2C qo'yiladi"},
         "notes": {"type": "string", "default": ""},
         "channel": {"type": "string", "enum": ["olx", "instagram", "telegram", "tavsiya", "b2b", "boshqa"],
                     "description": "Qayerdan keldi. Yangi mijozda albatta so'rang"}}}},
    {"name": "get_rate",
     "description": "Joriy USD/UZS kursi (CBU).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "update_price",
     "description": "Mahsulot sotish narxini o'zgartirish.",
     "input_schema": {"type": "object", "required": ["product", "new_price_usd"], "properties": {
         "product": {"type": "string"}, "new_price_usd": {"type": "number"}}}},
    {"name": "post_channel",
     "description": "Telegram kanalga post yuborish. Faqat foydalanuvchi aniq so'raganda.",
     "input_schema": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}},
]

# ── Asboblarni bajarish ──────────────────────────────────────────
async def execute_tool(name, inp, ctx=None):
    # ── Yopilgan davrga yozishni taqiqlash ──
    YOZUV = {"record_sale", "record_sale_multi", "record_expense", "record_cash", "add_debt", "pay_debt",
             "pay_factory_debt", "undo_operation", "add_stock"}
    if name in YOZUV:
        _s = inp.get("date") or today()
        if is_closed(_s):
            return _j({"error": f"{str(_s)[:7]} davri yopilgan \u2014 yozuv kiritib bo'lmaydi. "
                                f"Ochish uchun close_period ni reopen=true bilan chaqiring yoki /och {str(_s)[:7]}"})

    try:
        if name == "get_stock":
            q = (inp.get("query") or "").lower()
            ps = get_products()
            if q:
                ps = [p for p in ps if q in p['name'].lower() or q in p['cat'].lower() or q in p['sup'].lower()]
            return _j([{"id": p['id'], "name": p['name'], "cat": p['cat'], "supplier": p['sup'],
                        "qty": p['qty'], "cost": p['cost'], "price": p['price']} for p in ps])

        if name == "record_sale":
            prod, cands = match_product(inp.get("product", ""), prefer_stock=True)
            if not prod:
                if cands:
                    return _j({"error": f"'{inp.get('product')}' aniq emas — qaysi biri? Egasidan qisqa so'rang.",
                               "variantlar": cands})
                return _j({"error": f"Mahsulot topilmadi: {inp.get('product')}. get_stock bilan nomini tekshiring."})
            qty = max(1, int(inp.get("qty") or 1))
            if prod['qty'] < qty:
                return _j({"error": f"Astatkada yetarli emas: {prod['name']} — {prod['qty']} ta bor, {qty} ta sotildi deyilyapti. "
                                    f"Tovar kelgan bo'lsa avval add_stock qiling."})
            rate = get_exchange_rate()
            price = _to_usd(inp.get("price_usd"), inp.get("price_uzs"), rate)
            total_in = _to_usd(inp.get("total_usd"), inp.get("total_uzs"), rate)
            if price <= 0 and total_in > 0: price = round(total_in / qty, 4)
            if price <= 0: price = prod['price']
            disc = float(inp.get("discount_pct") or 0)
            if disc > 0: price = round(price * (1 - disc / 100), 2)
            cust = (inp.get("customer") or "").strip()
            ctype = inp.get("customer_type") or "B2C"
            on_credit = bool(inp.get("on_credit"))
            if on_credit and not cust:
                return _j({"error": "Nasiya uchun mijoz ismi kerak — egasidan so'rang."})
            ok, sale_id = save_sale(prod['id'], prod['name'], qty, price, prod['cost'], disc, cust, ctype,
                                    cash=not on_credit, method=inp.get("payment_method") or "naqd")
            if not ok: return _j({"error": f"Saqlanmadi — astatka yetmadi ({prod['name']})"})
            total = round(price * qty, 2)
            profit = round((price - prod['cost']) * qty, 2)
            if on_credit:
                add_debt(cust, total, DEBITOR, f"nasiya: {prod['name']} x{qty} (#s{sale_id})")
                cash_note = "nasiya — kassaga tushmadi, debitor yozildi"
            else:
                cash_note = "kassaga kirim yozildi"
            after = next((p for p in get_products() if p['id'] == prod['id']), None)
            return _j({"ok": True, "sale_id": sale_id, "product": prod['name'], "qty": qty,
                       "unit_price": round(price, 2), "total": total, "profit": profit,
                       "astatkada_qoldi": after['qty'] if after else prod['qty'] - qty,
                       "kassa_qoldigi": round(get_cash_balance(), 2), "cash": cash_note,
                       "uzs_total": round(total * rate)})

        if name == "record_sale_multi":
            items = inp.get("items") or []
            if not items: return _j({"error": "items bo'sh"})
            rate = get_exchange_rate()
            prods_now = get_products()
            rows, xato = [], []
            for it in items:
                p, cands = match_product((it or {}).get("product", ""), prefer_stock=True, prods=prods_now)
                if not p:
                    xato.append({"product": (it or {}).get("product"),
                                 **({"variantlar": cands} if cands else {"error": "topilmadi"})})
                    continue
                q = max(1, int((it or {}).get("qty") or 1))
                rows.append({"p": p, "qty": q,
                             "unit": _to_usd((it or {}).get("price_usd"), (it or {}).get("price_uzs"), rate)})
            if xato:
                return _j({"error": "Ba'zi mahsulotlar aniq emas — HECH NARSA yozilmadi. Egasidan aniqlang.",
                           "tafsil": xato})
            kerak = defaultdict(int)
            for r in rows: kerak[r["p"]["id"]] += r["qty"]
            yetmaydi = sorted({f"{r['p']['name']}: {r['p']['qty']} ta bor, {kerak[r['p']['id']]} ta kerak"
                               for r in rows if r["p"]["qty"] < kerak[r["p"]["id"]]})
            if yetmaydi:
                return _j({"error": "Astatkada yetarli emas — hech narsa yozilmadi", "tafsil": yetmaydi})
            total_in = _to_usd(inp.get("total_usd"), inp.get("total_uzs"), rate)
            fixed = [r for r in rows if r["unit"] > 0]
            free = [r for r in rows if r["unit"] <= 0]
            for r in fixed: r["sum"] = round(r["unit"] * r["qty"], 2)
            if total_in > 0:
                fixed_sum = sum(r["sum"] for r in fixed)
                if free:
                    rest = round(total_in - fixed_sum, 2)
                    if rest < 0:
                        return _j({"error": f"Umumiy summa ${total_in:,.2f} alohida aytilgan narxlardan (${fixed_sum:,.2f}) kichik"})
                    parts = _taqsimla(rest, [r["p"]["price"] * r["qty"] for r in free])
                    for r, s in zip(free, parts): r["sum"] = s
                elif abs(fixed_sum - total_in) > 0.01:
                    parts = _taqsimla(total_in, [r["sum"] for r in fixed])
                    for r, s in zip(fixed, parts): r["sum"] = s
            else:
                for r in free: r["sum"] = round(r["p"]["price"] * r["qty"], 2)
            disc = float(inp.get("discount_pct") or 0)
            cust = (inp.get("customer") or "").strip()
            ctype = inp.get("customer_type") or "B2C"
            on_credit = bool(inp.get("on_credit"))
            if on_credit and not cust:
                return _j({"error": "Nasiya uchun mijoz ismi kerak — egasidan so'rang."})
            method = inp.get("payment_method") or "naqd"
            done = []
            for r in rows:
                s = r["sum"] * (1 - disc / 100) if disc > 0 else r["sum"]
                unit = s / r["qty"]
                ok, sid = save_sale(r["p"]["id"], r["p"]["name"], r["qty"], unit, r["p"]["cost"], disc,
                                    cust, ctype, cash=not on_credit, method=method)
                if not ok:
                    return _j({"error": f"{r['p']['name']} saqlanmadi (astatka yetmadi). Yozilganlari: {done}"})
                done.append({"sale_id": sid, "product": r["p"]["name"], "qty": r["qty"],
                             "summa": round(s, 2), "foyda": round(s - r["p"]["cost"] * r["qty"], 2)})
            jami = round(sum(d["summa"] for d in done), 2)
            if on_credit:
                add_debt(cust, jami, DEBITOR, "nasiya: " + ", ".join(f"{d['product']} x{d['qty']}" for d in done)
                         + " (" + ",".join(f"#s{d['sale_id']}" for d in done) + ")")
            after = {p['id']: p['qty'] for p in get_products()}
            for d, r in zip(done, rows): d["astatkada_qoldi"] = after.get(r["p"]["id"])
            return _j({"ok": True, "sotuvlar": done, "jami": jami,
                       "jami_foyda": round(sum(d["foyda"] for d in done), 2),
                       "taqsimlash": "umumiy summa ro'yxat narxi ulushiga qarab bo'lindi" if (total_in > 0 and free) else "",
                       "kassa_qoldigi": round(get_cash_balance(), 2),
                       "cash": "nasiya — kassaga tushmadi, debitor yozildi" if on_credit else "kassaga kirim yozildi",
                       "uzs_total": round(jami * rate)})

        if name == "add_stock":
            prod, cands = match_product(inp.get("product", ""))
            if not prod:
                if cands: return _j({"error": f"'{inp.get('product')}' aniq emas — qaysi biri?", "variantlar": cands})
                return _j({"error": "Mahsulot topilmadi"})
            add_qty(prod['id'], int(inp.get("qty", 1)))
            after = next((p for p in get_products() if p['id'] == prod['id']), None)
            return _j({"ok": True, "product": prod['name'], "new_qty": after['qty'] if after else prod['qty'] + int(inp.get("qty", 1))})

        if name == "record_expense":
            amt = float(inp.get("amount_usd", 0))
            if amt >= 5000: amt = round(amt / get_exchange_rate(), 2)
            eid = add_expense(amt, inp.get("category", "boshqa"), inp.get("expense_type", "period"),
                              inp.get("note", ""), cash=inp.get("from_cash", True), date=inp.get("date"))
            return _j({"ok": True, "expense_id": eid, "amount": amt,
                       "cash_balance": get_cash_balance(),
                       "cash_note": "kassadan chiqim yozildi" if inp.get("from_cash", True) else "kassaga tegilmadi"})

        if name == "record_cash":
            amt = float(inp.get("amount_usd", 0))
            if amt >= 5000: amt = round(amt / get_exchange_rate(), 2)
            add_cash(amt, inp.get("direction", "kirim"), "boshqa", inp.get("note", ""), inp.get("method", "naqd"))
            return _j({"ok": True, "cash_balance": get_cash_balance()})

        if name == "get_cash":
            hist = get_cash_history()[:8]
            return _j({"balance": get_cash_balance(),
                       "recent": [{"date": r[1], "type": r[3], "amount": r[4], "note": r[6]} for r in hist]})

        if name == "get_report":
            p = inp.get("period", "today")
            if p == "today": f = today()
            elif p == "month": f = inp.get("month") or this_month()
            else: f = inp.get("year") or datetime.now().strftime('%Y')
            sales = get_sales(f); exps = get_expenses(f)
            rev = sum(s[6] for s in sales); cogs = sum(s[5] * s[4] for s in sales)
            exp_total = sum(e[2] for e in exps)
            by_prod = defaultdict(lambda: [0, 0.0])
            for s in sales: by_prod[s[3]][0] += s[4]; by_prod[s[3]][1] += s[6]
            return _j({"period": f, "revenue": rev, "cogs": cogs, "gross_profit": rev - cogs,
                       "expenses": exp_total, "net_profit": rev - cogs - exp_total,
                       "sales_count": len(sales),
                       "by_product": [{"product": k, "qty": v[0], "revenue": v[1]} for k, v in by_prod.items()]})

        if name == "get_sales_list":
            days = int(inp.get("days", 7))
            since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            conn = db(); c = conn.cursor()
            c.execute("SELECT date,product,qty,revenue,profit,customer FROM sales WHERE date>=? AND reversed=0 ORDER BY id DESC LIMIT 40", (since,))
            rows = c.fetchall(); conn.close()
            pf = (inp.get("product") or "").lower()
            if pf: rows = [r for r in rows if pf in r[1].lower()]
            return _j([{"date": r[0], "product": r[1], "qty": r[2], "revenue": r[3], "profit": r[4], "customer": r[5]} for r in rows])

        if name == "get_expenses_list":
            m = inp.get("month") or this_month()
            return _j([{"date": e[1], "amount": e[2], "category": e[3], "type": e[4], "note": e[5]} for e in get_expenses(m)])

        if name == "get_last_operations":
            ops = get_last_ops(int(inp.get("n", 8)))
            return _j([{"op_id": o[0], "when": o[1], "type": o[3], "data": json.loads(o[4])} for o in ops])

        if name == "undo_operation":
            ok, msg = _undo_op(int(inp.get("op_id", 0)))
            return _j({"ok": ok, "message": msg})

        if name == "get_debts":
            conn = db(); c = conn.cursor()
            c.execute("SELECT date,person,amount,type,note FROM debts WHERE paid=0 ORDER BY id DESC")
            debts = c.fetchall()
            c.execute("SELECT supplier,product,remaining,status FROM transit WHERE remaining>0")
            fac = c.fetchall(); conn.close()
            deb = [{"date": d[0], "person": d[1], "amount": d[2], "note": d[4]} for d in debts if debt_turi(d[3]) == DEBITOR]
            kre = [{"date": d[0], "person": d[1], "amount": d[2], "note": d[4]} for d in debts if debt_turi(d[3]) == KREDITOR]
            zav = [{"supplier": f[0], "item": f[1], "remaining": f[2]} for f in fac]
            return _j({"debitorlik_mijozlar_bizga_qarz": deb,
                       "kreditorlik_biz_qarzmiz": kre,
                       "kreditorlik_zavod": zav,
                       "jami_debitorlik": round(sum(x["amount"] or 0 for x in deb), 2),
                       "jami_kreditorlik": round(sum(x["amount"] or 0 for x in kre) + sum(x["remaining"] or 0 for x in zav), 2)})

        if name == "add_debt":
            amt = float(inp.get("amount_usd", 0))
            if amt >= 5000: amt = round(amt / get_exchange_rate(), 2)
            turi = debt_turi(inp.get("type") or DEBITOR)
            if not turi:
                return _j({"error": "type faqat 'debitorlik' yoki 'kreditorlik' bo'lishi mumkin"})
            did = add_debt(inp.get("person", ""), amt, turi, inp.get("note", ""))
            return _j({"ok": True, "id": did, "type": turi})

        if name == "get_transit":
            conn = db(); c = conn.cursor()
            c.execute("SELECT id,date,supplier,product,qty,unit_cost,total_cost,deposit,remaining,status FROM transit WHERE status IN ('yolda','qarz') ORDER BY id DESC")
            rows = c.fetchall(); conn.close()
            return _j([{"id": r[0], "date": r[1], "supplier": r[2], "product": r[3], "qty": r[4],
                        "unit_cost": r[5], "total": r[6], "deposit": r[7], "remaining": r[8], "status": r[9]} for r in rows])

        if name == "pay_debt":
            amt = _to_usd(inp.get("amount_usd"), inp.get("amount_uzs"))
            return _j(await asyncio.to_thread(pay_debt, inp.get("kind"), inp.get("person", ""), amt,
                                              inp.get("method") or "naqd", inp.get("note") or ""))

        if name == "pay_factory_debt":
            sup = (inp.get("supplier") or "").strip()
            tid = inp.get("transit_id")
            amt = inp.get("amount_usd")
            if amt is not None:
                amt = float(amt)
                if amt >= 5000: amt = round(amt / get_exchange_rate(), 2)
            conn = db(); cc = conn.cursor()
            if tid:
                cc.execute("SELECT id,supplier,product,remaining FROM transit WHERE id=? AND remaining>0", (int(tid),))
            elif sup:
                cc.execute("SELECT id,supplier,product,remaining FROM transit WHERE supplier LIKE ? AND remaining>0 ORDER BY id", (f"%{sup}%",))
            else:
                cc.execute("SELECT id,supplier,product,remaining FROM transit WHERE remaining>0 ORDER BY id")
            rows = cc.fetchall(); conn.close()
            if not rows:
                return _j({"error": "Ochiq qarz topilmadi" + (f" ({sup})" if sup else "")})
            total_debt = sum(r[3] for r in rows)
            pay = total_debt if amt is None else min(amt, total_debt)
            left = pay; closed = []
            for r in rows:
                if left <= 0: break
                part = min(left, r[3])
                pay_transit_deposit(r[0], part)
                closed.append({"id": r[0], "supplier": r[1], "item": r[2],
                               "paid": round(part, 2), "still_owed": round(r[3] - part, 2)})
                left -= part
            from_cash = inp.get("from_cash", True)
            if from_cash:
                add_cash(pay, "chiqim", "zavod_qarz",
                         inp.get("note") or f"{sup or 'zavod'} qarziga to'lov")
            conn = db(); cc = conn.cursor()
            cc.execute("SELECT COALESCE(SUM(remaining),0) FROM transit WHERE remaining>0")
            rest = cc.fetchone()[0]; conn.close()
            return _j({"ok": True, "paid": round(pay, 2), "closed": closed,
                       "remaining_total_debt": round(rest, 2),
                       "cash_balance": get_cash_balance(),
                       "cash_note": "kassadan chiqim yozildi" if from_cash else "kassaga tegilmadi"})

        if name == "get_financial_statements":
            per = (inp.get("period") or this_month()).strip()
            return _j({"pl": pl_hisobot(per), "balans": balans(), "cash_flow": cash_flow(per),
                       "yopiq": is_closed(per + "-01")})

        if name == "get_aging":
            return _j(qarz_yoshi())

        if name == "get_inventory_turnover":
            return _j(aylanish(int(inp.get("days", 90))))

        if name == "close_period":
            per = (inp.get("period") or "").strip()
            if not re.match(r"^\d{4}-\d{2}$", per):
                return _j({"error": "Format: YYYY-MM"})
            if inp.get("reopen"):
                return _j({"ok": open_period(per), "period": per, "holat": "ochildi"})
            if is_closed(per + "-01"):
                return _j({"error": f"{per} allaqachon yopilgan"})
            pl = pl_hisobot(per)
            close_period(per)
            return _j({"ok": True, "period": per, "holat": "yopildi", "snapshot": pl})

        if name == "create_document":
            if ctx is None: return _j({"error": "ctx yo'q"})
            lines = inp.get("lines") or []
            qatorlar = []
            for ln in lines:
                p = find_product(ln.get("product", ""))
                if not p: return _j({"error": f"Mahsulot topilmadi: {ln.get('product')}"})
                narx = float(ln.get("price_usd") or 0) or p["price"]
                if narx >= 5000: narx = round(narx / get_exchange_rate(), 2)
                qatorlar.append((p["name"], int(ln.get("qty", 1)), narx))
            if not qatorlar: return _j({"error": "Mahsulot ko'rsatilmagan"})
            base = f"/tmp/doc_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
            p_, raqam, jami, is_pdf = await asyncio.to_thread(
                build_hujjat, base, inp.get("doc_type", "faktura"),
                inp.get("customer", ""), qatorlar, inp.get("note", ""))
            with open(p_, "rb") as fh:
                await ctx.bot.send_document(
                    chat_id=OWNER_ID, document=fh,
                    filename=f"{raqam}.{'pdf' if is_pdf else 'html'}",
                    caption=f"\U0001F4C4 {raqam} \u00b7 {fmt(jami)}")
            try: os.remove(p_)
            except Exception: pass
            return _j({"ok": True, "raqam": raqam, "jami": jami, "format": "pdf" if is_pdf else "html",
                       "eslatma": "" if is_pdf else "PDF uchun egasi /deps buyrug'ini berishi kerak"})

        if name == "get_customer_card":
            k = mijoz_karta(inp.get("name", ""))
            if not k:
                oxshash = mijoz_qidir(inp.get("name", ""))
                return _j({"error": f"Mijoz topilmadi: {inp.get('name')}",
                           "oxshash": [x["nom"] for x in oxshash[:5]]})
            k["sotuvlar"] = k["sotuvlar"][:20]
            return _j(k)

        if name == "link_customers":
            r = bogla_hammasi()
            r["dublikatlar"] = dublikatlar()
            return _j(r)

        if name == "merge_customers":
            return _j(birlashtir(inp.get("from_name", ""), inp.get("to_name", "")))

        if name == "set_customer_channel":
            return _j(kanal_belgila(inp.get("name", ""), inp.get("channel", "")))

        if name == "get_channel_report":
            return _j({"kanallar": kanal_hisobot((inp.get("period") or "").strip())})

        if name == "get_reorders":
            lst = qayta_buyurtma(int(inp.get("days_ahead", 5)))
            return _j({"soni": len(lst), "royxat": lst[:25],
                       "kuzatuvdagi_rasxodniklar": rasxodniklar()})

        if name == "set_consumable":
            return _j(rasxodnik_belgila(inp.get("product", ""), int(inp.get("days", 0))))

        if name == "log_contact":
            cid = mijoz_id(inp.get("name", ""), create=True)
            if not cid: return _j({"error": "Mijoz aniqlanmadi"})
            log_qosh(cid, inp.get("kind", "suhbat"), inp.get("text", ""))
            return _j({"ok": True, "mijoz": inp.get("name"), "sana": today()})

        if name == "create_statement":
            if ctx is None: return _j({"error": "ctx yo'q"})
            k = mijoz_karta(inp.get("name", ""))
            if not k: return _j({"error": f"Mijoz topilmadi: {inp.get('name')}"})
            if not k["sotuvlar"]: return _j({"error": "Bu mijozda xarid yo'q"})
            qatorlar = []
            for s in reversed(k["sotuvlar"]):
                sn = s["sana"][8:10] + "." + s["sana"][5:7] + "." + s["sana"][:4]
                dn = max(1, s["dona"])
                qatorlar.append((sn + " - " + s["mahsulot"], dn, round(s["summa"] / dn, 2)))
            izoh = f"Xaridlar soni: {k['sotuv_soni']}."
            if k["bizga_qarzdor"]:
                izoh += f" Qarz qoldigi: {k['bizga_qarzdor']:.2f} USD."
            base = f"/tmp/sd_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
            p_, raqam, jami, is_pdf = await asyncio.to_thread(
                build_hujjat, base, "dalolatnoma", k["nom"], qatorlar, izoh)
            with open(p_, "rb") as fh:
                await ctx.bot.send_document(
                    chat_id=OWNER_ID, document=fh,
                    filename=f"{raqam}.{'pdf' if is_pdf else 'html'}",
                    caption=f"\U0001F4C4 {raqam} \u00b7 {k['nom']} \u00b7 {fmt(jami)}")
            try: os.remove(p_)
            except Exception: pass
            log_qosh(k["id"], "hujjat", f"Dalolatnoma {raqam}")
            return _j({"ok": True, "raqam": raqam, "jami": jami})

        if name == "send_dashboard":
            if ctx is None: return _j({"error": "ctx yo'q"})
            p = f"/tmp/TC_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            await asyncio.to_thread(build_dashboard, p)
            with open(p, 'rb') as fh:
                await ctx.bot.send_document(
                    chat_id=OWNER_ID, document=fh,
                    filename=f"ThermoCrafts_{datetime.now().strftime('%d.%m.%Y')}.html",
                    caption="\U0001F4CA Biznes holati")
            try: os.remove(p)
            except Exception: pass
            return _j({"ok": True, "note": "Dashboard fayl yuborildi"})

        if name == "broadcast_customers":
            n = sub_count()
            if not inp.get("confirmed"):
                return _j({"subscribers": n, "need_confirm": True,
                           "note": f"{n} ta obunachiga yuboriladi. Egasidan tasdiq so'rang, keyin confirmed=true bilan qayta chaqiring."})
            if n == 0: return _j({"error": "Obunachi yo'q. /obunachilar dagi havolani mijozlarga tarqating."})
            if ctx is None: return _j({"error": "ctx yo'q"})
            full = f"\U0001F4E3 ThermoCrafts\n\n{inp.get('text','')}\n\n\U0001F4CD Yunusobod, Toshkent"
            yub = blok = 0
            for cid, *_ in sub_list():
                try:
                    await ctx.bot.send_message(chat_id=cid, text=full); yub += 1
                except Exception:
                    sub_off(cid); blok += 1
                await asyncio.sleep(0.05)
            return _j({"ok": True, "sent": yub, "blocked": blok})

        if name == "record_competitor_price":
            prod = find_product(inp.get("product", ""))
            pname = prod['name'] if prod else inp.get("product", "")
            price = float(inp.get("their_price_usd", 0))
            if price >= 5000: price = round(price / get_exchange_rate(), 2)
            add_competitor(inp.get("competitor", ""), pname, price, inp.get("note", ""))
            our = prod['price'] if prod else 0
            return _j({"ok": True, "product": pname, "their_price": price, "our_price": our,
                       "diff": round(our - price, 2) if our else None,
                       "position": ("biz qimmat" if our and our > price else "biz arzon" if our else "bizda yo'q")})

        if name == "get_competitor_analysis":
            days = int(inp.get("days", 90))
            since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            conn = db(); cc = conn.cursor()
            pf = (inp.get("product") or "").strip()
            if pf:
                p = find_product(pf); pf = p['name'] if p else pf
                cc.execute("SELECT product,competitor,their_price,date,note FROM competitors WHERE date>=? AND product LIKE ? ORDER BY date DESC", (since, f"%{pf}%"))
            else:
                cc.execute("SELECT product,competitor,their_price,date,note FROM competitors WHERE date>=? ORDER BY date DESC", (since,))
            rows = cc.fetchall(); conn.close()
            by = defaultdict(list)
            for r in rows: by[r[0]].append(r)
            out = []
            for pname, lst in by.items():
                p = find_product(pname)
                prices = [r[2] for r in lst if r[2] and r[2] > 0]
                if not prices: continue
                mn, mx = min(prices), max(prices)
                avg = round(sum(prices) / len(prices), 2)
                our = p['price'] if p else 0
                cost = p['cost'] if p else 0
                item = {"product": pname, "our_price": our, "our_cost": cost,
                        "market_min": mn, "market_avg": avg, "market_max": mx,
                        "sellers": [{"who": r[1], "price": r[2], "date": r[3], "note": r[4]} for r in lst[:5]]}
                if our:
                    item["vs_min_pct"] = round((our - mn) / mn * 100, 1) if mn else None
                    item["position"] = ("eng arzon" if our <= mn else "eng qimmat" if our >= mx else "o'rtacha")
                    item["margin_now"] = round(our - cost, 2)
                    item["margin_if_match_min"] = round(mn - cost, 2)
                    item["in_stock"] = p['qty']
                out.append(item)
            return _j({"days": days, "products": out} if out else {"info": "Raqobatchi narxlari hali yozilmagan"})

        if name == "get_analytics":
            k = inp.get("kind")
            if k == "abc_xyz": return _j(abc_xyz_analysis())
            if k == "nelikvid": return _j(get_nelikvid(60))
            if k == "trend":
                months, change = get_sales_trend(); return _j({"months": months, "change_pct": change})
            if k == "cashflow": return _j(cash_flow_forecast())
            return _j({"error": "noma'lum kind"})

        if name == "get_customers":
            conn = db(); c = conn.cursor()
            c.execute("SELECT id,name,phone,type,total_purchases,notes,created FROM customers ORDER BY total_purchases DESC LIMIT 50")
            rows = c.fetchall(); conn.close()
            return _j({"count": len(rows),
                       "customers": [{"id": r[0], "name": r[1], "phone": r[2], "type": r[3],
                                      "total_purchases": r[4], "notes": r[5], "since": r[6]} for r in rows]})

        if name == "add_customer":
            nm = (inp.get("name") or "").strip()
            if not nm: return _j({"error": "Mijoz ismi bo'sh"})
            holat, cid = add_customer(nm, inp.get("phone") or "", inp.get("customer_type") or "", inp.get("notes") or "")
            if holat == 'xato': return _j({"error": "Saqlanmadi"})
            if inp.get("channel"): kanal_belgila(nm, inp.get("channel"))
            return _j({"ok": True, "status": holat, "id": cid, "name": nm,
                       "kanal": inp.get("channel") or "",
                       "jami_mijoz": len(find_customers())})

        if name == "delete_customer":
            # AI o'zi o'chira olmaydi — egasiga tasdiqlash tugmalari yuboriladi
            return _j(await _mijoz_ochirish_sorovi(inp.get("name", ""), ctx))

        if name == "get_rate":
            return _j({"usd_uzs": get_exchange_rate(), "source": "cbu.uz"})

        if name == "update_price":
            prod = find_product(inp.get("product", ""))
            if not prod: return _j({"error": "Mahsulot topilmadi"})
            update_product(prod['id'], price=float(inp.get("new_price_usd", prod['price'])))
            return _j({"ok": True, "product": prod['name'], "old": prod['price'], "new": inp.get("new_price_usd")})

        if name == "post_channel":
            if ctx is None: return _j({"error": "ctx yo'q"})
            ok = await post_to_channel(ctx, inp.get("text", ""))
            return _j({"ok": ok})

        return _j({"error": f"Noma'lum asbob: {name}"})
    except Exception as e:
        log.exception("tool error")
        return _j({"error": str(e)[:200]})

# ── Agent tsikli ─────────────────────────────────────────────────
def _ai_system_prompt():
    rate = get_exchange_rate()
    return f"""Siz ThermoCrafts (Yunusobod, Toshkent) biznes yordamchisisiz. Egasi — Ilyosbek.
Biznes: Two Trees lazer/CNC, Freesub termopress, sublimatsiya qog'ozlari. Sotuv OLX.uz va Telegram orqali.
Bugun: {datetime.now().strftime('%d.%m.%Y %H:%M')}. Kurs: 1 USD = {rate:,.0f} so'm.

QOIDALAR:
1. Har doim o'zbek tilida, qisqa va aniq javob bering. Telegram Markdown ishlatmang — oddiy matn, emoji mumkin.
2. Pul birligi — dollar. Foydalanuvchi so'mda aytsa (mln, so'm, 5000 dan katta raqam) — price_uzs/amount ga so'mni bering, asbob o'zi o'giradi. Javobda ikkala valyutani ko'rsating.
3. Sotuv/xarajat/qarz kabi YOZUV amallarini bajarishdan oldin ma'lumot yetarli bo'lsa DARHOL bajaring, so'ng nima qilganingizni bir-ikki qatorda tasdiqlang. Faqat mahsulot yoki summa aniq bo'lmasa savol bering.
4. Mahsulot nomini foydalanuvchi qisqa yozsa (tts20, cnc, 15in1) — get_stock bilan toping, taxmin qilmang.
5. "sotilmadi", "ketmadi" — bu SOTUV EMAS. Inkorni to'g'ri tushuning.
6. Savolga javob berish uchun kerak bo'lsa bir nechta asbobni ketma-ket chaqiring va o'zingiz hisoblang.
7. Xato bo'lsa (asbob error qaytarsa) — sababini tushuntiring va nima qilishni taklif qiling.
8. Bekor qilish so'ralsa: avval get_last_operations, keyin undo_operation.
9. Raqamlarni o'qish oson formatda yozing: $1,250 / 14,700,000 so'm.
"""


# ══════════════════════════════════════════════════════════════════
# MIRA-USLUBI: doimiy xotira, xarakter, proaktiv xabarlar, vision
# ══════════════════════════════════════════════════════════════════
AI_NAME   = os.getenv('AI_NAME', 'Aida')
AI_WEB    = os.getenv('AI_WEB', '1') == '1'          # internetdan qidirish
TZ_OFFSET = int(os.getenv('TZ_OFFSET', '5'))         # Toshkent UTC+5
BRIEF_MORNING = os.getenv('BRIEF_MORNING', '09:00')  # ertalabki xulosa
BRIEF_EVENING = os.getenv('BRIEF_EVENING', '21:00')  # kechki xulosa
_WEB_OK = {'v': AI_WEB}

def _local_now():
    # datetime.utcnow() Python 3.12+ da eskirgan (deprecated) — natija o'sha: Toshkent vaqti, tzinfo'siz
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=TZ_OFFSET)

def _hhmm(s):
    """'9:00' → '09:00' (BRIEF_MORNING/EVENING solishtirish uchun)"""
    try:
        h, m = str(s).strip().split(':')[:2]
        return f"{int(h):02d}:{int(m):02d}"
    except Exception:
        return str(s).strip()

# ── Doimiy xotira (SQLite) ───────────────────────────────────────
def init_sub_table():
    conn = db(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS subscribers (
        chat_id INTEGER PRIMARY KEY, name TEXT, username TEXT,
        joined TEXT, active INTEGER DEFAULT 1, last_sent TEXT, source TEXT)""")
    conn.commit(); conn.close()

def sub_add(chat_id, name='', username='', source=''):
    conn = db(); c = conn.cursor()
    c.execute("SELECT chat_id FROM subscribers WHERE chat_id=?", (chat_id,))
    if c.fetchone():
        c.execute("UPDATE subscribers SET active=1, name=?, username=? WHERE chat_id=?",
                  (name, username, chat_id))
        new = False
    else:
        c.execute("INSERT INTO subscribers (chat_id,name,username,joined,active,source) VALUES (?,?,?,?,1,?)",
                  (chat_id, name, username, today(), source))
        new = True
    conn.commit(); conn.close(); return new

def sub_list(active_only=True):
    conn = db(); c = conn.cursor()
    q = "SELECT chat_id,name,username,joined,active FROM subscribers"
    if active_only: q += " WHERE active=1"
    c.execute(q + " ORDER BY joined DESC")
    rows = c.fetchall(); conn.close(); return rows

def sub_off(chat_id):
    conn = db(); c = conn.cursor()
    c.execute("UPDATE subscribers SET active=0 WHERE chat_id=?", (chat_id,))
    conn.commit(); conn.close()

def sub_count():
    conn = db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM subscribers WHERE active=1")
    n = c.fetchone()[0]; conn.close(); return n

def init_ai_tables():
    conn = db(); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ai_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        role TEXT, content TEXT, ts TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ai_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fact TEXT,
        category TEXT DEFAULT 'umumiy', created TEXT, active INTEGER DEFAULT 1)''')
    # Suhbat tarixi cheksiz o'smasin (har zaxirada butun baza yuklanadi); oxirgi 400 ta xabar yetarli
    c.execute('''DELETE FROM ai_messages WHERE id NOT IN
                 (SELECT id FROM ai_messages ORDER BY id DESC LIMIT 400)''')
    conn.commit(); conn.close()

def mem_add(fact, category='umumiy'):
    conn = db(); c = conn.cursor()
    c.execute('SELECT id FROM ai_memory WHERE active=1 AND lower(fact)=lower(?)', (fact.strip(),))
    if c.fetchone(): conn.close(); return None
    c.execute('INSERT INTO ai_memory (fact,category,created) VALUES (?,?,?)',
              (fact.strip(), category, today()))
    mid = c.lastrowid; conn.commit(); conn.close(); return mid

def mem_list(limit=60):
    conn = db(); c = conn.cursor()
    c.execute('SELECT id,fact,category,created FROM ai_memory WHERE active=1 ORDER BY id DESC LIMIT ?', (limit,))
    rows = c.fetchall(); conn.close(); return rows

def mem_forget(mid):
    conn = db(); c = conn.cursor()
    c.execute('UPDATE ai_memory SET active=0 WHERE id=?', (mid,))
    ok = c.rowcount > 0; conn.commit(); conn.close(); return ok

def hist_load(user_id, n=AI_HISTORY_MAX):
    """Oxirgi n xabarni bazadan yuklaydi (faqat matn — tool bloklari saqlanmaydi)"""
    conn = db(); c = conn.cursor()
    c.execute('SELECT role,content FROM ai_messages WHERE user_id=? ORDER BY id DESC LIMIT ?', (user_id, n))
    rows = c.fetchall()[::-1]; conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

def hist_save(user_id, role, text):
    conn = db(); c = conn.cursor()
    c.execute('INSERT INTO ai_messages (user_id,role,content,ts) VALUES (?,?,?,?)',
              (user_id, role, text, _local_now().strftime('%Y-%m-%d %H:%M')))
    conn.commit(); conn.close()

def hist_clear(user_id):
    conn = db(); c = conn.cursor()
    c.execute('DELETE FROM ai_messages WHERE user_id=?', (user_id,))
    conn.commit(); conn.close()

# ── Xotira asboblari ────────────────────────────────────────────
AI_TOOLS += [
    {"name": "remember",
     "description": "Muhim faktni doimiy xotiraga yozadi (mijoz haqida, egasining odati, qaror, narx siyosati, eslatma). Suhbat tugasa ham saqlanadi.",
     "input_schema": {"type": "object", "required": ["fact"], "properties": {
         "fact": {"type": "string", "description": "Qisqa, aniq fakt. Masalan: 'Alisher — zargar, B2B, har oy 1-2 ta TTS oladi'"},
         "category": {"type": "string", "enum": ["mijoz", "egasi", "qaror", "narx", "eslatma", "umumiy"], "default": "umumiy"}}}},
    {"name": "forget",
     "description": "Xotiradan faktni o'chiradi (id bo'yicha).",
     "input_schema": {"type": "object", "required": ["memory_id"], "properties": {"memory_id": {"type": "integer"}}}},
    {"name": "list_memory",
     "description": "Doimiy xotiradagi barcha faktlar (id bilan).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "set_reminder",
     "description": "Eslatma qo'yadi — belgilangan sanada ertalabki xulosada chiqadi.",
     "input_schema": {"type": "object", "required": ["text", "date"], "properties": {
         "text": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD"}}}},
]

async def _execute_tool_mira(name, inp, ctx=None):
    if name == "remember":
        mid = mem_add(inp.get("fact", ""), inp.get("category", "umumiy"))
        return _j({"ok": True, "id": mid, "note": "allaqachon bor" if mid is None else "saqlandi"})
    if name == "forget":
        return _j({"ok": mem_forget(int(inp.get("memory_id", 0)))})
    if name == "list_memory":
        return _j([{"id": r[0], "fact": r[1], "category": r[2], "created": r[3]} for r in mem_list()])
    if name == "set_reminder":
        mid = mem_add(f"[{inp.get('date')}] {inp.get('text','')}", "eslatma")
        return _j({"ok": True, "id": mid})
    return None

# ── Xarakter + xotira bilan system prompt ───────────────────────
def _mira_system_prompt():
    rate = get_exchange_rate()
    mem = mem_list(60)
    mem_txt = "\n".join(f"- (#{r[0]}, {r[2]}) {r[1]}" for r in mem) if mem else "- (hali bo'sh)"
    return f"""Siz — {AI_NAME}, ThermoCrafts (Yunusobod, Toshkent) biznesining shaxsiy AI hamkori. Egasi — Ilyosbek.
Biznes: Two Trees lazer/CNC, Freesub termopress, AlgoLaser, sublimatsiya qog'ozlari. Sotuv OLX.uz, Telegram kanal, B2B.
Hozir: {_local_now().strftime('%d.%m.%Y %H:%M')} (Toshkent). Kurs: 1 USD = {rate:,.0f} so'm.

XARAKTER:
- Siz chatbot emas, biznes-sherik. O'z fikringiz bor: raqam ko'rsangiz — xulosa chiqaring, xato ko'rsangiz — ayting.
- Qisqa, aniq, do'stona. Bo'sh maqtov yo'q. Egasiga "siz" deb murojaat qiling.
- O'zbek tilida. Telegram Markdown ishlatmang (yulduzcha, pastki chiziq yo'q) — oddiy matn + emoji.

DOIMIY XOTIRA (siz oldin eslab qolganlar):
{mem_txt}

XOTIRA QOIDALARI:
- Egasi mijoz, odat, qaror yoki muhim narsa aytsa — darhol `remember` bilan yozing (so'ramasdan). Masalan: yangi mijoz kim, qaysi narxga kelishildi, egasi qachon ishlamaydi.
- Eslab qolganingizni javobda bir so'z bilan ko'rsating: "(eslab qoldim)".
- Xotiradagi fakt eskirgan bo'lsa — `forget` qiling va yangisini yozing.

ISH QOIDALARI:
1. Pul birligi — dollar. So'mda aytilsa (mln, so'm, 5000+ raqam) — price_uzs/amount ga so'mni bering, asbob o'giradi. Javobda ikkala valyutani ko'rsating.
2. Sotuv/xarajat/qarz YOZUV amallari: ma'lumot yetarli bo'lsa darhol bajaring, keyin 1-2 qatorda tasdiqlang. Faqat mahsulot yoki summa aniq bo'lmasa so'rang.
   SOTUV ("sotuv", "sotdim", "ketdi", "sotildi" + mahsulot + summa): DARHOL yozing.
   - Mijoz ismi va to'lov usuli IXTIYORIY — aytilmagan bo'lsa SO'RAMANG: naqd, mijozsiz yozing. Faqat "nasiya/qarzga" desa on_credit=true (shunda mijoz ismi kerak).
   - Bir nechta mahsulot bitta umumiy summaga ("tts 20 pro + honeycomb + pump 470$ ga") — BITTA record_sale_multi chaqiruvi, total_usd=470. Alohida narx aytilgan mahsulotga price_usd bering.
   - Bitta mahsulot bir necha dona umumiy summaga ("2 ta 940$") — record_sale, qty=2, total_usd=940.
   - Asbob "variantlar" qaytarsa (masalan ikki xil honeycomb) — variantlarni ko'rsatib bitta qisqa savol bering, javobdan keyin yozing.
   - Yozgandan keyin tasdiq: nima sotildi, jami summa ($ va so'm), har biridan astatkada nechta qoldi, kassa qoldig'i.
   EXCEL: egasi .xlsx faylni shu chatga yuborsa bot uni o'zi o'qiydi (astatka, sotuv, xarajat, kassa) va tasdiqlash tugmasini chiqaradi. Excel haqida so'rasa — faylni shu yerga yuborishni ayting.
3. Qisqa nomlar (tts20, cnc, 15in1) — get_stock bilan toping, taxmin qilmang.
4. "sotilmadi", "ketmadi" — bu sotuv EMAS.
5. Kerak bo'lsa bir nechta asbobni ketma-ket chaqiring va o'zingiz hisoblang.
6. Bekor qilish: avval get_last_operations, keyin undo_operation.
7. Internetdan ma'lumot kerak bo'lsa (raqobatchi narxi, texnik xususiyat, yangi model) — web_search ishlating va manbani ayting.
8. Raqamlar: $1,250 / 14,700,000 so'm.
9. Egasi rasm yuborsa: chek bo'lsa — xarajat yozing; mahsulot bo'lsa — qaysi mahsulot ekanini ayting; boshqa bo'lsa — tavsiflab so'rang.
10. Zavod qarzi to'langan desa — pay_factory_debt ishlating. Qarz ilgari to'langan bo'lib faqat tizimda ochiq qolgan bo'lsa, from_cash=false qo'ying (kassa ikki marta kamaymasin). To'lov hozir bo'lgan bo'lsa from_cash=true.
16. MIJOZ: 'Alisher kim', 'nima olgan', 'qancha foyda bergan' - get_customer_card. Mijoz tarixi bo'sh chiqsa avval link_customers. Yangi mijoz qo'shganda kanalini so'rang (olx/instagram/tavsiya/b2b) - set_customer_channel yoki add_customer ning channel maydoni.
17. TAKRORIY SAVDO: rasxodnik (qog'oz, krujka, futbolka, siyoh) sotilsa set_consumable bilan necha kunda tugashini belgilang. get_reorders - kimga qayta taklif qilish vaqti kelgan. Egasi mijoz bilan gaplashganini aytsa log_contact bilan yozib qo'ying.
18. KANAL: get_channel_report - qaysi kanal ko'p foyda beryapti. Reklama byudjeti haqida savol bo'lsa shundan boshlang.
14. MOLIYA: 'foyda qancha', 'balans', 'biznes qancha turadi' — get_financial_statements. 'kim qarzdor', 'qachondan beri' — get_aging. 'qaysi tovar turib qoldi', 'qayta buyurtma' — get_inventory_turnover. Hisobotlarni izohlab bering: shunchaki raqam emas, xulosa ayting.
15. HUJJAT: mijozga faktura/chek kerak bo'lsa create_document. Oy yopish so'ralsa close_period — avval o'sha oy hisobotini ko'rsatib tasdiq oling.
13. RAQOBAT: egasi raqobatchi narxini aytsa — record_competitor_price bilan darhol yozing. "bozorda qancha?", "raqobatchilar qancha sotyapti?" desa — avval get_competitor_analysis; ma'lumot yo'q yoki eskirgan bo'lsa web_search bilan OLX/birbir dan qidiring, topganingizni record_competitor_price bilan saqlang, keyin xulosa ayting. Narx bo'yicha maslahat berganda marjani (narx - sebest) hisobga oling — sebestdan past taklif qilmang.
11. PUL CHIQIMI UCHUN QAYSI ASBOB (muhim, chalkashtirmang):
    - record_expense — HAQIQIY XARAJAT: reklama, OLX, transport, ijara, bank komissiyasi, AI xizmati, yo'lkira. Bu kassadan ham chiqadi, xarajat hisobotida ham ko'rinadi. Chiqim bo'lsa DOIM shuni ishlating.
    - pay_debt kind=kreditorlik — zavodga/yetkazuvchiga qarz to'lash. Bu xarajat EMAS (qarz kamayadi), xarajat hisobotiga tushmaydi.
      (pay_factory_debt — faqat aniq transit_id kerak bo'lsa yoki pul ilgari to'langan bo'lib from_cash=false kerak bo'lsa.)
    - pay_debt kind=debitorlik — MIJOZ QARZINI QAYTARDI/TO'LADI. record_cash EMAS (aks holda qarz ochiq qoladi).
    - record_cash — faqat xarajat ham, qarz to'lovi ham bo'lmagan harakat uchun: shaxsiy pul olish, kassa to'g'irlash.
    - QARZ faqat 2 tur: DEBITORLIK — mijozlar bizga qarz (nasiya, add_debt type=debitorlik); KREDITORLIK — biz zavod/yetkazuvchiga qarzmiz (zavod qarzi transit orqali, boshqasi add_debt type=kreditorlik).
    Shubha bo'lsa record_expense tanlang. record_cash bilan chiqim yozsangiz, u xarajat hisobotida KO'RINMAYDI.
12. Eski yozuvni to'g'irlashda (pul allaqachon kassadan chiqqan, faqat xarajat jurnalida yo'q) — record_expense ni from_cash=false bilan chaqiring va date bering. Aks holda kassa ikki marta kamayadi.
"""

def _all_tools():
    tools = list(AI_TOOLS)
    if _WEB_OK['v']:
        tools.append({"type": "web_search_20250305", "name": "web_search", "max_uses": 3})
    return tools

# ── Yangi agent tsikli (doimiy xotira + rasm) ───────────────────
async def ai_agent(user_id: int, user_msg, ctx=None, persist=True) -> str:
    """user_msg: matn yoki content-bloklar ro'yxati (rasm uchun)"""
    history = hist_load(user_id)
    while history and history[0].get("role") != "user":   # tarix assistant xabaridan boshlanmasin (API talabi)
        history.pop(0)
    messages = history + [{"role": "user", "content": user_msg}]
    save_text = user_msg if isinstance(user_msg, str) else "[rasm] " + next(
        (b.get("text", "") for b in user_msg if isinstance(b, dict) and b.get("type") == "text"), "")
    final_text = ""
    for _ in range(7):
        try:
            # system prompt kursni (tarmoq) va bazani o'qiydi — event loop'ni to'smasligi uchun oqimda
            system = await asyncio.to_thread(_mira_system_prompt)
            resp = await asyncio.to_thread(
                ai.messages.create, model=AI_MODEL, max_tokens=1500,
                system=system, tools=_all_tools(), messages=messages)
        except Exception as e:
            if _WEB_OK['v'] and 'web_search' in str(e).lower():
                _WEB_OK['v'] = False
                log.warning("web_search o'chirildi: %s", e)
                continue
            raise
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "pause_turn":      # web_search uzoq davom etdi — o'sha javobni davom ettiramiz
            continue
        if resp.stop_reason != "tool_use":
            final_text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            break
        results = []
        for b in resp.content:
            if getattr(b, "type", "") != "tool_use": continue
            out = await _execute_tool_mira(b.name, b.input or {}, ctx)
            if out is None: out = await execute_tool(b.name, b.input or {}, ctx)
            log.info(f"AI tool {b.name}: {str(b.input)[:100]} -> {out[:100]}")
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
        messages.append({"role": "user", "content": results})
    else:
        final_text = "Juda ko'p qadam bo'ldi — savolni qisqaroq qiling."
    if not final_text: final_text = "Bajarildi."
    if persist:
        hist_save(user_id, "user", save_text)
        hist_save(user_id, "assistant", final_text)
    return final_text

async def cmd_ai_reset(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    hist_clear(u.effective_user.id)
    await u.message.reply_text("🧹 Suhbat tozalandi. Doimiy xotira saqlanib qoldi (/xotira).")

async def cmd_xotira(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    mem = mem_list(60)
    if not mem:
        await u.message.reply_text(f"🧠 {AI_NAME} xotirasi hali bo'sh. Suhbatda mijoz, qaror, odatlaringizni ayting — eslab qoladi."); return
    text = f"🧠 {AI_NAME} XOTIRASI ({len(mem)} ta)\n\n"
    for r in mem: text += f"#{r[0]} [{r[2]}] {r[1]}\n"
    text += "\nO'chirish: \"#12 ni unut\" deb yozing."
    await u.message.reply_text(text)

# ── Rasm → AI (vision) ───────────────────────────────────────────
async def handle_photo_ai(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Rasm: caption'da 'kanal'/'post' bo'lsa — kanalga; aks holda AI tahlil qiladi"""
    if await skan_rasm(u, ctx): return                     # 10-bosqich: POS/Ombor/Serial skaner rejimi
    if not can(u, 'boshqaruv'): return
    cap = (u.message.caption or "").strip()
    if any(w in cap.lower() for w in ("kanal", "post", "e'lon", "elon")):
        return await mkt_media(u, ctx)                     # oldindan ko'rish bilan (avval darhol kanalga ketardi)
    if ctx.user_data.get('photo_product_id'):
        return await handle_photo(u, ctx)
    _mst = _ui_ol(ctx, 'mkt')
    if _mst and (_mst.get('wait') == 'media' or (getattr(u.message, 'media_group_id', None) and _mst.get('mg') == u.message.media_group_id)):
        return await mkt_media(u, ctx)
    await ctx.bot.send_chat_action(chat_id=u.effective_chat.id, action='typing')
    try:
        f = await ctx.bot.get_file(u.message.photo[-1].file_id)
        raw = await f.download_as_bytearray()
        b64 = base64.b64encode(bytes(raw)).decode()
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                   {"type": "text", "text": cap or "Bu rasmda nima? Kerak bo'lsa tegishli amalni bajaring."}]
        reply = await ai_agent(u.effective_user.id, content, ctx)
    except Exception as e:
        log.exception("photo ai"); reply = f"⚠️ Rasmni o'qiy olmadim: {str(e)[:150]}"
    await u.message.reply_text(reply)

# ── Proaktiv xabarlar (ertalab / kechqurun) ─────────────────────
async def _briefing(app, kind):
    try:
        rate = get_exchange_rate()
        bal = get_cash_balance()
        if kind == 'morning':
            y = (_local_now() - timedelta(days=1)).strftime('%Y-%m-%d')
            ys = get_sales(y); yrev = sum(s[6] for s in ys); yprof = sum(s[7] for s in ys)
            low = [p['name'] for p in get_products() if 0 < p['qty'] <= 1]
            out = [p['name'] for p in get_products() if p['qty'] == 0 and p['id'] <= 21]
            nel = get_nelikvid(60)
            rem = [r for r in mem_list(60) if r[2] == 'eslatma' and r[1].startswith(f"[{today()}]")]
            head = (f"☀️ Xayrli tong! {_local_now().strftime('%d.%m.%Y')}\n\n"
                    f"💵 Kassa: {fmt(bal)} (~{bal*rate:,.0f} so'm)\n"
                    f"📊 Kecha: {len(ys)} ta sotuv, {fmt(yrev)} tushum, {fmt(yprof)} foyda\n")
            if low: head += f"⚠️ 1 ta qoldi: {', '.join(low[:6])}\n"
            if out: head += f"🔴 Tugagan: {', '.join(out[:6])}\n"
            if nel: head += f"❄️ 2+ oy sotilmagan: {len(nel)} ta ({', '.join(x['name'] for x in nel[:3])}...)\n"
            if rem: head += "🔔 Bugun: " + "; ".join(r[1].split('] ', 1)[-1] for r in rem) + "\n"
            try:
                cn = db(); cx = cn.cursor()
                cx.execute("SELECT product, MIN(their_price) FROM competitors WHERE date>=? GROUP BY product",
                           ((_local_now() - timedelta(days=60)).strftime('%Y-%m-%d'),))
                cheap = []
                for pn, mp in cx.fetchall():
                    pp = find_product(pn)
                    if pp and pp['qty'] > 0 and mp and pp['price'] > mp:
                        cheap.append(f"{pn} (bozor {fmt(mp)}, biz {fmt(pp['price'])})")
                cn.close()
                if cheap: head += "🔍 Bizdan arzon: " + "; ".join(cheap[:3]) + "\n"
            except Exception:
                pass
            try:
                qb = qayta_buyurtma(0)
                if qb:
                    head += "\U0001F501 Qayta buyurtma: " + "; ".join(
                        f"{x['mijoz']} - {x['mahsulot']} ({x['otgan']} kun)" for x in qb[:3]) + "\n"
            except Exception:
                pass
            prompt = ("Bu ertalabki xulosa. Egasiga 2-3 qatorda o'z fikringizni ayting: bugun nimaga e'tibor berish kerak. "
                      "Raqamlarni takrorlamang, xulosa chiqaring.\n\n" + head)
        else:
            ts = get_sales(today()); trev = sum(s[6] for s in ts); tprof = sum(s[7] for s in ts)
            m = get_sales(this_month()); mrev = sum(s[6] for s in m)
            head = (f"🌙 Kun yakuni {_local_now().strftime('%d.%m')}\n\n"
                    f"📦 Bugun: {len(ts)} ta sotuv — {fmt(trev)} / foyda {fmt(tprof)}\n"
                    f"📈 Oy boshidan: {fmt(mrev)}\n💵 Kassa: {fmt(bal)}\n")
            if ts: head += "• " + "\n• ".join(f"{s[3]} ×{s[4]} = {fmt(s[6])}" for s in ts[:8]) + "\n"
            prompt = "Bu kechki xulosa. 1-2 qator izoh: kun qanday o'tdi, ertaga nima qilish kerak.\n\n" + head
        try:
            comment = await ai_agent(OWNER_ID, prompt, None, persist=False)
        except Exception as e:
            comment = ""
            log.warning("briefing AI: %s", e)
        text = head + ("\n💬 " + comment if comment else "")
        await app.bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception:
        log.exception("briefing")

async def _scheduler(app):
    log.info("Proaktiv xabarlar yoqildi: %s / %s (UTC%+d)", BRIEF_MORNING, BRIEF_EVENING, TZ_OFFSET)
    sent = set()
    bm, be = _hhmm(BRIEF_MORNING), _hhmm(BRIEF_EVENING)
    while True:
        now = _local_now(); key = now.strftime('%Y-%m-%d %H:%M'); hm = now.strftime('%H:%M')
        if hm == bm and ('m' + key[:10]) not in sent:
            sent.add('m' + key[:10]); await _briefing(app, 'morning')
            try: await _ertalab_ogohlantirish(app)
            except Exception: log.exception("ertalab ogohlantirish")
        if hm == be and ('e' + key[:10]) not in sent:
            sent.add('e' + key[:10]); await _briefing(app, 'evening')
        # Kunlik kontent (9-bosqich): vaqt — 📢 Marketing sozlamasi; restartdan keyin takrorlanmaydi (kontent_ishladi)
        try:
            if (app is not None and ('k' + key[:10]) not in sent and hm == _hhmm(soz('kontent_vaqt'))
                    and soz('kontent_kunlik') == '1' and soz('kontent_ishladi') != key[:10]):
                sent.add('k' + key[:10]); soz_yoz('kontent_ishladi', key[:10])
                _t = asyncio.create_task(kontent_kunlik(app.bot)); _FON.add(_t); _t.add_done_callback(_FON.discard)
        except Exception:
            log.exception("kunlik kontent")
        # Kunlik zaxira (10-bosqich): belgilangan vaqtdan keyin, kuniga bir marta (restart bo'lsa ham shu kuni qiladi)
        try:
            if app is not None and ('z' + key[:10]) not in sent and zaxira_vaqti_keldimi():
                sent.add('z' + key[:10]); soz_yoz('zaxira_ishladi', key[:10])
                _t = asyncio.create_task(zaxira_kunlik(app.bot)); _FON.add(_t); _t.add_done_callback(_FON.discard)
        except Exception:
            log.exception("kunlik zaxira")
        # Eski kunlarni tozalash (avval sent.clear() — xuddi shu daqiqada xulosa ikkinchi marta ketishi mumkin edi)
        if len(sent) > 50: sent = {k for k in sent if k[1:] == key[:10]}
        # Kunlik kursni oldindan (alohida oqimda) olib qo'yamiz — handlerlar keshdan oladi, tarmoqni kutmaydi
        if _RATE.get('date') != datetime.now().strftime('%Y-%m-%d') and time.time() >= _RATE.get('retry_at', 0):
            try: await asyncio.to_thread(get_exchange_rate)
            except Exception: log.exception("kurs")
        # Avto-zaxira: FAQAT baza mazmuni o'zgarganda va FAQAT alohida branch'ga (main'ga emas —
        # main'ga yozilsa Railway qayta deploy qiladi va bot o'zini o'chirib-yoqib, yozuvlarni yo'qotadi)
        try:
            if GITHUB_TOKEN and not _BK['blocked'] and time.time() >= _BK['next_try']:
                migrate = _BK.pop('migrate', False)
                if migrate or await asyncio.to_thread(_bk_check_dirty):
                    ok, msg = await asyncio.to_thread(db_backup_to_github, 'avto')
                    log.info("Avto-zaxira: %s — %s", "OK" if ok else "XATO", msg)
                    if not ok:
                        if migrate: _BK['migrate'] = True
                        _BK['next_try'] = time.time() + min(900, 30 * (2 ** min(_BK['fail'], 5)))
                        if _BK['fail'] == 3 and app is not None:     # jim yo'qolmasin — egasiga bir marta aytamiz
                            if db_on_volume():
                                holat = ("Baza Railway diskida (Volume) — yozuvlar saqlanadi, "
                                         "faqat GitHub'dagi nusxa yangilanmayapti.")
                            else:
                                holat = ("DIQQAT: Volume ulanmagan — bot qayta ishga tushsa, oxirgi yozuvlar yo'qoladi. "
                                         "Railway'da botga Volume ulang (mount path: /data).")
                            try:
                                await app.bot.send_message(
                                    chat_id=OWNER_ID,
                                    text=f"⚠️ Bazani GitHub'ga zaxiralab bo'lmayapti (3 marta): {msg}\n{holat}")
                            except Exception:
                                log.exception("zaxira ogohlantirish")
        except Exception:
            log.exception("avto-zaxira")
        await asyncio.sleep(15)

def init_all_tables():
    init_db()
    init_ai_tables()
    init_sub_table()
    init_erp_tables()
    init_crm_tables()
    init_excel_tables()
    init_users_table()

_BG_TASKS = set()

async def _post_init(app):
    init_ai_tables()
    init_sub_table()
    init_erp_tables()
    init_crm_tables()
    init_excel_tables()
    init_users_table()
    _bk_set_baseline()          # hozirgi holat = zaxiradagi holat (keraksiz zaxira bo'lmasin)
    upd = _check_update_marker()
    if upd:
        _BK['migrate'] = True   # belgi o'chirilgani zaxiraga ham tushsin (keyingi restartda qayta aytmasin)
    _t = asyncio.create_task(_scheduler(app))     # havola saqlanadi — aks holda GC vazifani o'chirib yuborishi mumkin
    _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)
    if upd:
        d, running = upd
        if d.get('sha') and d.get('sha') == running:
            text = (f"✅ Bot yangi versiyada ishga tushdi ({_local_now().strftime('%H:%M')}).\n"
                    f"Fayl: {d.get('src', '')}, yuborilgan: {d.get('at', '')}")
        else:
            text = ("ℹ️ Bot qayta ishga tushdi, lekin ishlayotgan kod siz yuborgan fayldan farq qiladi — "
                    "Railway hali eski versiyani ishlatayotgan bo'lishi mumkin. Bir necha daqiqadan keyin /start bosib tekshiring.")
        try: await app.bot.send_message(chat_id=OWNER_ID, text=text)
        except Exception: log.exception("yangilanish xabari")
    if _BK.get('restore_msg'):
        try: await app.bot.send_message(chat_id=OWNER_ID, text=_BK['restore_msg'])
        except Exception: log.exception("restore xabari")

async def _post_shutdown(app):
    """To'xtashdan oldin (Railway yangi deploy qilganda) oxirgi o'zgarishlarni zaxiralaydi"""
    try:
        if GITHUB_TOKEN and not _BK['blocked'] and await asyncio.to_thread(_bk_check_dirty):
            ok, msg = await asyncio.to_thread(db_backup_to_github, "to'xtash")
            log.info("Yakuniy zaxira: %s — %s", "OK" if ok else "XATO", msg)
    except Exception:
        log.exception("yakuniy zaxira")


_DASH_TPL = r"""<!DOCTYPE html>
<html lang="uz"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ThermoCrafts</title>
<style>
:root{
  color-scheme:dark;
  --surface:#1a1a19; --card:#232322; --line:#383835;
  --ink:#ffffff; --ink2:#c3c2b7; --ink3:#8a8a80;
  --s1:#3987e5; --s2:#d95926;
  --good:#0ca30c; --warning:#fab219; --critical:#d03b3b;
}
@media (prefers-color-scheme:light){
  :root{
    color-scheme:light;
    --surface:#fcfcfb; --card:#ffffff; --line:#e5e4e0;
    --ink:#0b0b0b; --ink2:#52514e; --ink3:#78776f;
    --s1:#2a78d6; --s2:#eb6834;
  }
}
*{box-sizing:border-box}
body{margin:0;padding:20px 16px 48px;background:var(--surface);color:var(--ink);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  -webkit-text-size-adjust:100%}
.wrap{max-width:760px;margin:0 auto}
header{margin-bottom:20px}
h1{font-size:21px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:16px;margin:28px 0 10px;letter-spacing:-.01em}
h3{font-size:14px;margin:18px 0 8px;font-weight:600}
h3 .sub{font-weight:400}
.sub{color:var(--ink2);font-size:13px}
.pad{margin:6px 0 8px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.tile .k{font-size:12px;color:var(--ink2);margin-bottom:5px}
.tile .v{font-size:21px;font-weight:650;letter-spacing:-.02em;line-height:1.15}
.tile .sub{font-size:11px;margin-top:3px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 12px;margin-top:10px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-weight:500;color:var(--ink2);font-size:11px;
  text-transform:uppercase;letter-spacing:.04em;padding:0 0 6px;border-bottom:1px solid var(--line)}
td{padding:7px 0;border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:0}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.muted{color:var(--ink2)}
.jami td{font-weight:650;border-top:1px solid var(--line)}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:7px;vertical-align:1px}
.dot.good{background:var(--good)} .dot.warning{background:var(--warning)} .dot.critical{background:var(--critical)}
.good{color:var(--good)} .warning{color:var(--warning)} .critical{color:var(--critical)}
.tag{display:inline-block;margin-left:7px;padding:1px 6px;border-radius:5px;font-size:10.5px;
  border:1px solid var(--line);color:var(--ink2)}
.tag.warn{border-color:var(--warning)}
.tag.warn::before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--warning);margin-right:5px;vertical-align:1px}
.bosh{color:var(--ink2);font-size:13px;padding:6px 0}
.legend{display:flex;gap:16px;margin:2px 0 8px;font-size:12px;color:var(--ink2)}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;vertical-align:0}
.chart{position:relative}
svg{display:block;overflow:visible}
.grid-l{stroke:var(--line);stroke-width:1}
.axis{stroke:var(--line);stroke-width:1}
.ax{fill:var(--ink3);font-size:9.5px;font-family:inherit}
.lbl{fill:var(--ink2);font-size:10px;font-weight:600;font-family:inherit}
.s1{fill:var(--s1)} .s2{fill:var(--s2)}
.hit{fill:transparent;cursor:pointer}
.hit:hover,.hit.on{fill:var(--ink);opacity:.055}
#tip{position:absolute;display:none;background:var(--card);border:1px solid var(--line);
  border-radius:9px;padding:7px 10px;font-size:12px;pointer-events:none;white-space:nowrap;
  box-shadow:0 4px 14px rgba(0,0,0,.28);z-index:5}
#tip b{display:block;margin-bottom:3px;font-size:11px;color:var(--ink2);font-weight:500}
#tip s{display:block;text-decoration:none;font-variant-numeric:tabular-nums}
details{margin-top:8px}
summary{font-size:12px;color:var(--ink2);cursor:pointer;padding:4px 0}
footer{margin-top:28px;color:var(--ink3);font-size:11.5px;text-align:center}
@media(min-width:620px){.grid{grid-template-columns:repeat(4,1fr)}}
</style></head><body><div class="wrap">

<header>
  <h1>ThermoCrafts</h1>
  <div class="sub">{{SANA}} &middot; 1 USD = {{RATE}} so&#8216;m</div>
</header>

<div class="grid">{{KPI}}</div>

<h2>Oylik savdo &mdash; {{YIL}}</h2>
<div class="card">
  <div class="legend">
    <span><i style="background:var(--s1)"></i>Tushum</span>
    <span><i style="background:var(--s2)"></i>Foyda</span>
  </div>
  <div class="chart" id="ch">{{CHART}}<div id="tip"></div></div>
  <div class="sub pad">Yil boshidan: tushum <b>${{YILTUSH}}</b> &middot; foyda <b>${{YILFOYD}}</b></div>
  <details><summary>Jadval ko&#8216;rinishi</summary>
    <table><thead><tr><th>Oy</th><th class="num">Sotuv</th><th class="num">Tushum</th><th class="num">Foyda</th></tr></thead>
    <tbody>{{OYROWS}}</tbody></table>
  </details>
</div>

<h2>Astatka</h2>
<div class="card">{{ASTATKA}}</div>

<h2>Bu oy sotuvlar</h2>
<div class="card">{{SOTUV}}</div>

<h2>Bu oy xarajatlar</h2>
<div class="card">{{XARAJAT}}</div>

<h2>Nelikvid &mdash; 2+ oy sotilmagan</h2>
<div class="card">{{NELIKVID}}</div>

<footer>ThermoCrafts &middot; Yunusobod, Toshkent</footer>
</div>
<script>
(function(){
  var ch=document.getElementById('ch'),tip=document.getElementById('tip');
  if(!ch||!tip)return;
  var cur=null;
  function fmt(n){return '$'+Number(n).toLocaleString('en-US');}
  function show(el,ev){
    if(cur)cur.classList.remove('on');
    el.classList.add('on');cur=el;
    tip.innerHTML='<b>'+el.dataset.oy+'</b>'+
      '<s>Tushum: '+fmt(el.dataset.t)+'</s><s>Foyda: '+fmt(el.dataset.f)+'</s>';
    tip.style.display='block';
    var r=ch.getBoundingClientRect(),b=el.getBoundingClientRect();
    var x=b.left-r.left+b.width/2-tip.offsetWidth/2;
    x=Math.max(2,Math.min(x,r.width-tip.offsetWidth-2));
    tip.style.left=x+'px';tip.style.top='4px';
  }
  function hide(){tip.style.display='none';if(cur){cur.classList.remove('on');cur=null;}}
  ch.querySelectorAll('.hit').forEach(function(el){
    el.addEventListener('mouseenter',function(e){show(el,e);});
    el.addEventListener('click',function(e){e.stopPropagation();
      if(cur===el){hide();}else{show(el,e);}});
  });
  ch.addEventListener('mouseleave',hide);
  document.addEventListener('click',hide);
})();
</script>
</body></html>"""



# ══════════════════════════════════════════════════════════════════
# MOLIYA — P&L, Balans, Cash Flow, oy yopish, qarz yoshi, aylanish
# ══════════════════════════════════════════════════════════════════

def init_erp_tables():
    conn = db(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS closed_periods (
        period TEXT PRIMARY KEY, closed_at TEXT, snapshot TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT, raqam TEXT, turi TEXT,
        sana TEXT, mijoz TEXT, summa REAL, sale_id INTEGER, izoh TEXT)""")
    conn.commit(); conn.close()


# ── Oy yopish ─────────────────────────────────────────────────────
def is_closed(sana):
    """Shu sanadagi oy yopilganmi"""
    if not sana: return False
    conn = db(); c = conn.cursor()
    c.execute("SELECT 1 FROM closed_periods WHERE period=?", (str(sana)[:7],))
    r = c.fetchone(); conn.close(); return bool(r)

def closed_list():
    conn = db(); c = conn.cursor()
    c.execute("SELECT period, closed_at FROM closed_periods ORDER BY period")
    r = c.fetchall(); conn.close(); return r

def close_period(period):
    snap = json.dumps(pl_hisobot(period), ensure_ascii=False, default=str)
    conn = db(); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO closed_periods (period,closed_at,snapshot) VALUES (?,?,?)",
              (period, now_t(), snap))
    conn.commit(); conn.close()

def open_period(period):
    conn = db(); c = conn.cursor()
    c.execute("DELETE FROM closed_periods WHERE period=?", (period,))
    n = c.rowcount; conn.commit(); conn.close(); return n > 0


# ── P&L (Daromad va xarajatlar) ───────────────────────────────────
def pl_hisobot(davr):
    """davr: 'YYYY-MM' yoki 'YYYY'"""
    conn = db(); c = conn.cursor()
    f = davr + '%'
    c.execute("SELECT COALESCE(SUM(revenue),0), COALESCE(SUM(unit_cost*qty),0), COALESCE(SUM(CASE WHEN qty>0 THEN 1 ELSE 0 END),0), "
              "COALESCE(SUM(qty),0), COALESCE(SUM(CASE WHEN qty<0 THEN -revenue ELSE 0 END),0) "
              "FROM sales WHERE date LIKE ? AND reversed=0", (f,))
    tushum, cogs, adet, dona, qaytgan = c.fetchone()
    c.execute("SELECT expense_type, category, COALESCE(SUM(amount),0) FROM expenses "
              "WHERE date LIKE ? AND reversed=0 GROUP BY expense_type, category", (f,))
    rows = c.fetchall(); conn.close()

    togri = {}   # cogs_bank, cogs_delivery
    davr_x = {}  # period
    for et, cat, amt in rows:
        (togri if et in ('cogs_bank', 'cogs_delivery') else davr_x)[cat] = \
            (togri if et in ('cogs_bank', 'cogs_delivery') else davr_x).get(cat, 0) + amt
    t_togri = sum(togri.values()); t_davr = sum(davr_x.values())
    yalpi = tushum - cogs - t_togri
    sof = yalpi - t_davr
    return {'davr': davr, 'tushum': tushum, 'cogs': cogs, 'togri_xarajat': t_togri,
            'togri_tafsil': togri, 'yalpi_foyda': yalpi, 'davr_xarajat': t_davr,
            'davr_tafsil': davr_x, 'sof_foyda': sof, 'sotuv_soni': adet, 'dona': dona, 'qaytarish': round(qaytgan or 0, 2),
            'marja_pct': round(yalpi / tushum * 100, 1) if tushum else 0,
            'sof_pct': round(sof / tushum * 100, 1) if tushum else 0}


# ── Balans ────────────────────────────────────────────────────────
def balans(sanagacha=None):
    sana = sanagacha or today()
    conn = db(); c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(CASE WHEN type='kirim' THEN amount ELSE -amount END),0) "
              "FROM cash_box WHERE date<=?", (sana,))
    naqd = c.fetchone()[0] or 0
    c.execute(f"SELECT COALESCE(SUM(amount),0) FROM debts WHERE paid=0 AND type IN {DEBITOR_SQL} AND date<=?", (sana,))
    debitor = c.fetchone()[0] or 0
    c.execute(f"SELECT COALESCE(SUM(amount),0) FROM debts WHERE paid=0 AND type IN {KREDITOR_SQL} AND date<=?", (sana,))
    kreditor = c.fetchone()[0] or 0
    c.execute("SELECT COALESCE(SUM(remaining),0) FROM transit WHERE remaining>0")
    zavod = c.fetchone()[0] or 0
    # Yo'ldagi tovar: kelmagan donalar landed tannarxda (barcha qatorlar — eski ham, transit_balans_otkaz).
    # To'lanmagan qismi transit.remaining — passivda. Buyurtma berish / to'lov / qabul kapitalni o'zgartirmaydi.
    c.execute("SELECT COALESCE(SUM(MAX(0, COALESCE(qty,0)-COALESCE(received_qty,0))*COALESCE(real_cost,unit_cost,0)),0) "
              "FROM transit WHERE status='yolda'")
    yolda = c.fetchone()[0] or 0
    conn.close()
    tovar = sum(p['qty'] * p['cost'] for p in get_products())
    aktiv = naqd + tovar + debitor + yolda
    passiv = kreditor + zavod
    return {'sana': sana, 'naqd': naqd, 'tovar': tovar, 'debitor': debitor, 'yolda': yolda,
            'aktiv': aktiv, 'kreditor': kreditor, 'zavod_qarzi': zavod, 'passiv': passiv,
            'kapital': aktiv - passiv}


# ── Cash Flow ─────────────────────────────────────────────────────
def cash_flow(davr):
    conn = db(); c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(CASE WHEN type='kirim' THEN amount ELSE -amount END),0) "
              "FROM cash_box WHERE date < ?", (davr + '-01' if len(davr) == 7 else davr + '-01-01',))
    boshi = c.fetchone()[0] or 0
    c.execute("SELECT type, category, COALESCE(SUM(amount),0) FROM cash_box "
              "WHERE date LIKE ? GROUP BY type, category", (davr + '%',))
    rows = c.fetchall(); conn.close()
    kirim = {}; chiqim = {}
    for t, cat, amt in rows:
        (kirim if t == 'kirim' else chiqim)[cat or 'boshqa'] = amt
    tk = sum(kirim.values()); tc = sum(chiqim.values())
    return {'davr': davr, 'boshi': boshi, 'kirim': kirim, 'chiqim': chiqim,
            'jami_kirim': tk, 'jami_chiqim': tc, 'oxiri': boshi + tk - tc}


# ── Qarz yoshi ────────────────────────────────────────────────────
def qarz_yoshi():
    conn = db(); c = conn.cursor()
    c.execute("SELECT id,date,person,amount,type,note FROM debts WHERE paid=0 ORDER BY date")
    debts = c.fetchall()
    c.execute("SELECT id,date,supplier,product,remaining FROM transit WHERE remaining>0 ORDER BY date")
    tr = c.fetchall(); conn.close()
    bugun = datetime.now()

    def guruh(rows, kim_i, sum_i, sana_i=1, izoh=None):
        out = {'0-30': [], '31-60': [], '61-90': [], '90+': []}
        for r in rows:
            try: kun = (bugun - datetime.strptime(r[sana_i], '%Y-%m-%d')).days
            except Exception: kun = 0
            b = '0-30' if kun <= 30 else '31-60' if kun <= 60 else '61-90' if kun <= 90 else '90+'
            out[b].append({'kim': r[kim_i], 'summa': r[sum_i], 'kun': kun,
                           'izoh': r[izoh] if izoh is not None else ''})
        return out

    bizga = guruh([d for d in debts if debt_turi(d[4]) == DEBITOR], 2, 3, 1, 5)     # debitorlik
    bizdan = guruh([d for d in debts if debt_turi(d[4]) == KREDITOR], 2, 3, 1, 5)   # kreditorlik (zavoddan tashqari)
    zavod = guruh(tr, 2, 4, 1, 3)
    def jami(g): return sum(x['summa'] for b in g.values() for x in b)
    return {'bizga_qarzdor': bizga, 'biz_qarzdormiz': bizdan, 'zavod': zavod,
            'jami_debitor': jami(bizga), 'jami_kreditor': jami(bizdan) + jami(zavod)}


# ── Tovar aylanishi ───────────────────────────────────────────────
def aylanish(kun=90):
    since = (datetime.now() - timedelta(days=kun)).strftime('%Y-%m-%d')
    conn = db(); c = conn.cursor()
    c.execute("SELECT product, SUM(qty), SUM(revenue), SUM(unit_cost*qty), MAX(date) FROM sales "
              "WHERE date>=? AND reversed=0 GROUP BY product", (since,))
    sot = {r[0]: (r[1], r[2], r[3], r[4]) for r in c.fetchall()}
    conn.close()
    out = []
    for p in get_products():
        q, rev, cogs, oxirgi = sot.get(p['name'], (0, 0, 0, None))
        kunlik = q / kun if q else 0
        zaxira_kun = round(p['qty'] / kunlik) if kunlik > 0 else (None if p['qty'] > 0 else 0)
        band = p['qty'] * p['cost']
        out.append({'nom': p['name'], 'sup': p['sup'], 'qoldiq': p['qty'],
                    'sotildi': q, 'tushum': rev, 'cogs': cogs, 'band_kapital': band,
                    'kunlik': round(kunlik, 3), 'zaxira_kun': zaxira_kun,
                    'oxirgi_sotuv': oxirgi, 'marja': p['price'] - p['cost'],
                    'holat': ('tez' if zaxira_kun is not None and zaxira_kun < 30 else
                              'normal' if zaxira_kun is not None and zaxira_kun <= 90 else
                              'sekin' if zaxira_kun is not None else 'harakatsiz')})
    out.sort(key=lambda x: -x['band_kapital'])
    jami_band = sum(x['band_kapital'] for x in out)
    jami_cogs = sum(x['cogs'] for x in out)
    return {'kun': kun, 'mahsulotlar': out, 'jami_band_kapital': jami_band,
            'davr_cogs': jami_cogs,
            'aylanish_koef': round(jami_cogs / jami_band, 2) if jami_band else 0,
            'ortacha_zaxira_kun': round(jami_band / (jami_cogs / kun)) if jami_cogs else None}


# ══════════════════════════════════════════════════════════════════
# MIJOZLAR (CRM) — karta, ID bog'lash, kanal, qayta buyurtma
# ══════════════════════════════════════════════════════════════════

KANALLAR = ['olx', 'instagram', 'telegram', 'tavsiya', 'b2b', 'boshqa']


def init_crm_tables():
    conn = db(); c = conn.cursor()
    for ddl in [
        "ALTER TABLE customers ADD COLUMN channel TEXT DEFAULT ''",
        "ALTER TABLE customers ADD COLUMN last_contact TEXT DEFAULT ''",
        "ALTER TABLE customers ADD COLUMN chat_id INTEGER DEFAULT 0",
        "ALTER TABLE sales ADD COLUMN customer_id INTEGER DEFAULT 0",
        "ALTER TABLE debts ADD COLUMN customer_id INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN reorder_days INTEGER DEFAULT 0",
    ]:
        try: c.execute(ddl)
        except Exception: pass
    c.execute("""CREATE TABLE IF NOT EXISTS customer_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER,
        sana TEXT, turi TEXT, matn TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS reorder (
        id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER,
        product TEXT, last_date TEXT, cycle_days INTEGER DEFAULT 30,
        active INTEGER DEFAULT 1, last_remind TEXT DEFAULT '')""")
    try: c.execute("CREATE INDEX IF NOT EXISTS ix_sales_cid ON sales(customer_id)")
    except Exception: pass
    try: c.execute("CREATE INDEX IF NOT EXISTS ix_debts_cid ON debts(customer_id)")
    except Exception: pass
    conn.commit(); conn.close()


# ── Ism normalizatsiyasi ──────────────────────────────────────────
_TASH = ["'", '"', '‘', '’', 'ʻ', 'ʼ', '`', '.', ',', '-', '_', '(', ')']

def norm_ism(s):
    s = (s or '').lower().strip()
    for ch in _TASH:
        s = s.replace(ch, '')
    return re.sub(r'\s+', ' ', s).strip()


def mijoz_id(name, create=False, channel='', ctype=''):
    """Ism bo'yicha mijoz ID. create=True — topilmasa yaratadi. 0 = topilmadi."""
    n = norm_ism(name)
    if not n: return 0
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, name FROM customers")
    rows = c.fetchall()
    for cid, nm in rows:
        if norm_ism(nm) == n:
            conn.close(); return cid
    # Biri ikkinchisining boshi: "Alisher" <-> "Alisher Zargarov"
    nomzod = [cid for cid, nm in rows
              if norm_ism(nm).startswith(n + ' ') or n.startswith(norm_ism(nm) + ' ')]
    if len(nomzod) == 1:
        conn.close(); return nomzod[0]
    if not create:
        conn.close(); return 0
    c.execute("INSERT INTO customers (name,phone,type,total_purchases,notes,created,last_purchase,"
              "channel,last_contact,chat_id) VALUES (?,'',?,0,'',?,'',?,'',0)",
              ((name or '').strip(), ctype or 'B2C', today(), (channel or '').lower()))
    cid = c.lastrowid
    conn.commit(); conn.close()
    return cid


def mijoz_qidir(q):
    """Qismiy moslik bo'yicha ro'yxat"""
    n = norm_ism(q)
    conn = db(); c = conn.cursor()
    c.execute("SELECT id,name,phone,type FROM customers ORDER BY total_purchases DESC")
    rows = c.fetchall(); conn.close()
    if not n: return [{'id': r[0], 'nom': r[1], 'tel': r[2], 'tur': r[3]} for r in rows]
    return [{'id': r[0], 'nom': r[1], 'tel': r[2], 'tur': r[3]}
            for r in rows if n in norm_ism(r[1]) or n in norm_ism(r[2] or '')]


def yangila_jami(cid):
    conn = db(); c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(revenue),0), MAX(date) FROM sales WHERE customer_id=? AND reversed=0", (cid,))
    jami, oxirgi = c.fetchone()
    c.execute("UPDATE customers SET total_purchases=?, last_purchase=? WHERE id=?",
              (jami or 0, oxirgi or '', cid))
    conn.commit(); conn.close()


def log_qosh(cid, turi, matn):
    if not cid: return
    conn = db(); c = conn.cursor()
    c.execute("INSERT INTO customer_log (customer_id,sana,turi,matn) VALUES (?,?,?,?)",
              (cid, today(), turi, matn))
    c.execute("UPDATE customers SET last_contact=? WHERE id=?", (today(), cid))
    conn.commit(); conn.close()


# ── Eski yozuvlarni bog'lash ──────────────────────────────────────
def bogla_hammasi():
    """sales.customer / debts.person matnlarini customer_id ga bog'laydi"""
    conn = db(); c = conn.cursor()
    c.execute("SELECT DISTINCT customer FROM sales WHERE COALESCE(customer_id,0)=0 "
              "AND TRIM(COALESCE(customer,''))<>''")
    s_ism = [r[0] for r in c.fetchall()]
    c.execute("SELECT DISTINCT person FROM debts WHERE COALESCE(customer_id,0)=0 "
              "AND TRIM(COALESCE(person,''))<>''")
    d_ism = [r[0] for r in c.fetchall()]
    conn.close()

    n_s = n_d = yangi = 0
    for nm in s_ism:
        bor = mijoz_id(nm)
        cid = bor or mijoz_id(nm, create=True)
        if not cid: continue
        if not bor: yangi += 1
        conn = db(); c = conn.cursor()
        c.execute("UPDATE sales SET customer_id=? WHERE COALESCE(customer_id,0)=0 AND customer=?", (cid, nm))
        n_s += c.rowcount; conn.commit(); conn.close()
        yangila_jami(cid)
    for nm in d_ism:
        bor = mijoz_id(nm)
        cid = bor or mijoz_id(nm, create=True)
        if not cid: continue
        if not bor: yangi += 1
        conn = db(); c = conn.cursor()
        c.execute("UPDATE debts SET customer_id=? WHERE COALESCE(customer_id,0)=0 AND person=?", (cid, nm))
        n_d += c.rowcount; conn.commit(); conn.close()
    return {'sotuv': n_s, 'qarz': n_d, 'yangi_mijoz': yangi}


def sub_bogla(chat_id=None, nomi=''):
    """Obunachini (yoki hammasini) mijoz kartasiga ism bo'yicha bog'laydi"""
    conn = db(); c = conn.cursor()
    if chat_id:
        subs = [(chat_id, nomi or '')]
    else:
        c.execute("SELECT chat_id, name FROM subscribers")
        subs = c.fetchall()
    c.execute("SELECT id, name, COALESCE(chat_id,0) FROM customers")
    custs = c.fetchall()
    conn.close()
    band = {x[2] for x in custs if x[2]}
    n = 0
    for chid, nm in subs:
        if not chid or chid in band: continue
        nn = norm_ism(nm)
        if not nn: continue
        bosh = [x[0] for x in custs if not x[2] and norm_ism(x[1]) == nn]
        if len(bosh) != 1:
            bosh = [x[0] for x in custs if not x[2] and
                    (norm_ism(x[1]).startswith(nn + ' ') or nn.startswith(norm_ism(x[1]) + ' '))]
        if len(bosh) == 1:
            conn = db(); c = conn.cursor()
            c.execute("UPDATE customers SET chat_id=? WHERE id=?", (chid, bosh[0]))
            conn.commit(); conn.close()
            band.add(chid); n += 1
    return n


def sub_ulash(name, chat_id):
    """Mijozni obunachiga qo'lda ulash"""
    cid = mijoz_id(name)
    if not cid: return {'error': f"Mijoz topilmadi: {name}"}
    conn = db(); c = conn.cursor()
    c.execute("SELECT name FROM subscribers WHERE chat_id=?", (int(chat_id),))
    r = c.fetchone()
    if not r:
        conn.close(); return {'error': "Bunday obunachi yo'q"}
    # Bitta chat_id faqat bitta mijozda bo'lishi kerak
    c.execute("UPDATE customers SET chat_id=0 WHERE chat_id=? AND id<>?", (int(chat_id), cid))
    olindi = c.rowcount
    c.execute("UPDATE customers SET chat_id=? WHERE id=?", (int(chat_id), cid))
    conn.commit(); conn.close()
    return {'ok': True, 'mijoz': name, 'obunachi': r[0], 'chat_id': int(chat_id),
            'boshqadan_olindi': olindi}


def birlashtir(manba, nishon):
    """manba mijozni nishon ichiga qo'shib yuboradi, manba o'chadi"""
    a = mijoz_id(manba); b = mijoz_id(nishon)
    if not a: return {'error': f"Topilmadi: {manba}"}
    if not b: return {'error': f"Topilmadi: {nishon}"}
    if a == b: return {'error': "Bir xil mijoz"}
    conn = db(); c = conn.cursor()
    c.execute("SELECT name,phone,notes,channel,chat_id FROM customers WHERE id=?", (a,))
    an, ap, anot, ach, acid = c.fetchone()
    c.execute("SELECT name,phone,notes,channel,chat_id FROM customers WHERE id=?", (b,))
    bn, bp, bnot, bch, bcid = c.fetchone()
    c.execute("UPDATE sales SET customer_id=? WHERE customer_id=?", (b, a)); ns = c.rowcount
    c.execute("UPDATE debts SET customer_id=? WHERE customer_id=?", (b, a)); nd = c.rowcount
    c.execute("UPDATE customer_log SET customer_id=? WHERE customer_id=?", (b, a))
    c.execute("UPDATE reorder SET customer_id=? WHERE customer_id=?", (b, a))
    izoh = bnot or ''
    if anot and anot not in izoh:
        izoh = (izoh + ' | ' + anot).strip(' |')
    c.execute("UPDATE customers SET phone=?, notes=?, channel=?, chat_id=? WHERE id=?",
              (bp or ap or '', izoh, bch or ach or '', bcid or acid or 0, b))
    c.execute("DELETE FROM customers WHERE id=?", (a,))
    conn.commit(); conn.close()
    yangila_jami(b)
    return {'ok': True, 'manba': an, 'nishon': bn, 'sotuv': ns, 'qarz': nd}


def dublikatlar():
    """Ehtimoliy dublikat juftliklar"""
    conn = db(); c = conn.cursor()
    c.execute("SELECT id,name,phone FROM customers")
    rows = c.fetchall(); conn.close()
    juft = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            na, nb = norm_ism(a[1]), norm_ism(b[1])
            tel = (a[2] or '').replace(' ', '') and (a[2] or '').replace(' ', '') == (b[2] or '').replace(' ', '')
            if tel or na.startswith(nb + ' ') or nb.startswith(na + ' '):
                juft.append({'a': a[1], 'b': b[1], 'sabab': 'telefon' if tel else 'ism'})
    return juft


# ── Mijoz kartasi ─────────────────────────────────────────────────
def mijoz_karta(kim):
    cid = kim if isinstance(kim, int) else mijoz_id(kim)
    if not cid: return None
    conn = db(); c = conn.cursor()
    c.execute("SELECT id,name,phone,type,total_purchases,notes,created,last_purchase,"
              "COALESCE(channel,''),COALESCE(last_contact,''),COALESCE(chat_id,0) "
              "FROM customers WHERE id=?", (cid,))
    r = c.fetchone()
    if not r:
        conn.close(); return None
    c.execute("SELECT date,product,qty,revenue,profit FROM sales "
              "WHERE customer_id=? AND reversed=0 ORDER BY date DESC", (cid,))
    sot = [{'sana': x[0], 'mahsulot': x[1], 'dona': x[2], 'summa': x[3], 'foyda': x[4]}
           for x in c.fetchall()]
    c.execute("SELECT id,date,amount,type,note FROM debts WHERE customer_id=? AND paid=0 ORDER BY date", (cid,))
    qarz = [{'id': x[0], 'sana': x[1], 'summa': x[2], 'turi': debt_turi(x[3]) or x[3], 'izoh': x[4]} for x in c.fetchall()]
    c.execute("SELECT sana,turi,matn FROM customer_log WHERE customer_id=? ORDER BY id DESC LIMIT 6", (cid,))
    log = [{'sana': x[0], 'turi': x[1], 'matn': x[2]} for x in c.fetchall()]
    c.execute("SELECT product,last_date,cycle_days FROM reorder WHERE customer_id=? AND active=1", (cid,))
    qayta = []
    for pr, ld, cyc in c.fetchall():
        try: otgan = (datetime.now() - datetime.strptime(ld, '%Y-%m-%d')).days
        except Exception: otgan = 0
        qayta.append({'mahsulot': pr, 'oxirgi': ld, 'sikl': cyc, 'otgan': otgan,
                      'muddati_keldi': otgan >= (cyc or 30)})
    obuna = None; chid = r[10]
    if chid:
        c.execute("SELECT active FROM subscribers WHERE chat_id=?", (chid,))
        x = c.fetchone()
        if x: obuna = bool(x[0])
    else:
        # chat_id qo'yilmagan bo'lsa ism bo'yicha topishga urinish
        c.execute("SELECT chat_id, name, active FROM subscribers WHERE chat_id NOT IN "
                  "(SELECT COALESCE(chat_id,0) FROM customers WHERE COALESCE(chat_id,0)>0)")
        subs = c.fetchall(); n_ = norm_ism(r[1])
        mos = [s for s in subs if norm_ism(s[1]) == n_]
        if len(mos) != 1:
            mos = [s for s in subs if norm_ism(s[1]) and
                   (n_.startswith(norm_ism(s[1]) + ' ') or norm_ism(s[1]).startswith(n_ + ' '))]
        if len(mos) == 1:
            chid = mos[0][0]; obuna = bool(mos[0][2])
    conn.close()

    bizga = sum(q['summa'] for q in qarz if q['turi'] == DEBITOR)
    bizdan = sum(q['summa'] for q in qarz if q['turi'] == KREDITOR)
    kunlar = None
    if len(sot) >= 2:
        try:
            s1 = datetime.strptime(sot[0]['sana'], '%Y-%m-%d')
            s2 = datetime.strptime(sot[-1]['sana'], '%Y-%m-%d')
            kunlar = round((s1 - s2).days / max(1, len(sot) - 1))
        except Exception: pass
    return {
        'id': r[0], 'nom': r[1], 'tel': r[2] or '', 'tur': r[3] or 'B2C',
        'izoh': r[5] or '', 'royxatga': r[6] or '', 'oxirgi_xarid': r[7] or '',
        'kanal': r[8] or '', 'oxirgi_aloqa': r[9] or '', 'chat_id': chid or 0,
        'obuna': obuna, 'sotuvlar': sot, 'sotuv_soni': len(sot),
        'jami_tushum': sum(x['summa'] for x in sot),
        'jami_foyda': sum(x['foyda'] for x in sot),
        'ortacha_chek': round(sum(x['summa'] for x in sot) / len(sot), 2) if sot else 0,
        'xarid_oraligi_kun': kunlar,
        'qarzlar': qarz, 'bizga_qarzdor': bizga, 'biz_qarzdormiz': bizdan,
        'qayta_buyurtma': qayta, 'tarix': log}


# ── Kanal hisoboti ────────────────────────────────────────────────
def kanal_hisobot(davr=''):
    conn = db(); c = conn.cursor()
    c.execute("""SELECT CASE WHEN COALESCE(s.customer_id,0)=0 THEN 'mijozsiz'
                             ELSE COALESCE(NULLIF(TRIM(LOWER(cu.channel)),''),'nomalum') END AS k,
                        COUNT(DISTINCT s.customer_id), COUNT(*),
                        COALESCE(SUM(s.revenue),0), COALESCE(SUM(s.profit),0)
                 FROM sales s LEFT JOIN customers cu ON cu.id=s.customer_id
                 WHERE s.reversed=0 AND s.date LIKE ?
                 GROUP BY k ORDER BY 5 DESC""", ((davr or '') + '%',))
    rows = c.fetchall(); conn.close()
    jami_f = sum(r[4] for r in rows) or 1
    return [{'kanal': r[0], 'mijoz': r[1], 'sotuv': r[2], 'tushum': r[3], 'foyda': r[4],
             'ulush_pct': round(r[4] / jami_f * 100, 1)} for r in rows]


def kanal_belgila(name, kanal):
    cid = mijoz_id(name)
    if not cid: return {'error': f"Mijoz topilmadi: {name}"}
    k = (kanal or '').lower().strip()
    if k not in KANALLAR:
        return {'error': f"Kanal noto'g'ri. Mumkin: {', '.join(KANALLAR)}"}
    conn = db(); c = conn.cursor()
    c.execute("UPDATE customers SET channel=? WHERE id=?", (k, cid))
    conn.commit(); conn.close()
    return {'ok': True, 'mijoz': name, 'kanal': k}


# ── Qayta buyurtma ────────────────────────────────────────────────
def reorder_yangila(cid, pname, sana=None):
    """Sotuvdan keyin chaqiriladi. Mahsulotda reorder_days>0 bo'lsa kuzatuvga oladi."""
    if not cid or not pname: return
    sana = sana or today()
    conn = db(); c = conn.cursor()
    c.execute("SELECT COALESCE(reorder_days,0) FROM products WHERE name=?", (pname,))
    r = c.fetchone()
    kun = (r[0] or 0) if r else 0
    if kun <= 0:
        conn.close(); return
    c.execute("SELECT id,last_date FROM reorder WHERE customer_id=? AND product=?", (cid, pname))
    row = c.fetchone()
    if row:
        oq = 0
        try:
            oq = (datetime.strptime(sana, '%Y-%m-%d') - datetime.strptime(row[1], '%Y-%m-%d')).days
        except Exception: pass
        sikl = oq if 5 <= oq <= 365 else kun
        c.execute("UPDATE reorder SET last_date=?, cycle_days=?, active=1, last_remind='' WHERE id=?",
                  (sana, sikl, row[0]))
    else:
        c.execute("INSERT INTO reorder (customer_id,product,last_date,cycle_days) VALUES (?,?,?,?)",
                  (cid, pname, sana, kun))
    conn.commit(); conn.close()


def qayta_buyurtma(oldindan=3):
    """Muddati kelgan (yoki oldindan N kun qolgan) qayta buyurtmalar"""
    conn = db(); c = conn.cursor()
    c.execute("""SELECT r.id,r.customer_id,cu.name,cu.phone,COALESCE(cu.chat_id,0),
                        r.product,r.last_date,r.cycle_days,COALESCE(r.last_remind,'')
                 FROM reorder r JOIN customers cu ON cu.id=r.customer_id
                 WHERE r.active=1""")
    rows = c.fetchall(); conn.close()
    bugun = datetime.now(); out = []
    for rid, cid, nm, ph, chid, pr, ld, cyc, lr in rows:
        try: otgan = (bugun - datetime.strptime(ld, '%Y-%m-%d')).days
        except Exception: continue
        sikl = cyc or 30
        if otgan >= sikl - oldindan:
            out.append({'id': rid, 'customer_id': cid, 'mijoz': nm, 'tel': ph or '',
                        'chat_id': chid, 'mahsulot': pr, 'oxirgi': ld, 'otgan': otgan,
                        'sikl': sikl, 'kechikkan': otgan - sikl, 'eslatilgan': lr})
    out.sort(key=lambda x: -x['kechikkan'])
    return out


def reorder_eslatildi(rid):
    conn = db(); c = conn.cursor()
    c.execute("UPDATE reorder SET last_remind=? WHERE id=?", (today(), rid))
    conn.commit(); conn.close()


def reorder_ochir(name, product):
    cid = mijoz_id(name)
    if not cid: return {'error': f"Mijoz topilmadi: {name}"}
    conn = db(); c = conn.cursor()
    c.execute("UPDATE reorder SET active=0 WHERE customer_id=? AND product LIKE ?", (cid, f'%{product}%'))
    n = c.rowcount; conn.commit(); conn.close()
    return {'ok': True, 'ochirildi': n}


def rasxodnik_belgila(pname, kun):
    p = find_product(pname)
    if not p: return {'error': f"Mahsulot topilmadi: {pname}"}
    conn = db(); c = conn.cursor()
    c.execute("UPDATE products SET reorder_days=? WHERE id=?", (int(kun), p['id']))
    conn.commit(); conn.close()
    return {'ok': True, 'mahsulot': p['name'], 'sikl_kun': int(kun)}


def rasxodniklar():
    conn = db(); c = conn.cursor()
    c.execute("SELECT name, reorder_days FROM products WHERE COALESCE(reorder_days,0)>0 ORDER BY name")
    r = c.fetchall(); conn.close()
    return [{'mahsulot': x[0], 'sikl_kun': x[1]} for x in r]

# ══════════════════════════════════════════════════════════════════
# DASHBOARD — bitta ekranda butun biznes (HTML fayl)
# ══════════════════════════════════════════════════════════════════
OY_NOM = ['Yan','Fev','Mar','Apr','May','Iyn','Iyl','Avg','Sen','Okt','Noy','Dek']

def _dash_data():
    """Dashboard uchun barcha ma'lumotni bazadan yig'adi"""
    yil = datetime.now().strftime('%Y')
    conn = db(); c = conn.cursor()

    c.execute("""SELECT substr(date,1,7) AS oy, SUM(revenue), SUM(profit), COUNT(*)
                 FROM sales WHERE date LIKE ? AND reversed=0
                 GROUP BY oy ORDER BY oy""", (yil + '%',))
    oylik = {r[0]: (r[1] or 0, r[2] or 0, r[3]) for r in c.fetchall()}

    c.execute("""SELECT substr(date,1,7) AS oy, SUM(amount) FROM expenses
                 WHERE date LIKE ? AND reversed=0 GROUP BY oy""", (yil + '%',))
    xar_oy = {r[0]: (r[1] or 0) for r in c.fetchall()}

    c.execute("""SELECT date,product,qty,revenue,profit FROM sales
                 WHERE date LIKE ? AND reversed=0 ORDER BY date DESC""", (this_month() + '%',))
    bu_oy_sotuv = c.fetchall()

    c.execute("""SELECT category,SUM(amount) FROM expenses
                 WHERE date LIKE ? AND reversed=0 GROUP BY category ORDER BY SUM(amount) DESC""",
              (this_month() + '%',))
    bu_oy_xar = c.fetchall()

    c.execute("SELECT COALESCE(SUM(remaining),0) FROM transit WHERE remaining>0")
    qarz = c.fetchone()[0] or 0

    c.execute("""SELECT product, MIN(their_price) FROM competitors
                 WHERE date>=? GROUP BY product""",
              ((datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'),))
    raq = {r[0]: r[1] for r in c.fetchall() if r[1]}
    conn.close()

    return {'yil': yil, 'oylik': oylik, 'xar_oy': xar_oy,
            'bu_oy_sotuv': bu_oy_sotuv, 'bu_oy_xar': bu_oy_xar,
            'qarz': qarz, 'raq': raq,
            'prods': get_products(), 'kassa': get_cash_balance(),
            'nelikvid': get_nelikvid(60), 'rate': get_exchange_rate()}


def _bar(x, y, w, h, r=4):
    """Yuqori burchaklari yumaloq ustun (asosga bog'langan)"""
    if h <= 0: return ''
    r = min(r, w / 2, h)
    return (f'M{x:.1f},{y+h:.1f} V{y+r:.1f} Q{x:.1f},{y:.1f} {x+r:.1f},{y:.1f} '
            f'H{x+w-r:.1f} Q{x+w:.1f},{y:.1f} {x+w:.1f},{y+r:.1f} V{y+h:.1f} Z')


def _chart(oylik, xar_oy, yil):
    """Oylik tushum va foyda — guruhlangan ustunlar"""
    oylar = [f"{yil}-{m:02d}" for m in range(1, 13)]
    oylar = [o for o in oylar if o in oylik] or oylar[:1]
    tush = [oylik.get(o, (0, 0, 0))[0] for o in oylar]
    foyd = [oylik.get(o, (0, 0, 0))[1] for o in oylar]
    cap = max(tush + foyd + [1])

    # o'lchamlar
    W, H = 360, 190
    L, R, T, B = 36, 8, 12, 30
    pw, ph = W - L - R, H - T - B
    n = len(oylar)
    gw = pw / n
    bw = min(13.0, (gw - 8) / 2)
    gap = 2

    # y-o'qi
    def nice(v):
        import math
        e = 10 ** math.floor(math.log10(v)) if v > 0 else 1
        for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
            if v <= e * m: return e * m
        return e * 10
    ymax = nice(cap)
    svg = []
    for i in range(5):
        v = ymax * i / 4
        y = T + ph - (v / ymax) * ph
        svg.append(f'<line class="grid-l" x1="{L}" y1="{y:.1f}" x2="{W-R}" y2="{y:.1f}"/>')
        svg.append(f'<text class="ax" x="{L-6}" y="{y+3:.1f}" text-anchor="end">'
                   f'{"0" if v == 0 else f"{v/1000:.1f}k" if v >= 1000 else f"{v:.0f}"}</text>')

    hits = []
    for i, o in enumerate(oylar):
        cx = L + gw * i + gw / 2
        x1 = cx - bw - gap / 2
        x2 = cx + gap / 2
        h1 = (tush[i] / ymax) * ph
        h2 = (foyd[i] / ymax) * ph
        svg.append(f'<path class="s1" d="{_bar(x1, T+ph-h1, bw, h1)}"/>')
        svg.append(f'<path class="s2" d="{_bar(x2, T+ph-h2, bw, h2)}"/>')
        oy_i = int(o.split('-')[1]) - 1
        svg.append(f'<text class="ax" x="{cx:.1f}" y="{T+ph+14}" text-anchor="middle">{OY_NOM[oy_i]}</text>')
        hits.append(f'<rect class="hit" x="{L+gw*i:.1f}" y="{T}" width="{gw:.1f}" height="{ph}" '
                    f'data-oy="{OY_NOM[oy_i]}" data-t="{tush[i]:.0f}" data-f="{foyd[i]:.0f}"/>')

    # eng baland ustunga to'g'ridan yorliq
    if tush:
        bi = tush.index(max(tush))
        cx = L + gw * bi + gw / 2 - bw / 2 - gap / 2
        y = T + ph - (tush[bi] / ymax) * ph
        svg.append(f'<text class="lbl" x="{cx+bw/2:.1f}" y="{y-5:.1f}" text-anchor="middle">${tush[bi]:,.0f}</text>')

    svg.append(f'<line class="axis" x1="{L}" y1="{T+ph}" x2="{W-R}" y2="{T+ph}"/>')
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
            f'aria-label="Oylik tushum va foyda">{"".join(svg)}{"".join(hits)}</svg>')


def build_dashboard(path):
    """Dashboard HTML faylini yaratadi"""
    d = _dash_data()
    rate = d['rate']
    prods = d['prods']
    tovar = sum(p['qty'] * p['cost'] for p in prods)
    bu_oy = d['oylik'].get(this_month(), (0, 0, 0))
    bu_xar = d['xar_oy'].get(this_month(), 0)
    sof = bu_oy[1] - bu_xar
    yil_tush = sum(v[0] for v in d['oylik'].values())
    yil_foyd = sum(v[1] for v in d['oylik'].values())

    def uzs(v): return f"{v*rate:,.0f} so'm"
    def esc(s): return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

    # ── KPI plitkalari ──
    kpi = [
        ('Kassa', f"${d['kassa']:,.0f}", uzs(d['kassa']), 'good' if d['kassa'] > 0 else 'critical'),
        ('Tovar qoldig‘i', f"${tovar:,.0f}", f"{sum(p['qty'] for p in prods)} dona", ''),
        ('Zavod qarzi', f"${d['qarz']:,.0f}", 'to‘langan' if d['qarz'] == 0 else 'ochiq', 'good' if d['qarz'] == 0 else 'warning'),
        ('Bu oy sof foyda', f"${sof:,.0f}", f"tushum ${bu_oy[0]:,.0f}", 'good' if sof > 0 else 'critical'),
    ]
    kpi_html = ''.join(
        f'<div class="tile"><div class="k">{esc(k)}</div>'
        f'<div class="v {st}">{esc(v)}</div><div class="sub">{esc(s)}</div></div>'
        for k, v, s, st in kpi)

    # ── Astatka ──
    def blok(sup, nom):
        ps = sorted([p for p in prods if p['sup'] == sup], key=lambda x: -x['qty'] * x['cost'])
        if not ps: return ''
        bor = [p for p in ps if p['qty'] > 0]
        qm = sum(p['qty'] * p['cost'] for p in ps)
        rows = ''
        for p in bor:
            st = 'critical' if p['qty'] == 0 else 'warning' if p['qty'] == 1 else 'good'
            mr = p['price'] - p['cost']
            rq = d['raq'].get(p['name'])
            raq_s = ''
            if rq and p['price'] > rq:
                raq_s = f'<span class="tag warn">bozor ${rq:,.0f}</span>'
            rows += (f'<tr><td><span class="dot {st}"></span>{esc(p["name"])}{raq_s}</td>'
                     f'<td class="num">{p["qty"]}</td>'
                     f'<td class="num">${p["price"]:,.0f}</td>'
                     f'<td class="num muted">+${mr:,.0f}</td></tr>')
        yoq = [p['name'] for p in ps if p['qty'] == 0]
        foot = (f'<div class="sub pad">Tugagan: {esc(", ".join(yoq))}</div>' if yoq else '')
        return (f'<h3>{esc(nom)} <span class="sub">{sum(p["qty"] for p in bor)} dona · ${qm:,.0f}</span></h3>'
                f'<table><thead><tr><th>Mahsulot</th><th class="num">Soni</th>'
                f'<th class="num">Narx</th><th class="num">Marja</th></tr></thead>'
                f'<tbody>{rows}</tbody></table>{foot}')

    astatka = blok('Two Trees', '\U0001F535 Two Trees') + blok('Freesub', '\U0001F7E0 Freesub')

    # ── Bu oy sotuvlar ──
    if d['bu_oy_sotuv']:
        sot = ''.join(f'<tr><td>{esc(r[0][5:])}</td><td>{esc(r[1])}</td>'
                      f'<td class="num">{r[2]}</td><td class="num">${r[3]:,.0f}</td>'
                      f'<td class="num good">+${r[4]:,.0f}</td></tr>' for r in d['bu_oy_sotuv'])
        sotuv_html = (f'<table><thead><tr><th>Sana</th><th>Mahsulot</th><th class="num">Soni</th>'
                      f'<th class="num">Summa</th><th class="num">Foyda</th></tr></thead>'
                      f'<tbody>{sot}</tbody></table>')
    else:
        sotuv_html = '<div class="bosh">Bu oy hali sotuv yo‘q</div>'

    # ── Xarajatlar ──
    if d['bu_oy_xar']:
        xr = ''.join(f'<tr><td>{esc(r[0])}</td><td class="num">${r[1]:,.0f}</td></tr>'
                     for r in d['bu_oy_xar'])
        xar_html = (f'<table><tbody>{xr}'
                    f'<tr class="jami"><td>Jami</td><td class="num">${bu_xar:,.0f}</td></tr>'
                    f'</tbody></table>')
    else:
        xar_html = '<div class="bosh">Bu oy xarajat yo‘q</div>'

    # ── Nelikvid ──
    nl = d['nelikvid']
    if nl:
        muz = sum(x['qty'] * x['cost'] for x in nl)
        nl_rows = ''.join(f'<tr><td>{esc(x["name"])}</td><td class="num">{x["qty"]}</td>'
                          f'<td class="num muted">{str(x["days_since"]) + " kun" if x["days_since"] < 900 else "hech sotilmagan"}</td></tr>'
                          for x in nl[:12])
        nel_html = (f'<div class="sub pad">Muzlatilgan kapital: <b>${muz:,.0f}</b></div>'
                    f'<table><thead><tr><th>Mahsulot</th><th class="num">Soni</th>'
                    f'<th class="num">Sotilmagan</th></tr></thead><tbody>{nl_rows}</tbody></table>')
    else:
        nel_html = '<div class="bosh">Nelikvid yo‘q — hammasi harakatda</div>'

    # ── Grafik jadvali (kirish imkoniyati) ──
    oy_rows = ''
    for o in sorted(d['oylik'].keys()):
        t, f_, n = d['oylik'][o]
        oy_rows += (f'<tr><td>{OY_NOM[int(o.split("-")[1])-1]}</td>'
                    f'<td class="num">{n}</td><td class="num">${t:,.0f}</td>'
                    f'<td class="num">${f_:,.0f}</td></tr>')

    html = _DASH_TPL
    for k, v in {
        '{{SANA}}': datetime.now().strftime('%d.%m.%Y %H:%M'),
        '{{RATE}}': f"{rate:,.0f}",
        '{{KPI}}': kpi_html,
        '{{CHART}}': _chart(d['oylik'], d['xar_oy'], d['yil']),
        '{{YIL}}': d['yil'],
        '{{YILTUSH}}': f"{yil_tush:,.0f}",
        '{{YILFOYD}}': f"{yil_foyd:,.0f}",
        '{{OYROWS}}': oy_rows,
        '{{ASTATKA}}': astatka,
        '{{SOTUV}}': sotuv_html,
        '{{XARAJAT}}': xar_html,
        '{{NELIKVID}}': nel_html,
    }.items():
        html = html.replace(k, v)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return path


async def cmd_dashboard(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/dashboard — biznes holatini bitta HTML faylda yuboradi"""
    if not can(u, 'boshqaruv'): return
    await u.message.reply_text("⏳ Dashboard tayyorlanmoqda...")
    try:
        p = f"/tmp/ThermoCrafts_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
        await asyncio.to_thread(build_dashboard, p)
        with open(p, 'rb') as f:
            await ctx.bot.send_document(
                chat_id=u.effective_chat.id, document=f,
                filename=f"ThermoCrafts_{datetime.now().strftime('%d.%m.%Y')}.html",
                caption="\U0001F4CA Biznes holati — faylni bosib brauzerda oching")
        try: os.remove(p)
        except Exception: pass
    except Exception as e:
        log.exception("dashboard")
        await u.message.reply_text(f"⚠️ Xato: {str(e)[:250]}")




# ── HUJJAT (hisob-faktura / chek) ─────────────────────────────────
FIRMA = {
    'nom': os.getenv('FIRMA_NOM', 'ThermoCrafts'),
    'manzil': os.getenv('FIRMA_MANZIL', "Yunusobod tumani, Toshkent"),
    'tel': os.getenv('FIRMA_TEL', ''),
    'stir': os.getenv('FIRMA_STIR', ''),
    'hisob': os.getenv('FIRMA_HISOB', ''),
}

def _lat(s):
    """PDF uchun matnni latin-1 ga moslashtiradi"""
    s = str(s)
    for a, b in (('ʻ', "'"), ('ʼ', "'"), ('‘', "'"), ('’', "'"),
                 ('—', '-'), ('–', '-'), ('…', '...')):
        s = s.replace(a, b)
    return s.encode('latin-1', 'replace').decode('latin-1')

def keyingi_raqam(turi):
    conn = db(); c = conn.cursor()
    yil = datetime.now().strftime('%Y')
    c.execute("SELECT COUNT(*) FROM documents WHERE turi=? AND sana LIKE ?", (turi, yil + '%'))
    n = c.fetchone()[0] + 1; conn.close()
    pref = {'faktura': 'HF', 'chek': 'CH', 'dalolatnoma': 'SD'}.get(turi, 'DOC')
    return f"{pref}-{yil}-{n:04d}"

def hujjat_yoz(raqam, turi, mijoz, summa, sale_id=None, izoh=''):
    conn = db(); c = conn.cursor()
    c.execute("INSERT INTO documents (raqam,turi,sana,mijoz,summa,sale_id,izoh) VALUES (?,?,?,?,?,?,?)",
              (raqam, turi, today(), mijoz, summa, sale_id, izoh))
    conn.commit(); conn.close()

def build_hujjat(path, turi, mijoz, qatorlar, izoh=''):
    """qatorlar: [(nom, soni, narx)]  -> PDF yoki HTML fayl yaratadi"""
    raqam = keyingi_raqam(turi)
    rate = get_exchange_rate()
    jami = sum(q * n for _, q, n in qatorlar)
    sarlavha = ('HISOB-FAKTURA' if turi == 'faktura' else
                'SOLISHTIRISH DALOLATNOMASI' if turi == 'dalolatnoma' else 'CHEK')
    try:
        from fpdf import FPDF
    except ImportError:
        p2 = path.rsplit('.', 1)[0] + '.html'
        _hujjat_html(p2, raqam, sarlavha, mijoz, qatorlar, jami, rate, izoh)
        hujjat_yoz(raqam, turi, mijoz, jami, None, izoh)
        return p2, raqam, jami, False

    pdf = FPDF(); pdf.add_page(); pdf.set_auto_page_break(True, 18)
    pdf.set_font('helvetica', 'B', 17)
    pdf.cell(0, 9, _lat(FIRMA['nom']), ln=1)
    pdf.set_font('helvetica', '', 9)
    for k in ('manzil', 'tel', 'stir', 'hisob'):
        if FIRMA[k]:
            yor = {'manzil': '', 'tel': 'Tel: ', 'stir': 'STIR: ', 'hisob': 'H/r: '}[k]
            pdf.cell(0, 4.6, _lat(yor + FIRMA[k]), ln=1)
    pdf.ln(4)
    pdf.set_draw_color(200, 200, 200); pdf.set_line_width(0.3)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(5)

    pdf.set_font('helvetica', 'B', 13)
    pdf.cell(0, 7, _lat(f"{sarlavha}  {raqam}"), ln=1)
    pdf.set_font('helvetica', '', 10)
    pdf.cell(0, 5.5, _lat(f"Sana: {datetime.now().strftime('%d.%m.%Y')}"), ln=1)
    if mijoz: pdf.cell(0, 5.5, _lat(f"Mijoz: {mijoz}"), ln=1)
    pdf.ln(4)

    w = (95, 20, 35, 35)
    pdf.set_font('helvetica', 'B', 9); pdf.set_fill_color(240, 240, 238)
    for t, wd, al in zip(('Mahsulot', 'Soni', 'Narx', 'Summa'), w, 'LCRR'):
        pdf.cell(wd, 8, _lat(t), border='B', align=al, fill=True)
    pdf.ln()
    pdf.set_font('helvetica', '', 9.5)
    for nom, soni, narx in qatorlar:
        pdf.cell(w[0], 7.5, _lat(nom)[:52], border='B')
        pdf.cell(w[1], 7.5, str(soni), border='B', align='C')
        pdf.cell(w[2], 7.5, f"${narx:,.2f}", border='B', align='R')
        pdf.cell(w[3], 7.5, f"${soni*narx:,.2f}", border='B', align='R')
        pdf.ln()
    pdf.set_font('helvetica', 'B', 11)
    pdf.cell(w[0] + w[1] + w[2], 10, _lat('JAMI'), align='R')
    pdf.cell(w[3], 10, f"${jami:,.2f}", align='R'); pdf.ln()
    pdf.set_font('helvetica', '', 9)
    pdf.cell(0, 5.5, _lat(f"({jami*rate:,.0f} so'm,  kurs 1 USD = {rate:,.0f})"), align='R', ln=1)

    if izoh:
        pdf.ln(4); pdf.set_font('helvetica', '', 9)
        pdf.multi_cell(0, 5, _lat(izoh))
    pdf.ln(12)
    pdf.set_font('helvetica', '', 9)
    pdf.cell(95, 6, _lat('Topshirdi: ____________________'))
    pdf.cell(95, 6, _lat('Qabul qildi: ____________________'), ln=1)
    pdf.output(path)
    hujjat_yoz(raqam, turi, mijoz, jami, None, izoh)
    return path, raqam, jami, True


def _hujjat_html(path, raqam, sarlavha, mijoz, qatorlar, jami, rate, izoh):
    # Mijoz/mahsulot nomidagi < > & belgilar HTML'ni buzmasin
    def e(v): return _html.escape(str(v or ''))
    mijoz, izoh = e(mijoz), e(izoh)
    rek = ''.join(f'<div>{e(v)}</div>' for k, v in FIRMA.items() if v and k != 'nom')
    rows = ''.join(
        f'<tr><td>{e(n)}</td><td class=c>{q}</td><td class=r>${p:,.2f}</td>'
        f'<td class=r>${q*p:,.2f}</td></tr>' for n, q, p in qatorlar)
    html = f"""<!DOCTYPE html><html lang=uz><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{raqam}</title><style>
body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:720px;margin:0 auto;padding:28px 18px;color:#111}}
h1{{font-size:20px;margin:0 0 3px}} .rek{{color:#555;font-size:12px}}
hr{{border:0;border-top:1px solid #ddd;margin:16px 0}}
h2{{font-size:16px;margin:0 0 6px}} .meta{{color:#555;font-size:13px;margin-bottom:14px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;background:#f4f4f2;padding:8px 6px;border-bottom:1px solid #ddd;font-size:11px;
text-transform:uppercase;letter-spacing:.04em}}
td{{padding:8px 6px;border-bottom:1px solid #eee}} .c{{text-align:center}} .r{{text-align:right}}
.jami td{{font-weight:700;font-size:15px;border-top:2px solid #333;border-bottom:0}}
.uzs{{text-align:right;color:#555;font-size:12px;margin-top:4px}}
.imzo{{display:flex;justify-content:space-between;margin-top:46px;color:#555;font-size:13px}}
@media print{{body{{padding:0}}}}
</style></head><body>
<h1>{e(FIRMA['nom'])}</h1><div class=rek>{rek}</div><hr>
<h2>{sarlavha} &nbsp;{raqam}</h2>
<div class=meta>Sana: {datetime.now().strftime('%d.%m.%Y')}{f'<br>Mijoz: {mijoz}' if mijoz else ''}</div>
<table><thead><tr><th>Mahsulot</th><th class=c>Soni</th><th class=r>Narx</th><th class=r>Summa</th></tr></thead>
<tbody>{rows}<tr class=jami><td colspan=3 class=r>JAMI</td><td class=r>${jami:,.2f}</td></tr></tbody></table>
<div class=uzs>({jami*rate:,.0f} so'm, kurs 1 USD = {rate:,.0f})</div>
{f'<p>{izoh}</p>' if izoh else ''}
<div class=imzo><span>Topshirdi: ____________</span><span>Qabul qildi: ____________</span></div>
</body></html>"""
    with open(path, 'w', encoding='utf-8') as f: f.write(html)


# ── BUYRUQLAR ─────────────────────────────────────────────────────
async def cmd_moliya(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/moliya [YYYY-MM|yil] — P&L, balans, cash flow"""
    if not can(u, 'boshqaruv'): return
    a = (ctx.args or [])
    davr = a[0] if a else this_month()
    if davr.lower() in ('yil', 'year'): davr = datetime.now().strftime('%Y')
    pl = pl_hisobot(davr); bl = balans(); cf = cash_flow(davr)
    yopiq = ' \U0001F512' if is_closed(davr + '-01') else ''

    t = f"\U0001F4C8 MOLIYAVIY HISOBOT — {davr}{yopiq}\n\n"
    t += "── DAROMAD VA XARAJATLAR ──\n"
    t += f"Tushum               {fmt(pl['tushum'])}\n"
    t += f"Tovar tannarxi      -{fmt(pl['cogs'])}\n"
    if pl['togri_xarajat']:
        t += f"Bank + dostavka     -{fmt(pl['togri_xarajat'])}\n"
    t += "────────────────────\n"
    t += f"Yalpi foyda          {fmt(pl['yalpi_foyda'])}  ({pl['marja_pct']}%)\n\n"
    if pl['davr_tafsil']:
        t += "Davr xarajatlari:\n"
        for k, v in sorted(pl['davr_tafsil'].items(), key=lambda x: -x[1]):
            t += f"  {k:<16} -{fmt(v)}\n"
        t += f"  {'jami':<16} -{fmt(pl['davr_xarajat'])}\n\n"
    t += f"✅ SOF FOYDA          {fmt(pl['sof_foyda'])}  ({pl['sof_pct']}%)\n"
    t += f"   {pl['sotuv_soni']} ta sotuv · {pl['dona']} dona\n" + (f"   ↩️ qaytarish: −{fmt(pl['qaytarish'])}\n" if pl.get('qaytarish') else "") + "\n"

    t += "── BALANS ──\n"
    t += "AKTIV\n"
    t += f"  Kassa              {fmt(bl['naqd'])}\n"
    t += f"  Tovar (sebest)     {fmt(bl['tovar'])}\n"
    if bl['debitor']: t += f"  Debitorlik         {fmt(bl['debitor'])}  (mijozlar bizga qarz)\n"
    if bl['yolda']:   t += f"  Yo'ldagi tovar     {fmt(bl['yolda'])}  (tannarxda)\n"
    t += f"  Jami aktiv         {fmt(bl['aktiv'])}\n\n"
    t += "PASSIV\n"
    if bl['zavod_qarzi']: t += f"  Kreditorlik—zavod  {fmt(bl['zavod_qarzi'])}  (biz zavodga qarzmiz)\n"
    if bl['kreditor']:    t += f"  Kreditorlik—boshqa {fmt(bl['kreditor'])}\n"
    t += f"  Jami passiv        {fmt(bl['passiv'])}\n\n"
    t += f"\U0001F4B0 SOF KAPITAL        {fmt(bl['kapital'])}\n\n"

    t += "── PUL OQIMI ──\n"
    t += f"Boshida              {fmt(cf['boshi'])}\n"
    t += f"Kirim               +{fmt(cf['jami_kirim'])}\n"
    t += f"Chiqim              -{fmt(cf['jami_chiqim'])}\n"
    t += f"Oxirida              {fmt(cf['oxiri'])}\n"
    await u.message.reply_text(t)


async def cmd_qarz_yosh(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/qarz_yosh — qarzdorlik yoshi bo'yicha"""
    if not can(u, 'boshqaruv'): return
    q = qarz_yoshi()
    def blok(g, sarlavha, emoji):
        jami = sum(x['summa'] for b in g.values() for x in b)
        if jami == 0: return ''
        s = f"{emoji} {sarlavha}: {fmt(jami)}\n"
        for b in ('0-30', '31-60', '61-90', '90+'):
            if not g[b]: continue
            bs = sum(x['summa'] for x in g[b])
            mark = '\U0001F7E2' if b == '0-30' else '\U0001F7E1' if b == '31-60' else '\U0001F534'
            s += f"  {mark} {b} kun: {fmt(bs)}\n"
            for x in sorted(g[b], key=lambda y: -y['kun'])[:6]:
                s += f"     • {x['kim']} — {fmt(x['summa'])} ({x['kun']} kun)\n"
        return s + "\n"
    t = "\U0001F4CB QARZDORLIK YOSHI\n\n"
    t += blok(q['bizga_qarzdor'], "Debitorlik — mijozlar bizga qarz", "\U0001F4E5")
    t += blok(q['zavod'], "Kreditorlik — biz zavodga qarzmiz", "\U0001F3ED")
    t += blok(q['biz_qarzdormiz'], "Kreditorlik — boshqa (biz qarzmiz)", "\U0001F4E4")
    if q['jami_debitor'] == 0 and q['jami_kreditor'] == 0:
        t += "Ochiq qarz yo'q — hammasi toza."
    else:
        t += "────────────────\n"
        t += f"Debitorlik {fmt(q['jami_debitor'])} · Kreditorlik {fmt(q['jami_kreditor'])}\n"
        t += f"Sof: {fmt(q['jami_debitor'] - q['jami_kreditor'])}"
    await u.message.reply_text(t)


async def cmd_aylanish(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/aylanish — tovar aylanishi va band kapital"""
    if not can(u, 'boshqaruv'): return
    a = aylanish(90)
    t = "\U0001F504 TOVAR AYLANISHI (90 kun)\n\n"
    t += f"Band kapital: {fmt(a['jami_band_kapital'])}\n"
    t += f"Davr tannarxi: {fmt(a['davr_cogs'])}\n"
    t += f"Aylanish koeffitsienti: {a['aylanish_koef']}\n"
    if a['ortacha_zaxira_kun']:
        t += f"O'rtacha zaxira: {a['ortacha_zaxira_kun']} kun\n"
    t += "\n"
    guruh = {'tez': [], 'normal': [], 'sekin': [], 'harakatsiz': []}
    for x in a['mahsulotlar']:
        if x['qoldiq'] > 0: guruh[x['holat']].append(x)
    nom = {'tez': ('\U0001F7E2 Tez ketadi (<30 kun)', 'Qayta buyurtma kerak'),
           'normal': ('\U0001F535 Normal (30-90 kun)', ''),
           'sekin': ('\U0001F7E1 Sekin (>90 kun)', ''),
           'harakatsiz': ('\U0001F534 Harakatsiz', '90 kunda sotilmagan')}
    for k in ('tez', 'normal', 'sekin', 'harakatsiz'):
        if not guruh[k]: continue
        sarl, izoh = nom[k]
        band = sum(x['band_kapital'] for x in guruh[k])
        t += f"{sarl} — {fmt(band)}"
        t += f"  • {izoh}\n" if izoh else "\n"
        for x in sorted(guruh[k], key=lambda y: -y['band_kapital'])[:8]:
            zk = f"{x['zaxira_kun']} kun" if x['zaxira_kun'] is not None else "—"
            t += f"   {x['nom']}: {x['qoldiq']} ta · {fmt(x['band_kapital'])} · {zk}\n"
        t += "\n"
    await u.message.reply_text(t)


async def cmd_yop(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/yop YYYY-MM — oyni yopadi"""
    if not can(u, 'boshqaruv'): return
    a = ctx.args or []
    if not a:
        yop = closed_list()
        t = "\U0001F512 YOPILGAN DAVRLAR\n\n"
        t += ("\n".join(f"• {p} — {c}" for p, c in yop) if yop else "Yopilgan davr yo'q.")
        t += "\n\nYopish: /yop 2026-09\nOchish: /och 2026-09"
        await u.message.reply_text(t); return
    davr = a[0].strip()
    if not re.match(r'^\d{4}-\d{2}$', davr):
        await u.message.reply_text("Format: /yop 2026-09"); return
    if is_closed(davr + '-01'):
        await u.message.reply_text(f"{davr} allaqachon yopilgan."); return
    pl = pl_hisobot(davr)
    close_period(davr)
    await u.message.reply_text(
        f"\U0001F512 {davr} yopildi\n\n"
        f"Tushum: {fmt(pl['tushum'])}\nSof foyda: {fmt(pl['sof_foyda'])}\n\n"
        f"Bu oyga yangi yozuv kiritib bo'lmaydi.\nOchish: /och {davr}")


async def cmd_och(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    a = ctx.args or []
    if not a or not re.match(r'^\d{4}-\d{2}$', a[0].strip()):
        await u.message.reply_text("Format: /och 2026-09"); return
    ok = open_period(a[0].strip())
    await u.message.reply_text(f"\U0001F513 {a[0]} ochildi." if ok else f"{a[0]} yopilmagan edi.")


async def cmd_hujjat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/hujjat [faktura|chek] Mijoz | Mahsulot x soni"""
    if not can(u, 'boshqaruv'): return
    a = ctx.args or []
    if not a:
        await u.message.reply_text(
            "\U0001F4C4 Hujjat yaratish\n\n"
            "Oxirgi sotuv uchun:\n  /hujjat oxirgi\n\n"
            "Qo'lda:\n  /hujjat faktura Alisher | TTS 20 Pro x1\n\n"
            "Rekvizitlarni Railway Variables da sozlang:\n"
            "FIRMA_NOM, FIRMA_MANZIL, FIRMA_TEL, FIRMA_STIR, FIRMA_HISOB")
        return

    turi = 'faktura'
    matn = ' '.join(a)
    if a[0].lower() in ('faktura', 'chek'):
        turi = a[0].lower(); matn = ' '.join(a[1:])

    if matn.strip().lower() in ('oxirgi', 'last'):
        conn = db(); c = conn.cursor()
        c.execute("SELECT product,qty,revenue,customer FROM sales WHERE reversed=0 ORDER BY id DESC LIMIT 1")
        r = c.fetchone(); conn.close()
        if not r: await u.message.reply_text("Sotuv topilmadi."); return
        mijoz = r[3] or ''
        qatorlar = [(r[0], r[1], r[2] / max(1, r[1]))]
    else:
        qism = matn.split('|')
        mijoz = qism[0].strip()
        qatorlar = []
        for q in qism[1:]:
            q = q.strip()
            if not q: continue
            m = re.match(r'(.+?)\s*[xх\*]\s*(\d+)\s*$', q, re.I)
            nom, soni = (m.group(1).strip(), int(m.group(2))) if m else (q, 1)
            p = find_product(nom)
            if not p:
                await u.message.reply_text(f"Mahsulot topilmadi: {nom}"); return
            qatorlar.append((p['name'], soni, p['price']))
        if not qatorlar:
            await u.message.reply_text("Mahsulot ko'rsatilmagan.\nMisol: /hujjat faktura Alisher | TTS 20 Pro x1"); return

    await u.message.reply_text("⏳ Hujjat tayyorlanmoqda...")
    try:
        base = f"/tmp/doc_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        p, raqam, jami, is_pdf = await asyncio.to_thread(build_hujjat, base, turi, mijoz, qatorlar)
        with open(p, 'rb') as fh:
            await ctx.bot.send_document(
                chat_id=u.effective_chat.id, document=fh,
                filename=f"{raqam}.{'pdf' if is_pdf else 'html'}",
                caption=f"\U0001F4C4 {raqam} · {fmt(jami)}" +
                        ("" if is_pdf else "\n\n⚠️ PDF uchun /deps buyrug'ini bering"))
        try: os.remove(p)
        except Exception: pass
    except Exception as e:
        log.exception("hujjat")
        await u.message.reply_text(f"⚠️ Xato: {str(e)[:250]}")


async def cmd_deps(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/deps — PDF kutubxonasini GitHub requirements.txt ga qo'shadi"""
    if not can(u, 'system'): return
    if not GITHUB_TOKEN:
        await u.message.reply_text("GITHUB_TOKEN sozlanmagan."); return
    try:
        __import__('fpdf')   # faqat o'rnatilganini tekshirish
        await u.message.reply_text("✅ PDF kutubxonasi allaqachon o'rnatilgan."); return
    except ImportError:
        pass
    await u.message.reply_text("⏳ requirements.txt yangilanmoqda...")
    try:
        api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/requirements.txt"
        r = await asyncio.to_thread(requests.get, api, headers=_gh_headers(), timeout=20)
        if r.status_code != 200:
            await u.message.reply_text(f"requirements.txt topilmadi ({r.status_code})"); return
        j = r.json()
        cur = base64.b64decode(j['content']).decode('utf-8')
        if 'fpdf' in cur.lower():
            await u.message.reply_text("fpdf2 allaqachon ro'yxatda. Railway qayta deploy qiling."); return
        yangi = cur.rstrip() + "\nfpdf2>=2.7.0\n"
        r2 = await asyncio.to_thread(requests.put, api, headers=_gh_headers(), timeout=30, json={
            "message": "fpdf2 qo'shildi (PDF hujjatlar uchun)",
            "content": base64.b64encode(yangi.encode()).decode(), "sha": j['sha']})
        if r2.status_code in (200, 201):
            await u.message.reply_text(
                "✅ fpdf2 qo'shildi\n\U0001F680 Railway qayta deploy qilmoqda...\n"
                "⏳ 2-3 daqiqadan keyin /hujjat PDF beradi.")
        else:
            await u.message.reply_text(f"Xato: {r2.status_code}")
    except Exception as e:
        log.exception("deps")
        await u.message.reply_text(f"Xato: {str(e)[:200]}")



# ══════════════════════════════════════════════════════════════════
# MIJOZLAR — buyruqlar
# ══════════════════════════════════════════════════════════════════

def _md(s):
    for ch in ('*', '_', '`', '['):
        s = str(s).replace(ch, '')
    return s

_KAN_EMOJI = {'olx': '\U0001F4E6', 'instagram': '\U0001F4F8', 'telegram': '✈️',
              'tavsiya': '\U0001F91D', 'b2b': '\U0001F3E2', 'boshqa': '•',
              'nomalum': '❓', 'mijozsiz': '⚪'}


async def cmd_mijoz(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    q = ' '.join(ctx.args).strip() if ctx.args else ''
    if not q:
        await u.message.reply_text(
            "\U0001F464 *Mijoz kartasi*\n\n`/mijoz Alisher`\n\n"
            "Ro'yxat uchun — /mijozlar", parse_mode='Markdown')
        return
    k = mijoz_karta(q)
    if not k:
        top = mijoz_qidir(q)
        if not top:
            await u.message.reply_text(f"❌ Topilmadi: {_md(q)}")
            return
        if len(top) > 1:
            t = "\U0001F50D Bir nechta mijoz topildi:\n\n"
            t += "\n".join(f"• {_md(x['nom'])}" for x in top[:10])
            await u.message.reply_text(t)
            return
        k = mijoz_karta(top[0]['id'])

    tur = "\U0001F3E2 B2B" if k['tur'] == 'B2B' else "\U0001F464 B2C"
    t = f"*{_md(k['nom'])}*\n{tur}"
    if k['kanal']: t += f"  ·  {_KAN_EMOJI.get(k['kanal'], '')} {k['kanal']}"
    t += "\n"
    if k['tel']: t += f"\U0001F4DE `{k['tel']}`\n"
    if k['obuna'] is True: t += "✅ Botga obuna — xabar yuborish mumkin\n"
    elif k['chat_id']: t += "⚪ Botdan chiqib ketgan\n"
    t += "\n"

    t += (f"\U0001F4B0 *{k['sotuv_soni']} ta xarid · {fmt(k['jami_tushum'])}*\n"
          f"Foyda: {fmt(k['jami_foyda'])}")
    if k['jami_tushum']:
        t += f"  ({round(k['jami_foyda'] / k['jami_tushum'] * 100)}%)"
    t += f"\nO'rtacha chek: {fmt(k['ortacha_chek'])}\n"
    if k['xarid_oraligi_kun']:
        t += f"Xarid oralig'i: ~{k['xarid_oraligi_kun']} kun\n"
    t += "\n"

    if k['bizga_qarzdor']:
        t += f"\U0001F534 *Debitorlik (bizga qarzi): {fmt(k['bizga_qarzdor'])}*\n"
    if k['biz_qarzdormiz']:
        t += f"\U0001F535 Kreditorlik (biz qarzmiz): {fmt(k['biz_qarzdormiz'])}\n"
    if k['bizga_qarzdor'] or k['biz_qarzdormiz']: t += "\n"

    kelgan = [x for x in k['qayta_buyurtma'] if x['muddati_keldi']]
    if kelgan:
        t += "\U0001F501 *Qayta buyurtma vaqti:*\n"
        for x in kelgan[:5]:
            t += f"• {_md(x['mahsulot'])} — {x['otgan']} kun oldin\n"
        t += "\n"

    if k['sotuvlar']:
        t += "\U0001F4CB *Xaridlar:*\n"
        for s in k['sotuvlar'][:8]:
            sana = s['sana'][8:10] + '.' + s['sana'][5:7]
            dona = f" x{s['dona']}" if s['dona'] > 1 else ""
            t += f"`{sana}` {_md(s['mahsulot'])}{dona} — {fmt(s['summa'])}\n"
        if len(k['sotuvlar']) > 8:
            t += f"_...yana {len(k['sotuvlar']) - 8} ta_\n"
        t += "\n"

    if k['tarix']:
        t += "\U0001F4DD *Aloqa tarixi:*\n"
        for g in k['tarix'][:4]:
            t += f"`{g['sana'][5:]}` {_md(g['matn'])[:60]}\n"
        t += "\n"

    if k['izoh']: t += f"\U0001F4AC {_md(k['izoh'])}\n"
    if k['oxirgi_aloqa']: t += f"\nOxirgi aloqa: {k['oxirgi_aloqa']}"
    await u.message.reply_text(t, parse_mode='Markdown')


async def cmd_mijozlar_yangi(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    conn = db(); c = conn.cursor()
    c.execute("""SELECT cu.id, cu.name, cu.phone, cu.type, COALESCE(cu.channel,''),
                        COUNT(s.id), COALESCE(SUM(s.revenue),0), COALESCE(SUM(s.profit),0),
                        MAX(s.date)
                 FROM customers cu LEFT JOIN sales s
                      ON s.customer_id=cu.id AND s.reversed=0
                 GROUP BY cu.id ORDER BY 8 DESC, 7 DESC""")
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM sales WHERE COALESCE(customer_id,0)=0 AND reversed=0 "
              "AND TRIM(COALESCE(customer,''))<>''")
    bogsiz = c.fetchone()[0]
    conn.close()
    if not rows:
        await u.message.reply_text("\U0001F465 Hali mijoz qo'shilmagan.")
        return

    qarzlar = {}
    conn = db(); c = conn.cursor()
    c.execute("SELECT customer_id, SUM(amount) FROM debts "
              f"WHERE paid=0 AND type IN {DEBITOR_SQL} AND COALESCE(customer_id,0)>0 GROUP BY customer_id")
    for cid, s in c.fetchall(): qarzlar[cid] = s
    conn.close()

    b2b = [r for r in rows if r[3] == 'B2B']
    b2c = [r for r in rows if r[3] != 'B2B']
    jami_f = sum(r[7] for r in rows)
    t = f"\U0001F465 *MIJOZLAR · {len(rows)} ta*\nJami foyda: {fmt(jami_f)}\n\n"

    def blok(lst, sarlavha):
        s = f"*{sarlavha}*\n"
        for r in lst[:12]:
            kan = _KAN_EMOJI.get(r[4], '') if r[4] else ''
            s += f"• {_md(r[1])} {kan}\n"
            s += f"  {r[5]} xarid · {fmt(r[6])} · foyda {fmt(r[7])}"
            if qarzlar.get(r[0]):
                s += f" · \U0001F534 qarz {fmt(qarzlar[r[0]])}"
            s += "\n"
        return s + "\n"

    if b2b: t += blok(b2b, "\U0001F3E2 B2B")
    if b2c: t += blok(b2c, "\U0001F464 B2C")
    if bogsiz:
        t += f"⚠️ {bogsiz} ta sotuv mijozga bog'lanmagan — /bogla\n"
    t += "\nBatafsil: `/mijoz Ism`"
    await u.message.reply_text(t, parse_mode='Markdown')


async def cmd_bogla(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    msg = await u.message.reply_text("⏳ Bog'lanmoqda...")
    r = await asyncio.to_thread(bogla_hammasi)
    nsub = await asyncio.to_thread(sub_bogla)
    d = await asyncio.to_thread(dublikatlar)
    t = (f"✅ *Bog'landi*\n\n"
         f"Sotuvlar: {r['sotuv']} ta\nQarzlar: {r['qarz']} ta\n"
         f"Yangi mijoz kartasi: {r['yangi_mijoz']} ta\n"
         f"Botdagi obunachiga ulandi: {nsub} ta\n")
    if d:
        t += f"\n⚠️ *{len(d)} ta ehtimoliy dublikat:*\n"
        for x in d[:8]:
            t += f"• {_md(x['a'])} ↔ {_md(x['b'])} ({x['sabab']})\n"
        t += "\nBirlashtirish: `/birlashtir Eski | Yangi`"
    await msg.edit_text(t, parse_mode='Markdown')


async def cmd_birlashtir(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    arg = ' '.join(ctx.args) if ctx.args else ''
    if '|' not in arg:
        await u.message.reply_text(
            "\U0001F517 *Mijozlarni birlashtirish*\n\n"
            "`/birlashtir Alisher | Alisher Zargarov`\n\n"
            "Chapdagi o'ngdagiga qo'shiladi va o'chadi.", parse_mode='Markdown')
        return
    a, b = [x.strip() for x in arg.split('|', 1)]
    r = await asyncio.to_thread(birlashtir, a, b)
    if r.get('error'):
        await u.message.reply_text(f"❌ {r['error']}")
        return
    await u.message.reply_text(
        f"✅ *{_md(r['manba'])}* → *{_md(r['nishon'])}*\n\n"
        f"Ko'chirildi: {r['sotuv']} sotuv, {r['qarz']} qarz", parse_mode='Markdown')


async def cmd_ulash(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mijoz kartasini botdagi obunachiga ulash"""
    if not can(u, 'boshqaruv'): return
    args = ctx.args or []
    if len(args) < 2 or not args[-1].lstrip('-').isdigit():
        conn = db(); c = conn.cursor()
        c.execute("SELECT s.chat_id, s.name, s.username, "
                  "(SELECT name FROM customers WHERE chat_id=s.chat_id) "
                  "FROM subscribers s WHERE s.active=1 ORDER BY s.joined DESC LIMIT 20")
        rows = c.fetchall(); conn.close()
        t = "\U0001F517 *Mijozni botdagi obunachiga ulash*\n\n`/ulash Alisher Zargarov 555001`\n\n"
        if rows:
            t += "*Obunachilar:*\n"
            for chid, nm, un, mij in rows:
                t += f"`{chid}` {_md(nm or '?')}"
                if un: t += f" @{un}"
                t += f" → {_md(mij)}" if mij else " — _ulanmagan_"
                t += "\n"
        else:
            t += "Hali obunachi yo'q."
        await u.message.reply_text(t, parse_mode='Markdown')
        return
    chid = int(args[-1]); ism = ' '.join(args[:-1])
    r = await asyncio.to_thread(sub_ulash, ism, chid)
    if r.get('error'):
        await u.message.reply_text(f"❌ {r['error']}")
        return
    await u.message.reply_text(
        f"✅ {_md(r['mijoz'])} ↔ {_md(r['obunachi'])}\n\nEndi unga botdan xabar yuborish mumkin.")


async def cmd_kanal(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    if len(ctx.args or []) < 2:
        await u.message.reply_text(
            "\U0001F4E1 *Mijoz kanali*\n\n`/kanal Alisher instagram`\n\n"
            f"Kanallar: {', '.join(KANALLAR)}", parse_mode='Markdown')
        return
    kanal = ctx.args[-1]
    ism = ' '.join(ctx.args[:-1])
    r = await asyncio.to_thread(kanal_belgila, ism, kanal)
    if r.get('error'):
        await u.message.reply_text(f"❌ {r['error']}")
        return
    await u.message.reply_text(f"✅ {_md(r['mijoz'])} → {_KAN_EMOJI.get(r['kanal'],'')} {r['kanal']}")


async def cmd_kanallar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    davr = (ctx.args[0] if ctx.args else '').strip()
    rows = await asyncio.to_thread(kanal_hisobot, davr)
    if not rows:
        await u.message.reply_text("Sotuv yo'q.")
        return
    sarl = "\U0001F4E1 *KANALLAR"
    if davr: sarl += " · " + davr
    t = sarl + "*\n\n"
    for r in rows:
        em = _KAN_EMOJI.get(r['kanal']) or "•"
        t += (f"{em} *{r['kanal']}*\n"
              f"  {r['sotuv']} sotuv · {r['mijoz']} mijoz\n"
              f"  Tushum {fmt(r['tushum'])} · foyda {fmt(r['foyda'])} ({r['ulush_pct']}%)\n\n")
    nom = next((r for r in rows if r['kanal'] == 'nomalum'), None)
    if nom and nom['ulush_pct'] > 15:
        t += ("⚠️ Kanali belgilanmagan mijozlar bor.\n"
              "`/kanal Ism olx` bilan belgilang.\n")
    ms = next((r for r in rows if r['kanal'] == 'mijozsiz'), None)
    if ms:
        t += ("\n_mijozsiz — eski sotuvlar, ismi yozilmagan. "
              "Bundan keyin har sotuvda mijoz ismini ayting._")
    await u.message.reply_text(t, parse_mode='Markdown')


async def cmd_qayta(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    lst = await asyncio.to_thread(qayta_buyurtma, 5)
    rx = await asyncio.to_thread(rasxodniklar)
    if not lst:
        t = "\U0001F501 *Qayta buyurtma*\n\nHozircha muddati kelgani yo'q.\n\n"
        if rx:
            t += "Kuzatuvdagi rasxodniklar:\n"
            t += "\n".join(f"• {_md(x['mahsulot'])} — {x['sikl_kun']} kun" for x in rx)
        else:
            t += ("Hali rasxodnik belgilanmagan.\n\n"
                  "`/rasxodnik Sublimatsiya qog'ozi 30`\n"
                  "— shu mahsulot har 30 kunda tugaydi deb hisoblanadi. "
                  "Mijoz uni sotib olsa, vaqti kelganda eslatib turaman.")
        await u.message.reply_text(t, parse_mode='Markdown')
        return
    t = f"\U0001F501 *QAYTA BUYURTMA · {len(lst)} ta*\n\n"
    for x in lst[:15]:
        belgi = "\U0001F534" if x['kechikkan'] > 7 else "\U0001F7E1" if x['kechikkan'] >= 0 else "⚪"
        t += f"{belgi} *{_md(x['mijoz'])}* — {_md(x['mahsulot'])}\n"
        t += f"   {x['otgan']} kun oldin olgan (sikl {x['sikl']} kun)"
        if x['tel']: t += f"\n   \U0001F4DE `{x['tel']}`"
        if x['chat_id']: t += "  ✅ botda"
        t += "\n\n"
    t += "To'xtatish: `/qayta_ochir Ism | Mahsulot`"
    await u.message.reply_text(t, parse_mode='Markdown')


async def cmd_qayta_ochir(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    arg = ' '.join(ctx.args) if ctx.args else ''
    if '|' not in arg:
        await u.message.reply_text("`/qayta_ochir Alisher | qog'oz`", parse_mode='Markdown')
        return
    a, b = [x.strip() for x in arg.split('|', 1)]
    r = await asyncio.to_thread(reorder_ochir, a, b)
    if r.get('error'):
        await u.message.reply_text(f"❌ {r['error']}")
        return
    await u.message.reply_text(f"✅ {r['ochirildi']} ta kuzatuv o'chirildi.")


async def cmd_rasxodnik(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    args = ctx.args or []
    if len(args) < 2 or not args[-1].isdigit():
        rx = await asyncio.to_thread(rasxodniklar)
        t = ("\U0001F504 *Rasxodnik belgilash*\n\n"
             "`/rasxodnik Sublimatsiya qog'ozi 30`\n"
             "— oxirgi raqam: necha kunda tugaydi.\n\n"
             "0 qo'ysangiz kuzatuvdan chiqadi.\n\n")
        if rx:
            t += "*Hozirgi ro'yxat:*\n" + "\n".join(
                f"• {_md(x['mahsulot'])} — {x['sikl_kun']} kun" for x in rx)
        await u.message.reply_text(t, parse_mode='Markdown')
        return
    kun = int(args[-1]); nom = ' '.join(args[:-1])
    r = await asyncio.to_thread(rasxodnik_belgila, nom, kun)
    if r.get('error'):
        await u.message.reply_text(f"❌ {r['error']}")
        return
    if kun == 0:
        await u.message.reply_text(f"✅ {_md(r['mahsulot'])} kuzatuvdan chiqdi.")
    else:
        await u.message.reply_text(
            f"✅ *{_md(r['mahsulot'])}* — har {kun} kunda tugaydi.\n\n"
            f"Endi kim sotib olsa, {kun} kundan keyin eslataman.", parse_mode='Markdown')


async def cmd_dalolatnoma(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    q = ' '.join(ctx.args).strip() if ctx.args else ''
    if not q:
        await u.message.reply_text(
            "\U0001F4C4 *Solishtirish dalolatnomasi*\n\n`/dalolatnoma Alisher`\n\n"
            "Mijozning barcha xaridlari va qarz qoldig'i — imzolash uchun.",
            parse_mode='Markdown')
        return
    k = await asyncio.to_thread(mijoz_karta, q)
    if not k:
        await u.message.reply_text(f"❌ Mijoz topilmadi: {_md(q)}")
        return
    if not k['sotuvlar']:
        await u.message.reply_text(f"⚠️ {_md(k['nom'])} da xarid yo'q.")
        return
    qatorlar = []
    for s in reversed(k['sotuvlar']):
        sana = s['sana'][8:10] + '.' + s['sana'][5:7] + '.' + s['sana'][:4]
        dona = max(1, s['dona'])
        qatorlar.append((f"{sana} - {s['mahsulot']}", dona, round(s['summa'] / dona, 2)))
    izoh = f"Xaridlar soni: {k['sotuv_soni']}."
    if k['bizga_qarzdor']:
        izoh += f" Qarz qoldigi: {k['bizga_qarzdor']:.2f} USD."
    else:
        izoh += " Qarz qoldigi yoq - hisob-kitob yopiq."
    msg = await u.message.reply_text("⏳ Tayyorlanmoqda...")
    base = f"/tmp/sd_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    p, raqam, jami, is_pdf = await asyncio.to_thread(
        build_hujjat, base, 'dalolatnoma', k['nom'], qatorlar, izoh)
    with open(p, 'rb') as fh:
        await ctx.bot.send_document(
            chat_id=OWNER_ID, document=fh,
            filename=f"{raqam}.{'pdf' if is_pdf else 'html'}",
            caption=f"\U0001F4C4 {raqam} · {_md(k['nom'])} · {fmt(jami)}")
    try: os.remove(p)
    except Exception: pass
    await asyncio.to_thread(log_qosh, k['id'], 'hujjat', f"Dalolatnoma {raqam}")
    await msg.delete()


async def cmd_brief(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/brief — ertalabki xulosani hozir ko'rish"""
    if not can(u, 'boshqaruv'): return
    await _briefing(ctx.application, 'evening' if _local_now().hour >= 15 else 'morning')


# ── COMMAND HANDLERS ──────────────────────────────────────────────
# Menyu tugmalari xaritalash
MENU_MAP = {
    "📦 Astatka": "stock",
    "💰 Bugun": "today",
    "📈 Oylik": "month",
    "📅 Yillik": "year",
    "🚚 Yo'lda": "transit",
    "💳 Zavod qarzi": "supplier_debt",
    "💵 Narxlar": "prices",
    "📊 Analiz": "analiz",
    "👥 Mijozlar": "customers",
    "🔁 Qayta": "reorder",
    "📡 Kanallar": "kanallar",
    "💳 Qarzlar": "debts",
    "💸 Xarajatlar": "expenses",
    "🎯 Maqsad": "target",
    "🔧 Kafolat": "warranties",
    "📈 Trend": "trend",
    "💵 Cash Flow": "cashflow",
    "📢 OLX": "olx",
    "➕ Yangi tovar": "new_product",
    "↩️ Qayt etish": "undo_list",
    "🛒 Sotuv": "pos",
    "👷 Sotuvchilar": "sotuvchilar",
    "📦 Qoldiq": "qoldiq",
    "📋 Bugungi sotuvlarim": "mening",
    "❓ Yordam": "yordam",
    "💵 Kassa": "kassa",
    "📉 Nelikvid": "nelikvid",
    "🔔 Eslatmalar": "eslatmalar",
    "📣 Reklama": "reklama_menu",
    "📊 Dashboard": "dashboard",
    "📈 Moliya": "moliya",
    "🔄 Aylanish": "aylanish",
    "📋 Qarz yoshi": "qarz_yosh",
    "🔍 Raqobat": "raqobat",
    # 5–8-bosqich: yangi asosiy menyu
    "📦 Ombor": "ombor",
    "📊 Hisobotlar": "hisobotlar",
    "🏭 Zavod": "zavod_ui",
    "⚙️ Boshqa": "boshqa",
    "📢 Marketing": "marketing",
    "⬅️ Asosiy menyu": "asosiy",
    # 10-bosqich
    "📥 Qaytarish": "qaytarish",
    "🧾 Smena": "smena",
    "💾 Zaxira": "zaxira",
    "🔢 Serial": "serial",
}

# Egasi/admin asosiy menyusi (5–8-bosqich). Eski to'liq menyu — "⚙️ Boshqa" ichida, barcha eski tugmalar ishlaydi.
ASOSIY_KB = [["🛒 Sotuv", "📦 Ombor"], ["👥 Mijozlar", "📊 Hisobotlar"], ["🏭 Zavod", "👷 Sotuvchilar"],
             ["📥 Qaytarish", "🧾 Smena"], ["📢 Marketing", "⚙️ Boshqa"]]
# Olib tashlangan (yangi ekran to'liq qoplaydi): 📦 Astatka → 📦 Ombor; 💰 Bugun / 📈 Oylik / 📅 Yillik → 📊 Hisobotlar;
# 💳 Zavod qarzi → 🏭 Zavod → Zavodlar balansi; 💳 Qarzlar → 👥 Mijozlar → Qarzdorlar/Kreditorlar;
# 💵 Cash Flow → 📊 Hisobotlar → 💰 Kassa; 👥 Mijozlar (takror). Buyruqlari (/astatka, /bugun, /oy ...) qoladi.
OLIB_TASHLANGAN_TUGMALAR = {"📦 Astatka", "💰 Bugun", "📈 Oylik", "📅 Yillik", "💳 Zavod qarzi", "💳 Qarzlar", "💵 Cash Flow"}
ESKI_KB = [
    ["🚚 Yo'lda",     "💵 Kassa"],
    ["💵 Narxlar",    "💸 Xarajatlar"],
    ["📊 Analiz",     "📈 Moliya"],
    ["🔁 Qayta",      "📉 Nelikvid"],
    ["🔄 Aylanish",   "📈 Trend"],
    ["📊 Dashboard",  "🎯 Maqsad"],
    ["🔧 Kafolat",    "🔔 Eslatmalar"],
    ["📡 Kanallar",   "📣 Reklama"],
    ["🔍 Raqobat",    "📢 OLX"],
    ["➕ Yangi tovar", "↩️ Qayt etish"],
    ["💾 Zaxira",     "🔢 Serial"],
    ["⬅️ Asosiy menyu"],
]

def _asosiy_kb():
    return ReplyKeyboardMarkup(ASOSIY_KB, resize_keyboard=True, is_persistent=True)

async def route_menu(u: Update, ctx: ContextTypes.DEFAULT_TYPE, msg: str):
    """Menyu tugmasini tegishli bo'limga yo'naltiradi"""
    action = MENU_MAP.get(msg)
    if not action:
        return False
    if   action == 'stock':         await cmd_astatka(u, ctx)
    elif action == 'today':         await cmd_bugun(u, ctx)
    elif action == 'month':         await cmd_oy(u, ctx)
    elif action == 'year':          await cmd_yil(u, ctx)
    elif action == 'transit':       await cmd_yolda(u, ctx)
    elif action == 'supplier_debt': await cmd_zavod_qarz(u, ctx)
    elif action == 'prices':        await cmd_narxlar(u, ctx)
    elif action == 'analiz':        await cmd_analiz(u, ctx)
    elif action == 'customers':     await cmd_mijozlar_ui(u, ctx)          # tugmali (eski ro'yxat: /mijozlar)
    elif action == 'reorder':       await cmd_qayta(u, ctx)
    elif action == 'kanallar':      await cmd_kanallar(u, ctx)
    elif action == 'debts':         await cmd_qarzlar(u, ctx)
    elif action == 'expenses':      await cmd_xarajatlar(u, ctx)
    elif action == 'target':        await cmd_maqsad(u, ctx)
    elif action == 'warranties':    await cmd_kafolat(u, ctx)
    elif action == 'trend':         await cmd_trend(u, ctx)
    elif action == 'cashflow':      await cmd_cashflow(u, ctx)
    elif action == 'olx':           await cmd_olx(u, ctx)
    elif action == 'dashboard':     await cmd_dashboard(u, ctx)
    elif action == 'moliya':        await cmd_moliya(u, ctx)
    elif action == 'aylanish':      await cmd_aylanish(u, ctx)
    elif action == 'qarz_yosh':     await cmd_qarz_yosh(u, ctx)
    elif action == 'raqobat':       await cmd_raqobat(u, ctx)
    elif action == 'undo_list':     await cmd_undo_list(u, ctx)
    elif action == 'kassa':         await cmd_kassa(u, ctx)
    elif action == 'nelikvid':      await cmd_nelikvid(u, ctx)
    elif action == 'eslatmalar':    await cmd_eslatmalar(u, ctx)
    elif action == 'new_product':   await conv_start(u, ctx)
    elif action == 'pos':           await pos_start(u, ctx)
    elif action == 'sotuvchilar':   await cmd_sotuvchilar(u, ctx)
    elif action == 'qoldiq':        await cmd_qoldiq(u, ctx)
    elif action == 'mening':        await cmd_mening(u, ctx)
    elif action == 'yordam':        await cmd_yordam(u, ctx)
    elif action == 'ombor':         await cmd_ombor(u, ctx)
    elif action == 'hisobotlar':    await cmd_hisobotlar(u, ctx)
    elif action == 'zavod_ui':      await cmd_zavod_ui(u, ctx)
    elif action == 'marketing':     await cmd_marketing(u, ctx)
    elif action == 'qaytarish':     await cmd_qaytarish(u, ctx)
    elif action == 'smena':         await cmd_smena(u, ctx)
    elif action == 'zaxira':        await cmd_zaxira(u, ctx)
    elif action == 'serial':        await cmd_serial(u, ctx)
    elif action == 'boshqa':
        if can(u, 'boshqaruv'):
            await u.message.reply_text("⚙️ Boshqa bo'limlar. Qaytish: ⬅️ Asosiy menyu",
                                       reply_markup=ReplyKeyboardMarkup(ESKI_KB, resize_keyboard=True, is_persistent=True))
    elif action == 'asosiy':
        if can(u, 'boshqaruv'):
            await u.message.reply_text("🏠 Asosiy menyu", reply_markup=_asosiy_kb())
    elif action == 'reklama_menu':
        await u.message.reply_text(
            "\U0001F4E3 *Reklama yuborish*\n\nFormat: `/reklama Xabar matni`\n\n"
            "Misol:\n`/reklama Yangi TTS 20 Pro keldi!`",
            parse_mode='Markdown')
    return True


async def cmd_start_public(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mijoz /start bosganda — ro'yxatga oladi va katalog ko'rsatadi"""
    if ctx.args and await pub_start_link(u, ctx, ctx.args[0]):      # kanal tugmasi: /start p<ID>
        return
    us = u.effective_user
    nomi = (us.first_name or '') + ((' ' + us.last_name) if us.last_name else '')
    yangi = sub_add(us.id, nomi.strip(), us.username or '', 'start')
    try: sub_bogla(us.id, nomi.strip())
    except Exception: pass
    prods = [p for p in get_products() if p['qty'] > 0]
    rate = get_exchange_rate()
    text = ("\U0001F3ED ThermoCrafts \u2014 lazer, CNC va termopress uskunalari\n"
            "\U0001F4CD Yunusobod, Toshkent\n\n")
    if prods:
        tt = [p for p in prods if p['sup'] == 'Two Trees']
        fs = [p for p in prods if p['sup'] == 'Freesub']
        text += "\U0001F4E6 HOZIR MAVJUD:\n\n"
        if tt:
            text += "\U0001F535 Lazer va CNC:\n"
            for p in tt: text += f"  \u2022 {p['name']} \u2014 {fmt(p['price'])}\n"
            text += "\n"
        if fs:
            text += "\U0001F7E0 Termopress va sublimatsiya:\n"
            for p in fs: text += f"  \u2022 {p['name']} \u2014 {fmt(p['price'])}\n"
            text += "\n"
        text += f"\U0001F4B1 1 USD = {rate:,.0f} so'm\n\n"
    text += ("\U0001F4DE Buyurtma va savollar uchun yozing \u2014 javob beramiz.\n"
             "\U0001F4E2 Kanal: @ThermoCrafts\n\n")
    text += ("\u2705 Yangi tovar va chegirmalar haqida xabar beramiz."
             if yangi else "\u2705 Siz allaqachon obunasiz.")
    text += "\n\nObunani bekor qilish: /stop"
    await u.message.reply_text(text)
    if yangi:
        try:
            await ctx.bot.send_message(OWNER_ID,
                f"\U0001F464 Yangi obunachi: {nomi.strip() or 'ismsiz'}"
                + (f" (@{us.username})" if us.username else "")
                + f"\nJami: {sub_count()} ta")
        except Exception: pass

async def cmd_stop_public(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if user_role(u): return
    sub_off(u.effective_user.id)
    await u.message.reply_text("Obuna bekor qilindi. Qaytish uchun /start bosing.")

async def handle_text_public(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mijoz yozganda: so'rov (ism/telefon) → tovar kartasi → aks holda egasiga yetkazadi"""
    us = u.effective_user
    if await pub_matn(u, ctx): return
    if not _rl_ok(us.id, 'msg', 20, 60):
        if _rl_ok(us.id, 'ogoh', 1, 60): await u.message.reply_text("Juda ko'p xabar — 1 daqiqadan keyin yozing.")
        return
    try:
        if await pub_qidir(u, ctx): return
    except Exception:
        log.exception("ochiq qidiruv")
    sub_add(us.id, ((us.first_name or '') + (' ' + us.last_name if us.last_name else '')).strip(),
            us.username or '', 'message')
    await u.message.reply_text(
        "Rahmat! Xabaringiz qabul qilindi \u2014 tez orada javob beramiz.\n\n"
        "Mahsulotlar ro'yxati: /start")
    try:
        await ctx.bot.send_message(OWNER_ID,
            f"\U0001F4AC Mijozdan xabar\n"
            f"\U0001F464 {us.first_name or ''} "
            + (f"(@{us.username})" if us.username else f"(id: {us.id})")
            + f"\n\n{u.message.text[:600]}")
    except Exception: pass

async def cmd_start(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if user_role(u) == 'sotuvchi':
        return await cmd_start_sotuvchi(u, ctx)
    if not can(u, 'boshqaruv'): return
    rate = get_exchange_rate()
    kb = _asosiy_kb()
    await u.message.reply_text(
        f"🏭 ThermoCrafts v5.0 — {AI_NAME} bilan\n💱 1 USD = {rate:,.0f} so'm\n\n"
        "🛒 Sotuv · 📦 Ombor · 👥 Mijozlar · 📊 Hisobotlar · 🏭 Zavod · 👷 Sotuvchilar\n"
        "⚙️ Boshqa — qolgan bo'limlar (kassa, narxlar, moliya, kafolat, qaytarish…)\n\n"
        "Erkin yozing: \"tts20 ni Alisherga 450 ga nasiya berdim\" yoki \"bu oy eng ko'p nima ketdi?\"",
        reply_markup=kb)


async def cmd_astatka(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    prods = get_products()
    rate = get_exchange_rate()
    text = f"📦 *ASTATKA* — {now_t()}\n\n"

    # Two Trees oilasi
    tt = [p for p in prods if p['sup'] == 'Two Trees']
    if tt:
        tt_cost = sum(p['qty']*p['cost'] for p in tt)
        tt_qty  = sum(p['qty'] for p in tt)
        text += f"🔵 *TWO TREES* ({tt_qty} dona | sebest {fmt(tt_cost)})\n"
        for cat in ['Lazer', 'CNC']:
            ps = [p for p in tt if p['cat'] == cat]
            if ps:
                text += f"  _{cat}:_\n"
                for p in ps:
                    e = "🔴" if p['qty']==0 else "🟡" if p['qty']<=1 else "🟢"
                    text += f"  {e} {p['name']}: *{p['qty']} ta* · {fmt(p['price'])}\n"
        text += "\n"

    # Freesub oilasi
    fs = [p for p in prods if p['sup'] == 'Freesub']
    if fs:
        fs_cost = sum(p['qty']*p['cost'] for p in fs)
        fs_qty  = sum(p['qty'] for p in fs)
        text += f"🟠 *FREESUB* ({fs_qty} dona | sebest {fmt(fs_cost)})\n"
        for cat in ['Press', "Qog'oz"]:
            ps = [p for p in fs if p['cat'] == cat]
            if ps:
                text += f"  _{cat}:_\n"
                for p in ps:
                    e = "🔴" if p['qty']==0 else "🟡" if p['qty']<=1 else "🟢"
                    text += f"  {e} {p['name']}: *{p['qty']} ta* · {fmt(p['price'])}\n"
        text += "\n"

    # Boshqa yetkazuvchilar
    other = [p for p in prods if p['sup'] not in ('Two Trees', 'Freesub')]
    if other:
        text += "⚪ *BOSHQA*\n"
        for p in other:
            e = "🔴" if p['qty']==0 else "🟡" if p['qty']<=1 else "🟢"
            text += f"  {e} {p['name']}: *{p['qty']} ta* · {fmt(p['price'])}\n"
        text += "\n"

    tc  = sum(p['qty']*p['cost'] for p in prods)
    tp  = sum(p['qty']*p['price'] for p in prods)
    out = [p['name'] for p in prods if p['qty']==0]
    text += f"💰 Jami sebest: *{fmt(tc)}* | Narxda: *{fmt(tp)}*\n"
    text += f"💱 1 USD = {rate:,.0f} so'm"
    if out: text += f"\n\n⚠️ *Tugagan:* {', '.join(out)}"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_narxlar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    prods = get_products()
    text = "💵 *NARX JADVALI*\n_(Zavod | Sebest | Sotuv | Marja)_\n\n"
    for cat in ['Lazer', 'CNC', 'Press', "Qog'oz"]:
        ps = [p for p in prods if p['cat'] == cat]
        if ps:
            text += f"*{cat}:*\n"
            for p in ps:
                margin = p['price'] - p['cost']
                pct = margin/p['price']*100 if p['price'] else 0
                text += (f"  {p['name']}\n"
                         f"  🏭${p['factory']:.0f} → 📦${p['cost']:.0f} → 💵${p['price']:.0f} | ✅${margin:.0f} ({pct:.0f}%)\n")
            text += "\n"
    narxli = [p for p in prods if p['price'] > 0]      # mahsulot yo'q / narxsiz bo'lsa ZeroDivisionError bo'lardi
    avg_margin = sum((p['price']-p['cost'])/p['price']*100 for p in narxli) / len(narxli) if narxli else 0
    text += f"📊 O'rtacha marja: *{avg_margin:.0f}%*"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_bugun(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    sales = get_sales(today())
    exps_cogs = get_expenses(today(), 'cogs_bank') + get_expenses(today(), 'cogs_delivery')
    exps_period = get_expenses(today(), 'period')
    label = datetime.now().strftime('%d.%m.%Y')
    if not sales and not exps_cogs and not exps_period:
        await u.message.reply_text(f"📊 *{label}*\n\nBugun hali hech narsa yo'q.", parse_mode='Markdown')
        return
    tR = sum(s[6] for s in sales)
    tCOGS = sum(s[5]*s[4] for s in sales)  # unit_cost * qty
    tCogsEx = sum(e[2] for e in exps_cogs)
    tPeriod = sum(e[2] for e in exps_period)
    text = f"📊 *Bugungi hisobot — {label}*\n\n"
    if sales:
        text += "*Sotuvlar:*\n"
        for s in sales:
            cust = f" ({s[9]})" if s[9] else ""
            text += f"• {s[3]}: {s[4]}ta = *{fmt(s[6])}*{cust}\n"
        text += f"\n💵 Tushum: *{fmt(tR)}*\n"
        text += f"📦 Tovar tannarxi: −{fmt(tCOGS)}\n"
        text += f"💳 Bank+dostavka: −{fmt(tCogsEx)}\n"
        text += f"📈 Yalpi foyda: *{fmt(tR-tCOGS-tCogsEx)}*\n"
    if exps_period:
        text += "\n*Davr xarajatlari:*\n"
        for e in exps_period:
            text += f"• {e[3]}: −{fmt(e[2])}\n"
        text += f"💸 Jami: −{fmt(tPeriod)}\n"
    text += f"\n✅ *SOF FOYDA: {fmt(tR-tCOGS-tCogsEx-tPeriod)}*"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_oy(u: Update, ctx: ContextTypes.DEFAULT_TYPE, month=None):
    if not can(u, 'boshqaruv'): return
    # /oy 2026-07 — CommandHandler oyni ctx.args da beradi (avval e'tiborsiz qolib, doim joriy oy chiqardi)
    if not month and getattr(ctx, 'args', None): month = ctx.args[0].strip()
    if not month: month = this_month()
    if not re.match(r'^\d{4}-\d{2}$', str(month)):
        await u.message.reply_text("Format: /oy 2026-07"); return
    sales = get_sales(month)
    exps_cogs = get_expenses(month, 'cogs_bank') + get_expenses(month, 'cogs_delivery')
    exps_period = get_expenses(month, 'period')
    label = month
    tR = sum(s[6] for s in sales)
    tCOGS = sum(s[5]*s[4] for s in sales)
    tCogsEx = sum(e[2] for e in exps_cogs)
    tPeriod = sum(e[2] for e in exps_period)
    sof = tR - tCOGS - tCogsEx - tPeriod
    text = f"📈 *Oylik hisobot — {label}*\n\n"
    text += f"🛍 Sotuvlar: {len(sales)} ta\n"
    text += f"💵 Tushum: *{fmt(tR)}*\n"
    text += f"📦 Tovar tannarxi: −{fmt(tCOGS)}\n"
    text += f"💳 Bank+dostavka: −{fmt(tCogsEx)}\n"
    text += f"📈 Yalpi foyda: *{fmt(tR-tCOGS-tCogsEx)}*\n"
    text += f"💸 Davr xarajatlari: −{fmt(tPeriod)}\n"
    text += f"✅ *Sof foyda: {fmt(sof)}*\n"
    if tR > 0: text += f"📊 Marja: *{sof/tR*100:.0f}%*\n"
    prod_cnt = Counter(s[3] for s in sales)
    if prod_cnt:
        text += "\n*Top mahsulotlar:*\n"
        for name, cnt in prod_cnt.most_common(3):
            text += f"• {name}: {cnt} ta\n"
    # Maqsad
    conn = db(); c = conn.cursor()
    y, m = month.split('-')
    c.execute('SELECT target_revenue,target_profit FROM targets WHERE year=? AND month=?', (int(y), int(m)))
    tgt = c.fetchone(); conn.close()
    if tgt:
        rpct = tR/tgt[0]*100 if tgt[0] else 0
        ppct = sof/tgt[1]*100 if tgt[1] else 0
        text += "\n🎯 *Maqsad:*\n"
        text += f"Tushum: {rpct:.0f}% ({fmt(tR)}/{fmt(tgt[0])})\n"
        text += f"Foyda: {ppct:.0f}% ({fmt(sof)}/{fmt(tgt[1])})"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_yil(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    year = datetime.now().strftime('%Y')
    # Yan–Avg 2026: Excel'dagi yakuniy raqamlar (o'zgarmadi). Qolgan oylar — bazadagi sotuvlardan.
    # (Avval faqat shu 8 oy + joriy oy chiqardi: oktyabrda sentyabr tushib qolardi, o'rtacha esa doim /9 edi.)
    HIST = {
        '2026-01': (1987, 429), '2026-02': (2680, 540), '2026-03': (2185, 871), '2026-04': (3190, 820),
        '2026-05': (1515, 799), '2026-06': (1500, 257), '2026-07': (525, 97),   '2026-08': (1993, 637),
    }
    text = f"📅 *YILLIK HISOBOT — {year}*\n\n"
    text += "```\n"
    text += f"{'Oy':<10} {'Tushum':>8} {'Foyda':>8}\n"
    text += "─" * 28 + "\n"
    total_r, total_f, n_oy = 0, 0, 0
    for mo in range(1, datetime.now().month + 1):
        key = f"{year}-{mo:02d}"
        if key in HIST and key != this_month():
            rev, profit = HIST[key]
        else:
            ss = get_sales(key)
            rev = sum(s[6] for s in ss); profit = sum(s[7] for s in ss)
        text += f"{_OY_NOMI[mo]:<10} {fmt(rev):>8} {fmt(profit):>8}\n"
        total_r += rev; total_f += profit; n_oy += 1
    text += "─" * 28 + "\n"
    text += f"{'JAMI':<10} {fmt(total_r):>8} {fmt(total_f):>8}\n"
    text += "```\n"
    n_oy = max(1, n_oy)
    text += f"\n📊 O'rtacha oylik: {fmt(total_r/n_oy)} tushum | {fmt(total_f/n_oy)} foyda"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_yolda(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    conn = db(); c = conn.cursor()
    c.execute("SELECT * FROM transit WHERE status='yolda' ORDER BY id DESC")
    rows = c.fetchall(); conn.close()
    if not rows:
        await u.message.reply_text("🚚 *Yo'lda*\n\nHozirda yo'lda tovar yo'q.", parse_mode='Markdown')
        return
    text = "🚚 *YO'LDAGI TOVARLAR*\n\n"
    total_cost = total_deposit = total_remaining = 0
    for r in rows:
        text += f"📦 *#{r[0]}* — {r[2]} | {r[1]}\n"
        text += f"  {r[3]}: {r[4]} ta × {fmt(r[5])} = *{fmt(r[6])}*\n"
        text += f"  💳 Deposit: {fmt(r[7])} | 💸 Qolgan: *{fmt(r[8])}*\n"
        if r[9]: text += f"  🏦 Bank to'lovi: {fmt(r[9])}\n"
        if r[10]: text += f"  🚚 Dostavka: {fmt(r[10])}\n"
        text += f"  📊 Haqiqiy sebest: {fmt(r[10+1])}/ta\n\n"
        total_cost += r[6]; total_deposit += r[7]; total_remaining += r[8]
    text += f"💰 Jami zakaz: *{fmt(total_cost)}*\n"
    text += f"💳 Jami deposit: *{fmt(total_deposit)}*\n"
    text += f"💸 Jami qolgan: *{fmt(total_remaining)}*\n\n"
    text += "_Tovar kelganda: 'Zakaz #ID keldi' deb yozing_"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_zavod_qarz(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    conn = db(); c = conn.cursor()
    c.execute("""SELECT supplier, SUM(total_cost), SUM(deposit), SUM(remaining), COUNT(*)
                 FROM transit WHERE status='yolda' OR remaining>0
                 GROUP BY supplier ORDER BY SUM(remaining) DESC""")
    rows = c.fetchall(); conn.close()
    if not rows:
        await u.message.reply_text("💳 *Zavod qarzlari*\n\nHozirda zavod qarzi yo'q ✅", parse_mode='Markdown')
        return
    text = "💳 *ZAVOD QARZLARI*\n\n"
    total_remaining = 0
    for r in rows:
        text += f"🏭 *{r[0]}*\n"
        text += f"  Jami zakaz: {fmt(r[1])}\n"
        text += f"  To'langan: {fmt(r[2])}\n"
        text += "  ──────────────\n"
        text += f"  💸 Qolgan qarz: *{fmt(r[3])}*\n\n"
        total_remaining += r[3]
    text += f"💸 *JAMI ZAVOD QARZI: {fmt(total_remaining)}*"
    text += "\n\nTo'lash: /zavod\\_tolov Two Trees 300 \\[usul]"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_analiz(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    items = abc_xyz_analysis()
    total_rev = sum(i['rev'] for i in items) or 1
    text = "📊 *ABC TAHLIL*\n_(A=80%, B=15%, C=5% daromad)_\n\n"
    for grp, emoji, tip in [
        ('A','🟢',"Yulduz — Har doim astatikada bo'lsin"),
        ('B','🔵','Muhim — Nazorat qiling'),
        ('C','🟡','Past — Ortiqcha zakaz qilmang'),
    ]:
        gl = [i for i in items if i['abc']==grp]
        grev = sum(i['rev'] for i in gl)
        if not gl: continue
        text += f"{emoji} *Guruh {grp}* — {fmt(grev)} ({grev/total_rev*100:.0f}%): _{tip}_\n"
        for item in gl:
            text += f"  · {item['name']}: {fmt(item['rev'])} ({item['pct']}%) | {item['cnt']} marta\n"
        text += "\n"
    text += "─────────────────\n"
    text += "📈 *XYZ TAHLIL (CV formula)*\n_(X<0.5 barqaror | Y 0.5-1.0 | Z>1.0 noaniq)_\n\n"
    for grp, emoji, tip in [
        ('X','✅','Barqaror'),('Y','⚡',"O'zgaruvchan"),('Z','❌','Noaniq'),
    ]:
        gl = [(i['name'], i) for i in items if i['xyz']==grp]
        gl.sort(key=lambda x: -x[1]['total_sold'])
        if not gl: continue
        text += f"{emoji} *{grp}* — {tip}:\n"
        for name, d in gl:
            cv = d['cv'] if d['cv'] < 99 else '∞'
            text += f"  · {name}: {d['total_sold']:.0f} ta | CV={cv}\n"
        text += "\n"
    text += "─────────────────\n🎯 *Strategiya:*\n\n"
    matrix = defaultdict(list)
    for item in items:
        matrix[item['abc']+item['xyz']].append(item['name'])
    for key, emoji, action in [
        ('AX','🔥',"Yulduz! Oz zaxira — tez aylanma"),
        ('AY','⭐',"Muhim — haftalik nazorat"),
        ('AZ','⚠️',"Qimmat+noaniq — katta zaxira"),
        ('BX','✅',"Normal — oylik nazorat"),
        ('BY','👀',"Kuzatib turing"),
        ('BZ','📦',"Oz saqlang"),
        ('CZ','❄️',"Zakaz bermang"),
    ]:
        if matrix[key]:
            text += f"{emoji} *{key}* — _{action}_:\n"
            for n in matrix[key]: text += f"  · {n}\n"
            text += "\n"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_mijozlar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    conn = db(); c = conn.cursor()
    c.execute("SELECT * FROM customers ORDER BY total_purchases DESC LIMIT 15")
    rows = c.fetchall(); conn.close()
    if not rows:
        await u.message.reply_text("👥 *Mijozlar*\n\nHali mijoz qo'shilmagan.", parse_mode='Markdown')
        return
    text = "👥 *MIJOZLAR*\n\n"
    b2b = [r for r in rows if r[3]=='B2B']
    b2c = [r for r in rows if r[3]!='B2B']
    if b2b:
        text += "*🏢 B2B (Biznes):*\n"
        for r in b2b:
            text += f"• *{r[1]}*"
            if r[2]: text += f" | 📞 {r[2]}"
            text += f" | {fmt(r[4])}\n"
        text += "\n"
    if b2c:
        text += "*👤 B2C (Shaxsiy):*\n"
        for r in b2c:
            text += f"• {r[1]}"
            if r[2]: text += f" | {r[2]}"
            text += f" | {fmt(r[4])}\n"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_qarzlar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    conn = db(); c = conn.cursor()
    c.execute("SELECT date, person, amount, type FROM debts WHERE paid=0 ORDER BY id DESC")
    rows = c.fetchall()
    c.execute("SELECT supplier, SUM(remaining) FROM transit WHERE remaining>0 GROUP BY supplier ORDER BY SUM(remaining) DESC")
    zavod = c.fetchall(); conn.close()
    # Avval: r[3] (summa) ism o'rnida, fmt(r[2]) (ism) summa o'rnida → qarz bo'lsa buyruq xato berardi
    deb = [r for r in rows if debt_turi(r[3]) == DEBITOR]
    kre = [r for r in rows if debt_turi(r[3]) == KREDITOR]
    nomalum = [r for r in rows if debt_turi(r[3]) is None]
    if not (deb or kre or zavod or nomalum):
        await u.message.reply_text("💳 Qarzlar\n\nQarz yo'q ✅")
        return
    j_deb = sum(r[2] or 0 for r in deb)
    j_kre = sum(r[2] or 0 for r in kre) + sum(z[1] or 0 for z in zavod)
    text = "💳 QARZLAR\n\n"
    text += "📥 DEBITORLIK — mijozlar bizga qarz:\n"
    text += "".join(f"• {r[1]}: {fmt(r[2] or 0)} — {r[0]}\n" for r in deb) or "• yo'q\n"
    text += f"Jami debitorlik: {fmt(j_deb)}\n\n"
    text += "📤 KREDITORLIK — biz zavodga qarzmiz:\n"
    text += "".join(f"🏭 {z[0]}: {fmt(z[1] or 0)}\n" for z in zavod)
    text += "".join(f"• {r[1]}: {fmt(r[2] or 0)} — {r[0]}\n" for r in kre)
    if not (zavod or kre): text += "• yo'q\n"
    text += f"Jami kreditorlik: {fmt(j_kre)}\n"
    if nomalum:
        text += "\n❓ Turi noma'lum yozuvlar (hisobga qo'shilmadi):\n"
        text += "".join(f"• {r[1]}: {fmt(r[2] or 0)} — {r[0]} ({r[3]})\n" for r in nomalum)
    text += f"\n⚖️ Sof (debitorlik − kreditorlik): {fmt(j_deb - j_kre)}"
    text += "\n\nTo'lov: /qarz_tolov <mijoz> <summa> [usul] · /zavod_tolov <zavod> <summa> [usul]"
    await u.message.reply_text(text)

def _tolov_args(args):
    """'<ism...> <summa> [usul]' → (ism, summa, usul) | None. '1,200' = 1200, '12,5' = 12.5"""
    a = [s for s in (args or []) if s.strip()]
    usul = 'naqd'
    if a and tolov_usuli(a[-1]): usul = tolov_usuli(a.pop())
    if len(a) < 2: return None
    s = a[-1].replace('$', '').strip()
    s = s.replace(',', '') if re.fullmatch(r'\d{1,3}(,\d{3})+(\.\d+)?', s) else s.replace(',', '.')
    try: summa = float(s)
    except ValueError: return None
    return ' '.join(a[:-1]).strip(), summa, usul

def _tolov_javob(r, uzs_izoh=''):
    if not r.get('ok'):
        t = "❌ " + r.get('error', "To'lov yozilmadi")
        if r.get('variantlar'): t += "\n\nVariantlar:\n" + "\n".join(f"• {v}" for v in r['variantlar'])
        return t
    deb = r['kind'] == DEBITOR
    t = ("✅ To'lov yozildi — Debitorlik (mijoz bizga to'ladi)\n" if deb
         else "✅ To'lov yozildi — Kreditorlik (biz to'ladik)\n")
    t += f"{'👤' if deb else '🏭'} {r['person']}: {_usd2(r['paid'])} ({r['method']}){uzs_izoh}\n"
    t += f"📄 Yopildi: {r['yopildi']} ta" + (f" · qisman: {r['qisman']} ta" if r['qisman'] else "") + "\n"
    if r['qoldiq'] > 0:
        t += (f"📥 Qolgan qarzi: {_usd2(r['qoldiq'])}\n" if deb else f"📤 Qolgan qarzimiz: {_usd2(r['qoldiq'])}\n")
    else:
        t += "✅ Qarz to'liq yopildi\n"
    t += f"💰 Kassa qoldig'i: {_usd2(r['kassa'])}\n↩️ Bekor qilish: /undo (#{r['op_id']})"
    return t

async def _tolov_buyruq(u, ctx, turi, cmd, misol):
    if not can(u, 'boshqaruv'): return
    p = _tolov_args(ctx.args)
    if not p:
        ochiq = ochiq_qarzlar(turi)
        t = (f"Foydalanish: /{cmd} <ism> <summa> [usul]\nMasalan: /{cmd} {misol}\n"
             f"Usullar: {', '.join(TOLOV_USULLARI)} (aytilmasa naqd). 5000 dan katta summa so'm deb olinadi.\n\n")
        t += ("📥 Ochiq debitorlik (mijozlar bizga qarz):\n" if turi == DEBITOR else "📤 Ochiq kreditorlik (biz qarzmiz):\n")
        t += "\n".join(f"• {k}: {_usd2(v)}" for k, v in sorted(ochiq.items(), key=lambda x: -x[1])) or "• yo'q"
        await u.message.reply_text(t); return
    ism, summa, usul = p
    uzs = ''
    if summa >= 5000:                          # bot qoidasi: 5000 dan katta "dollar" — so'm
        rate = get_exchange_rate(); usd = round(summa / rate, 2)
        uzs = f"\n💱 {summa:,.0f} so'm → {_usd2(usd)} (kurs {rate:,.0f})"; summa = usd
    r = await asyncio.to_thread(pay_debt, turi, ism, summa, usul)
    await u.message.reply_text(_tolov_javob(r, uzs))

async def cmd_qarz_tolov(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/qarz_tolov <mijoz> <summa> [usul] — mijoz bizga qarzini to'ladi (debitorlik kamayadi, kassaga kirim)"""
    await _tolov_buyruq(u, ctx, DEBITOR, 'qarz_tolov', 'Alibek 150 karta')

async def cmd_zavod_tolov(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/zavod_tolov <zavod> <summa> [usul] — biz zavodga/yetkazuvchiga to'ladik (kreditorlik kamayadi, kassadan chiqim)"""
    await _tolov_buyruq(u, ctx, KREDITOR, 'zavod_tolov', 'Two Trees 300 otkazma')

async def cmd_xarajatlar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    exps = get_expenses(this_month())
    label = datetime.now().strftime('%B %Y')
    cogs = [e for e in exps if e[4] in ('cogs_bank','cogs_delivery')]
    period = [e for e in exps if e[4]=='period']
    text = f"💸 *XARAJATLAR — {label}*\n\n"
    if cogs:
        text += "*📦 Sebest xarajatlari (COGS):*\n"
        by_cat = defaultdict(float)
        for e in cogs: by_cat[e[3]] += e[2]
        for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
            text += f"• {cat}: *{fmt(amt)}*\n"
        text += f"Jami: *{fmt(sum(e[2] for e in cogs))}*\n\n"
    if period:
        text += "*📋 Davr xarajatlari:*\n"
        by_cat = defaultdict(float)
        for e in period: by_cat[e[3]] += e[2]
        for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
            text += f"• {cat}: *{fmt(amt)}*\n"
        text += f"Jami: *{fmt(sum(e[2] for e in period))}*\n"
    if not exps:
        text += "Bu oy xarajat yo'q."
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_kafolat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    conn = db(); c = conn.cursor()
    today_str = today()
    c.execute("SELECT * FROM warranties WHERE status='active' ORDER BY end_date")
    rows = c.fetchall(); conn.close()
    if not rows:
        await u.message.reply_text("🔧 *Kafolat*\n\nFaol kafolat yo'q.", parse_mode='Markdown')
        return
    text = "🔧 *KAFOLAT KUZATISH*\n\n"
    expiring = []
    for r in rows:
        days_left = (datetime.strptime(r[5],'%Y-%m-%d') - datetime.strptime(today_str,'%Y-%m-%d')).days
        e = "🔴" if days_left <= 0 else "🟡" if days_left <= 14 else "🟢"
        if days_left <= 30: expiring.append((r, days_left))
        text += f"{e} {r[2]}"
        if r[3]: text += f" ({r[3]})"
        text += f"\n  📅 {r[4]} → {r[5]}"
        if days_left > 0: text += f" ({days_left} kun qoldi)"
        else: text += " (tugagan!)"
        text += "\n\n"
    if expiring:
        text += f"⚠️ {len(expiring)} ta kafolat yaqin tugaydi!"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_cashflow(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    cf = cash_flow_forecast()
    text = "💵 *CASH FLOW PROGNOZ (30 kun)*\n\n"
    text += f"📈 Kutilayotgan tushum: *{fmt(cf['expected_30day'])}*\n"
    text += f"🏭 Kreditorlik — biz zavodga qarzmiz: −{fmt(cf['transit_to_pay'])}\n"
    text += f"📥 Debitorlik (mijozlar bizga qarz): +{fmt(cf['debts_to_receive'])}\n"
    if cf['debts_to_pay']:
        text += f"📤 Kreditorlik — boshqa (biz qarzmiz): −{fmt(cf['debts_to_pay'])}\n"
    text += "──────────────────────\n"
    net = cf['net_forecast']
    emoji = "✅" if net > 0 else "❌"
    text += f"{emoji} *Prognoz qoldi: {fmt(net)}*\n\n"
    text += f"_O'rtacha oylik tushum: {fmt(cf['avg_monthly_revenue'])}_"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_trend(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    months, change = get_sales_trend()
    text = "📈 *SAVDO TRENDI*\n\n"
    for m in months:
        month_label = m['month']
        text += f"📅 {month_label}: {fmt(m['rev'])} | foyda: {fmt(m['profit'])}\n"
    emoji = "📈" if change > 0 else "📉"
    text += f"\n{emoji} O'zgarish: *{change:+.1f}%*\n"
    if change > 10: text += "💪 Yaxshi o'sish!"
    elif change > 0: text += "✅ O'sish bor"
    elif change > -10: text += "⚠️ Biroz kamaydi"
    else: text += "❌ Sezilarli kamayish — sabab tekshiring!"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_rate(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    rate = get_exchange_rate()
    prods = get_products()
    text = "💱 *VALYUTA KURSI*\n\n"
    text += f"1 USD = *{rate:,.0f} so'm* (CBU)\n\n"
    text += "*Asosiy tovarlar UZS da:*\n"
    for p in prods[:5]:
        text += f"• {p['name']}: *{p['price']*rate:,.0f} so'm*\n"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_maqsad(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    conn = db(); c = conn.cursor()
    now = datetime.now()
    c.execute('SELECT * FROM targets WHERE year=? AND month=?', (now.year, now.month))
    tgt = c.fetchone(); conn.close()
    sales = get_sales(this_month())
    exps_period = get_expenses(this_month(), 'period')
    tR = sum(s[6] for s in sales)
    tCOGS = sum(s[5]*s[4] for s in sales)
    tCogsEx = sum(e[2] for e in (get_expenses(this_month(),'cogs_bank')+get_expenses(this_month(),'cogs_delivery')))
    tPeriod = sum(e[2] for e in exps_period)
    sof = tR - tCOGS - tCogsEx - tPeriod
    text = f"🎯 *OYLIK MAQSAD — {now.strftime('%B %Y')}*\n\n"
    if tgt:
        rpct = tR/tgt[3]*100 if tgt[3] else 0
        ppct = sof/tgt[4]*100 if tgt[4] else 0
        rb = max(0, min(10, int(rpct/10))); pb = max(0, min(10, int(ppct/10)))
        r_bar = "█" * rb + "░" * (10 - rb)
        p_bar = "█" * pb + "░" * (10 - pb)
        text += f"💵 Tushum: {rpct:.0f}%\n`{r_bar}` {fmt(tR)}/{fmt(tgt[3])}\n\n"
        text += f"✅ Foyda: {ppct:.0f}%\n`{p_bar}` {fmt(sof)}/{fmt(tgt[4])}\n\n"
        # dekabrda keyingi oy — KEYINGI yilning yanvari (avval shu yil yanvari olinib, kunlar manfiy chiqardi)
        days = (datetime(now.year + (now.month == 12), now.month % 12 + 1, 1) - now).days
        need_daily = (tgt[3]-tR)/days if days>0 and tgt[3]>tR else 0
        text += f"⏰ {days} kun qoldi | Kuniga: *{fmt(need_daily)}* kerak"
    else:
        text += f"Hozir:\nTushum: *{fmt(tR)}*\nFoyda: *{fmt(sof)}*\n\n"
        text += "_Maqsad qo'yish: '3000 dollar maqsad' deb yozing_"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_olx(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    conn = db(); c = conn.cursor()
    c.execute("SELECT * FROM olx_listings ORDER BY last_updated")
    rows = c.fetchall(); conn.close()
    text = "📢 *OLX HOLATI*\n\n"
    prods = get_products()
    today_str = today()
    for p in prods:
        listing = next((r for r in rows if r[1]==p['name']), None)
        if listing:
            days = (datetime.strptime(today_str,'%Y-%m-%d') - datetime.strptime(listing[2],'%Y-%m-%d')).days
            e = "🔴" if days>=7 else "🟡" if days>=3 else "🟢"
            text += f"{e} {p['name']}: {days} kun — {listing[3]} qo'ng'iroq\n"
        else:
            text += f"⚪ {p['name']}: E'lon yo'q\n"
    text += "\n_'TTS 20 Pro OLX yangilandi 2 qongiroq keldi' deb yozing_"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_raqobat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Raqobat tahlili — bizning narx vs bozor"""
    if not can(u, 'boshqaruv'): return
    since = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    conn = db(); c = conn.cursor()
    c.execute("SELECT product,competitor,their_price,date,note FROM competitors WHERE date>=? ORDER BY date DESC", (since,))
    rows = c.fetchall(); conn.close()
    if not rows:
        await u.message.reply_text(
            "\U0001F50D RAQOBAT TAHLILI\n\nHali ma'lumot yo'q.\n\n"
            "Qo'shish uchun shunchaki yozing:\n"
            "\u2022 apexmach TTS 20 Pro ni 470 ga sotyapti\n"
            "\u2022 CNC3018 bozorda qancha turibdi? (o'zim qidiraman)")
        return

    by = defaultdict(list)
    for r in rows: by[r[0]].append(r)
    text = "\U0001F50D RAQOBAT TAHLILI (90 kun)\n\n"
    ogoh = []
    for pname, lst in sorted(by.items()):
        prices = [r[2] for r in lst if r[2] and r[2] > 0]
        if not prices: continue
        p = find_product(pname)
        mn, mx = min(prices), max(prices)
        avg = sum(prices) / len(prices)
        our  = p['price'] if p else 0
        cost = p['cost'] if p else 0
        qty  = p['qty'] if p else 0
        if not our:        mark, holat = "\u26AA", "bizda yo'q"
        elif our <= mn:    mark, holat = "\U0001F7E2", "eng arzon"
        else:              mark, holat = "\U0001F534", "biz qimmat"
        text += f"{mark} {pname}" + (f"  ({qty} ta)\n" if p else "\n")
        if our: text += f"   Biz: {fmt(our)} \u2022 {holat}\n"
        text += f"   Bozor: {fmt(mn)} \u2013 {fmt(mx)} (o'rt. {fmt(avg)})\n"
        for r in lst[:3]:
            text += f"   \u2022 {r[1]}: {fmt(r[2])} ({r[3][5:]})\n"
        if our and cost:
            text += f"   Marja: {fmt(our-cost)}"
            if our > mn:
                text += f" \u2192 {fmt(mn)} ga tushsa {fmt(mn-cost)}"
                if qty > 0: ogoh.append(f"{pname}: bozor {fmt(mn)}, biz {fmt(our)}")
            text += "\n"
        text += "\n"

    if ogoh:
        text += "\u26A0\uFE0F Astatkada bor, bizdan arzonrog'i ham bor:\n"
        for o in ogoh[:5]: text += f"\u2022 {o}\n"
    await u.message.reply_text(text)

async def cmd_undo_list(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    ops = get_last_ops(8)
    if not ops:
        await u.message.reply_text("↩️ Qaytarish uchun operatsiya yo'q.", parse_mode='Markdown')
        return
    text = "↩️ *OXIRGI OPERATSIYALAR*\n\n"
    kb = []
    for op in ops:
        data = json.loads(op[4])
        label = f"#{op[0]} [{op[1]} {op[2]}] {op[3]}: "
        if op[3] == 'sale': label += f"{data.get('product','')} {fmt(data.get('price',0)*data.get('qty',1))}"
        elif op[3] == 'expense': label += f"{data.get('note','')} {fmt(data.get('amount',0))}"
        elif op[3] == 'transit': label += f"{data.get('product','')} {fmt(data.get('total',0))}"
        elif op[3] == 'debt_payment': label += f"{data.get('kind','')} {data.get('person','')} {fmt(data.get('amount',0))}"
        elif op[3] == 'return': label += f"qaytarish R-{data.get('rid','')} {data.get('product','')[:40]} {fmt(data.get('jami',0))}"
        elif op[3] == 'stock': label += (f"ombor {data.get('kind','')} {data.get('product','')} {data.get('qty','')}"
                                         if data.get('kind') != 'inventar' else f"inventarizatsiya {len(data.get('qatorlar', []))} ta")
        else: label += str(data)[:30]
        text += f"{label}\n"
        kb.append([InlineKeyboardButton(f"↩️ #{op[0]} qayt", callback_data=f"undo_{op[0]}")])
    kb.append([InlineKeyboardButton("❌ Yopish", callback_data='close')])
    await u.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def cmd_katalog(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    args = ctx.args
    if not args:
        await u.message.reply_text("Foydalanish: /katalog TTS 20 Pro")
        return
    name = ' '.join(args)
    prod = find_product(name)
    if not prod:
        await u.message.reply_text(f"❓ Topilmadi: {name}")
        return
    photos = get_product_photos(prod['id'])
    specs = get_product_specs(prod['id'])
    if photos:
        media = [InputMediaPhoto(media=fid) for fid in photos[:10]]
        await u.message.reply_media_group(media)
    margin = prod['price'] - prod['cost']
    text = f"📋 *{prod['name']}*\n\n"
    if specs:
        for sname, sval in specs:
            text += f"*{sname}:* {sval}\n"
        text += "\n"
    text += f"🏭 Zavod: {fmt(prod['factory'])} | 📦 Sebest: {fmt(prod['cost'])}\n"
    pct = margin/prod['price']*100 if prod['price'] else 0
    text += f"💵 Narx: *{fmt(prod['price'])}* | ✅ Marja: {fmt(margin)} ({pct:.0f}%)\n"
    text += f"📦 Astatka: {prod['qty']} ta"
    kb = [[InlineKeyboardButton("📸 Rasm qo'sh", callback_data=f"add_photo_{prod['id']}"),
           InlineKeyboardButton("✏️ Specs tahrirlash", callback_data=f"edit_specs_{prod['id']}")]]
    await u.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def cmd_yordam(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if user_role(u) == 'sotuvchi':
        return await cmd_yordam_sotuvchi(u, ctx)
    if not can(u, 'boshqaruv'): return
    text = (
        "📋 *Buyruqlar:*\n"
        "/astatka /narxlar /bugun /oy /yil\n"
        "/yolda /zavod_qarz /analiz /xarajatlar\n"
        "/mijozlar /qarzlar /kafolat /cashflow\n"
        "/qarz\\_tolov /zavod\\_tolov /qarz\\_yosh\n"
        "/trend /rate /maqsad /olx /undo\n"
        "/katalog [nom] /yangi_tovar\n\n"
        "🛒 *Tugmali sotuv:* /sotuv yoki 🛒 Sotuv tugmasi\n"
        "📦 *Ombor:* /ombor · kam qolganlar: /kam\n"
        "👥 *Mijozlar:* 👥 Mijozlar tugmasi · qarzdorlar: /qarzdorlar\n"
        "📊 *Hisobotlar:* /hisobotlar · 🏭 *Zavod buyurtmalari:* /zavod\n"
        "📢 *Marketing:* /marketing — video/rasm yuboring → tovar → ko'rinish → kanal/Instagram\n"
        "📥 *Qaytarish:* /qaytarish · 🧾 *Smena (kassa yopish):* /smena\n"
        "🔢 *Serial/kafolat:* /serial · 🏷 *Yorliqlar (shtrix-kod/QR):* /yorliq · 💾 *Zaxira:* /zaxira\n"
        "⚙️ Boshqa — eski to'liq menyu\n"
        "👷 *Xodimlar:* /xodim\\_qosh /xodimlar /xodim\\_ochir\n"
        "📊 Sotuvchilar hisoboti: /sotuvchilar · ID bilish: /id\n\n"
        "*Erkin yozish:*\n\n"
        "💰 *Sotuv:*\n`TTS 20 Pro sotdim 470 ga`\n"
        "`Sotuv tts 20 pro + honeycomb 400 + pump 470$ ga`\n"
        "`Ahmadga 10% chegirma bilan P8100 ketdi`\n\n"
        "📥 *Excel:* oylik jadval (.xlsx) faylini shu chatga yuboring — astatka, sotuv, xarajat va kassa "
        "Excel bo'yicha yangilanadi (tasdiqlashdan oldin ko'rsatadi). Boshqa oy: izohga `2026-08`, hammasi: `hammasi`.\n\n"
        "🚚 *Yo'lda:*\n`Two Trees ga TTS 20 Pro 3 ta zakaz berdim 280 dan, 200 deposit`\n"
        "`Zakaz #1 keldi`\n`Two Trees ga 300 dollar to'ladim`\n\n"
        "💸 *Xarajat:*\n`Bank to'lovi 45 dollar`\n"
        "`Abusaxiy dostavka 110 dollar`\n`OLX reklama 33 dollar`\n\n"
        "👥 *Mijoz:*\n`Jahongir B2B mijoz qo'sh 998901234567`\n\n"
        "💳 *Qarz:*\n`Alibek 200 dollar qarz oldi`\n"
        "`/qarz_tolov Alibek 150 karta` — mijoz qarzini to'ladi\n"
        "`/zavod_tolov Two Trees 300` — zavodga to'ladik\n"
        "`Alibek qarzidan 100 dollar qaytardi`\n\n"
        "🎯 *Maqsad:*\n`Bu oy 3000 dollar maqsad 800 foyda`\n\n"
        "📊 *Tahlil:*\n`ABC XYZ tahlil` | `Trend` | `Cash flow`\n"
        "`TTS 20 Pro katalog` | `apexmach TTS 20 490 raqobatchi`\n"
        "`OLX TTS 20 yangilandi 2 qongiroq`"
    )
    await u.message.reply_text(text, parse_mode='Markdown')


# ── YANGI TOVAR QOSHISH (ConversationHandler) ─────────────────────
async def conv_start(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return ConversationHandler.END
    if u.callback_query:
        await u.callback_query.answer()
    ctx.user_data.clear()
    await u.effective_message.reply_text(
        "➕ *Yangi tovar qo'shish*\n\nMahsulot nomini yozing:",
        parse_mode='Markdown')
    return S_NAME

async def conv_name(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['name'] = u.message.text.strip()
    kb = [[InlineKeyboardButton("Lazer", callback_data='cat_Lazer'),
           InlineKeyboardButton("CNC", callback_data='cat_CNC')],
          [InlineKeyboardButton("Press", callback_data='cat_Press'),
           InlineKeyboardButton("Qog'oz", callback_data="cat_Qog'oz")]]
    await u.message.reply_text("Kategoriya:", reply_markup=InlineKeyboardMarkup(kb))
    return S_CAT

async def conv_cat_cb(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    ctx.user_data['cat'] = u.callback_query.data.replace('cat_','')
    kb = [[InlineKeyboardButton("Two Trees", callback_data='sup_Two Trees'),
           InlineKeyboardButton("Freesub", callback_data='sup_Freesub')],
          [InlineKeyboardButton("Boshqa", callback_data='sup_Boshqa')]]
    await u.callback_query.message.reply_text("Yetkazuvchi:", reply_markup=InlineKeyboardMarkup(kb))
    return S_SUP

async def conv_sup_cb(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    ctx.user_data['sup'] = u.callback_query.data.replace('sup_','')
    await u.callback_query.message.reply_text("Zavod narxi ($):")
    return S_COST

async def conv_cost(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try: ctx.user_data['factory'] = float(u.message.text.replace('$','').strip())
    except ValueError: await u.message.reply_text("Raqam kiriting:"); return S_COST
    await u.message.reply_text("Sotuv narxi ($):")
    return S_PRICE

async def conv_price(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try: ctx.user_data['price'] = float(u.message.text.replace('$','').strip())
    except ValueError: await u.message.reply_text("Raqam kiriting:"); return S_PRICE
    ctx.user_data['cost'] = ctx.user_data['factory']
    await u.message.reply_text("Boshlang'ich miqdor (dona):")
    return S_QTY

async def conv_qty(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try: ctx.user_data['qty'] = int(u.message.text.strip())
    except ValueError: await u.message.reply_text("Raqam kiriting:"); return S_QTY
    await u.message.reply_text(
        "Texnik ma'lumotlar qo'shing:\n"
        "Har qatorga: `Xususiyat: Qiymat`\n"
        "Masalan:\n`Quvvat: 20W`\n`Og'irlik: 3 kg`\n\n"
        "Tugatish uchun: /tayyor", parse_mode='Markdown')
    ctx.user_data['specs'] = []
    return S_SPECS

async def conv_specs(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    line = u.message.text.strip()
    if ':' in line:
        parts = line.split(':', 1)
        ctx.user_data['specs'].append((parts[0].strip(), parts[1].strip()))
        await u.message.reply_text(f"✅ {parts[0].strip()} qo'shildi. Davom eting yoki /tayyor")
    else:
        await u.message.reply_text("Format: `Xususiyat: Qiymat`", parse_mode='Markdown')
    return S_SPECS

async def conv_specs_done(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("📸 Ha, rasm qo'shaman", callback_data='photos_yes'),
           InlineKeyboardButton("Keyinroq", callback_data='photos_no')]]
    await u.message.reply_text("Rasmlar qo'shasizmi? (8-10 ta)",
                                reply_markup=InlineKeyboardMarkup(kb))
    return S_PHOTOS

async def conv_photos_cb(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await u.callback_query.answer()
    if u.callback_query.data == 'photos_yes':
        ctx.user_data['photos'] = []
        await u.callback_query.message.reply_text(
            "Rasmlarni yuboring (8-10 ta)\nTugatish: /tayyor")
        return S_PHOTOS
    else:
        return await save_new_product(u.callback_query.message, ctx)

async def conv_photo(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if u.message.photo:
        file_id = u.message.photo[-1].file_id
        ctx.user_data.setdefault('photos', []).append(file_id)
        count = len(ctx.user_data['photos'])
        await u.message.reply_text(f"✅ Rasm {count} qo'shildi. Davom eting yoki /tayyor")
    return S_PHOTOS

async def conv_finish(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await save_new_product(u.message, ctx)

async def save_new_product(msg, ctx):
    d = ctx.user_data
    pid = add_product(
        d['name'], d.get('cat','Lazer'), d.get('sup','Boshqa'),
        d.get('qty',0), d.get('cost',0), d.get('price',0),
        d.get('factory',0)
    )
    if not pid:
        await msg.reply_text("❌ Xatolik! Bu nomda mahsulot allaqachon bor.")
        return ConversationHandler.END
    for sname, sval in d.get('specs',[]):
        add_spec(pid, sname, sval)
    for fid in d.get('photos',[]):
        add_photo(pid, fid)
    margin = d.get('price',0) - d.get('cost',0)
    await msg.reply_text(
        f"✅ *{d['name']} qo'shildi!*\n\n"
        f"📦 Astatka: {d.get('qty',0)} ta\n"
        f"🏭 Zavod: {fmt(d.get('factory',0))}\n"
        f"💵 Narx: {fmt(d.get('price',0))}\n"
        f"✅ Marja: {fmt(margin)}\n"
        f"📋 Specs: {len(d.get('specs',[]))} ta\n"
        f"📸 Rasmlar: {len(d.get('photos',[]))} ta",
        parse_mode='Markdown')
    ctx.user_data.clear()
    return ConversationHandler.END

async def conv_cancel(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await u.message.reply_text("❌ Bekor qilindi.")
    return ConversationHandler.END


# ── CALLBACK HANDLER ──────────────────────────────────────────────
# ── 🛒 TUGMALI SOTUV (POS) ────────────────────────────────────────
# Holat: ctx.user_data['pos'] (har foydalanuvchiga alohida). Faqat tugmalar; yozish — qidiruv, son, narx.
# Saqlash: pos_saqlash() — butun savat bitta tranzaksiyada. Tasdiq ikki marta bosilsa ham bir marta yoziladi.
POS_TTL = 1800                     # 30 daqiqa harakatsiz qolsa savat eskiradi
POS_SAHIFA = 8
POS_SONLAR = (1, 2, 3, 5, 10)
POS_CHEGIRMALAR = (3, 5, 10, 15, 20)
POS_USULLAR = (('naqd', '💵 Naqd'), ('karta', '💳 Karta'), ('payme', '📱 Payme'),
               ('click', '📱 Click'), ('otkazma', "🏦 O'tkazma"), ('nasiya', '📝 Nasiya'))
POS_USUL_NOMI = dict(POS_USULLAR)
SOTUVCHI_KB = [["🛒 Sotuv", "📦 Qoldiq"], ["📦 Ombor", "👥 Mijozlar"], ["📥 Qaytarish", "🧾 Smena"],
               ["📋 Bugungi sotuvlarim", "❓ Yordam"]]

def _btn(t, d): return InlineKeyboardButton(t, callback_data=d)
def _pos_bekor(): return [_btn("❌ Bekor qilish", "pos:x")]
def _pos_savat_btn(pos):
    return [_btn(f"🧺 Savat ({len(pos['items'])})", "pos:cart")] if pos.get('items') else []

def _pos_yangi(ctx):
    pos = {'id': secrets.token_hex(4), 'ts': time.time(), 'items': [], 'disc': None,
           'cust': None, 'method': None, 'wait': None, 'found': [], 'cats': []}
    ctx.user_data['pos'] = pos
    return pos

def _pos_ol(ctx):
    """Joriy savat; muddati o'tgan bo'lsa o'chiriladi va None qaytadi."""
    pos = ctx.user_data.get('pos')
    if not pos: return None
    if time.time() - pos.get('ts', 0) > POS_TTL:
        ctx.user_data.pop('pos', None)
        return None
    pos['ts'] = time.time()
    return pos

def _pos_son(s):
    """'450', '450$', '1 250,5' → float; so'm (>=5000) → $ ga o'tkaziladi. Xato → None."""
    t = re.sub(r'[^\d.,]', '', str(s or '')).replace(',', '.')
    if not t or t.count('.') > 1: return None
    try: v = float(t)
    except ValueError: return None
    return _to_usd(v, 0, get_exchange_rate()) if v >= 5000 else v

def _pos_mahsulot(pid):
    return next((p for p in get_products() if p['id'] == pid), None)

def _pos_mavjud(pos, pid, qty_db, bundan_tashqari=False):
    """Astatka minus savatdagi (o'zgartirilayotgan qator hisobga olinmasin desa — bundan_tashqari)."""
    band = 0 if bundan_tashqari else sum(i['qty'] for i in pos['items'] if i['pid'] == pid)
    return (qty_db or 0) - band

def _pos_qator(pos, pid):
    return next((i for i in pos['items'] if i['pid'] == pid), None)

def pos_hisob(pos):
    """Savat hisobi: qatorlar (base, final, unit, disc%), oraliq, chegirma, jami, samarali chegirma %."""
    its = pos['items']
    base = [round(i['price'] * i['qty'], 2) for i in its]
    sub = round(sum(base), 2)
    royxat = round(sum(i['list'] * i['qty'] for i in its), 2)
    dsc = pos.get('disc'); D = 0.0
    if dsc and sub > 0:
        D = round(sub * dsc['val'] / 100, 2) if dsc['type'] == 'pct' else round(min(dsc['val'], sub), 2)
    jami = round(sub - D, 2)
    finals = _taqsimla(jami, base) if its else []
    lines = []
    for i, b, f in zip(its, base, finals, strict=True):
        unit = f / i['qty']
        disc = round((1 - unit / i['list']) * 100, 1) if i['list'] > 0 else 0.0
        lines.append(dict(i, base=b, final=f, unit=unit, disc=max(0.0, disc)))
    eff = round((1 - jami / royxat) * 100, 2) if royxat > 0 else 0.0
    return {'lines': lines, 'sub': sub, 'D': D, 'jami': jami, 'royxat': royxat, 'eff': eff}

def pos_limit_xato(pos, x):
    """Sotuvchi chegirma limitidan oshsa — xato matni, aks holda None (egasi/admin — cheklovsiz)."""
    if not x or x['role'] != 'sotuvchi': return None
    mx = float(x['max_discount'])
    h = pos_hisob(pos)
    for ln in h['lines']:
        eng_past = ln['list'] * (1 - mx / 100)
        if ln['list'] > 0 and ln['unit'] < eng_past - 0.005:
            return f"Chegirma limiti {mx:g}%. {ln['name']} uchun eng past narx {_usd2(eng_past)}"
    if h['eff'] > mx + 0.01:
        return f"Chegirma limiti {mx:g}% (hozir {h['eff']:.1f}%)"
    return None

def pos_savat_matn(pos, rate):
    h = pos_hisob(pos)
    out = ["🧺 Savat:"]
    if not h['lines']: out.append("(bo'sh)")
    for n, ln in enumerate(h['lines'], 1):
        out.append(f"{n}. {ln['name']} × {ln['qty']} = {_usd2(ln['base'])}")
        if ln.get('sn'): out.append("   SN: " + ", ".join(ln['sn']))
        if abs(ln['price'] - ln['list']) > 0.004:
            out.append(f"   narx {_usd2(ln['price'])}/dona (ro'yxatda {_usd2(ln['list'])})")
    out.append("──────────────")
    if h['D'] > 0:
        dsc = pos['disc']
        foiz = f" ({dsc['val']:g}%)" if dsc['type'] == 'pct' else ""
        out.append(f"Oraliq: {_usd2(h['sub'])}")
        out.append(f"Chegirma: −{_usd2(h['D'])}{foiz}")
    out.append(f"JAMI: {_usd2(h['jami'])} ≈ {h['jami'] * rate:,.0f} so'm")
    cust = pos.get('cust')
    out.append("👤 Mijoz: " + (f"{cust['name']}" + (f" ({cust['phone']})" if cust.get('phone') else "")
                              if cust else "oddiy xaridor"))
    if pos.get('method'):
        out.append("💳 To'lov: " + POS_USUL_NOMI.get(pos['method'], pos['method']))
    return "\n".join(out), h

# ── Ekranlar: (matn, tugmalar) ──
def pos_ekran_kategoriya(pos):
    prods = get_products()
    cats = sorted({(p['cat'] or 'Boshqa') for p in prods})
    pos['cats'] = cats
    rows, row = [], []
    for i, cn in enumerate(cats):
        n = sum(1 for p in prods if (p['cat'] or 'Boshqa') == cn)
        row.append(_btn(f"{cn[:24]} ({n})", f"pos:k:{i}:0"))
        if len(row) == 2: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([_btn("🔍 Qidirish", "pos:s"), _btn("📋 Hammasi", "pos:k:-1:0")])
    if pos['items']: rows.append(_pos_savat_btn(pos))
    rows.append(_pos_bekor())
    return "🛒 Sotuv — kategoriyani tanlang (yoki 🔍 Qidirish)", rows

def _pos_royxat(pos, prods, sarlavha, page, nav_prefix):
    prods = sorted(prods, key=lambda p: (_pos_mavjud(pos, p['id'], p['qty']) <= 0, p['name']))
    pages = max(1, math.ceil(len(prods) / POS_SAHIFA))
    page = min(max(0, page), pages - 1)
    rows = []
    for p in prods[page * POS_SAHIFA:(page + 1) * POS_SAHIFA]:
        q = _pos_mavjud(pos, p['id'], p['qty'])
        belgi = "❌ " if q <= 0 else ""
        rows.append([_btn(f"{belgi}{p['name'][:28]} · {max(q, 0)} ta · {_usd2(p['price'] or 0)}", f"pos:p:{p['id']}")])
    if pages > 1:
        nav = []
        if page > 0: nav.append(_btn("⬅️", f"{nav_prefix}:{page - 1}"))
        nav.append(_btn(f"{page + 1}/{pages}", "pos:noop"))
        if page < pages - 1: nav.append(_btn("➡️", f"{nav_prefix}:{page + 1}"))
        rows.append(nav)
    rows.append([_btn("🔍 Qidirish", "pos:s"), _btn("⬅️ Kategoriyalar", "pos:cats")])
    if pos['items']: rows.append(_pos_savat_btn(pos))
    rows.append(_pos_bekor())
    matn = f"🛒 {sarlavha} — mahsulotni tanlang" + ("\n❌ — astatkada yo'q" if any(
        _pos_mavjud(pos, p['id'], p['qty']) <= 0 for p in prods) else "")
    if not prods: matn = f"🛒 {sarlavha}: hech narsa topilmadi"
    return matn, rows

def pos_ekran_mahsulotlar(pos, ci, page):
    prods = get_products()
    cats = pos.get('cats') or sorted({(p['cat'] or 'Boshqa') for p in prods})
    if 0 <= ci < len(cats):
        sel = [p for p in prods if (p['cat'] or 'Boshqa') == cats[ci]]; nom = cats[ci]
    else:
        sel = prods; nom = "Hammasi"
    return _pos_royxat(pos, sel, nom, page, f"pos:k:{ci}")

def pos_qidir(q):
    prods = get_products()
    p, cands = match_product(q, prods=prods)
    nomlar = [p['name']] if p else [c_['name'] for c_ in (cands or [])]
    n = _nrm(q)
    for x in prods:
        if n and n in _nrm(x['name']) and x['name'] not in nomlar: nomlar.append(x['name'])
    by = {x['name']: x for x in prods}
    return [by[nm] for nm in nomlar if nm in by][:40]

def pos_ekran_qidiruv(pos, page=0):
    prods = [p for p in get_products() if p['id'] in set(pos.get('found') or [])]
    return _pos_royxat(pos, prods, "Qidiruv natijasi", page, "pos:f")

def pos_ekran_son(pos, p, rate):
    q = _pos_mavjud(pos, p['id'], p['qty'])
    bor = _pos_qator(pos, p['id'])
    matn = (f"📦 {p['name']}\nNarx: {_usd2(p['price'] or 0)} ≈ {(p['price'] or 0) * rate:,.0f} so'm\n"
            f"Sotsa bo'ladi: {max(q, 0)} ta" + (f" (savatda {bor['qty']} ta bor)" if bor else "") + "\n\nNechta?")
    btns = [_btn(str(n), f"pos:q:{p['id']}:{n}") for n in POS_SONLAR if n <= q]
    rows = [btns] if btns else []
    rows.append([_btn("✍️ Boshqa son", f"pos:qc:{p['id']}")])
    rows.append([_btn("⬅️ Orqaga", "pos:cats")] + _pos_savat_btn(pos))
    rows.append(_pos_bekor())
    return matn, rows

def pos_ekran_savat(pos, rate, izoh=''):
    if not pos['items']:
        m, r = pos_ekran_kategoriya(pos)
        return ((izoh + "\n\n") if izoh else "") + "🧺 Savat bo'sh.\n" + m, r
    matn, _ = pos_savat_matn(pos, rate)
    rows = [[_btn("➕ Yana tovar", "pos:cats"), _btn("✏️ Tahrirlash", "pos:ed")],
            [_btn("💸 Chegirma", "pos:d"), _btn("👤 Mijoz", "pos:mj")],
            [_btn("💳 To'lov", "pos:pay")],
            _pos_bekor()]
    return ((izoh + "\n\n") if izoh else "") + matn, rows

def pos_ekran_tahrir(pos):
    rows = [[_btn(f"{n}. {i['name'][:28]} × {i['qty']}", f"pos:e:{i['pid']}")] for n, i in enumerate(pos['items'], 1)]
    rows.append([_btn("⬅️ Savat", "pos:cart")])
    rows.append(_pos_bekor())
    return "✏️ Qaysi qatorni o'zgartirasiz?", rows

def pos_ekran_qator(pos, it, x):
    matn = (f"✏️ {it['name']}\nSoni: {it['qty']} ta\nNarx: {_usd2(it['price'])}/dona"
            f" (ro'yxatda {_usd2(it['list'])})\nQator: {_usd2(it['price'] * it['qty'])}")
    if x and x['role'] == 'sotuvchi':
        matn += f"\n\nSizning chegirma limitingiz: {x['max_discount']:g}%"
    rows = [[_btn("➖ 1", f"pos:ei:{it['pid']}:-1"), _btn("➕ 1", f"pos:ei:{it['pid']}:1")],
            [_btn("✍️ Soni", f"pos:eq:{it['pid']}"), _btn("✍️ Narx", f"pos:ep:{it['pid']}")],
            [_btn("🗑 O'chirish", f"pos:er:{it['pid']}")],
            [_btn("⬅️ Savat", "pos:cart")], _pos_bekor()]
    return matn, rows

def pos_ekran_chegirma(pos, x, rate):
    matn, h = pos_savat_matn(pos, rate)
    mx = float(x['max_discount']) if x and x['role'] == 'sotuvchi' else None
    matn = "💸 Chegirma\n\n" + matn + (f"\n\nSizning limitingiz: {mx:g}%" if mx is not None else "")
    btns = [_btn(f"{p}%", f"pos:dv:{p}") for p in POS_CHEGIRMALAR if mx is None or p <= mx + 1e-9]
    rows = [btns[i:i + 3] for i in range(0, len(btns), 3)]
    rows.append([_btn("✍️ Foiz (%)", "pos:dp"), _btn("✍️ Summa ($)", "pos:du")])
    if pos.get('disc'): rows.append([_btn("🚫 Chegirmani olib tashlash", "pos:d0")])
    rows.append([_btn("⬅️ Savat", "pos:cart")])
    rows.append(_pos_bekor())
    return matn, rows

def _pos_oxirgi_mijozlar(n=6):
    conn = db(); c = conn.cursor()
    try:
        c.execute("SELECT c.id, c.name, c.phone FROM sales s JOIN customers c ON c.id=s.customer_id "
                  "WHERE s.customer_id>0 GROUP BY c.id ORDER BY MAX(s.id) DESC LIMIT ?", (n,))
        rows = c.fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    if not rows:
        rows = [(m['id'], m['nom'], m['tel']) for m in mijoz_qidir('')[:n]]
    return [{'id': r[0], 'name': r[1], 'phone': r[2] or ''} for r in rows]

def pos_ekran_mijoz(pos, royxat=None, sarlavha=None):
    royxat = _pos_oxirgi_mijozlar() if royxat is None else royxat
    matn = ("📝 Nasiya uchun mijozni tanlang (majburiy)\n\n" if pos.get('method') == 'nasiya' and not pos.get('cust') else "")
    matn += (sarlavha or "👤 Mijoz — oxirgi xaridorlar:") + ("" if royxat else "\n(topilmadi)")
    rows = [[_btn(f"{m['name'][:30]}" + (f" · {m['phone'][-4:]}" if m.get('phone') else ""), f"pos:mc:{m['id']}")]
            for m in royxat[:8]]
    rows.append([_btn("🔍 Qidirish", "pos:ms"), _btn("➕ Yangi mijoz", "pos:mn")])
    if pos.get('method') != 'nasiya':
        rows.append([_btn("🚶 Mijozsiz (oddiy xaridor)", "pos:mw")])
    rows.append([_btn("⬅️ Savat", "pos:cart")])
    rows.append(_pos_bekor())
    return matn, rows

def pos_ekran_tolov(pos, rate):
    matn, _ = pos_savat_matn(pos, rate)
    btns = [_btn(nom, f"pos:m:{k}") for k, nom in POS_USULLAR]
    rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
    rows.append([_btn("⬅️ Savat", "pos:cart")])
    rows.append(_pos_bekor())
    return "💳 To'lov usulini tanlang\n\n" + matn, rows

def pos_ekran_tasdiq(pos, rate):
    matn, _ = pos_savat_matn(pos, rate)
    if pos.get('method') == 'nasiya':
        matn += "\n\n📝 Nasiya: kassaga tushmaydi, mijoz qarzi (debitorlik) yoziladi."
    rows = [[_btn("✅ Tasdiqlash", f"pos:ok:{pos['id']}")],
            [_btn("⬅️ Savat", "pos:cart"), _btn("💳 Usul", "pos:pay")],
            _pos_bekor()]
    return "✅ Tekshiring va tasdiqlang\n\n" + matn, rows

def pos_chek_matn(res, h, pos, x, rate):
    s0 = res['sales'][0]['sale_id']
    out = [f"🧾 CHEK №S-{s0}", now_t(), f"Sotuvchi: {x['name']}"]
    cust = pos.get('cust')
    if cust: out.append(f"Mijoz: {cust['name']}" + (f" ({cust['phone']})" if cust.get('phone') else ""))
    out.append("──────────────")
    for n, (ln, sv) in enumerate(zip(h['lines'], res['sales'], strict=True), 1):
        out.append(f"{n}. {ln['name']} × {ln['qty']} = {_usd2(sv['summa'])}")
        out.append(f"   {_usd2(ln['unit'])}/dona" + (f", −{ln['disc']:g}%" if ln['disc'] >= 0.1 else ""))
        if ln.get('sn'): out.append("   SN: " + ", ".join(ln['sn']))
    out.append("──────────────")
    if h['D'] > 0:
        out.append(f"Oraliq: {_usd2(h['sub'])}")
        out.append(f"Chegirma: −{_usd2(h['D'])}")
    out.append(f"JAMI: {_usd2(res['jami'])} ≈ {res['jami'] * rate:,.0f} so'm")
    out.append("To'lov: " + POS_USUL_NOMI.get(pos['method'], pos['method']))
    if pos['method'] == 'nasiya':
        out.append(f"📝 Mijoz qarzi (debitorlik): {_usd2(res['jami'])}")
    out.append("Rahmat! 🙏")
    return "\n".join(out)

async def _pos_chiqar(q, matn, rows):
    """Callback xabarini tahrirlaydi (bo'lmasa yangi xabar)."""
    mk = InlineKeyboardMarkup(rows) if rows else None
    try:
        await q.edit_message_text(matn[:4000], reply_markup=mk)
    except BadRequest as e:
        if 'not modified' in str(e).lower(): return
        await q.message.reply_text(matn[:4000], reply_markup=mk)

async def pos_start(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/sotuv va 🛒 Sotuv tugmasi"""
    if not can(u, 'pos'): return
    pos = _pos_ol(ctx)
    if pos and pos['items']:
        pos['wait'] = None
        m, r = pos_ekran_savat(pos, get_exchange_rate(), "↪️ Oldingi savat davom etmoqda")
    else:
        pos = _pos_yangi(ctx)
        m, r = pos_ekran_kategoriya(pos)
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))

def _pos_qosh(pos, p, n):
    it = _pos_qator(pos, p['id'])
    if it: it['qty'] += n
    else: pos['items'].append({'pid': p['id'], 'name': p['name'], 'qty': n,
                               'list': float(p['price'] or 0), 'price': float(p['price'] or 0)})

async def _pos_tasdiq(u, ctx, cart_id):
    q = u.callback_query
    done = ctx.user_data.setdefault('pos_done', [])
    if cart_id in done:
        await q.answer("✅ Bu savat allaqachon saqlangan", show_alert=True); return
    pos = _pos_ol(ctx)
    if not pos or pos.get('id') != cart_id:
        await q.answer("Savat topilmadi yoki eskirgan. 🛒 Sotuv'dan qayta boshlang.", show_alert=True); return
    if pos.get('saving'):
        await q.answer("⏳ Saqlanmoqda..."); return
    x = xodim(u)
    xato = None
    if not pos['items']: xato = "Savat bo'sh"
    elif not pos.get('method'): xato = "Avval to'lov usulini tanlang"
    elif pos['method'] == 'nasiya' and not pos.get('cust'): xato = "Nasiya uchun mijoz tanlang"
    elif any(i['price'] <= 0 for i in pos['items']): xato = "Narxi 0 bo'lgan qator bor — ✏️ Tahrirlash orqali narx kiriting"
    else: xato = _pos_sn_xato(pos) or pos_limit_xato(pos, x)
    if xato:
        await q.answer(xato[:190], show_alert=True); return
    h = pos_hisob(pos)
    qatorlar = [{'pid': ln['pid'], 'name': ln['name'], 'qty': ln['qty'], 'unit': ln['unit'], 'disc': ln['disc'],
                 'serials': list(ln.get('serials') or [])} for ln in h['lines']]
    cust = pos.get('cust') or {}
    pos['saving'] = True                         # await'dan OLDIN — ikkinchi bosish kutib turmaydi
    await q.answer("⏳ Saqlanmoqda...")
    try:
        res = await asyncio.to_thread(pos_saqlash, qatorlar, cust.get('name', ''), cust.get('id', 0),
                                      pos['method'], x['id'], x['name'], cust.get('type') or 'B2C')
    except Exception as e:
        pos['saving'] = False
        log.exception("pos_saqlash")
        await _pos_chiqar(q, f"⚠️ Saqlashda xato: {str(e)[:150]}\nHech narsa yozilmadi.",
                          [[_btn("⬅️ Savat", "pos:cart")], _pos_bekor()])
        return
    pos['saving'] = False
    if not res.get('ok'):
        m, r = pos_ekran_savat(pos, get_exchange_rate(), "⚠️ " + res.get('error', 'Saqlanmadi'))
        await _pos_chiqar(q, m, r); return
    done.append(cart_id); del done[:-30]
    ctx.user_data.pop('pos', None)
    rate = get_exchange_rate()
    chek = pos_chek_matn(res, h, pos, x, rate)
    arxiv = ctx.user_data.setdefault('pos_chek', {})
    arxiv[cart_id] = {'mijoz': cust.get('name', ''),
                      'qatorlar': [(ln['name'], ln['qty'], round(ln['unit'], 2)) for ln in h['lines']]}
    for k in list(arxiv)[:-5]: arxiv.pop(k, None)
    await _pos_chiqar(q, chek, [[_btn("🧾 Hisob-faktura", f"pos:inv:{cart_id}")],
                                [_btn("🛒 Yangi sotuv", "pos:start")]])

async def _pos_faktura(u, ctx, cart_id):
    q = u.callback_query
    d = (ctx.user_data.get('pos_chek') or {}).get(cart_id)
    if not d:
        await q.answer("Chek ma'lumoti topilmadi (bot qayta ishga tushgan bo'lishi mumkin)", show_alert=True); return
    await q.answer("⏳ Hujjat tayyorlanmoqda...")
    try:
        base = f"/tmp/doc_{datetime.now().strftime('%Y%m%d%H%M%S')}_{cart_id}.pdf"
        p, raqam, jami, is_pdf = await asyncio.to_thread(build_hujjat, base, 'faktura', d['mijoz'], d['qatorlar'])
        with open(p, 'rb') as fh:
            await ctx.bot.send_document(chat_id=u.effective_chat.id, document=fh,
                                        filename=f"{raqam}.{'pdf' if is_pdf else 'html'}",
                                        caption=f"📄 {raqam} · {_usd2(jami)}")
        try: os.remove(p)
        except Exception: pass
    except Exception as e:
        log.exception("pos faktura")
        await q.message.reply_text(f"⚠️ Hujjat xatosi: {str(e)[:200]}")

async def pos_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """'pos:' tugmalari (on_callback'dan OLDIN ro'yxatga olinadi)"""
    q = u.callback_query
    if not can(u, 'pos'):
        await q.answer(); return
    parts = (q.data or '').split(':')
    act = parts[1] if len(parts) > 1 else ''
    arg = parts[2:]
    if act == 'ok': return await _pos_tasdiq(u, ctx, arg[0] if arg else '')
    if act == 'inv': return await _pos_faktura(u, ctx, arg[0] if arg else '')
    if act == 'noop':
        await q.answer(); return
    x = xodim(u)
    rate = get_exchange_rate()
    if act == 'start':
        pos = _pos_ol(ctx) or _pos_yangi(ctx)
        await q.answer()
        m, r = pos_ekran_savat(pos, rate) if pos['items'] else pos_ekran_kategoriya(pos)
        return await _pos_chiqar(q, m, r)
    pos = _pos_ol(ctx)
    if pos is None:
        await q.answer()
        return await _pos_chiqar(q, "⏰ Savat muddati o'tgan yoki yopilgan. Hech narsa yozilmadi.",
                                 [[_btn("🛒 Yangi sotuv", "pos:start")]])
    pos['wait'] = None

    def _int(i, default=0):
        try: return int(arg[i])
        except (IndexError, ValueError): return default

    m = r = None
    alert = None
    if act in ('sn', 'snw') or (act in ('q', 'qc', 'eq', 'ei') and _pos_sn_hook(pos, act, arg)):
        return await pos_sn_callback(u, ctx, pos, act, arg)      # 10-bosqich: serialli tovar
    if act == 'x':
        ctx.user_data.pop('pos', None)
        await q.answer("Bekor qilindi")
        return await _pos_chiqar(q, "❌ Sotuv bekor qilindi. Hech narsa yozilmadi.", None)
    elif act == 'cats':
        m, r = pos_ekran_kategoriya(pos)
    elif act == 'k':
        m, r = pos_ekran_mahsulotlar(pos, _int(0, -1), _int(1))
    elif act == 'f':
        m, r = pos_ekran_qidiruv(pos, _int(0))
    elif act == 's':
        pos['wait'] = 'search'
        m, r = ("🔍 Mahsulot nomini yozing (masalan: tts 20).\nShtrix-kod yoki serial ham bo'ladi — yozing yoki 📷 rasmini yuboring.",
                [[_btn("⬅️ Kategoriyalar", "pos:cats")], _pos_bekor()])
    elif act == 'p':
        p = _pos_mahsulot(_int(0))
        if not p: alert = "Mahsulot topilmadi"
        elif _pos_mavjud(pos, p['id'], p['qty']) <= 0: alert = f"❌ {p['name']} — astatkada yo'q (savatdagisi hisobga olindi)"
        elif (p['price'] or 0) <= 0 and x['role'] == 'sotuvchi': alert = "Bu mahsulotga narx qo'yilmagan — egasiga ayting"
        elif _serialli(p['id']): m, r = pos_ekran_serial(pos, p)
        else: m, r = pos_ekran_son(pos, p, rate)
    elif act == 'q':
        p = _pos_mahsulot(_int(0)); n = _int(1)
        if not p or n <= 0: alert = "Xato tanlov"
        elif n > _pos_mavjud(pos, p['id'], p['qty']): alert = f"Astatka yetmaydi: {max(0, _pos_mavjud(pos, p['id'], p['qty']))} ta bor"
        else:
            _pos_qosh(pos, p, n)
            m, r = pos_ekran_savat(pos, rate, f"✅ {p['name']} × {n} qo'shildi")
    elif act == 'qc':
        p = _pos_mahsulot(_int(0))
        if not p: alert = "Mahsulot topilmadi"
        else:
            pos['wait'] = f"qty:{p['id']}"
            m, r = (f"✍️ {p['name']} — nechta? (sotsa bo'ladi: {max(0, _pos_mavjud(pos, p['id'], p['qty']))} ta)\nSonni yozing:",
                    [[_btn("⬅️ Orqaga", f"pos:p:{p['id']}")], _pos_bekor()])
    elif act == 'cart':
        m, r = pos_ekran_savat(pos, rate)
    elif act == 'ed':
        m, r = pos_ekran_tahrir(pos) if pos['items'] else pos_ekran_savat(pos, rate)
    elif act in ('e', 'ei', 'eq', 'ep', 'er'):
        it = _pos_qator(pos, _int(0))
        if not it:
            alert = "Bu qator savatda yo'q"; m, r = pos_ekran_savat(pos, rate)
        elif act == 'e':
            m, r = pos_ekran_qator(pos, it, x)
        elif act == 'ei':
            yangi = it['qty'] + _int(1)
            p = _pos_mahsulot(it['pid'])
            if yangi <= 0: alert = "Kamida 1 ta. O'chirish uchun 🗑 bosing"
            elif not p or yangi > (p['qty'] or 0): alert = f"Astatka yetmaydi: {(p or {}).get('qty', 0)} ta bor"
            else: it['qty'] = yangi
            m, r = pos_ekran_qator(pos, it, x)
        elif act == 'eq':
            pos['wait'] = f"eq:{it['pid']}"
            m, r = f"✍️ {it['name']} — yangi sonni yozing:", [[_btn("⬅️ Orqaga", f"pos:e:{it['pid']}")], _pos_bekor()]
        elif act == 'ep':
            pos['wait'] = f"ep:{it['pid']}"
            lim = ""
            if x['role'] == 'sotuvchi':
                lim = f"\nEng past: {_usd2(it['list'] * (1 - x['max_discount'] / 100))} (limit {x['max_discount']:g}%)"
            m, r = (f"✍️ {it['name']} — dona narxini yozing ($; so'mda yozsangiz o'zi o'giradi):{lim}",
                    [[_btn("⬅️ Orqaga", f"pos:e:{it['pid']}")], _pos_bekor()])
        elif act == 'er':
            pos['items'].remove(it)
            m, r = pos_ekran_savat(pos, rate, f"🗑 {it['name']} olib tashlandi")
    elif act == 'd':
        m, r = pos_ekran_chegirma(pos, x, rate)
    elif act == 'dv':
        eski = pos.get('disc')
        pos['disc'] = {'type': 'pct', 'val': float(_int(0))}
        xato = pos_limit_xato(pos, x)
        if xato: pos['disc'] = eski; alert = xato
        m, r = pos_ekran_savat(pos, rate) if not xato else pos_ekran_chegirma(pos, x, rate)
    elif act in ('dp', 'du'):
        pos['wait'] = act
        m, r = ("✍️ Chegirma foizini yozing (masalan: 7):" if act == 'dp' else "✍️ Chegirma summasini yozing ($, masalan: 25):",
                [[_btn("⬅️ Orqaga", "pos:d")], _pos_bekor()])
    elif act == 'd0':
        pos['disc'] = None
        m, r = pos_ekran_savat(pos, rate, "Chegirma olib tashlandi")
    elif act == 'mj':
        m, r = pos_ekran_mijoz(pos)
    elif act == 'ms':
        pos['wait'] = 'ms'
        m, r = "🔍 Mijoz ismi yoki telefonini yozing:", [[_btn("⬅️ Orqaga", "pos:mj")], _pos_bekor()]
    elif act == 'mn':
        if not can(u, 'customer_add'): alert = "Ruxsat yo'q"
        else:
            pos['wait'] = 'mn'
            m, r = ("➕ Yangi mijoz: ism va telefonni yozing\nMasalan: Alisher Karimov +998901234567",
                    [[_btn("⬅️ Orqaga", "pos:mj")], _pos_bekor()])
    elif act == 'mc':
        cm = next((c_ for c_ in mijoz_qidir('') if c_['id'] == _int(0)), None)
        if not cm: alert = "Mijoz topilmadi"
        else:
            pos['cust'] = {'id': cm['id'], 'name': cm['nom'], 'phone': cm['tel'] or '', 'type': cm['tur'] or 'B2C'}
            m, r = (pos_ekran_tasdiq(pos, rate) if pos.get('method') else
                    pos_ekran_savat(pos, rate, f"👤 Mijoz: {cm['nom']}"))
    elif act == 'mw':
        pos['cust'] = None
        if pos.get('method') == 'nasiya': pos['method'] = None
        m, r = pos_ekran_savat(pos, rate, "🚶 Oddiy xaridor (mijozsiz)")
    elif act == 'pay':
        if not pos['items']: m, r = pos_ekran_savat(pos, rate)
        else: m, r = pos_ekran_tolov(pos, rate)
    elif act == 'm':
        usul = arg[0] if arg else ''
        if usul not in POS_USUL_NOMI: alert = "Noma'lum usul"
        else:
            pos['method'] = usul
            if usul == 'nasiya' and not pos.get('cust'):
                m, r = pos_ekran_mijoz(pos)
            else:
                m, r = pos_ekran_tasdiq(pos, rate)
    else:
        alert = "Eski tugma"
    await q.answer(alert[:190] if alert else None, show_alert=bool(alert))
    if m is not None:
        await _pos_chiqar(q, m, r)

async def pos_matn(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """POS yozma kiritishni kutayotgan bo'lsa — matnni qabul qiladi. True = matn ishlatildi."""
    pos0 = ctx.user_data.get('pos')
    if not pos0 or not pos0.get('wait') or not can(u, 'pos'): return False
    pos = _pos_ol(ctx)
    if pos is None:
        await u.message.reply_text("⏰ Savat muddati o'tgan. Hech narsa yozilmadi. Qayta: 🛒 Sotuv"); return True
    w = pos['wait']; pos['wait'] = None
    msg = (u.message.text or '').strip()
    x = xodim(u); rate = get_exchange_rate()
    m = r = None

    def qayta(xato):
        pos['wait'] = w                          # kutish davom etadi
        return f"⚠️ {xato}\nQaytadan yozing yoki tugmani bosing.", [_pos_bekor()]

    if w.startswith('sn:') or (w == 'search' and kod_top(msg)):
        return await pos_kod_matn(u, ctx, pos, msg, w)          # 10-bosqich: serial / shtrix-kod
    if w == 'search':
        topildi = pos_qidir(msg)
        pos['found'] = [p['id'] for p in topildi]
        m, r = pos_ekran_qidiruv(pos)
        if not topildi:
            pos['wait'] = 'search'
            m = f"🔍 '{msg[:40]}' topilmadi. Boshqacha yozing:"
    elif w.startswith('qty:') or w.startswith('eq:'):
        pid = int(w.split(':')[1]); p = _pos_mahsulot(pid)
        try: n = int(re.sub(r'\D', '', msg) or 0)
        except ValueError: n = 0
        it = _pos_qator(pos, pid)
        mavjud = _pos_mavjud(pos, pid, p['qty'] if p else 0, bundan_tashqari=w.startswith('eq:'))
        if not p: m, r = pos_ekran_savat(pos, rate, "Mahsulot topilmadi")
        elif n <= 0: m, r = qayta("Musbat butun son yozing")
        elif n > mavjud: m, r = qayta(f"Astatka yetmaydi: {max(0, mavjud)} ta bor")
        elif w.startswith('qty:'):
            _pos_qosh(pos, p, n); m, r = pos_ekran_savat(pos, rate, f"✅ {p['name']} × {n} qo'shildi")
        elif it:
            it['qty'] = n; m, r = pos_ekran_savat(pos, rate, f"✏️ {p['name']}: {n} ta")
        else: m, r = pos_ekran_savat(pos, rate)
    elif w.startswith('ep:'):
        it = _pos_qator(pos, int(w.split(':')[1])); v = _pos_son(msg)
        if not it: m, r = pos_ekran_savat(pos, rate)
        elif not v or v <= 0: m, r = qayta("Narxni raqam bilan yozing (masalan: 450)")
        else:
            eski = it['price']; it['price'] = round(v, 2)
            xato = pos_limit_xato(pos, x)
            if xato: it['price'] = eski; m, r = qayta(xato)
            else: m, r = pos_ekran_savat(pos, rate, f"✏️ {it['name']}: {_usd2(it['price'])}/dona")
    elif w in ('dp', 'du'):
        if w == 'du':
            v = _pos_son(msg)
        else:
            t = re.sub(r'[^\d.]', '', msg.replace(',', '.'))
            try: v = float(t) if t else None
            except ValueError: v = None
        if v is None or v < 0 or (w == 'dp' and v > 100): m, r = qayta("To'g'ri qiymat yozing")
        else:
            eski = pos.get('disc')
            pos['disc'] = {'type': 'pct' if w == 'dp' else 'usd', 'val': round(v, 2)} if v > 0 else None
            xato = pos_limit_xato(pos, x)
            if xato: pos['disc'] = eski; m, r = qayta(xato)
            else: m, r = pos_ekran_savat(pos, rate, "💸 Chegirma qo'yildi" if v > 0 else "Chegirma olib tashlandi")
    elif w == 'ms':
        topildi = [{'id': c_['id'], 'name': c_['nom'], 'phone': c_['tel'] or ''} for c_ in mijoz_qidir(msg)]
        m, r = pos_ekran_mijoz(pos, topildi, f"🔍 '{msg[:30]}' bo'yicha:")
    elif w == 'mn':
        tel_m = re.search(r'(\+?\d[\d\s\-()]{6,}\d)', msg)
        tel = re.sub(r'[^\d+]', '', tel_m.group(1)) if tel_m else ''
        ism = (msg[:tel_m.start()] + msg[tel_m.end():]).strip(' ,;-') if tel_m else msg.strip()
        if len(ism) < 2: m, r = qayta("Ism yozilmadi. Masalan: Alisher +998901234567")
        else:
            holat, cid = add_customer(ism, tel)
            if not cid: m, r = qayta("Mijozni saqlab bo'lmadi")
            else:
                pos['cust'] = {'id': cid, 'name': ism, 'phone': tel, 'type': 'B2C'}
                izoh = ("➕ Yangi mijoz qo'shildi: " if holat == 'qoshildi' else "👤 Mavjud mijoz tanlandi: ") + ism
                m, r = (pos_ekran_tasdiq(pos, rate) if pos.get('method') else pos_ekran_savat(pos, rate, izoh))
    else:
        return False
    await u.message.reply_text(m[:4000], reply_markup=InlineKeyboardMarkup(r) if r else None)
    return True

# ── XODIMLAR VA SOTUVCHI BO'LIMI ──────────────────────────────────
def _sotuvchi_kb():
    return ReplyKeyboardMarkup(SOTUVCHI_KB, resize_keyboard=True, is_persistent=True)

async def cmd_start_sotuvchi(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    x = xodim(u)
    if not x or x['role'] != 'sotuvchi': return
    await u.message.reply_text(
        f"👋 Salom, {x['name']}! Siz sotuvchisiz.\n\n"
        "🛒 Sotuv — tugmalar orqali sotish\n📦 Qoldiq — tovarlar va narxlar\n"
        "📦 Ombor — tovar kartasi (faqat ko'rish)\n👥 Mijozlar — mijoz qidirish/qo'shish\n"
        "📋 Bugungi sotuvlarim — bugun nima sotdingiz\n❓ Yordam",
        reply_markup=_sotuvchi_kb())

async def cmd_yordam_sotuvchi(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    x = xodim(u)
    if not x: return
    await u.message.reply_text(
        "❓ Qanday sotiladi:\n"
        "1) 🛒 Sotuv ni bosing\n2) Kategoriya → tovarni tanlang (❌ — tugagan)\n"
        "3) Sonini bosing (1/2/3/5/10 yoki ✍️ Boshqa son)\n"
        "4) Kerak bo'lsa ➕ Yana tovar\n"
        f"5) 💸 Chegirma (sizning limitingiz {x['max_discount']:g}%)\n"
        "6) 👤 Mijoz — tanlang, yangi qo'shing yoki 🚶 mijozsiz\n"
        "7) 💳 To'lov — usulni tanlang (📝 Nasiya faqat mijoz bilan)\n"
        "8) ✅ Tasdiqlash — chek chiqadi\n\n"
        "Har qadamda ❌ Bekor qilish bor. 30 daqiqa tegmasangiz savat o'chadi.\n"
        "📦 Ombor — qoldiqni ko'rish · 👥 Mijozlar — yangi mijoz qo'shish\n"
        "📥 Qaytarish — mijoz tovar qaytarsa so'rov yuborasiz (egasi tasdiqlaydi)\n"
        "🧾 Smena — kun boshida oching, kun oxirida kassadagi pulni sanab yoping\n"
        "🔢 Serialli tovar — 🛒 Sotuvda serial raqamni tanlang yoki skanerlang (📷 rasm ham bo'ladi)\n"
        "Buyruqlar: /sotuv /qoldiq /ombor /mening /id /qaytarish /smena /serial",
        reply_markup=_sotuvchi_kb() if x['role'] == 'sotuvchi' else None)

async def cmd_qoldiq(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tannarxsiz qoldiq ro'yxati (sotuvchi ham ko'radi)"""
    if not can(u, 'stock_view'): return
    prods = get_products()
    guruh = defaultdict(list)
    for p in prods: guruh[p['cat'] or 'Boshqa'].append(p)
    qism = ["📦 Qoldiq (soni · narx):"]
    for cat in sorted(guruh):
        qism.append(f"\n▪️ {cat}")
        for p in guruh[cat]:
            q = p['qty'] or 0
            belgi = "🔴" if q <= 0 else ("🟡" if q <= 2 else "🟢")
            qism.append(f"{belgi} {p['name']} — {q} ta · {_usd2(p['price'] or 0)}")
    matn, bolak = "", []
    for line in qism:
        if len(matn) + len(line) > 3800: bolak.append(matn); matn = ""
        matn += line + "\n"
    bolak.append(matn)
    for b in bolak:
        if b.strip(): await u.message.reply_text(b)

async def cmd_mening(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Bugungi o'z sotuvlarim (foydasiz)"""
    if not can(u, 'own_sales'): return
    x = xodim(u)
    conn = db(); c = conn.cursor()
    c.execute("SELECT time, product, qty, revenue, customer FROM sales WHERE date=? AND seller_id=? AND reversed=0 "
              "ORDER BY id", (today(), x['id']))
    rows = c.fetchall(); conn.close()
    if not rows:
        await u.message.reply_text("📋 Bugun hali sotuv yo'q."); return
    out = [f"📋 Bugungi sotuvlarim ({today()}):"]
    for t, pr, qty, rev, cu in rows:
        out.append(f"{t} · {pr} × {qty} = {_usd2(rev)}" + (f" · {cu}" if cu else ""))
    jami = round(sum(r[3] for r in rows), 2)
    out.append(f"──────────────\nJami: {len(rows)} ta qator · {_usd2(jami)} ≈ {jami * get_exchange_rate():,.0f} so'm")
    await u.message.reply_text("\n".join(out)[:4000])

async def sotuvchi_matn(u: Update, ctx: ContextTypes.DEFAULT_TYPE, msg: str):
    """Sotuvchi yozgan matn: faqat o'z menyusi. AI agentga yuborilmaydi."""
    fn = {"🛒 Sotuv": pos_start, "📦 Qoldiq": cmd_qoldiq, "📦 Astatka": cmd_qoldiq,
          "📋 Bugungi sotuvlarim": cmd_mening, "❓ Yordam": cmd_yordam_sotuvchi,
          "📦 Ombor": cmd_ombor, "👥 Mijozlar": cmd_mijozlar_ui,
          "📥 Qaytarish": cmd_qaytarish, "🧾 Smena": cmd_smena, "🔢 Serial": cmd_serial}.get(msg)
    if fn:
        await fn(u, ctx); return
    await u.message.reply_text("Sotish uchun 🛒 Sotuv tugmasini bosing.\n📦 Qoldiq · 📋 Bugungi sotuvlarim · ❓ Yordam",
                               reply_markup=_sotuvchi_kb())

async def cmd_id(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Har kim: o'z Telegram ID sini bilib oladi (egasi uni /xodim_qosh bilan qo'shadi)"""
    us = u.effective_user
    await u.message.reply_text(f"🆔 Sizning Telegram ID: {us.id}\nBu raqamni do'kon egasiga yuboring.")

def _rol_ol(s):
    s = (s or '').strip().lower()
    return {'admin': 'admin', 'sotuvchi': 'sotuvchi', 'seller': 'sotuvchi', 'kassir': 'sotuvchi'}.get(s)

async def cmd_xodim_qosh(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/xodim_qosh <telegram_id> <ism> <rol> [limit%]"""
    if not can(u, 'roles'): return
    a = list(ctx.args or [])
    namuna = ("Format: /xodim_qosh <telegram_id> <ism> <rol> [chegirma%]\n"
              "Rol: sotuvchi yoki admin\nMisol: /xodim_qosh 123456789 Ali sotuvchi 5\n\n"
              "ID ni bilish: xodim botga /id yozsin.")
    limit = None
    if a and re.fullmatch(r'\d+(\.\d+)?%?', a[-1]) and len(a) >= 4:
        limit = min(100.0, float(a.pop().rstrip('%')))
    if len(a) < 3 or not a[0].isdigit() or not _rol_ol(a[-1]):
        await u.message.reply_text(namuna); return
    tid, rol, ism = int(a[0]), _rol_ol(a[-1]), ' '.join(a[1:-1]).strip()
    if tid == OWNER_ID:
        await u.message.reply_text("Bu — egasining ID si. Egasi doim to'liq huquqli."); return
    holat = xodim_saqla(tid, ism, rol, limit)
    x = xodim(tid)
    holat_s = "qo'shildi" if holat == 'qoshildi' else "yangilandi"
    await u.message.reply_text(
        f"✅ {ism} {holat_s}: {ROL_NOMI[rol]}"
        + (f", chegirma limiti {x['max_discount']:g}%" if rol == 'sotuvchi' and x else "")
        + "\nU botda /start bossin. Ro'yxat: /xodimlar")
    try:
        await ctx.bot.send_message(tid, f"👋 Siz ThermoCrafts botiga {ROL_NOMI[rol]} sifatida qo'shildingiz. /start bosing.")
    except Exception:
        pass                                     # xodim hali botni ochmagan bo'lsa — xabar bormaydi

async def cmd_xodim_ochir(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/xodim_ochir <telegram_id> — nofaol qiladi (tarix saqlanadi)"""
    if not can(u, 'roles'): return
    a = ctx.args or []
    if not a or not a[0].isdigit():
        await u.message.reply_text("Format: /xodim_ochir <telegram_id>\nRo'yxat: /xodimlar"); return
    ok = xodim_ozgartir(int(a[0]), active=0)
    await u.message.reply_text("🚫 Xodim o'chirildi (nofaol). Sotuv tarixi saqlanadi.\nQayta yoqish: /xodimlar"
                               if ok else "Bunday xodim yo'q. Ro'yxat: /xodimlar")

def _xodimlar_ekran():
    xs = xodimlar_royxati()
    if not xs:
        return ("👷 Xodimlar yo'q.\nQo'shish: /xodim_qosh <telegram_id> <ism> <rol>\n"
                "Xodim ID sini botga /id yozib bilib oladi."), None
    out = ["👷 Xodimlar:"]
    rows = []
    for x in xs:
        holat = "✅" if x['active'] else "🚫"
        lim = f" · limit {x['max_discount']:g}%" if x['role'] == 'sotuvchi' else ""
        out.append(f"{holat} {x['name']} ({x['id']}) — {ROL_NOMI.get(x['role'], x['role'])}{lim}")
        rows.append([_btn(f"{holat} {x['name'][:20]}", f"xod:u:{x['id']}")])
    out.append("\nO'zgartirish uchun ismni bosing.")
    return "\n".join(out), rows

def _xodim_ekran(tid):
    x = next((y for y in xodimlar_royxati() if y['id'] == tid), None)
    if not x: return "Xodim topilmadi", [[_btn("⬅️ Ro'yxat", "xod:list")]]
    boshqa = 'admin' if x['role'] == 'sotuvchi' else 'sotuvchi'
    matn = (f"👷 {x['name']} ({x['id']})\nRol: {ROL_NOMI.get(x['role'], x['role'])}\n"
            f"Holat: {'faol' if x['active'] else 'nofaol'}\n"
            + (f"Chegirma limiti: {x['max_discount']:g}%\n" if x['role'] == 'sotuvchi' else "")
            + f"Qo'shilgan: {x['created'] or '-'}")
    rows = [[_btn(f"🔁 Rol → {boshqa}", f"xod:r:{tid}")]]
    if x['role'] == 'sotuvchi':
        rows.append([_btn(f"💸 Limit: {x['max_discount']:g}% → keyingi", f"xod:l:{tid}")])
    rows.append([_btn("🚫 O'chirish (nofaol)" if x['active'] else "✅ Faollashtirish", f"xod:a:{tid}")])
    rows.append([_btn("⬅️ Ro'yxat", "xod:list")])
    return matn, rows

XODIM_LIMITLAR = (0, 5, 10, 15, 20, 30)

async def cmd_xodimlar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'roles'): return
    m, r = _xodimlar_ekran()
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r) if r else None)

async def xodim_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """'xod:' tugmalari — faqat egasi"""
    q = u.callback_query
    if not can(u, 'roles'):
        await q.answer("Faqat egasi uchun", show_alert=True); return
    parts = (q.data or '').split(':')
    act = parts[1] if len(parts) > 1 else ''
    try: tid = int(parts[2]) if len(parts) > 2 else 0
    except ValueError: tid = 0
    x = next((y for y in xodimlar_royxati() if y['id'] == tid), None) if tid else None
    izoh = None
    if act == 'r' and x:
        xodim_ozgartir(tid, role=('admin' if x['role'] == 'sotuvchi' else 'sotuvchi')); izoh = "Rol o'zgardi"
    elif act == 'a' and x:
        xodim_ozgartir(tid, active=0 if x['active'] else 1); izoh = "Holat o'zgardi"
    elif act == 'l' and x:
        joriy = x['max_discount']
        keyingi = next((v for v in XODIM_LIMITLAR if v > joriy + 1e-9), XODIM_LIMITLAR[0])
        xodim_ozgartir(tid, max_discount_pct=float(keyingi)); izoh = f"Limit: {keyingi}%"
    await q.answer(izoh)
    m, r = _xodimlar_ekran() if act == 'list' or not tid else _xodim_ekran(tid)
    try:
        await q.edit_message_text(m, reply_markup=InlineKeyboardMarkup(r) if r else None)
    except BadRequest as e:
        if 'not modified' not in str(e).lower(): raise

async def cmd_sotuvchilar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Sotuvchilar kesimida: bugun va shu oy (soni, tushum, foyda) — egasi/admin"""
    if not can(u, 'boshqaruv'): return
    nomlar = {x['id']: x['name'] for x in xodimlar_royxati()}
    nomlar[OWNER_ID] = 'Egasi'
    conn = db(); c = conn.cursor()
    out = ["👷 Sotuvchilar bo'yicha sotuv"]
    for sarl, shart, val in (("📅 Bugun", "date=?", today()), ("📆 Shu oy", "date LIKE ?", this_month() + '%')):
        c.execute(f"SELECT COALESCE(seller_id,0), MAX(seller_name), COUNT(*), COALESCE(SUM(revenue),0), "
                  f"COALESCE(SUM(profit),0) FROM sales WHERE reversed=0 AND {shart} "
                  "GROUP BY COALESCE(seller_id,0) ORDER BY 4 DESC", (val,))
        rows = c.fetchall()
        out.append(f"\n{sarl}:")
        if not rows: out.append("  sotuv yo'q")
        for sid, snom, n, rev, prof in rows:
            nom = nomlar.get(sid) or snom or ("Egasi (AI/matn)" if not sid else str(sid))
            out.append(f"  {nom}: {n} ta · {_usd2(rev)} · foyda {_usd2(prof)}")
    conn.close()
    await u.message.reply_text("\n".join(out)[:4000])

# ── 📦 OMBOR (tugmali) ────────────────────────────────────────────
# Holat: ctx.user_data['omb']. Ko'rish — 'stock_view' (sotuvchi ham); yozish/inventar/qiymat — 'ombor' (egasi/admin).
UI_TTL = 1800

def _ui_ol(ctx, key):
    st = ctx.user_data.get(key)
    if not st: return None
    if time.time() - st.get('ts', 0) > UI_TTL:
        ctx.user_data.pop(key, None); return None
    st['ts'] = time.time()
    return st

def _ui_yangi(ctx, key, **kv):
    st = {'id': secrets.token_hex(4), 'ts': time.time(), 'wait': None}
    st.update(kv); ctx.user_data[key] = st
    return st

def _ui_done(ctx, token):
    """Ikki marta bosishdan himoya: token birinchi marta — True."""
    done = ctx.user_data.setdefault('ui_done', [])
    if token in done: return False
    done.append(token); del done[:-50]
    return True

def _x_btn(prefix): return [_btn("❌ Yopish", f"{prefix}:x")]
def _ui_user(u):
    x = xodim(u) or {}
    return (x.get('id', 0), x.get('name', ''))

def _omb_cats(prods):
    return sorted({(p['cat'] or 'Boshqa') for p in prods})

def _omb_menu(u):
    kam = len(kam_qolganlar())
    rows = [[_btn("📋 Tovarlar", "omb:cats"), _btn("🔍 Qidirish", "omb:s")],
            [_btn(f"⚠️ Kam qolgan ({kam})", "omb:kam")]]
    if can(u, 'ombor'):
        rows.append([_btn("📥 Kirim", "omb:kirim"), _btn("📤 Chiqim", "omb:chiqim")])
        rows.append([_btn("🧮 Inventarizatsiya", "omb:inv"), _btn("💰 Ombor qiymati", "omb:val")])
        rows.append([_btn("📜 Oxirgi harakatlar", "omb:log:0")])
    rows.append([_btn("🔢 Serial / kafolat", "sn:menu")] + ([_btn("🏷 Yorliqlar", "kod:menu")] if can(u, 'ombor') else []))
    rows.append(_x_btn('omb'))
    return "📦 Ombor — bo'limni tanlang\n🔍 Qidirishda shtrix-kod yoki serial yozsangiz (📷 rasm ham) — to'g'ridan-to'g'ri topadi", rows

_OMB_REJIM = {'card': "📦 Tovar kartasi", 'kirim': "📥 Kirim — tovarni tanlang", 'chiqim': "📤 Chiqim — tovarni tanlang",
              'zav': "🏭 Buyurtmaga tovar tanlang"}

def _omb_kat_ekran(st, prefix='omb'):
    prods = get_products()
    cats = _omb_cats(prods); st['cats'] = cats
    rows, row = [], []
    for i, cn in enumerate(cats):
        row.append(_btn(f"{cn[:24]} ({sum(1 for p in prods if (p['cat'] or 'Boshqa') == cn)})", f"{prefix}:k:{i}:0"))
        if len(row) == 2: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([_btn("🔍 Qidirish", f"{prefix}:s"), _btn("📋 Hammasi", f"{prefix}:k:-1:0")])
    rows.append([_btn("⬅️ Orqaga", f"{prefix}:menu")] + _x_btn(prefix))
    return _OMB_REJIM.get(st.get('mode'), "Tovarni tanlang") + "\nKategoriya:", rows

def _omb_royxat(st, prods, sarlavha, page, nav, prefix='omb'):
    pages = max(1, math.ceil(len(prods) / POS_SAHIFA)); page = min(max(0, page), pages - 1)
    rows = []
    for p in prods[page * POS_SAHIFA:(page + 1) * POS_SAHIFA]:
        q = p['qty'] or 0
        belgi = "🔴" if q <= 0 else ("🟡" if q <= max(2, p.get('min') or 0) else "🟢")
        rows.append([_btn(f"{belgi} {p['name'][:30]} · {q} ta · {_usd2(p['price'] or 0)}", f"{prefix}:p:{p['id']}")])
    if pages > 1:
        nv = []
        if page > 0: nv.append(_btn("⬅️", f"{nav}:{page - 1}"))
        nv.append(_btn(f"{page + 1}/{pages}", "pos:noop"))
        if page < pages - 1: nv.append(_btn("➡️", f"{nav}:{page + 1}"))
        rows.append(nv)
    rows.append([_btn("🔍 Qidirish", f"{prefix}:s"), _btn("⬅️ Kategoriyalar", f"{prefix}:cats")])
    rows.append(_x_btn(prefix))
    return (f"{_OMB_REJIM.get(st.get('mode'), '')}\n{sarlavha}" if prods else f"{sarlavha}: topilmadi"), rows

def _omb_kat_mahsulot(st, ci, page, prefix='omb'):
    prods = get_products()
    cats = st.get('cats') or _omb_cats(prods)
    sel, nom = ((prods, "Hammasi") if not (0 <= ci < len(cats))
                else ([p for p in prods if (p['cat'] or 'Boshqa') == cats[ci]], cats[ci]))
    return _omb_royxat(st, sorted(sel, key=lambda p: p['name']), nom, page, f"{prefix}:k:{ci}", prefix)

def _omb_qidiruv_ekran(st, page=0, prefix='omb'):
    ids = st.get('found') or []
    by = {p['id']: p for p in get_products()}
    return _omb_royxat(st, [by[i] for i in ids if i in by], "Qidiruv natijasi", page, f"{prefix}:f", prefix)

def _omb_mahsulot(pid):
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, name, cat, supplier, COALESCE(qty,0), COALESCE(cost,0), COALESCE(price,0), COALESCE(min_qty,0), active, "
              "COALESCE(factory_price,0) FROM products WHERE id=?", (pid,))
    r = c.fetchone(); conn.close()
    if not r: return None
    return {'id': r[0], 'name': r[1], 'cat': r[2], 'sup': r[3], 'qty': r[4], 'cost': r[5], 'price': r[6], 'min': r[7],
            'active': r[8], 'factory': r[9]}

def _sm_qator(m, narx=True):
    _id, d, t, kind, qty, bal, uc, reason, ref, uname, sup = m
    s = f"{d[8:10]}.{d[5:7]} {t} {OMBOR_TURLARI.get(kind, kind)} {qty:+d} → {bal}"
    if narx and kind in ('kirim', 'zavod_kirim') and uc: s += f" @{_usd2(uc)}"
    if reason: s += f" · {reason[:40]}"
    if uname: s += f" ({uname})"
    return s

def _omb_karta(u, pid, page=0):
    p = _omb_mahsulot(pid)
    if not p: return "Mahsulot topilmadi", [[_btn("⬅️ Orqaga", "omb:menu")]]
    bosh = can(u, 'boshqaruv')
    out = [f"📦 {p['name']}", f"Kategoriya: {p['cat'] or '-'} · Yetkazuvchi: {p['sup'] or '-'}",
           f"Qoldiq: {p['qty']} ta" + (f" (min: {p['min']})" if p['min'] else ""), f"Narx: {_usd2(p['price'])}"]
    if bosh:
        out.append(f"Tannarx: {_usd2(p['cost'])} · Ombordagi qiymati: {_usd2(max(0, p['qty']) * p['cost'])}")
    rows = []
    if can(u, 'ombor'):
        rows.append([_btn("📥 Kirim", f"omb:pk:{pid}"), _btn("📤 Chiqim", f"omb:pc:{pid}")])
        rows.append([_btn(f"⚠️ Min qoldiq: {p['min']}", f"omb:min:{pid}")])
    if bosh:
        tarix, n = ombor_tarix(pid, 8, page * 8)
        pages = max(1, math.ceil(n / 8))
        out.append(f"\n📜 Harakatlar ({n} ta, sahifa {page + 1}/{pages}):")
        out += [_sm_qator(m) for m in tarix] or ["(yo'q)"]
        nv = []
        if page > 0: nv.append(_btn("⬅️ Yangiroq", f"omb:h:{pid}:{page - 1}"))
        if page < pages - 1: nv.append(_btn("Eskiroq ➡️", f"omb:h:{pid}:{page + 1}"))
        if nv: rows.append(nv)
    _omb_karta_b10(u, pid, out, rows)            # 10-bosqich: serial / shtrix-kod
    rows.append([_btn("⬅️ Ro'yxat", "omb:cats")] + _x_btn('omb'))
    return "\n".join(out), rows

def _omb_kirim_ekran(st):
    p = _omb_mahsulot(st['pid'])
    out = [f"📥 Kirim: {p['name']}", f"Hozir: {p['qty']} ta · tannarx {_usd2(p['cost'])}"]
    if st.get('qty'): out.append(f"Soni: {st['qty']} ta")
    if st.get('cost') is not None: out.append(f"Dona narxi (tannarx): {_usd2(st['cost'])}")
    if st.get('sup') is not None: out.append(f"Yetkazuvchi: {st['sup'] or '-'}")
    rows = []
    if not st.get('qty'):
        out.append("\nNechta keldi?")
        rows.append([_btn(str(n), f"omb:kq:{n}") for n in (1, 2, 3, 5, 10, 20)])
        rows.append([_btn("✍️ Boshqa son", "omb:kqc")])
    elif st.get('cost') is None:
        out.append("\nDona tannarxi qancha?")
        rows.append([_btn(f"Joriy: {_usd2(p['cost'])}", "omb:kc:cur")] +
                    ([_btn(f"Zavod: {_usd2(p['factory'])}", "omb:kc:fac")] if p.get('factory') else []))
        rows.append([_btn("✍️ Narx yozish", "omb:kcc")])
    elif st.get('sup') is None:
        out.append("\nYetkazuvchi kim?")
        sups = _yetkazuvchilar(p['sup']); st['sups'] = sups
        rows += [[_btn(s_[:30], f"omb:ks:{i}")] for i, s_ in enumerate(sups[:6])]
        rows.append([_btn("✍️ Boshqa", "omb:ksc"), _btn("— Ko'rsatmaslik", "omb:ks0")])
    elif not st.get('pay'):
        yangi = (max(0, p['qty']) * p['cost'] + st['qty'] * st['cost']) / (max(0, p['qty']) + st['qty'])
        out.append(f"Summa: {_usd2(st['qty'] * st['cost'])} · yangi o'rtacha tannarx ≈ {_usd2(yangi)}")
        out.append("\nPuli qanday?")
        rows.append([_btn("💵 Kassadan to'landi", "omb:kp:cash")])
        if st.get('sup'): rows.append([_btn("📝 Qarzga (kreditorlik)", "omb:kp:debt")])
        rows.append([_btn("➖ Pulsiz (faqat astatka)", "omb:kp:none")])
    else:
        nomi = {'cash': "kassadan", 'debt': "qarzga (kreditorlik)", 'none': "pulsiz"}[st['pay']]
        out.append(f"To'lov: {nomi}\n\nTasdiqlaysizmi?")
        rows.append([_btn("✅ Tasdiqlash", f"omb:kok:{st['id']}")])
    rows.append([_btn("⬅️ Ombor", "omb:menu")] + _x_btn('omb'))
    return "\n".join(out), rows

def _yetkazuvchilar(birinchi=''):
    conn = db(); c = conn.cursor()
    c.execute("SELECT supplier FROM products WHERE COALESCE(supplier,'')<>'' UNION SELECT supplier FROM transit WHERE COALESCE(supplier,'')<>''")
    s = sorted({r[0] for r in c.fetchall()}); conn.close()
    if birinchi and birinchi in s: s.remove(birinchi); s.insert(0, birinchi)
    return s

def _omb_chiqim_ekran(st):
    p = _omb_mahsulot(st['pid'])
    out = [f"📤 Chiqim (spisanie): {p['name']}", f"Qoldiq: {p['qty']} ta"]
    rows = []
    if not st.get('qty'):
        out.append("\nNechta?")
        rows.append([_btn(str(n), f"omb:cq:{n}") for n in (1, 2, 3, 5, 10) if n <= p['qty']])
        rows.append([_btn("✍️ Boshqa son", "omb:cqc")])
    elif not st.get('sabab'):
        out.append(f"Soni: {st['qty']} ta\n\nSababi?")
        rows += [[_btn(nom, f"omb:cs:{k}")] for k, nom in CHIQIM_SABABLARI]
    else:
        out.append(f"Soni: {st['qty']} ta · Sabab: {CHIQIM_SABAB_NOMI[st['sabab']]}")
        out.append(f"Xarajat sifatida yoziladi (tannarx bo'yicha): {_usd2(st['qty'] * p['cost'])}\nKassaga tegmaydi.\n\nTasdiqlaysizmi?")
        rows.append([_btn("✅ Tasdiqlash", f"omb:cok:{st['id']}")])
    rows.append([_btn("⬅️ Ombor", "omb:menu")] + _x_btn('omb'))
    return "\n".join(out), rows

def _omb_min_ekran(pid):
    p = _omb_mahsulot(pid)
    rows = [[_btn(str(n), f"omb:mv:{pid}:{n}") for n in (0, 1, 2, 3, 5, 10)], [_btn("✍️ Boshqa son", f"omb:mvc:{pid}")],
            [_btn("⬅️ Karta", f"omb:p:{pid}")] + _x_btn('omb')]
    return (f"⚠️ {p['name']} — minimal qoldiq (hozir {p['min']}).\nQoldiq shundan oshmasa ertalab ogohlantiraman. "
            "0 — kuzatilmaydi."), rows

def _omb_kam_ekran():
    ks = kam_qolganlar()
    out = ["⚠️ Kam qolgan tovarlar:"] + [f"{'🔴' if k['qty'] <= 0 else '🟡'} {k['name']} — {k['qty']} ta (min {k['min']})" for k in ks]
    if not ks: out = ["✅ Kam qolgan tovar yo'q.", "(Min qoldiq tovar kartasida belgilanadi.)"]
    rows = [[_btn(f"{k['name'][:30]} · {k['qty']}", f"omb:p:{k['id']}")] for k in ks[:10]]
    rows.append([_btn("⬅️ Ombor", "omb:menu")] + _x_btn('omb'))
    return "\n".join(out), rows

def _omb_qiymat_ekran():
    v = ombor_qiymati()
    out = ["💰 Ombor qiymati (tannarx bo'yicha):"]
    for k, (d, s) in sorted(v['kat'].items(), key=lambda x: -x[1][1]):
        out.append(f"▪️ {k}: {d} ta · {_usd2(s)}")
    out.append(f"──────────────\nJami: {v['dona']} ta · {_usd2(v['jami'])} ≈ {v['jami'] * get_exchange_rate():,.0f} so'm")
    return "\n".join(out), [[_btn("⬅️ Ombor", "omb:menu")] + _x_btn('omb')]

def _omb_log_ekran(page):
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, date, time, kind, qty, balance, unit_cost, reason, ref, user_name, supplier, product "
              "FROM stock_moves ORDER BY id DESC LIMIT 10 OFFSET ?", (page * 10,))
    rows_ = c.fetchall(); c.execute("SELECT COUNT(*) FROM stock_moves"); n = c.fetchone()[0]; conn.close()
    pages = max(1, math.ceil(n / 10))
    out = [f"📜 Oxirgi harakatlar ({page + 1}/{pages}):"] + [f"{m[11][:22]}: " + _sm_qator(m[:11]) for m in rows_]
    nv = []
    if page > 0: nv.append(_btn("⬅️", f"omb:log:{page - 1}"))
    if page < pages - 1: nv.append(_btn("➡️", f"omb:log:{page + 1}"))
    rows = ([nv] if nv else []) + [[_btn("⬅️ Ombor", "omb:menu")] + _x_btn('omb')]
    return "\n".join(out), rows

# Inventarizatsiya
def _inv_ekran(st):
    inv = st['inv']; pids = inv['pids']
    if inv['i'] >= len(pids):
        return _inv_xulosa(st)
    p = _omb_mahsulot(pids[inv['i']])
    if not p:
        inv['i'] += 1; return _inv_ekran(st)
    tizim = p['qty']
    joriy = inv['sanoq'].get(str(p['id']))
    out = [f"🧮 Inventarizatsiya {inv['i'] + 1}/{len(pids)}", f"📦 {p['name']}", f"Tizimda: {tizim} ta"]
    if joriy: out.append(f"Siz sanagan: {joriy[1]} ta")
    out.append("\nOmborda nechta bor? (sanab, bosing yoki yozing)")
    vals = sorted({max(0, tizim + d) for d in (-2, -1, 0, 1, 2)} | {0})
    rows = [[_btn(f"✅ {v}" if v == tizim else str(v), f"omb:iv:{v}") for v in vals[:6]],
            [_btn("✍️ Boshqa son", "omb:ivc"), _btn("⏭ O'tkazish", "omb:isk")]]
    nv = []
    if inv['i'] > 0: nv.append(_btn("⬅️ Oldingi", "omb:ibk"))
    nv.append(_btn("🏁 Yakunlash", "omb:ifin"))
    rows.append(nv)
    rows.append([_btn("❌ Bekor qilish", "omb:x")])
    st['inv_tizim'] = tizim
    return "\n".join(out), rows

def _inv_xulosa(st):
    inv = st['inv']
    out = ["🧮 Inventarizatsiya natijasi:"]
    farqlar = []
    for spid, (tizim, sanalgan) in inv['sanoq'].items():
        if sanalgan != tizim:
            p = _omb_mahsulot(int(spid))
            if p: farqlar.append((p, tizim, sanalgan))
    kam = sum((t - s) * p['cost'] for p, t, s in farqlar if s < t)
    for p, t, s in farqlar:
        out.append(f"{'🔻' if s < t else '🔺'} {p['name']}: tizim {t} → sanoq {s} ({s - t:+d}) · {_usd2((s - t) * p['cost'])}")
    out.append(f"\nSanaldi: {len(inv['sanoq'])} ta tovar · farqli: {len(farqlar)} ta")
    if not farqlar:
        out.append("✅ Hammasi to'g'ri — hech narsa yozilmaydi.")
        return "\n".join(out), [[_btn("✅ Yopish", "omb:x")]]
    out.append(f"Kamomad (xarajat bo'ladi): {_usd2(kam)}. Ortiqcha — faqat astatkaga qo'shiladi.\n\nTasdiqlaysizmi?")
    rows = [[_btn("✅ Tasdiqlash", f"omb:iok:{st['id']}")], [_btn("⬅️ Sanashga qaytish", "omb:ibk")],
            [_btn("❌ Bekor qilish", "omb:x")]]
    return "\n".join(out), rows

async def cmd_ombor(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """📦 Ombor tugmasi / /ombor"""
    if not can(u, 'stock_view'): return
    _ui_yangi(ctx, 'omb', mode='card')
    m, r = _omb_menu(u)
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))

async def cmd_kam(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'stock_view'): return
    _ui_yangi(ctx, 'omb', mode='card')
    m, r = _omb_kam_ekran()
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))

async def omb_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not can(u, 'stock_view'):
        await q.answer(); return
    parts = (q.data or '').split(':'); act = parts[1] if len(parts) > 1 else ''; arg = parts[2:]
    def _i(k, dflt=0):
        try: return int(arg[k])
        except (IndexError, ValueError): return dflt
    if act == 'x':
        ctx.user_data.pop('omb', None); await q.answer()
        return await _pos_chiqar(q, "📦 Ombor yopildi.", None)
    st = _ui_ol(ctx, 'omb')
    if st is None:
        if act == 'menu':
            st = _ui_yangi(ctx, 'omb', mode='card')
        else:
            await q.answer()
            return await _pos_chiqar(q, "⏰ Oyna eskirgan. Qaytadan: 📦 Ombor", None)
    st['wait'] = None
    yoz = can(u, 'ombor')
    YOZ_ACTS = {'kirim', 'chiqim', 'pk', 'pc', 'kq', 'kqc', 'kc', 'kcc', 'ks', 'ksc', 'ks0', 'kp', 'kok', 'cq', 'cqc', 'cs',
                'cok', 'min', 'mv', 'mvc', 'inv', 'ik', 'iv', 'ivc', 'isk', 'ibk', 'ifin', 'iok', 'val', 'log', 'h'}
    if act in YOZ_ACTS and not yoz:
        await q.answer("Ruxsat yo'q", show_alert=True); return
    m = r = None; alert = None
    if act == 'menu':
        st.update(mode='card', pid=None); m, r = _omb_menu(u)
    elif act == 'cats':
        m, r = _omb_kat_ekran(st)
    elif act == 'k':
        m, r = _omb_kat_mahsulot(st, _i(0, -1), _i(1))
    elif act == 's':
        st['wait'] = 'search'; m, r = "🔍 Tovar nomini yozing:", [[_btn("⬅️ Orqaga", "omb:cats")] + _x_btn('omb')]
    elif act == 'f':
        m, r = _omb_qidiruv_ekran(st, _i(0))
    elif act in ('kirim', 'chiqim'):
        st.update(mode=act, pid=None); m, r = _omb_kat_ekran(st)
    elif act in ('p', 'pk', 'pc'):
        pid = _i(0); p = _omb_mahsulot(pid)
        mode = {'pk': 'kirim', 'pc': 'chiqim'}.get(act, st.get('mode', 'card'))
        if not p: alert = "Topilmadi"
        elif mode == 'kirim':
            st.update(mode='kirim', pid=pid, qty=None, cost=None, sup=None, pay=None); m, r = _omb_kirim_ekran(st)
        elif mode == 'chiqim':
            if p['qty'] <= 0: alert = "Astatkada yo'q"
            else: st.update(mode='chiqim', pid=pid, qty=None, sabab=None); m, r = _omb_chiqim_ekran(st)
        else:
            st['pid'] = pid; m, r = _omb_karta(u, pid)
    elif act == 'h':
        m, r = _omb_karta(u, _i(0), _i(1))
    elif act == 'kq':
        st['qty'] = max(1, _i(0, 1)); m, r = _omb_kirim_ekran(st)
    elif act == 'kqc':
        st['wait'] = 'kq'; m, r = "✍️ Nechta keldi? Sonni yozing:", [_x_btn('omb')]
    elif act == 'kc':
        p = _omb_mahsulot(st['pid'])
        st['cost'] = p['factory'] if (arg[:1] == ['fac'] and p.get('factory')) else p['cost']
        m, r = _omb_kirim_ekran(st)
    elif act == 'kcc':
        st['wait'] = 'kc'; m, r = "✍️ Dona tannarxini yozing ($; so'mda yozsangiz o'giraman):", [_x_btn('omb')]
    elif act == 'ks':
        sups = st.get('sups') or []
        st['sup'] = sups[_i(0)] if _i(0) < len(sups) else ''; m, r = _omb_kirim_ekran(st)
    elif act == 'ks0':
        st['sup'] = ''; m, r = _omb_kirim_ekran(st)
    elif act == 'ksc':
        st['wait'] = 'ks'; m, r = "✍️ Yetkazuvchi nomini yozing:", [_x_btn('omb')]
    elif act == 'kp':
        st['pay'] = arg[0] if arg and arg[0] in ('cash', 'debt', 'none') else None; m, r = _omb_kirim_ekran(st)
    elif act == 'kok':
        tok = 'okir' + (arg[0] if arg else '')
        if not (arg and arg[0] == st.get('id') and st.get('pay')) or not _ui_done(ctx, tok):
            await q.answer("Allaqachon saqlangan yoki eskirgan", show_alert=True); return
        res = ombor_kirim(st['pid'], st['qty'], st['cost'], st.get('sup') or '', st['pay'], _ui_user(u))
        if res['ok']:
            ctx.user_data.pop('omb', None)
            m = (f"✅ Kirim saqlandi: {res['product']} +{st['qty']} ta → {res['balance']} ta\n"
                 f"Yangi tannarx: {_usd2(res['new_cost'])} · Summa: {_usd2(res['summa'])}\n(Bekor qilish: /undo)")
            r = sn_kirim_btn([(st['pid'], st['qty'], res['product'])]) + [[_btn("📦 Ombor", "omb:menu")]]
        else:
            ctx.user_data['ui_done'].remove(tok); m, r = "⚠️ " + res['error'], [[_btn("⬅️ Ombor", "omb:menu")]]
    elif act == 'cq':
        p = _omb_mahsulot(st['pid'])
        if _i(0) > p['qty']: alert = f"Astatka: {p['qty']} ta"
        else: st['qty'] = _i(0); m, r = _omb_chiqim_ekran(st)
    elif act == 'cqc':
        st['wait'] = 'cq'; m, r = "✍️ Nechta chiqim? Sonni yozing:", [_x_btn('omb')]
    elif act == 'cs':
        st['sabab'] = arg[0] if arg and arg[0] in CHIQIM_SABAB_NOMI else None; m, r = _omb_chiqim_ekran(st)
    elif act == 'cok':
        tok = 'ochq' + (arg[0] if arg else '')
        if not (arg and arg[0] == st.get('id') and st.get('sabab')) or not _ui_done(ctx, tok):
            await q.answer("Allaqachon saqlangan yoki eskirgan", show_alert=True); return
        res = ombor_chiqim(st['pid'], st['qty'], st['sabab'], _ui_user(u))
        if res['ok']:
            ctx.user_data.pop('omb', None)
            m = (f"✅ Chiqim saqlandi: {res['product']} −{st['qty']} ta → {res['balance']} ta\n"
                 f"Xarajat: {_usd2(res['summa'])} (spisanie)\n(Bekor qilish: /undo)")
            r = [[_btn("📦 Ombor", "omb:menu")]]
        else:
            ctx.user_data['ui_done'].remove(tok); m, r = "⚠️ " + res['error'], [[_btn("⬅️ Ombor", "omb:menu")]]
    elif act == 'min':
        m, r = _omb_min_ekran(_i(0))
    elif act == 'mv':
        set_min_qty(_i(0), _i(1)); alert = None; m, r = _omb_karta(u, _i(0))
    elif act == 'mvc':
        st['wait'] = f"min:{_i(0)}"; m, r = "✍️ Minimal qoldiqni yozing:", [_x_btn('omb')]
    elif act == 'kam':
        m, r = _omb_kam_ekran()
    elif act == 'val':
        m, r = _omb_qiymat_ekran()
    elif act == 'log':
        m, r = _omb_log_ekran(_i(0))
    elif act == 'inv':
        prods = get_products(); cats = _omb_cats(prods); st['cats'] = cats
        rows = [[_btn(f"{cn[:26]} ({sum(1 for p in prods if (p['cat'] or 'Boshqa') == cn)})", f"omb:ik:{i}")]
                for i, cn in enumerate(cats)]
        rows.append([_btn(f"📋 Hammasi ({len(prods)})", "omb:ik:-1")]); rows.append([_btn("⬅️ Ombor", "omb:menu")] + _x_btn('omb'))
        m, r = "🧮 Inventarizatsiya — nimani sanaymiz?\n(Tovarlar birma-bir chiqadi; oxirida farqlar ko'rsatiladi va tasdiqlaysiz.)", rows
    elif act == 'ik':
        prods = get_products(); cats = st.get('cats') or _omb_cats(prods); ci = _i(0, -1)
        sel = prods if not (0 <= ci < len(cats)) else [p for p in prods if (p['cat'] or 'Boshqa') == cats[ci]]
        st['inv'] = {'pids': [p['id'] for p in sorted(sel, key=lambda p: (p['cat'] or '', p['name']))], 'i': 0, 'sanoq': {}}
        st['id'] = secrets.token_hex(4)
        m, r = _inv_ekran(st)
    elif act in ('iv', 'isk', 'ibk', 'ifin'):
        inv = st.get('inv')
        if not inv: alert = "Inventarizatsiya boshlanmagan"
        else:
            if act == 'iv' and inv['i'] < len(inv['pids']):
                inv['sanoq'][str(inv['pids'][inv['i']])] = [st.get('inv_tizim', 0), max(0, _i(0))]; inv['i'] += 1
            elif act == 'isk': inv['i'] += 1
            elif act == 'ibk': inv['i'] = max(0, min(inv['i'], len(inv['pids'])) - 1)
            elif act == 'ifin': inv['i'] = len(inv['pids'])
            m, r = _inv_ekran(st)
    elif act == 'ivc':
        st['wait'] = 'iv'; m, r = "✍️ Sanagan sonni yozing:", [_x_btn('omb')]
    elif act == 'iok':
        tok = 'oinv' + (arg[0] if arg else '')
        if not (arg and arg[0] == st.get('id') and st.get('inv')) or not _ui_done(ctx, tok):
            await q.answer("Allaqachon saqlangan yoki eskirgan", show_alert=True); return
        sanoq = {int(k): tuple(v) for k, v in st['inv']['sanoq'].items()}
        res = ombor_inventar(sanoq, _ui_user(u))
        if res['ok']:
            ctx.user_data.pop('omb', None)
            m = (f"✅ Inventarizatsiya saqlandi: {len(res['qatorlar'])} ta tuzatish"
                 + (f", kamomad xarajati {_usd2(res['kamomad'])}" if res['kamomad'] else "") + "\n(Bekor qilish: /undo)")
            r = [[_btn("📦 Ombor", "omb:menu")]]
        else:
            ctx.user_data['ui_done'].remove(tok); m, r = "⚠️ " + res['error'], [[_btn("⬅️ Ombor", "omb:menu")]]
    else:
        alert = "Eski tugma"
    await q.answer(alert[:190] if alert else None, show_alert=bool(alert))
    if m is not None: await _pos_chiqar(q, m, r)

async def omb_matn(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    st0 = ctx.user_data.get('omb')
    if not st0 or not st0.get('wait') or not can(u, 'stock_view'): return False
    st = _ui_ol(ctx, 'omb')
    if st is None:
        await u.message.reply_text("⏰ Oyna eskirgan. Qaytadan: 📦 Ombor"); return True
    w = st['wait']; st['wait'] = None
    msg = (u.message.text or '').strip()
    def son():
        t = re.sub(r'[^\d]', '', msg)
        return int(t) if t and len(t) < 9 else None
    m = r = None
    def qayta(x):
        st['wait'] = w; return f"⚠️ {x}\nQaytadan yozing.", [_x_btn('omb')]
    if w == 'search' and kod_top(msg):          # shtrix-kod / serial → to'g'ridan-to'g'ri karta
        return await kod_natija(u, ctx, msg, 'omb')
    if w == 'search':
        topildi = pos_qidir(msg); st['found'] = [p['id'] for p in topildi]
        m, r = _omb_qidiruv_ekran(st)
        if not topildi: st['wait'] = 'search'; m = f"🔍 '{msg[:40]}' topilmadi. Boshqacha yozing:"
    elif not can(u, 'ombor'):
        return False
    elif w == 'kq':
        n = son()
        if not n: m, r = qayta("Musbat son yozing")
        else: st['qty'] = n; m, r = _omb_kirim_ekran(st)
    elif w == 'kc':
        v = _pos_son(msg)
        if v is None or v < 0: m, r = qayta("Narxni raqam bilan yozing")
        else: st['cost'] = round(v, 2); m, r = _omb_kirim_ekran(st)
    elif w == 'ks':
        st['sup'] = msg[:60]; m, r = _omb_kirim_ekran(st)
    elif w == 'cq':
        n = son(); p = _omb_mahsulot(st['pid'])
        if not n: m, r = qayta("Musbat son yozing")
        elif n > p['qty']: m, r = qayta(f"Astatka: {p['qty']} ta")
        else: st['qty'] = n; m, r = _omb_chiqim_ekran(st)
    elif w.startswith('min:'):
        n = son()
        if n is None: m, r = qayta("Son yozing (0 — kuzatilmaydi)")
        else:
            pid = int(w.split(':')[1]); set_min_qty(pid, n); m, r = _omb_karta(u, pid)
    elif w == 'iv':
        n = son()
        if n is None: m, r = qayta("Son yozing")
        else:
            inv = st['inv']
            if inv['i'] < len(inv['pids']):
                inv['sanoq'][str(inv['pids'][inv['i']])] = [st.get('inv_tizim', 0), n]; inv['i'] += 1
            m, r = _inv_ekran(st)
    else:
        return False
    await u.message.reply_text(m[:4000], reply_markup=InlineKeyboardMarkup(r) if r else None)
    return True

async def _ertalab_ogohlantirish(app):
    """Ertalabki xulosadan keyin: kam qolgan tovarlar (+ kechikkan zavod buyurtmalari) — egasiga."""
    qism = []
    ks = kam_qolganlar()
    if ks:
        qism.append("⚠️ Kam qolgan tovarlar:\n" + "\n".join(f"• {k['name']} — {k['qty']} ta (min {k['min']})" for k in ks[:20]))
    try:
        kech = zavod_kechikkanlar()
    except NameError:
        kech = []
    if kech:
        qism.append("⏰ Kechikkan zavod buyurtmalari:\n" + "\n".join(
            f"• #{p['id']} {p['supplier']} — kutilgan {p['expected']} ({p['kun']} kun kechikdi)" for p in kech[:10]))
    if qism and app is not None:
        await app.bot.send_message(chat_id=OWNER_ID, text="\n\n".join(qism)[:4000])
    return qism

# ── 👥 MIJOZLAR VA QARZLAR (tugmali) ──────────────────────────────
# Ko'rish/qo'shish — 'customer_add' (sotuvchi ham: faqat ism, telefon, tur); qarz, tarix, akt, tahrir — 'boshqaruv'.
QARZ_MUDDAT_KUN = 30          # shundan eski debitorlik — "muddati o'tgan" (⏰)

def _kun_farq(sana):
    try: return (datetime.now() - datetime.strptime(str(sana)[:10], '%Y-%m-%d')).days
    except (TypeError, ValueError): return 0

def _mijoz_row(cid):
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, name, COALESCE(phone,''), COALESCE(type,'B2C'), COALESCE(notes,''), COALESCE(created,'') "
              "FROM customers WHERE id=?", (cid,))
    r = c.fetchone(); conn.close()
    return {'id': r[0], 'name': r[1], 'phone': r[2], 'type': r[3], 'notes': r[4], 'created': r[5]} if r else None

def _mijoz_qarzlari(c, cid, name):
    """Mijozning ochiq debitorligi: customer_id bo'yicha yoki (bog'lanmagan) ism bo'yicha."""
    c.execute(f"SELECT id, date, amount, note, COALESCE(customer_id,0), person FROM debts "
              f"WHERE paid=0 AND amount>0 AND type IN {DEBITOR_SQL}")
    n = norm_ism(name)
    return [r for r in c.fetchall() if r[4] == cid or (not r[4] and norm_ism(r[5]) == n)]

def _mijoz_barcha_qarz_idlar(c, cid, name):
    c.execute(f"SELECT id, COALESCE(customer_id,0), person FROM debts WHERE type IN {DEBITOR_SQL}")
    n = norm_ism(name)
    return {r[0] for r in c.fetchall() if r[1] == cid or (not r[1] and norm_ism(r[2]) == n)}

def _qarz_yosh_bolaklari(qarzlar):
    b = {'0-30': 0.0, '31-60': 0.0, '61-90': 0.0, '90+': 0.0}
    for r in qarzlar:
        k = _kun_farq(r[1]); a = r[2] or 0
        b['0-30' if k <= 30 else '31-60' if k <= 60 else '61-90' if k <= 90 else '90+'] += a
    return {k: round(v, 2) for k, v in b.items()}

def mijoz_malumot(cid):
    """Karta uchun: mijoz + jami xarid, oxirgi xarid, ochiq debitorlik, yosh bo'laklari."""
    m = _mijoz_row(cid)
    if not m: return None
    conn = db(); c = conn.cursor()
    c.execute("SELECT COUNT(*), COALESCE(SUM(revenue),0), MAX(date) FROM sales WHERE reversed=0 AND COALESCE(customer_id,0)=?", (cid,))
    n, jami, oxirgi = c.fetchone()
    qarz = _mijoz_qarzlari(c, cid, m['name']); conn.close()
    m.update(sotuv_soni=n, jami=round(jami or 0, 2), oxirgi=oxirgi or '', qarz=round(sum(r[2] for r in qarz), 2),
             qarzlar=qarz, yosh=_qarz_yosh_bolaklari(qarz),
             eng_eski=max((_kun_farq(r[1]) for r in qarz), default=0))
    return m

def mijoz_xaridlari(cid, limit=8, offset=0):
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, date, product, qty, revenue FROM sales WHERE reversed=0 AND COALESCE(customer_id,0)=? "
              "ORDER BY id DESC LIMIT ? OFFSET ?", (cid, limit, offset))
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM sales WHERE reversed=0 AND COALESCE(customer_id,0)=?", (cid,))
    n = c.fetchone()[0]; conn.close()
    return rows, n

def mijoz_tahrir(cid, **kv):
    ruxsat = {'name', 'phone', 'type', 'notes'}
    sets = [(k, v) for k, v in kv.items() if k in ruxsat]
    if not sets: return False
    conn = db(); c = conn.cursor()
    c.execute('UPDATE customers SET ' + ', '.join(f'{k}=?' for k, _ in sets) + ' WHERE id=?', [v for _, v in sets] + [cid])
    ok = c.rowcount > 0; conn.commit(); conn.close()
    return ok

def qarzdorlar(tartib='sum'):
    """Ochiq debitorlik — mijoz (yoki bog'lanmagan ism) bo'yicha: [{'cid','name','sum','kun','kechikkan'}]"""
    conn = db(); c = conn.cursor()
    c.execute(f"SELECT d.date, d.amount, COALESCE(d.customer_id,0), d.person, c.name FROM debts d "
              f"LEFT JOIN customers c ON c.id=d.customer_id WHERE d.paid=0 AND d.amount>0 AND d.type IN {DEBITOR_SQL}")
    rows = c.fetchall()
    c.execute("SELECT id, name FROM customers")
    by_norm = {}
    for i, nm in c.fetchall(): by_norm.setdefault(norm_ism(nm), i)
    conn.close()
    agg = {}
    for d, amt, cid, person, cname in rows:
        cid = cid or by_norm.get(norm_ism(person), 0)
        key = cid or ('n:' + norm_ism(person))
        a = agg.setdefault(key, {'cid': cid, 'name': cname or person or '?', 'sum': 0.0, 'kun': 0})
        a['sum'] += amt or 0; a['kun'] = max(a['kun'], _kun_farq(d))
    out = [dict(a, sum=round(a['sum'], 2), kechikkan=a['kun'] > QARZ_MUDDAT_KUN) for a in agg.values()]
    out.sort(key=(lambda a: (-a['kun'], -a['sum'])) if tartib == 'kun' else (lambda a: (-a['sum'], -a['kun'])))
    return out

def kreditorlar():
    """Biz qarzdor bo'lganlar (zavod/yetkazuvchi): debts kreditorlik + transit qoldig'i."""
    conn = db(); c = conn.cursor()
    c.execute(f"SELECT person, amount, date FROM debts WHERE paid=0 AND amount>0 AND type IN {KREDITOR_SQL}")
    rows = [(p, a, d) for p, a, d in c.fetchall()]
    c.execute("SELECT supplier, remaining, date FROM transit WHERE remaining>0")
    rows += c.fetchall(); conn.close()
    agg = {}
    for p, a, d in rows:
        x = agg.setdefault(norm_ism(p) or '?', {'name': p or '?', 'sum': 0.0, 'kun': 0})
        x['sum'] += a or 0; x['kun'] = max(x['kun'], _kun_farq(d))
    return sorted(({**v, 'sum': round(v['sum'], 2)} for v in agg.values()), key=lambda v: -v['sum'])

def eslatma_matni(name, summa, kun):
    """Mijozga yuborish uchun NUSXA matn (bot o'zi yubormaydi)."""
    return (f"Assalomu alaykum, {name}!\nThermoCrafts do'konidan bezovta qilyapmiz. "
            f"Sizning {_usd2(summa)} (≈ {summa * get_exchange_rate():,.0f} so'm) qarzingiz bor"
            + (f", eng eskisi {kun} kun oldin" if kun else "") + ".\n"
            "Iltimos, qulay vaqtda to'lab bersangiz. Savollar bo'lsa yozing. Rahmat!")

AKT_DAVRLAR = (('oy', 'Bu oy'), ('otgan', "O'tgan oy"), ('3oy', '3 oy'), ('yil', 'Bu yil'), ('hammasi', 'Hammasi'))

def _akt_oraliq(kod):
    bugun = datetime.now(); d2 = bugun.strftime('%Y-%m-%d')
    if kod == 'oy': return bugun.strftime('%Y-%m-01'), d2
    if kod == 'otgan':
        oxiri = bugun.replace(day=1) - timedelta(days=1)
        return oxiri.strftime('%Y-%m-01'), oxiri.strftime('%Y-%m-%d')
    if kod == '3oy': return (bugun - timedelta(days=90)).strftime('%Y-%m-%d'), d2
    if kod == 'yil': return bugun.strftime('%Y-01-01'), d2
    return '2000-01-01', d2

def akt_sverka(cid, d1, d2):
    """Solishtirish dalolatnomasi (akt sverka): davrdagi xaridlar, qarzga yozilganlar va to'lovlar.
    Yakuniy qoldiq HOZIRGI ochiq qarzdan orqaga hisoblanadi (doim haqiqiy qoldiq bilan mos)."""
    m = _mijoz_row(cid)
    if not m: return None
    conn = db(); c = conn.cursor()
    ids = _mijoz_barcha_qarz_idlar(c, cid, m['name'])
    hozir = round(sum(r[2] for r in _mijoz_qarzlari(c, cid, m['name'])), 2)
    # Har bir qarz yozuviga tushgan to'lovlar (op_log)
    c.execute("SELECT id, date, data_json FROM op_log WHERE op_type='debt_payment' AND reversed=0")
    tolovlar = []; tolangan_qism = defaultdict(float)
    for oid, sana, dj in c.fetchall():
        try: d = json.loads(dj or '{}')
        except ValueError: continue
        if d.get('kind') != DEBITOR: continue
        s = sum(it['part'] for it in d.get('items', []) if it.get('src') == 'debt' and it.get('id') in ids)
        for it in d.get('items', []):
            if it.get('src') == 'debt' and it.get('id') in ids: tolangan_qism[it['id']] += it['part']
        if s > 0: tolovlar.append((sana, round(s, 2), d.get('method', ''), oid))
    # Qarz yozuvlari (asl summa ≈ hozirgi + to'langan qism); sotuvdan kelgan nasiya — sotuv qatorida ko'rinadi
    qarz_yoz = []
    if ids:
        c.execute(f"SELECT id, date, amount, note, paid FROM debts WHERE id IN ({','.join('?' * len(ids))})", list(ids))
        for did, sana, amt, note, paid in c.fetchall():
            if paid and 'bekor' in (note or ''): continue            # sotuv bekor qilingani bilan yopilgan
            asl = round((amt or 0) + tolangan_qism.get(did, 0), 2)
            qarz_yoz.append((sana, asl, note or '', did))
    # Xaridlar
    c.execute("SELECT id, date, product, qty, revenue FROM sales WHERE reversed=0 AND COALESCE(customer_id,0)=? ORDER BY date, id", (cid,))
    sotuvlar = []
    for sid, sana, pr, qty, rev in c.fetchall():
        c.execute("SELECT payment_method FROM cash_box WHERE type='kirim' AND note LIKE ? LIMIT 1", (f'%(#{sid})',))
        pm = c.fetchone()
        sotuvlar.append((sana, pr, qty, round(rev or 0, 2), pm[0] if pm else 'nasiya', sid))
    conn.close()
    debet = lambda s_, e_: round(sum(a for d_, a, _n, _i in qarz_yoz if s_ <= d_ <= e_), 2)
    kredit = lambda s_, e_: round(sum(a for d_, a, _m, _o in tolovlar if s_ <= d_ <= e_), 2)
    keyin_d, keyin_k = debet(d2 + '~', '9999'), kredit(d2 + '~', '9999')
    yakun = round(hozir - keyin_d + keyin_k, 2)
    dav_d, dav_k = debet(d1, d2), kredit(d1, d2)
    boshi = round(yakun - dav_d + dav_k, 2)
    return {'mijoz': m, 'd1': d1, 'd2': d2, 'boshi': boshi, 'yakun': yakun, 'qarzga': dav_d, 'tolandi': dav_k,
            'sotuvlar': [s for s in sotuvlar if d1 <= s[0] <= d2],
            'qarz_yoz': sorted(x for x in qarz_yoz if d1 <= x[0] <= d2),
            'tolovlar': sorted(x for x in tolovlar if d1 <= x[0] <= d2), 'hozir': hozir}

def akt_matn(a):
    m = a['mijoz']
    out = [f"📋 AKT SVERKA — {m['name']}", f"Davr: {a['d1']} … {a['d2']}", "",
           f"Davr boshiga qarz: {_usd2(a['boshi'])}"]
    if a['sotuvlar']:
        out.append("\n🛒 Xaridlar:")
        for sana, pr, qty, rev, pm, _sid in a['sotuvlar']:
            out.append(f"{sana} · {pr} × {qty} = {_usd2(rev)} · {'📝 nasiya' if pm == 'nasiya' else pm}")
        out.append(f"Jami xarid: {_usd2(sum(s[3] for s in a['sotuvlar']))}")
    if a['qarz_yoz']:
        out.append("\n➕ Qarzga yozilgan:")
        out += [f"{sana} · {_usd2(asl)} · {note[:50]}" for sana, asl, note, _ in a['qarz_yoz']]
    if a['tolovlar']:
        out.append("\n➖ To'lovlar:")
        out += [f"{sana} · {_usd2(s)} · {pm}" for sana, s, pm, _ in a['tolovlar']]
    out += ["", f"Qarzga: +{_usd2(a['qarzga'])} · To'landi: −{_usd2(a['tolandi'])}",
            f"Davr oxiriga qarz: {_usd2(a['yakun'])}" + (f" (hozir: {_usd2(a['hozir'])})" if a['yakun'] != a['hozir'] else "")]
    return "\n".join(out)

def akt_html(a, path):
    def e(v): return _html.escape(str(v if v is not None else ''))
    m = a['mijoz']
    qator = []
    for sana, pr, qty, rev, pm, _ in a['sotuvlar']:
        qator.append((sana, f"Xarid: {pr} × {qty} ({pm})", rev if pm == 'nasiya' else 0, 0, rev))
    for sana, asl, note, _ in a['qarz_yoz']:
        if not note.startswith('nasiya'): qator.append((sana, f"Qarz yozildi: {note}", asl, 0, 0))
    for sana, s, pm, _ in a['tolovlar']:
        qator.append((sana, f"To'lov ({pm})", 0, s, 0))
    qator.sort(key=lambda r: r[0])
    tr = ''.join(f"<tr><td>{e(s)}</td><td>{e(t)}</td><td class=r>{'' if not d else f'${d:,.2f}'}</td>"
                 f"<td class=r>{'' if not k else f'${k:,.2f}'}</td></tr>" for s, t, d, k, _x in qator)
    html = f"""<!DOCTYPE html><html lang=uz><head><meta charset=utf-8><title>Akt sverka</title><style>
body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;margin:0 auto;padding:24px;color:#111}}
table{{width:100%;border-collapse:collapse;font-size:13px}} th,td{{padding:6px;border-bottom:1px solid #ddd;text-align:left}}
.r{{text-align:right}} .b td{{font-weight:700}}</style></head><body>
<h2>{e(FIRMA['nom'])} — Solishtirish dalolatnomasi (akt sverka)</h2>
<p>Mijoz: <b>{e(m['name'])}</b> {e(m['phone'])}<br>Davr: {e(a['d1'])} — {e(a['d2'])}</p>
<table><thead><tr><th>Sana</th><th>Izoh</th><th class=r>Qarzga (+)</th><th class=r>To'landi (−)</th></tr></thead><tbody>
<tr class=b><td></td><td>Davr boshiga qarz</td><td class=r>${a['boshi']:,.2f}</td><td></td></tr>{tr}
<tr class=b><td></td><td>Davr oxiriga qarz</td><td class=r>${a['yakun']:,.2f}</td><td></td></tr></tbody></table>
<p style="margin-top:40px">Topshirdi: ____________ &nbsp;&nbsp;&nbsp; Qabul qildi: ____________</p></body></html>"""
    with open(path, 'w', encoding='utf-8') as f: f.write(html)
    return path

def akt_excel(a, path_base):
    """openpyxl bo'lsa .xlsx, aks holda .csv. Qaytaradi: yo'l."""
    rows = [("Sana", "Turi", "Izoh", "Qarzga (+)", "To'landi (−)", "Xarid summasi")]
    rows.append(("", "", "Davr boshiga qarz", a['boshi'], "", ""))
    for sana, pr, qty, rev, pm, _ in a['sotuvlar']:
        rows.append((sana, "xarid", f"{pr} x{qty} ({pm})", rev if pm == 'nasiya' else "", "", rev))
    for sana, asl, note, _ in a['qarz_yoz']:
        if not note.startswith('nasiya'): rows.append((sana, "qarz", note, asl, "", ""))
    for sana, s, pm, _ in a['tolovlar']:
        rows.append((sana, "to'lov", pm, "", s, ""))
    rows.append(("", "", "Davr oxiriga qarz", a['yakun'], "", ""))
    return _jadval_fayl({'Akt sverka': rows}, path_base)

def _jadval_fayl(varaqlar, path_base):
    """{varaq_nomi: [qatorlar]} → .xlsx (openpyxl) yoki .csv (bo'lmasa). Qaytaradi: yo'l."""
    try:
        import openpyxl
        from openpyxl.styles import Font
        wb = openpyxl.Workbook(); wb.remove(wb.active)
        for nom, rows in varaqlar.items():
            ws = wb.create_sheet(nom[:30])
            for r in rows: ws.append(list(r))
            for cell in ws[1]: cell.font = Font(bold=True)
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(45, max(10, max(len(str(c.value or '')) for c in col) + 2))
        p = path_base + '.xlsx'; wb.save(p); return p
    except ImportError:
        import csv
        p = path_base + '.csv'
        with open(p, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            for nom, rows in varaqlar.items():
                w.writerow([f"## {nom}"]); w.writerows(rows); w.writerow([])
        return p

# ── Ekranlar ──
def _mij_menu(u):
    rows = [[_btn("🔍 Qidirish", "mij:s"), _btn("📋 Ro'yxat", "mij:l:0")], [_btn("➕ Yangi mijoz", "mij:n")]]
    if can(u, 'boshqaruv'):
        rows.append([_btn("💳 Qarzdorlar", "mij:deb:sum:0"), _btn("🏭 Kreditorlar", "mij:kre")])
    rows.append(_x_btn('mij'))
    return "👥 Mijozlar — bo'limni tanlang", rows

def _mij_royxat(u, mijozlar, page, nav, sarlavha):
    bosh = can(u, 'boshqaruv')
    pages = max(1, math.ceil(len(mijozlar) / POS_SAHIFA)); page = min(max(0, page), pages - 1)
    rows = []
    for m in mijozlar[page * POS_SAHIFA:(page + 1) * POS_SAHIFA]:
        t = m['nom'][:28] + (f" · {m['tel'][-4:]}" if m.get('tel') else "")
        if bosh and m.get('jami'): t += f" · {_usd2(m['jami'])}"
        rows.append([_btn(t, f"mij:c:{m['id']}")])
    if pages > 1:
        nv = []
        if page > 0: nv.append(_btn("⬅️", f"{nav}:{page - 1}"))
        nv.append(_btn(f"{page + 1}/{pages}", "pos:noop"))
        if page < pages - 1: nv.append(_btn("➡️", f"{nav}:{page + 1}"))
        rows.append(nv)
    rows.append([_btn("🔍 Qidirish", "mij:s"), _btn("➕ Yangi", "mij:n")])
    rows.append([_btn("⬅️ Menyu", "mij:menu")] + _x_btn('mij'))
    return (f"{sarlavha} ({len(mijozlar)} ta)" if mijozlar else f"{sarlavha}: topilmadi"), rows

def _mij_hammasi(u):
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, name, COALESCE(phone,''), COALESCE(total_purchases,0) FROM customers ORDER BY "
              + ("total_purchases DESC, name" if can(u, 'boshqaruv') else "name"))
    r = [{'id': x[0], 'nom': x[1], 'tel': x[2], 'jami': x[3]} for x in c.fetchall()]; conn.close()
    return r

def _mij_karta(u, cid):
    m = mijoz_malumot(cid)
    if not m: return "Mijoz topilmadi", [[_btn("⬅️ Menyu", "mij:menu")]]
    out = [f"👤 {m['name']}", f"📞 {m['phone'] or '-'} · {m['type']}"]
    rows = []
    if can(u, 'boshqaruv'):
        out.append(f"Jami xarid: {_usd2(m['jami'])} ({m['sotuv_soni']} ta) · oxirgi: {m['oxirgi'] or '-'}")
        if m['qarz'] > 0:
            y = m['yosh']
            out.append(f"\n💳 Qarzi (debitorlik): {_usd2(m['qarz'])}" + (" ⏰ muddati o'tgan" if m['eng_eski'] > QARZ_MUDDAT_KUN else ""))
            out.append("Yoshi: " + " · ".join(f"{k} kun: {_usd2(v)}" for k, v in y.items() if v))
        else:
            out.append("✅ Qarzi yo'q")
        if m['notes']: out.append(f"📝 {m['notes']}")
        if m['qarz'] > 0: rows.append([_btn("💵 Qarz to'lovi", f"mij:pay:{cid}"), _btn("📝 Eslatma matni", f"mij:rem:{cid}")])
        rows.append([_btn("📜 Xaridlar", f"mij:h:{cid}:0"), _btn("📋 Akt sverka", f"mij:akt:{cid}")])
        rows.append([_btn("✏️ Tahrirlash", f"mij:e:{cid}"), _btn("📞 Telefon", f"mij:tel:{cid}")])
    else:
        rows.append([_btn("📞 Telefon", f"mij:tel:{cid}")])
    if can(u, 'pos'): rows.append([_btn("🛒 Shu mijozga sotish", f"mij:sell:{cid}")])
    rows.append([_btn("⬅️ Ro'yxat", "mij:l:0")] + _x_btn('mij'))
    return "\n".join(out), rows

def _mij_tarix(cid, page):
    m = _mijoz_row(cid); rows_, n = mijoz_xaridlari(cid, 8, page * 8)
    pages = max(1, math.ceil(n / 8))
    out = [f"📜 {m['name']} — xaridlar ({n} ta, {page + 1}/{pages}):"] + \
          [f"{d} · {pr} × {qty} = {_usd2(rev)}" for _i, d, pr, qty, rev in rows_] + (["(yo'q)"] if not rows_ else [])
    nv = []
    if page > 0: nv.append(_btn("⬅️", f"mij:h:{cid}:{page - 1}"))
    if page < pages - 1: nv.append(_btn("➡️", f"mij:h:{cid}:{page + 1}"))
    return "\n".join(out), ([nv] if nv else []) + [[_btn("⬅️ Karta", f"mij:c:{cid}")] + _x_btn('mij')]

def _mij_tahrir_ekran(cid):
    m = _mijoz_row(cid)
    return (f"✏️ {m['name']}\n📞 {m['phone'] or '-'} · {m['type']}\n📝 {m['notes'] or '-'}\n\nNimani o'zgartiramiz?",
            [[_btn("✏️ Ism", f"mij:en:{cid}"), _btn("📞 Telefon", f"mij:ep:{cid}")],
             [_btn(f"🔁 Tur: {m['type']} → {'B2C' if m['type'] == 'B2B' else 'B2B'}", f"mij:et:{cid}"), _btn("📝 Izoh", f"mij:ez:{cid}")],
             [_btn("⬅️ Karta", f"mij:c:{cid}")] + _x_btn('mij')])

def _mij_tolov_ekran(st):
    p = st['pay']
    out = [f"💵 To'lov: {p['name']} ({'mijoz qarzi' if p['kind'] == DEBITOR else 'biz qarzmiz'})", f"Ochiq qarz: {_usd2(p['qarz'])}"]
    rows = []
    if not p.get('summa'):
        out.append("\nQancha to'landi?")
        rows.append([_btn(f"To'liq {_usd2(p['qarz'])}", "mij:ps:all")] +
                    ([_btn(f"Yarmi {_usd2(p['qarz'] / 2)}", "mij:ps:half")] if p['qarz'] >= 2 else []))
        rows.append([_btn("✍️ Summa yozish", "mij:psc")])
    elif not p.get('usul'):
        out.append(f"Summa: {_usd2(p['summa'])}\n\nQanday to'landi?")
        b = [_btn(nom, f"mij:pm:{k}") for k, nom in POS_USULLAR if k != 'nasiya']
        rows += [b[i:i + 2] for i in range(0, len(b), 2)]
    else:
        out.append(f"Summa: {_usd2(p['summa'])} · Usul: {POS_USUL_NOMI.get(p['usul'], p['usul'])}\n\nTasdiqlaysizmi?")
        rows.append([_btn("✅ Tasdiqlash", f"mij:pok:{st['id']}")])
    rows.append([_btn("⬅️ Orqaga", f"mij:c:{p['cid']}" if p.get('cid') else ("mij:kre" if p['kind'] == KREDITOR else "mij:deb:sum:0"))]
                + _x_btn('mij'))
    return "\n".join(out), rows

def _mij_deb_ekran(st, tartib, page):
    ds = qarzdorlar(tartib); st['deb'] = ds
    jami = round(sum(d['sum'] for d in ds), 2)
    pages = max(1, math.ceil(len(ds) / POS_SAHIFA)); page = min(max(0, page), pages - 1)
    out = [f"💳 Qarzdorlar (debitorlik): {len(ds)} ta · jami {_usd2(jami)}",
           f"Tartib: {'summa' if tartib == 'sum' else 'yoshi'} · ⏰ — {QARZ_MUDDAT_KUN} kundan eski"]
    rows = [[_btn(f"{'⏰ ' if d['kechikkan'] else ''}{d['name'][:24]} · {_usd2(d['sum'])} · {d['kun']} kun", f"mij:dc:{page * POS_SAHIFA + i}")]
            for i, d in enumerate(ds[page * POS_SAHIFA:(page + 1) * POS_SAHIFA])]
    nv = []
    if page > 0: nv.append(_btn("⬅️", f"mij:deb:{tartib}:{page - 1}"))
    if pages > 1: nv.append(_btn(f"{page + 1}/{pages}", "pos:noop"))
    if page < pages - 1: nv.append(_btn("➡️", f"mij:deb:{tartib}:{page + 1}"))
    if nv: rows.append(nv)
    rows.append([_btn("↕️ Summa bo'yicha" if tartib == 'kun' else "↕️ Yoshi bo'yicha", f"mij:deb:{'sum' if tartib == 'kun' else 'kun'}:0")])
    rows.append([_btn("⬅️ Menyu", "mij:menu")] + _x_btn('mij'))
    return "\n".join(out), rows

def _mij_kre_ekran(st):
    ks = kreditorlar(); st['kre'] = ks
    out = [f"🏭 Kreditorlar (biz qarzmiz): jami {_usd2(sum(k['sum'] for k in ks))}"] + \
          [f"• {k['name']}: {_usd2(k['sum'])} · eng eskisi {k['kun']} kun" for k in ks] + (["✅ Qarzimiz yo'q"] if not ks else [])
    rows = [[_btn(f"💵 {k['name'][:24]} · {_usd2(k['sum'])}", f"mij:kp:{i}")] for i, k in enumerate(ks[:10])]
    rows.append([_btn("⬅️ Menyu", "mij:menu")] + _x_btn('mij'))
    return "\n".join(out), rows

async def cmd_mijozlar_ui(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'customer_add'): return
    _ui_yangi(ctx, 'mij')
    m, r = _mij_menu(u)
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))

async def cmd_qarzdorlar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    st = _ui_yangi(ctx, 'mij')
    m, r = _mij_deb_ekran(st, 'sum', 0)
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))

async def _mij_fayl(u, ctx, a, tur):
    base = f"/tmp/akt_{a['mijoz']['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    p = await asyncio.to_thread(akt_html, a, base + '.html') if tur == 'html' else await asyncio.to_thread(akt_excel, a, base)
    try:
        with open(p, 'rb') as fh:
            await ctx.bot.send_document(chat_id=u.effective_chat.id, document=fh,
                                        filename=f"akt_{norm_ism(a['mijoz']['name']).replace(' ', '_') or 'mijoz'}{os.path.splitext(p)[1]}",
                                        caption=f"📋 Akt sverka · {a['mijoz']['name']} · {a['d1']}…{a['d2']}")
    finally:
        try: os.remove(p)
        except OSError: pass

async def mij_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not can(u, 'customer_add'):
        await q.answer(); return
    parts = (q.data or '').split(':'); act = parts[1] if len(parts) > 1 else ''; arg = parts[2:]
    def _i(k, dflt=0):
        try: return int(arg[k])
        except (IndexError, ValueError): return dflt
    if act == 'x':
        ctx.user_data.pop('mij', None); await q.answer()
        return await _pos_chiqar(q, "👥 Mijozlar yopildi.", None)
    st = _ui_ol(ctx, 'mij')
    if st is None:
        if act == 'menu': st = _ui_yangi(ctx, 'mij')
        else:
            await q.answer(); return await _pos_chiqar(q, "⏰ Oyna eskirgan. Qaytadan: 👥 Mijozlar", None)
    st['wait'] = None
    BOSH = {'h', 'akt', 'ap', 'af', 'e', 'en', 'ep', 'et', 'ez', 'pay', 'ps', 'psc', 'pm', 'pok', 'deb', 'dc', 'kre', 'kp', 'rem'}
    if act in BOSH and not can(u, 'boshqaruv'):
        await q.answer("Ruxsat yo'q", show_alert=True); return
    m = r = None; alert = None
    if act == 'menu': m, r = _mij_menu(u)
    elif act == 'l': m, r = _mij_royxat(u, _mij_hammasi(u), _i(0), "mij:l", "📋 Mijozlar")
    elif act == 's':
        st['wait'] = 'search'; m, r = "🔍 Mijoz ismi yoki telefonini yozing:", [[_btn("⬅️ Menyu", "mij:menu")] + _x_btn('mij')]
    elif act == 'f':
        m, r = _mij_royxat(u, st.get('found') or [], _i(0), "mij:f", "🔍 Natija")
    elif act == 'n':
        st['wait'] = 'new'
        m, r = ("➕ Yangi mijoz: ism va telefonni yozing (B2B bo'lsa oxiriga B2B)\nMasalan: Alisher Karimov +998901234567",
                [[_btn("⬅️ Menyu", "mij:menu")] + _x_btn('mij')])
    elif act == 'c': m, r = _mij_karta(u, _i(0))
    elif act == 'h': m, r = _mij_tarix(_i(0), _i(1))
    elif act == 'tel':
        mm = _mijoz_row(_i(0))
        if not mm or not mm['phone']: alert = "Telefon yozilmagan"
        else:
            await q.answer()
            await q.message.reply_text(f"📞 {mm['name']}: {mm['phone']}")
            return
    elif act == 'sell':
        mm = _mijoz_row(_i(0))
        if not mm or not can(u, 'pos'): alert = "Ruxsat yo'q"
        else:
            pos = _pos_ol(ctx) or _pos_yangi(ctx)
            pos['cust'] = {'id': mm['id'], 'name': mm['name'], 'phone': mm['phone'], 'type': mm['type']}
            ctx.user_data.pop('mij', None)
            m, r = pos_ekran_kategoriya(pos); m = f"👤 Mijoz: {mm['name']}\n" + m
    elif act == 'e': m, r = _mij_tahrir_ekran(_i(0))
    elif act in ('en', 'ep', 'ez'):
        st['wait'] = f"{act}:{_i(0)}"
        m, r = ({'en': "✍️ Yangi ismni yozing:", 'ep': "✍️ Yangi telefonni yozing:", 'ez': "✍️ Izohni yozing:"}[act],
                [[_btn("⬅️ Orqaga", f"mij:e:{_i(0)}")] + _x_btn('mij')])
    elif act == 'et':
        mm = _mijoz_row(_i(0))
        mijoz_tahrir(_i(0), type='B2C' if mm['type'] == 'B2B' else 'B2B'); m, r = _mij_tahrir_ekran(_i(0))
    elif act == 'rem':
        mm = mijoz_malumot(_i(0))
        await q.answer()
        await q.message.reply_text("📝 Nusxa olib, mijozga o'zingiz yuboring (bot yubormaydi):\n\n"
                                   + eslatma_matni(mm['name'], mm['qarz'], mm['eng_eski']))
        return
    elif act == 'pay':
        mm = mijoz_malumot(_i(0))
        if not mm or mm['qarz'] <= 0: alert = "Ochiq qarz yo'q"
        else:
            st['id'] = secrets.token_hex(4)
            st['pay'] = {'kind': DEBITOR, 'name': mm['name'], 'cid': mm['id'], 'qarz': mm['qarz']}
            m, r = _mij_tolov_ekran(st)
    elif act == 'kp':
        ks = st.get('kre') or kreditorlar()
        if _i(0) >= len(ks): alert = "Eskirgan"
        else:
            k = ks[_i(0)]; st['id'] = secrets.token_hex(4)
            st['pay'] = {'kind': KREDITOR, 'name': k['name'], 'cid': 0, 'qarz': k['sum']}
            m, r = _mij_tolov_ekran(st)
    elif act == 'ps' and st.get('pay'):
        st['pay']['summa'] = st['pay']['qarz'] if arg[:1] == ['all'] else round(st['pay']['qarz'] / 2, 2)
        m, r = _mij_tolov_ekran(st)
    elif act == 'psc' and st.get('pay'):
        st['wait'] = 'pay'; m, r = "✍️ Summani yozing ($; so'mda yozsangiz o'giraman):", [_x_btn('mij')]
    elif act == 'pm' and st.get('pay'):
        st['pay']['usul'] = arg[0] if arg and arg[0] in TOLOV_USULLARI else None; m, r = _mij_tolov_ekran(st)
    elif act == 'pok':
        p = st.get('pay') or {}
        tok = 'mpay' + (arg[0] if arg else '')
        if not (arg and arg[0] == st.get('id') and p.get('usul') and p.get('summa')) or not _ui_done(ctx, tok):
            await q.answer("Allaqachon saqlangan yoki eskirgan", show_alert=True); return
        res = await asyncio.to_thread(pay_debt, p['kind'], p['name'], p['summa'], p['usul'], "tugma orqali")
        st.pop('pay', None)
        if res.get('ok'):
            m = (f"✅ To'lov saqlandi: {res['person']} · {_usd2(res['paid'])} ({res['method']})\n"
                 f"Qolgan qarz: {_usd2(res['qoldiq'])} · Kassa: {_usd2(res['kassa'])}\n(Bekor qilish: /undo)")
        else:
            ctx.user_data['ui_done'].remove(tok)
            m = "⚠️ " + res.get('error', "Saqlanmadi") + (("\nVariantlar: " + ", ".join(res['variantlar'][:6])) if res.get('variantlar') else "")
        r = [[_btn("⬅️ Karta", f"mij:c:{p['cid']}")] if p.get('cid') else [_btn("⬅️ Menyu", "mij:menu")]]
    elif act == 'akt':
        cid = _i(0)
        m, r = ("📋 Akt sverka — davrni tanlang:",
                [[_btn(nom, f"mij:ap:{cid}:{k}") for k, nom in AKT_DAVRLAR[:3]],
                 [_btn(nom, f"mij:ap:{cid}:{k}") for k, nom in AKT_DAVRLAR[3:]],
                 [_btn("⬅️ Karta", f"mij:c:{cid}")] + _x_btn('mij')])
    elif act == 'ap':
        cid, kod = _i(0), (arg[1] if len(arg) > 1 else 'oy')
        a = akt_sverka(cid, *_akt_oraliq(kod))
        if not a: alert = "Mijoz topilmadi"
        else:
            m = akt_matn(a)
            r = [[_btn("🌐 HTML", f"mij:af:{cid}:{kod}:html"), _btn("📊 Excel", f"mij:af:{cid}:{kod}:xlsx")],
                 [_btn("⬅️ Karta", f"mij:c:{cid}")] + _x_btn('mij')]
    elif act == 'af':
        cid, kod, tur = _i(0), (arg[1] if len(arg) > 1 else 'oy'), (arg[2] if len(arg) > 2 else 'html')
        a = akt_sverka(cid, *_akt_oraliq(kod))
        if not a: alert = "Mijoz topilmadi"
        else:
            await q.answer("⏳ Fayl tayyorlanmoqda...")
            await _mij_fayl(u, ctx, a, tur)
            return
    elif act == 'deb':
        m, r = _mij_deb_ekran(st, arg[0] if arg and arg[0] in ('sum', 'kun') else 'sum', _i(1))
    elif act == 'dc':
        ds = st.get('deb') or qarzdorlar()
        if _i(0) >= len(ds): alert = "Eskirgan"
        else:
            d = ds[_i(0)]
            if d['cid']: m, r = _mij_karta(u, d['cid'])
            else:
                st['id'] = secrets.token_hex(4)
                st['pay'] = {'kind': DEBITOR, 'name': d['name'], 'cid': 0, 'qarz': d['sum']}
                m, r = _mij_tolov_ekran(st)
                m = f"(Mijozlar ro'yxatida yo'q ism)\n📝 Eslatma:\n{eslatma_matni(d['name'], d['sum'], d['kun'])}\n\n" + m
    elif act == 'kre': m, r = _mij_kre_ekran(st)
    else: alert = "Eski tugma"
    await q.answer(alert[:190] if alert else None, show_alert=bool(alert))
    if m is not None: await _pos_chiqar(q, m, r)

async def mij_matn(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    st0 = ctx.user_data.get('mij')
    if not st0 or not st0.get('wait') or not can(u, 'customer_add'): return False
    st = _ui_ol(ctx, 'mij')
    if st is None:
        await u.message.reply_text("⏰ Oyna eskirgan. Qaytadan: 👥 Mijozlar"); return True
    w = st['wait']; st['wait'] = None
    msg = (u.message.text or '').strip()
    m = r = None
    if w == 'search':
        st['found'] = mijoz_qidir(msg)
        for f in st['found']: f['jami'] = 0
        m, r = _mij_royxat(u, st['found'], 0, "mij:f", f"🔍 '{msg[:30]}'")
    elif w == 'new':
        b2b = bool(re.search(r'\bB2B\b', msg, re.I)); msg2 = re.sub(r'\bB2[BC]\b', '', msg, flags=re.I).strip()
        tel_m = re.search(r'(\+?\d[\d\s\-()]{6,}\d)', msg2)
        tel = re.sub(r'[^\d+]', '', tel_m.group(1)) if tel_m else ''
        ism = (msg2[:tel_m.start()] + msg2[tel_m.end():]).strip(' ,;-') if tel_m else msg2
        if len(ism) < 2:
            st['wait'] = w; m, r = "⚠️ Ism yozilmadi. Masalan: Alisher +998901234567", [_x_btn('mij')]
        else:
            holat, cid = add_customer(ism, tel, 'B2B' if b2b else 'B2C')
            m, r = _mij_karta(u, cid)
            m = ("➕ Yangi mijoz qo'shildi\n" if holat == 'qoshildi' else "👤 Bu ism bor edi — ma'lumot yangilandi\n") + m
    elif not can(u, 'boshqaruv'):
        return False
    elif w == 'pay':
        v = _pos_son(msg); p = st.get('pay')
        if not p: return False
        if v is None or v <= 0:
            st['wait'] = w; m, r = "⚠️ Summani raqam bilan yozing", [_x_btn('mij')]
        elif v > p['qarz'] + 0.005:
            st['wait'] = w; m, r = f"⚠️ Ortiqcha: ochiq qarz {_usd2(p['qarz'])}", [_x_btn('mij')]
        else:
            p['summa'] = round(v, 2); m, r = _mij_tolov_ekran(st)
    elif w[:3] in ('en:', 'ep:', 'ez:'):
        cid = int(w.split(':')[1]); fld = {'en': 'name', 'ep': 'phone', 'ez': 'notes'}[w[:2]]
        if fld == 'name' and len(msg) < 2:
            st['wait'] = w; m, r = "⚠️ Ism juda qisqa", [_x_btn('mij')]
        else:
            mijoz_tahrir(cid, **{fld: msg[:200]}); m, r = _mij_tahrir_ekran(cid); m = "✅ Saqlandi\n" + m
    else:
        return False
    await u.message.reply_text(m[:4000], reply_markup=InlineKeyboardMarkup(r) if r else None)
    return True


# ══ 7-BOSQICH (Faza 3/4): 📊 HISOBOTLAR — davr, foyda, kassa, grafik, Excel (egasi/admin) ══
HIS_DAVRLAR = [('bugun', "Bugun"), ('kecha', "Kecha"), ('hafta', "Shu hafta"), ('oy', "Shu oy"),
               ('otgan', "O'tgan oy"), ('yil', "Shu yil")]

def _d(s): return datetime.strptime(s, '%Y-%m-%d')
def _ds(d): return d.strftime('%Y-%m-%d')

def his_oraliq(kalit, bugun=None):
    """Davr kaliti → (d1, d2, oldingi_d1, oldingi_d2, nomi). Oldingi davr — solishtirish uchun teng bo'lak."""
    b = bugun or datetime.now()
    b = datetime(b.year, b.month, b.day)
    if kalit == 'bugun':
        return _ds(b), _ds(b), _ds(b - timedelta(1)), _ds(b - timedelta(1)), "Bugun"
    if kalit == 'kecha':
        k = b - timedelta(1)
        return _ds(k), _ds(k), _ds(k - timedelta(1)), _ds(k - timedelta(1)), "Kecha"
    if kalit == 'hafta':
        d1 = b - timedelta(b.weekday())
        return _ds(d1), _ds(b), _ds(d1 - timedelta(7)), _ds(b - timedelta(7)), "Shu hafta"
    if kalit == 'oy':
        d1 = b.replace(day=1); p1 = (d1 - timedelta(1)).replace(day=1)
        p2 = p1.replace(day=min(b.day, calendar.monthrange(p1.year, p1.month)[1]))
        return _ds(d1), _ds(b), _ds(p1), _ds(p2), "Shu oy"
    if kalit == 'otgan':
        d2 = b.replace(day=1) - timedelta(1); d1 = d2.replace(day=1)
        p2 = d1 - timedelta(1); p1 = p2.replace(day=1)
        return _ds(d1), _ds(d2), _ds(p1), _ds(p2), "O'tgan oy"
    if kalit == 'yil':
        d1 = b.replace(month=1, day=1)
        try: p2 = b.replace(year=b.year - 1)
        except ValueError: p2 = b.replace(year=b.year - 1, day=28)
        return _ds(d1), _ds(b), _ds(d1.replace(year=b.year - 1)), _ds(p2), "Shu yil"
    raise ValueError(kalit)

def his_ixtiyoriy(d1, d2):
    """Ixtiyoriy oraliq: oldingi davr — xuddi shu uzunlikdagi undan oldingi kunlar."""
    a, z = _d(d1), _d(d2)
    if z < a: a, z = z, a
    n = (z - a).days + 1
    return _ds(a), _ds(z), _ds(a - timedelta(n)), _ds(a - timedelta(1)), f"{_ds(a)} … {_ds(z)}"

def _sana_parse(s):
    s = s.strip()
    for f in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y'):
        try: return datetime.strptime(s, f)
        except ValueError: pass
    return None

def _his_asos(c, d1, d2):
    """P&L asosi — pl_hisobot bilan bir xil qoida (oraliq uchun)."""
    c.execute("SELECT COALESCE(SUM(revenue),0), COALESCE(SUM(unit_cost*qty),0), COALESCE(SUM(CASE WHEN qty>0 THEN 1 ELSE 0 END),0), "
              "COALESCE(SUM(qty),0), "
              "COALESCE(SUM(CASE WHEN discount>0 AND discount<100 THEN revenue*discount/(100-discount) ELSE 0 END),0), "
              "COALESCE(SUM(CASE WHEN qty<0 THEN -revenue ELSE 0 END),0) "
              "FROM sales WHERE date BETWEEN ? AND ? AND reversed=0", (d1, d2))
    tushum, cogs, soni, dona, cheg, qaytgan = c.fetchone()
    c.execute("SELECT expense_type, COALESCE(category,'boshqa'), COALESCE(SUM(amount),0) FROM expenses "
              "WHERE date BETWEEN ? AND ? AND reversed=0 GROUP BY expense_type, category", (d1, d2))
    togri = {}; xar = {}
    for et, cat, amt in c.fetchall():
        dd = togri if et in ('cogs_bank', 'cogs_delivery') else xar
        dd[cat] = dd.get(cat, 0) + amt
    t_togri = sum(togri.values()); t_xar = sum(xar.values())
    tannarx = cogs + t_togri
    yalpi = tushum - tannarx; sof = yalpi - t_xar
    r2 = lambda v: round(v or 0, 2)
    return {'tushum': r2(tushum), 'cogs': r2(cogs), 'togri': r2(t_togri), 'togri_tafsil': {k: r2(v) for k, v in togri.items()},
            'tannarx': r2(tannarx), 'yalpi': r2(yalpi), 'xarajat': r2(t_xar),
            'xarajat_tafsil': dict(sorted(((k, r2(v)) for k, v in xar.items()), key=lambda kv: -kv[1])),
            'sof': r2(sof), 'soni': soni, 'dona': dona or 0, 'chegirma': r2(cheg), 'qaytarish': r2(qaytgan),
            'marja': round(yalpi / tushum * 100, 1) if tushum else 0.0,
            'sof_pct': round(sof / tushum * 100, 1) if tushum else 0.0}

def hisobot(d1, d2, od1=None, od2=None, nomi=''):
    """To'liq hisobot (egasi/admin). Barcha raqamlar $ da."""
    conn = db(); c = conn.cursor()
    h = _his_asos(c, d1, d2)
    h.update({'d1': d1, 'd2': d2, 'nomi': nomi or f"{d1} … {d2}"})
    # Kassa: usul va kategoriya bo'yicha
    c.execute("SELECT COALESCE(SUM(CASE WHEN type='kirim' THEN amount ELSE -amount END),0) FROM cash_box WHERE date < ?", (d1,))
    boshi = c.fetchone()[0] or 0
    c.execute("SELECT type, COALESCE(NULLIF(payment_method,''),'naqd'), COALESCE(NULLIF(category,''),'boshqa'), COALESCE(SUM(amount),0) "
              "FROM cash_box WHERE date BETWEEN ? AND ? GROUP BY 1, 2, 3", (d1, d2))
    k = {'kirim_usul': {}, 'chiqim_usul': {}, 'kirim_kat': {}, 'chiqim_kat': {}}
    for t, usul, kat, amt in c.fetchall():
        pre = 'kirim' if t == 'kirim' else 'chiqim'
        k[pre + '_usul'][usul] = round(k[pre + '_usul'].get(usul, 0) + amt, 2)
        k[pre + '_kat'][kat] = round(k[pre + '_kat'].get(kat, 0) + amt, 2)
    k['jami_kirim'] = round(sum(k['kirim_usul'].values()), 2); k['jami_chiqim'] = round(sum(k['chiqim_usul'].values()), 2)
    k['boshi'] = round(boshi, 2); k['oxiri'] = round(boshi + k['jami_kirim'] - k['jami_chiqim'], 2)
    h['kassa'] = k
    # Top mahsulotlar
    c.execute("SELECT product, SUM(qty), ROUND(SUM(revenue),2), ROUND(SUM(revenue - unit_cost*qty),2) FROM sales "
              "WHERE date BETWEEN ? AND ? AND reversed=0 GROUP BY product", (d1, d2))
    mah = [{'nom': r[0], 'dona': r[1], 'tushum': r[2], 'foyda': r[3]} for r in c.fetchall()]
    h['mahsulotlar'] = mah
    h['top_tushum'] = sorted(mah, key=lambda x: -x['tushum'])[:5]
    h['top_foyda'] = sorted(mah, key=lambda x: -x['foyda'])[:5]
    c.execute("SELECT customer, SUM(CASE WHEN qty>0 THEN 1 ELSE 0 END), ROUND(SUM(revenue),2), ROUND(SUM(revenue - unit_cost*qty),2) FROM sales "
              "WHERE date BETWEEN ? AND ? AND reversed=0 AND TRIM(COALESCE(customer,''))<>'' GROUP BY customer ORDER BY 3 DESC", (d1, d2))
    h['mijozlar'] = [{'nom': r[0], 'soni': r[1], 'tushum': r[2], 'foyda': r[3]} for r in c.fetchall()]
    h['top_mijoz'] = h['mijozlar'][:5]
    c.execute("SELECT COALESCE(NULLIF(seller_name,''),'Egasi / AI'), SUM(CASE WHEN qty>0 THEN 1 ELSE 0 END), COALESCE(SUM(qty),0), ROUND(SUM(revenue),2), "
              "ROUND(SUM(revenue - unit_cost*qty),2) FROM sales WHERE date BETWEEN ? AND ? AND reversed=0 GROUP BY 1 ORDER BY 4 DESC", (d1, d2))
    h['sotuvchilar'] = [{'nom': r[0], 'soni': r[1], 'dona': r[2], 'tushum': r[3], 'foyda': r[4]} for r in c.fetchall()]
    c.execute("SELECT date, ROUND(SUM(revenue),2), ROUND(SUM(revenue - unit_cost*qty),2) FROM sales "
              "WHERE date BETWEEN ? AND ? AND reversed=0 GROUP BY date ORDER BY date", (d1, d2))
    h['kunlik'] = [{'sana': r[0], 'tushum': r[1], 'foyda': r[2]} for r in c.fetchall()]
    c.execute(f"SELECT COALESCE(SUM(amount),0) FROM debts WHERE paid=0 AND type IN {DEBITOR_SQL}")
    deb = c.fetchone()[0] or 0
    c.execute(f"SELECT COALESCE(SUM(amount),0) FROM debts WHERE paid=0 AND type IN {KREDITOR_SQL}")
    kre = c.fetchone()[0] or 0
    c.execute("SELECT COALESCE(SUM(remaining),0) FROM transit WHERE remaining>0")
    zav = c.fetchone()[0] or 0
    h['debitor'] = round(deb, 2); h['kreditor'] = round(kre + zav, 2); h['zavod_qarzi'] = round(zav, 2)
    h['oldingi'] = _his_asos(c, od1, od2) if od1 and od2 else None
    h['od1'], h['od2'] = od1, od2
    conn.close()
    h['ombor'] = ombor_qiymati()['jami']
    h['yolda'] = round(balans()['yolda'], 2)
    return h

def _foiz(yangi, eski):
    if not eski:
        return "" if not yangi else " (yangi)"
    p = (yangi - eski) / abs(eski) * 100
    return f" ({'▲' if p >= 0 else '▼'} {abs(p):.0f}%)"

def his_matn(h):
    o = h.get('oldingi') or {}
    f = (lambda key: _foiz(h[key], o.get(key, 0))) if o else (lambda key: "")
    L = [f"📊 HISOBOT — {h['nomi']}", f"📅 {h['d1']} … {h['d2']}", "",
         f"🧾 Sotuvlar: {h['soni']} ta qator, {h['dona']} dona",
         f"💵 Tushum: {_usd2(h['tushum'])}{f('tushum')}",
         f"📦 Tannarx: {_usd2(h['tannarx'])}" + (f" (tovar {_usd2(h['cogs'])} + bank/yetkazish {_usd2(h['togri'])})" if h['togri'] else ""),
         f"🟢 Yalpi foyda: {_usd2(h['yalpi'])} · marja {h['marja']}%{f('yalpi')}"]
    if h['chegirma']: L.append(f"🏷 Berilgan chegirma: {_usd2(h['chegirma'])}")
    if h.get('qaytarish'): L.append(f"↩️ Qaytarishlar: −{_usd2(h['qaytarish'])} (tushumdan ayirilgan)")
    L.append(f"💸 Xarajatlar: {_usd2(h['xarajat'])}{f('xarajat')}")
    for kat, v in list(h['xarajat_tafsil'].items())[:8]:
        L.append(f"   • {kat}: {_usd2(v)}")
    L.append(f"{'✅' if h['sof'] >= 0 else '🔴'} Sof foyda: {_usd2(h['sof'])} ({h['sof_pct']}%){f('sof')}")
    k = h['kassa']
    L += ["", f"💰 Kassa: +{_usd2(k['jami_kirim'])} / −{_usd2(k['jami_chiqim'])} → qoldiq {_usd2(k['oxiri'])}",
          f"🏬 Ombor (tannarxda, hozir): {_usd2(h['ombor'])}" + (f" · 🚢 yo'lda {_usd2(h['yolda'])}" if h.get('yolda') else ""),
          f"📥 Bizga qarz (debitorlik): {_usd2(h['debitor'])}",
          f"📤 Bizning qarz (kreditorlik, zavod bilan): {_usd2(h['kreditor'])}"]
    if o: L.append(f"\n↔️ Solishtirish: {h['od1']} … {h['od2']} bilan")
    L += ["", "💡 Qanday hisoblanadi:", "Tushum − Tannarx = Yalpi foyda", "Yalpi foyda − Xarajatlar = Sof foyda"]
    return "\n".join(L)

def his_mahsulot_matn(h):
    L = [f"📦 Mahsulotlar — {h['nomi']}", "", "💵 Tushum bo'yicha TOP:"]
    L += [f"{i}. {m['nom'][:30]} — {_usd2(m['tushum'])} ({m['dona']} dona)" for i, m in enumerate(h['top_tushum'], 1)] or ["—"]
    L += ["", "🟢 Foyda bo'yicha TOP:"]
    L += [f"{i}. {m['nom'][:30]} — {_usd2(m['foyda'])}" for i, m in enumerate(h['top_foyda'], 1)] or ["—"]
    return "\n".join(L)

def his_mijoz_matn(h):
    L = [f"👥 TOP mijozlar — {h['nomi']}", ""]
    L += [f"{i}. {m['nom'][:30]} — {_usd2(m['tushum'])} ({m['soni']} ta)" for i, m in enumerate(h['top_mijoz'], 1)] or ["Ismi yozilgan sotuv yo'q"]
    return "\n".join(L)

def his_sotuvchi_matn(h):
    L = [f"👷 Sotuvchilar — {h['nomi']}", ""]
    L += [f"• {s['nom']}: {_usd2(s['tushum'])} · {s['dona']} dona · foyda {_usd2(s['foyda'])}" for s in h['sotuvchilar']] or ["Sotuv yo'q"]
    return "\n".join(L)

def his_kassa_matn(h):
    k = h['kassa']
    L = [f"💰 Kassa — {h['nomi']}", f"Davr boshida: {_usd2(k['boshi'])}", "", f"⬆️ Kirim: {_usd2(k['jami_kirim'])}"]
    L += [f"   • {u_}: {_usd2(v)}" for u_, v in sorted(k['kirim_usul'].items(), key=lambda kv: -kv[1])]
    L += [f"   ({kat}: {_usd2(v)})" for kat, v in sorted(k['kirim_kat'].items(), key=lambda kv: -kv[1])]
    L += ["", f"⬇️ Chiqim: {_usd2(k['jami_chiqim'])}"]
    L += [f"   • {u_}: {_usd2(v)}" for u_, v in sorted(k['chiqim_usul'].items(), key=lambda kv: -kv[1])]
    L += [f"   ({kat}: {_usd2(v)})" for kat, v in sorted(k['chiqim_kat'].items(), key=lambda kv: -kv[1])]
    L += ["", f"Davr oxirida: {_usd2(k['oxiri'])}"]
    return "\n".join(L)

def his_grafik_matn(h):
    """matplotlib bo'lmasa — matnli grafik."""
    qism = [("Tushum", h['tushum']), ("Tannarx", h['tannarx']), ("Xarajat", h['xarajat']), ("Sof foyda", h['sof'])]
    mx = max([abs(v) for _, v in qism] + [1])
    L = [f"📈 {h['nomi']} (matnli grafik)", ""]
    for n, v in qism:
        L.append(f"{n:<10} {'█' * max(0, round(abs(v) / mx * 16)) or '·'} {_usd2(v)}")
    if len(h['kunlik']) > 1:
        mk = max([d['tushum'] for d in h['kunlik']] + [1])
        L += ["", "Kunlik tushum:"]
        for d in h['kunlik'][-14:]:
            L.append(f"{d['sana'][5:]} {'▇' * max(0, round(d['tushum'] / mk * 12)) or '·'} {_usd2(d['tushum'])}")
    return "\n".join(L)

def his_grafik_png(h, path):
    """PNG grafik (matplotlib). Kutubxona yo'q yoki xato bo'lsa None."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        return None
    try:
        kun = h['kunlik']
        fig, axes = plt.subplots(1, 2 if len(kun) > 1 else 1, figsize=(11 if len(kun) > 1 else 6, 4.2))
        ax = axes[0] if len(kun) > 1 else axes
        nom = ["Tushum", "Tannarx", "Xarajat", "Sof foyda"]
        val = [h['tushum'], h['tannarx'], h['xarajat'], h['sof']]
        bars = ax.bar(nom, val, color=['#2e86de', '#8395a7', '#ee5253', '#10ac84' if h['sof'] >= 0 else '#c0392b'])
        for b_, v in zip(bars, val, strict=True):
            ax.annotate(f"${v:,.0f}", (b_.get_x() + b_.get_width() / 2, b_.get_height()), ha='center', va='bottom', fontsize=9)
        ax.set_title(f"{h['nomi']}: {h['d1']} … {h['d2']}"); ax.grid(axis='y', alpha=.3)
        if len(kun) > 1:
            a2 = axes[1]
            xs = [d['sana'][5:] for d in kun]
            a2.plot(xs, [d['tushum'] for d in kun], marker='o', label='Tushum')
            a2.plot(xs, [d['foyda'] for d in kun], marker='o', label='Yalpi foyda')
            a2.set_title("Kunlik"); a2.legend(); a2.grid(alpha=.3)
            step = max(1, len(xs) // 10)
            a2.set_xticks(range(0, len(xs), step)); a2.set_xticklabels(xs[::step], rotation=45, fontsize=8)
        fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
        return path
    except Exception as e:
        log.warning(f"Grafik chizilmadi: {e}")
        try: plt.close('all')
        except Exception: pass
        return None

def his_excel(h, path_base):
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, date, time, product, qty, unit_cost, revenue, ROUND(revenue - unit_cost*qty,2), discount, customer, "
              "COALESCE(seller_name,'') FROM sales WHERE date BETWEEN ? AND ? AND reversed=0 ORDER BY date, id", (h['d1'], h['d2']))
    sot = c.fetchall()
    c.execute("SELECT date, category, expense_type, amount, note FROM expenses WHERE date BETWEEN ? AND ? AND reversed=0 ORDER BY date", (h['d1'], h['d2']))
    xar = c.fetchall()
    c.execute("SELECT date, time, type, amount, category, payment_method, note FROM cash_box WHERE date BETWEEN ? AND ? ORDER BY date, id", (h['d1'], h['d2']))
    kas = c.fetchall(); conn.close()
    xul = [["Ko'rsatkich", "Qiymat ($)"], ["Davr", f"{h['d1']} … {h['d2']}"], ["Tushum", h['tushum']], ["Tannarx (tovar)", h['cogs']],
           ["Bank/yetkazish (to'g'ridan)", h['togri']], ["Yalpi foyda", h['yalpi']], ["Marja %", h['marja']],
           ["Chegirma", h['chegirma']], ["Xarajatlar", h['xarajat']], ["Sof foyda", h['sof']],
           ["Kassa kirim", h['kassa']['jami_kirim']], ["Kassa chiqim", h['kassa']['jami_chiqim']], ["Kassa qoldiq", h['kassa']['oxiri']],
           ["Ombor qiymati (hozir)", h['ombor']], ["Yo'ldagi tovar (hozir)", h.get('yolda', 0)],
           ["Debitorlik", h['debitor']], ["Kreditorlik", h['kreditor']]]
    return _jadval_fayl({
        "Xulosa": xul,
        "Mahsulotlar": [["Mahsulot", "Dona", "Tushum", "Foyda"]] + [[m['nom'], m['dona'], m['tushum'], m['foyda']] for m in sorted(h['mahsulotlar'], key=lambda x: -x['tushum'])],
        "Mijozlar": [["Mijoz", "Soni", "Tushum", "Foyda"]] + [[m['nom'], m['soni'], m['tushum'], m['foyda']] for m in h['mijozlar']],
        "Sotuvchilar": [["Sotuvchi", "Soni", "Dona", "Tushum", "Foyda"]] + [[s['nom'], s['soni'], s['dona'], s['tushum'], s['foyda']] for s in h['sotuvchilar']],
        "Xarajatlar": [["Sana", "Kategoriya", "Turi", "Summa", "Izoh"]] + [list(r) for r in xar],
        "Kassa": [["Sana", "Vaqt", "Tur", "Summa", "Kategoriya", "Usul", "Izoh"]] + [list(r) for r in kas],
        "Sotuvlar": [["ID", "Sana", "Vaqt", "Mahsulot", "Dona", "Tannarx", "Tushum", "Foyda", "Chegirma %", "Mijoz", "Sotuvchi"]] + [list(r) for r in sot],
    }, path_base)

# ── UI ──
def _his_menu():
    rows = []; ks = HIS_DAVRLAR
    for i in range(0, len(ks), 2):
        rows.append([_btn(n, f"his:p:{k}") for k, n in ks[i:i + 2]])
    rows.append([_btn("📅 Oraliq (sanadan-sanagacha)", "his:c")])
    rows.append(_x_btn('his'))
    return "📊 Hisobotlar — davrni tanlang", rows

def _his_tugmalar():
    return [[_btn("📦 Mahsulotlar", "his:v:mah"), _btn("👥 Mijozlar", "his:v:mij")],
            [_btn("👷 Sotuvchilar", "his:v:sot"), _btn("💰 Kassa", "his:v:kas")],
            [_btn("📈 Grafik", "his:g"), _btn("📥 Excel", "his:xl")],
            [_btn("📊 Xulosa", "his:v:x"), _btn("⬅️ Davrlar", "his:menu")], _x_btn('his')]

def _his_ol(st):
    if not st.get('d1'): return None
    return hisobot(st['d1'], st['d2'], st.get('od1'), st.get('od2'), st.get('nomi', ''))

async def cmd_hisobotlar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    _ui_yangi(ctx, 'his')
    m, r = _his_menu()
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))

async def his_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not can(u, 'boshqaruv'):
        await q.answer("Ruxsat yo'q", show_alert=True); return
    parts = (q.data or '').split(':'); act = parts[1] if len(parts) > 1 else ''; arg = parts[2:]
    if act == 'x':
        ctx.user_data.pop('his', None); await q.answer()
        return await _pos_chiqar(q, "📊 Hisobotlar yopildi.", None)
    st = _ui_ol(ctx, 'his')
    if st is None:
        if act in ('menu', 'p'): st = _ui_yangi(ctx, 'his')
        else:
            await q.answer(); return await _pos_chiqar(q, "⏰ Oyna eskirgan. Qaytadan: 📊 Hisobotlar", None)
    st['wait'] = None
    m = r = None; alert = None
    if act == 'menu': m, r = _his_menu()
    elif act == 'p':
        try: d1, d2, od1, od2, nomi = his_oraliq(arg[0] if arg else '')
        except ValueError: d1 = None
        if not d1: alert = "Eski tugma"
        else:
            st.update(d1=d1, d2=d2, od1=od1, od2=od2, nomi=nomi)
            m, r = his_matn(await asyncio.to_thread(_his_ol, st)), _his_tugmalar()
    elif act == 'c':
        st['wait'] = 'range'
        m, r = ("📅 Oraliqni yozing: boshlanish va tugash sanasi\nMasalan: 2026-09-01 2026-09-30\nyoki: 01.09.2026 30.09.2026",
                [[_btn("⬅️ Davrlar", "his:menu")] + _x_btn('his')])
    elif act in ('v', 'g', 'xl'):
        h = await asyncio.to_thread(_his_ol, st)
        if h is None: alert = "Avval davrni tanlang"
        elif act == 'v':
            fn = {'x': his_matn, 'mah': his_mahsulot_matn, 'mij': his_mijoz_matn, 'sot': his_sotuvchi_matn, 'kas': his_kassa_matn}.get(arg[0] if arg else 'x', his_matn)
            m, r = fn(h), _his_tugmalar()
        elif act == 'g':
            await q.answer("Grafik tayyorlanmoqda…")
            p = f"/tmp/his_{u.effective_user.id}_{secrets.token_hex(3)}.png"
            got = await asyncio.to_thread(his_grafik_png, h, p)
            try:
                if got:
                    with open(got, 'rb') as fh:
                        await ctx.bot.send_photo(chat_id=u.effective_chat.id, photo=fh, caption=f"📈 {h['nomi']}: {h['d1']} … {h['d2']}")
                else:
                    await ctx.bot.send_message(chat_id=u.effective_chat.id, text=his_grafik_matn(h))
            finally:
                if got:
                    try: os.remove(got)
                    except OSError: pass
            return
        else:
            await q.answer("Excel tayyorlanmoqda…")
            p = await asyncio.to_thread(his_excel, h, f"/tmp/hisobot_{h['d1']}_{h['d2']}_{secrets.token_hex(3)}")
            try:
                with open(p, 'rb') as fh:
                    await ctx.bot.send_document(chat_id=u.effective_chat.id, document=fh,
                                                filename=f"hisobot_{h['d1']}_{h['d2']}{os.path.splitext(p)[1]}",
                                                caption=f"📥 Hisobot {h['d1']} … {h['d2']}")
            finally:
                try: os.remove(p)
                except OSError: pass
            return
    else: alert = "Eski tugma"
    await q.answer(alert if alert else None, show_alert=bool(alert))
    if m is not None: await _pos_chiqar(q, m[:4000], r)

async def his_matn_kirit(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    st0 = ctx.user_data.get('his')
    if not st0 or not st0.get('wait') or not can(u, 'boshqaruv'): return False
    st = _ui_ol(ctx, 'his')
    if st is None:
        await u.message.reply_text("⏰ Oyna eskirgan. Qaytadan: 📊 Hisobotlar"); return True
    st['wait'] = None
    sanalar = [_sana_parse(s) for s in re.split(r'\s+|…|—|-(?=\d{2}\.)', (u.message.text or '').replace('...', ' ').strip()) if s.strip()]
    sanalar = [s for s in sanalar if s]
    if len(sanalar) != 2:
        st['wait'] = 'range'
        await u.message.reply_text("⚠️ Ikki sana kerak. Masalan: 2026-09-01 2026-09-30",
                                   reply_markup=InlineKeyboardMarkup([[_btn("⬅️ Davrlar", "his:menu")] + _x_btn('his')]))
        return True
    d1, d2, od1, od2, nomi = his_ixtiyoriy(_ds(sanalar[0]), _ds(sanalar[1]))
    st.update(d1=d1, d2=d2, od1=od1, od2=od2, nomi=nomi)
    h = await asyncio.to_thread(_his_ol, st)
    await u.message.reply_text(his_matn(h)[:4000], reply_markup=InlineKeyboardMarkup(_his_tugmalar()))
    return True


# ══ 8-BOSQICH (Faza 5): 🏭 ZAVOD BUYURTMALARI (egasi/admin) ═══════════════════
# Buyurtma (purchase_orders) → har bir tovar qatori transit jadvalidagi bitta qator (po_id bilan).
# Shuning uchun zavod qarzi (transit.remaining) avvalgidek kreditorlikda, /zavod_tolov, pay_debt, balans, /undo bilan ishlaydi.
PO_HOLATLAR = [('buyurtma', "📝 Buyurtma berildi"), ('qisman_tolandi', "💵 To'landi qisman"), ('yolda', "🚢 Yo'lda"),
               ('bojxona', "🛃 Bojxonada"), ('keldi', "📦 Keldi"), ('yopildi', "✅ Yopildi"), ('bekor', "🗑 Bekor qilingan")]
PO_NOM = dict(PO_HOLATLAR)
PO_OCHIQ = ('buyurtma', 'qisman_tolandi', 'yolda', 'bojxona', 'keldi')
PO_KELMAGAN = ('buyurtma', 'qisman_tolandi', 'yolda', 'bojxona')

def init_po_tables():
    conn = db(); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS purchase_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, supplier TEXT, status TEXT DEFAULT 'buyurtma',
        expected_date TEXT DEFAULT '', deposit REAL DEFAULT 0, bank_fee REAL DEFAULT 0, delivery_fee REAL DEFAULT 0,
        note TEXT DEFAULT '', created_by TEXT DEFAULT '', closed_date TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS po_status_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, po_id INTEGER, ts TEXT, status TEXT, note TEXT DEFAULT '', user TEXT DEFAULT '')''')
    for ddl in ("ALTER TABLE transit ADD COLUMN po_id INTEGER DEFAULT 0",
                "ALTER TABLE transit ADD COLUMN received_qty INTEGER DEFAULT 0",
                "ALTER TABLE transit ADD COLUMN expected_date TEXT DEFAULT ''",
                "ALTER TABLE transit ADD COLUMN product_id INTEGER DEFAULT 0"):
        try: c.execute(ddl)
        except sqlite3.OperationalError: pass
    # Eski "keldi" qatorlar — to'liq kelgan deb belgilanadi (idempotent)
    c.execute("UPDATE transit SET received_qty=qty WHERE status='keldi' AND COALESCE(received_qty,0)=0 AND COALESCE(po_id,0)=0")
    c.execute('CREATE INDEX IF NOT EXISTS idx_transit_po ON transit(po_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_po_log ON po_status_log(po_id)')
    transit_balans_otkaz(c)
    conn.commit(); conn.close()

def transit_balans_otkaz(c):
    """Eski transit qatorlarini yangi balans usuliga belgilaydi (idempotent, ma'lumot o'zgarmaydi).
    Eski usul: aktivda faqat to'langan avans (deposit) edi — to'lov kapitalni sun'iy oshirardi, buyurtma kamaytirardi.
    Yangi usul: kelmagan donalar × landed tannarx aktivda, transit.remaining passivda (balans() ga qarang).
    Asl qiymatlar bs_asl ga yoziladi (qaytarish/tekshirish uchun). Qaytaradi: o'tkazilgan qatorlar soni."""
    for ddl in ("ALTER TABLE transit ADD COLUMN bs_usul TEXT DEFAULT ''",
                "ALTER TABLE transit ADD COLUMN bs_asl TEXT DEFAULT ''"):
        try: c.execute(ddl)
        except sqlite3.OperationalError: pass
    c.execute("SELECT id, status, qty, COALESCE(received_qty,0), unit_cost, total_cost, deposit, remaining, real_cost, "
              "bank_fee, delivery_fee FROM transit WHERE COALESCE(bs_usul,'')=''")
    rows = c.fetchall(); sana = today()
    for r in rows:
        asl = {'v': 1, 'sana': sana, 'status': r[1], 'qty': r[2], 'received_qty': r[3], 'unit_cost': r[4], 'total_cost': r[5],
               'deposit': r[6], 'remaining': r[7], 'real_cost': r[8], 'bank_fee': r[9], 'delivery_fee': r[10],
               'eski_aktiv': (r[6] or 0) if r[1] == 'yolda' else 0}
        c.execute("UPDATE transit SET bs_usul='toliq', bs_asl=? WHERE id=? AND COALESCE(bs_usul,'')=''",
                  (json.dumps(asl, ensure_ascii=False), r[0]))
    if rows:
        log.info(f"Transit: {len(rows)} ta qator yangi balans usuliga o'tkazildi (asl qiymatlar bs_asl da)")
    return len(rows)

def _po_kim(user):
    return (user[1] if isinstance(user, (tuple, list)) and len(user) > 1 else str(user or '')) or ''

def _po_log(c, po_id, status, note='', user=None):
    c.execute('INSERT INTO po_status_log (po_id, ts, status, note, user) VALUES (?,?,?,?,?)',
              (po_id, datetime.now().strftime('%Y-%m-%d %H:%M'), status, note, _po_kim(user)))

def _po_xarajat_tx(c, po_id, amount, kind):
    """Bank/yetkazish xarajatini HALI KELMAGAN dona qiymatiga mutanosib taqsimlaydi (landed cost, _taqsimla).
    Har qatorning real_cost (dona tannarxi) qolgan donalar uchun oshadi. Kelmagan tovar bo'lmasa False."""
    c.execute("SELECT id, qty, COALESCE(received_qty,0), COALESCE(unit_cost,0) FROM transit WHERE po_id=? AND status='yolda'", (po_id,))
    rows = [r for r in c.fetchall() if (r[1] or 0) - r[2] > 0]
    if not rows or amount <= 0: return False
    col = 'bank_fee' if kind == 'bank' else 'delivery_fee'
    for r, s in zip(rows, _taqsimla(amount, [(r[1] - r[2]) * r[3] for r in rows]), strict=True):
        if s <= 0: continue
        c.execute(f"UPDATE transit SET {col}=ROUND(COALESCE({col},0)+?,2), "
                  f"real_cost=ROUND(COALESCE(real_cost,unit_cost)+?,4) WHERE id=?", (s, s / (r[1] - r[2]), r[0]))
    c.execute(f"UPDATE purchase_orders SET {col}=ROUND(COALESCE({col},0)+?,2) WHERE id=?", (amount, po_id))
    return True

def _po_holat_avto(c, po_id, user=None):
    """Avtomatik holat: hammasi keldi → 'keldi'; keldi va qarz 0 → 'yopildi'; to'lov bo'lsa → 'qisman_tolandi'.
    /undo bilan qarz qaytsa 'yopildi' → 'keldi' (qayta ochiladi)."""
    c.execute('SELECT status FROM purchase_orders WHERE id=?', (po_id,))
    r = c.fetchone()
    if not r or r[0] == 'bekor': return r[0] if r else None
    st = r[0]
    c.execute("SELECT COALESCE(SUM(qty),0), COALESCE(SUM(received_qty),0), COALESCE(SUM(remaining),0), "
              "COALESCE(SUM(total_cost-remaining),0) FROM transit WHERE po_id=? AND status<>'bekor'", (po_id,))
    q, rq, qol, tol = c.fetchone()
    yangi = st
    if q > 0 and rq >= q and qol <= 0.005: yangi = 'yopildi'
    elif q > 0 and rq >= q: yangi = 'keldi'
    elif st == 'buyurtma' and tol > 0.005 and qol > 0.005: yangi = 'qisman_tolandi'
    if st == 'yopildi' and yangi != 'yopildi': yangi = 'keldi' if rq >= q else st
    if yangi != st:
        c.execute("UPDATE purchase_orders SET status=?, closed_date=? WHERE id=?",
                  (yangi, today() if yangi == 'yopildi' else '', po_id))
        _po_log(c, po_id, yangi, 'avtomatik', user)
    return yangi

def zavod_yarat(supplier, lines, deposit=0, bank_fee=0, delivery_fee=0, expected='', method='naqd', user=None, note=''):
    """Yangi zavod buyurtmasi. lines: [{'pid','qty','cost'}].
    Avans — kassadan chiqim ('zavod_qarz'); bank/yetkazish — kassadan chiqim ('zavod_xarajat') va tannarxga qo'shiladi."""
    supplier = (supplier or '').strip()
    if not supplier: return {'ok': False, 'error': "Zavod (yetkazuvchi) nomi kerak"}
    if is_closed(today()): return {'ok': False, 'error': f"{today()[:7]} davri yopilgan (/och)"}
    usul = tolov_usuli(method or 'naqd')
    if not usul: return {'ok': False, 'error': f"To'lov usuli noma'lum: {method}"}
    try:
        deposit = round(float(deposit or 0), 2); bank_fee = round(float(bank_fee or 0), 2); delivery_fee = round(float(delivery_fee or 0), 2)
        toza = [(int(x['pid']), int(x['qty']), round(float(x['cost']), 4)) for x in lines or []]
    except (TypeError, ValueError, KeyError):
        return {'ok': False, 'error': "Noto'g'ri raqam"}
    if not toza: return {'ok': False, 'error': "Kamida bitta tovar kerak"}
    if any(q <= 0 or cst < 0 for _, q, cst in toza) or min(deposit, bank_fee, delivery_fee) < 0:
        return {'ok': False, 'error': "Miqdor > 0, narx va summalar ≥ 0 bo'lishi kerak"}
    qiymat = [round(q * cst, 2) for _, q, cst in toza]; jami = round(sum(qiymat), 2)
    if deposit > jami + 0.005: return {'ok': False, 'error': f"Avans ({_usd2(deposit)}) tovar summasidan ({_usd2(jami)}) katta"}
    conn = db(); c = conn.cursor()
    try:
        nomlar = {}
        for pid, _, _ in toza:
            c.execute('SELECT name FROM products WHERE id=?', (pid,))
            r = c.fetchone()
            if not r: conn.close(); return {'ok': False, 'error': f"Tovar #{pid} topilmadi"}
            nomlar[pid] = r[0]
        d = today()
        holat = 'qisman_tolandi' if 0 < deposit < jami - 0.005 else 'buyurtma'
        c.execute('INSERT INTO purchase_orders (date, supplier, status, expected_date, deposit, note, created_by) VALUES (?,?,?,?,?,?,?)',
                  (d, supplier, holat, expected or '', deposit, note or '', _po_kim(user)))
        po = c.lastrowid
        _po_log(c, po, 'buyurtma', f"{len(toza)} xil tovar, {_usd2(jami)}", user)
        if holat != 'buyurtma': _po_log(c, po, holat, f"avans {_usd2(deposit)}", user)
        for (pid, q, cst), v, dep in zip(toza, qiymat, _taqsimla(deposit, qiymat), strict=True):
            c.execute('''INSERT INTO transit (date, supplier, product, qty, unit_cost, total_cost, deposit, remaining,
                         bank_fee, delivery_fee, real_cost, status, note, po_id, received_qty, expected_date, product_id, bs_usul)
                         VALUES (?,?,?,?,?,?,?,?,0,0,?,'yolda',?,?,0,?,?,'toliq')''',
                      (d, supplier, nomlar[pid], q, cst, v, dep, round(v - dep, 2), cst, f"zakaz #Z{po}", po, expected or '', pid))
        if bank_fee: _po_xarajat_tx(c, po, bank_fee, 'bank')
        if delivery_fee: _po_xarajat_tx(c, po, delivery_fee, 'yetkazish')
        t_ = datetime.now().strftime('%H:%M')
        if deposit > 0:
            c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                      (d, t_, 'chiqim', deposit, 'zavod_qarz', f"{supplier} zakaz #Z{po} avans", usul))
        if bank_fee + delivery_fee > 0:
            c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                      (d, t_, 'chiqim', round(bank_fee + delivery_fee, 2), 'zavod_xarajat', f"{supplier} zakaz #Z{po} bank/yetkazish", usul))
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return {'ok': True, 'po_id': po, 'jami': jami, 'deposit': deposit, 'qoldiq': round(jami - deposit, 2), 'holat': holat}

def po_malumot(po_id):
    conn = db(); c = conn.cursor()
    c.execute('SELECT id, date, supplier, status, COALESCE(expected_date,\'\'), deposit, bank_fee, delivery_fee, note, created_by, '
              'COALESCE(closed_date,\'\') FROM purchase_orders WHERE id=?', (po_id,))
    r = c.fetchone()
    if not r: conn.close(); return None
    c.execute("SELECT id, product, COALESCE(product_id,0), qty, COALESCE(received_qty,0), unit_cost, COALESCE(real_cost,unit_cost), "
              "total_cost, remaining, COALESCE(bank_fee,0)+COALESCE(delivery_fee,0), status FROM transit WHERE po_id=? ORDER BY id", (po_id,))
    qat = [{'tid': x[0], 'nom': x[1], 'pid': x[2], 'qty': x[3] or 0, 'kelgan': x[4], 'narx': x[5] or 0, 'tannarx': x[6] or 0,
            'summa': x[7] or 0, 'qoldiq': round(x[8] or 0, 2), 'xarajat': x[9], 'holat': x[10]} for x in c.fetchall()]
    c.execute('SELECT ts, status, note, user FROM po_status_log WHERE po_id=? ORDER BY id', (po_id,))
    log_ = c.fetchall(); conn.close()
    akt = [q for q in qat if q['holat'] != 'bekor']
    p = {'id': r[0], 'date': r[1], 'supplier': r[2], 'status': r[3], 'expected': r[4], 'note': r[8], 'by': r[9], 'closed': r[10],
         'qatorlar': qat, 'log': log_,
         'jami': round(sum(q['summa'] for q in akt), 2), 'qoldiq': round(sum(q['qoldiq'] for q in akt), 2),
         'xarajat': round(sum(q['xarajat'] for q in qat), 2),
         'dona': sum(q['qty'] for q in akt), 'kelgan': sum(q['kelgan'] for q in akt)}
    p['tolangan'] = round(p['jami'] - p['qoldiq'], 2)
    p['kech'] = _kun_farq(p['expected']) if p['expected'] and p['status'] in PO_KELMAGAN and p['expected'] < today() else 0
    return p

def zavod_holat(po_id, status, user=None, note=''):
    p = po_malumot(po_id)
    if not p: return {'ok': False, 'error': "Buyurtma topilmadi"}
    if p['status'] in ('yopildi', 'bekor'): return {'ok': False, 'error': f"Buyurtma {PO_NOM[p['status']].lower()} — o'zgartirib bo'lmaydi"}
    if status not in PO_NOM or status == 'bekor': return {'ok': False, 'error': "Noma'lum holat"}
    if status == 'keldi' and p['kelgan'] < p['dona']:
        return {'ok': False, 'error': "Tovarni '📦 Qabul qilish' orqali kiriting — hammasi kelganda holat o'zi 'Keldi' bo'ladi"}
    if status == 'yopildi' and (p['kelgan'] < p['dona'] or p['qoldiq'] > 0.005):
        return {'ok': False, 'error': f"Yopish uchun hamma tovar kelishi va qarz 0 bo'lishi kerak (kelgan {p['kelgan']}/{p['dona']}, qarz {_usd2(p['qoldiq'])})"}
    conn = db(); c = conn.cursor()
    c.execute("UPDATE purchase_orders SET status=?, closed_date=? WHERE id=?", (status, today() if status == 'yopildi' else '', po_id))
    _po_log(c, po_id, status, note, user)
    conn.commit(); conn.close()
    return {'ok': True, 'status': status}

def _po_pid(c, row_pid, nom):
    if row_pid:
        c.execute('SELECT id FROM products WHERE id=?', (row_pid,))
        if c.fetchone(): return row_pid
    c.execute('SELECT id FROM products WHERE name=?', (nom,))
    r = c.fetchone()
    if r: return r[0]
    p, _ = match_product(nom, prods=get_products(active_only=False))
    return p['id'] if p else None

def zavod_qabul(po_id, miqdor=None, user=None):
    """Qisman/to'liq qabul: {tid: dona} (None — hammasi). Har biri ombor jurnaliga 'zavod_kirim' (landed tannarx,
    o'rtacha tortilgan sebest). Bitta tranzaksiya."""
    if is_closed(today()): return {'ok': False, 'error': f"{today()[:7]} davri yopilgan (/och)"}
    p = po_malumot(po_id)
    if not p: return {'ok': False, 'error': "Buyurtma topilmadi"}
    if p['status'] in ('yopildi', 'bekor'): return {'ok': False, 'error': f"Buyurtma {PO_NOM[p['status']].lower()}"}
    qolgan = {q['tid']: q for q in p['qatorlar'] if q['holat'] == 'yolda' and q['qty'] > q['kelgan']}
    reja = {t: q['qty'] - q['kelgan'] for t, q in qolgan.items()} if miqdor is None else {int(t): int(n) for t, n in miqdor.items() if int(n) > 0}
    if not reja: return {'ok': False, 'error': "Qabul qilinadigan tovar yo'q"}
    for t, n in reja.items():
        if t not in qolgan: return {'ok': False, 'error': "Bu qator allaqachon to'liq kelgan"}
        if n > qolgan[t]['qty'] - qolgan[t]['kelgan']:
            return {'ok': False, 'error': f"{qolgan[t]['nom']}: faqat {qolgan[t]['qty'] - qolgan[t]['kelgan']} dona kutilmoqda"}
    conn = db(); c = conn.cursor(); out = []
    try:
        for t, n in reja.items():
            q = qolgan[t]
            pid = _po_pid(c, q['pid'], q['nom'])
            if not pid:
                conn.rollback(); conn.close(); return {'ok': False, 'error': f"'{q['nom']}' mahsuloti ombordan topilmadi"}
            c.execute('SELECT COALESCE(qty,0), COALESCE(cost,0) FROM products WHERE id=?', (pid,))
            oq, oc = c.fetchone(); oq = max(0, oq)
            yangi = round((oq * oc + n * q['tannarx']) / (oq + n), 2) if oq + n > 0 else q['tannarx']
            stock_move(c, pid, n, 'zavod_kirim', reason=f"zavod #Z{po_id}", ref=f"t{t}", user=user, unit_cost=round(q['tannarx'], 4),
                       new_cost=yangi, supplier=p['supplier'], allow_negative=True)
            toliq = q['kelgan'] + n >= q['qty']
            c.execute("UPDATE transit SET received_qty=COALESCE(received_qty,0)+?, status=CASE WHEN ? THEN 'keldi' ELSE status END, "
                      "arrived_date=CASE WHEN ? THEN ? ELSE arrived_date END, product_id=? WHERE id=?",
                      (n, 1 if toliq else 0, 1 if toliq else 0, today(), pid, t))
            out.append({'nom': q['nom'], 'dona': n, 'tannarx': round(q['tannarx'], 2), 'pid': pid})
        _po_log(c, po_id, p['status'], "📦 qabul: " + ", ".join(f"{o['nom']} × {o['dona']}" for o in out), user)
        holat = _po_holat_avto(c, po_id, user)
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return {'ok': True, 'qabul': out, 'holat': holat}

def zavod_tolov(po_id, amount, method='naqd', user=None):
    """Aynan shu buyurtma qatorlari bo'yicha zavodga to'lov (pay_debt kreditorlik, transit_ids filtri — /undo ishlaydi)."""
    p = po_malumot(po_id)
    if not p: return {'ok': False, 'error': "Buyurtma topilmadi"}
    ids = [q['tid'] for q in p['qatorlar'] if q['holat'] != 'bekor' and q['qoldiq'] > 0.004]
    if not ids: return {'ok': False, 'error': "Bu buyurtma bo'yicha qarz qolmagan"}
    r = pay_debt('kreditorlik', p['supplier'], amount, method, note=f"zakaz #Z{po_id}", transit_ids=ids)
    if r.get('ok'):
        conn = db(); c = conn.cursor()
        _po_log(c, po_id, p['status'], f"💵 to'lov {_usd2(r['paid'])} ({r['method']})", user)
        r['holat'] = _po_holat_avto(c, po_id, user)
        conn.commit(); conn.close()
        r['po_qoldiq'] = po_malumot(po_id)['qoldiq']
    return r

def zavod_xarajat(po_id, amount, kind='yetkazish', method='naqd', user=None):
    """Keyin qo'shilgan bank/yetkazish/bojxona xarajati: kassadan chiqim + kelmagan donalar tannarxiga taqsimlanadi."""
    if is_closed(today()): return {'ok': False, 'error': f"{today()[:7]} davri yopilgan (/och)"}
    usul = tolov_usuli(method or 'naqd')
    if not usul: return {'ok': False, 'error': f"To'lov usuli noma'lum: {method}"}
    try: amount = round(float(amount), 2)
    except (TypeError, ValueError): amount = 0
    if amount <= 0: return {'ok': False, 'error': "Summa 0 dan katta bo'lsin"}
    p = po_malumot(po_id)
    if not p or p['status'] in ('yopildi', 'bekor'): return {'ok': False, 'error': "Buyurtma ochiq emas"}
    conn = db(); c = conn.cursor()
    try:
        if not _po_xarajat_tx(c, po_id, amount, kind):
            conn.rollback(); conn.close()
            return {'ok': False, 'error': "Kelmagan tovar qolmagan — bu xarajatni oddiy xarajat sifatida yozing (tannarxga qo'shib bo'lmaydi)"}
        now = datetime.now()
        c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                  (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'), 'chiqim', amount, 'zavod_xarajat',
                   f"{p['supplier']} zakaz #Z{po_id} {kind}", usul))
        _po_log(c, po_id, p['status'], f"➕ {kind} xarajati {_usd2(amount)} (tannarxga)", user)
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return {'ok': True}

def zavod_bekor(po_id, user=None):
    """Faqat hech narsa kelmagan buyurtma bekor qilinadi. To'langan avans → zavodning bizga qarzi (debitorlik),
    bank/yetkazish → davr xarajati ('zavod_bekor', kassaga tegmaydi — pul avval chiqqan)."""
    if is_closed(today()): return {'ok': False, 'error': f"{today()[:7]} davri yopilgan (/och)"}
    p = po_malumot(po_id)
    if not p: return {'ok': False, 'error': "Buyurtma topilmadi"}
    if p['status'] in ('yopildi', 'bekor'): return {'ok': False, 'error': f"Buyurtma allaqachon {PO_NOM[p['status']].lower()}"}
    if p['kelgan'] > 0: return {'ok': False, 'error': "Tovar qisman kelgan — bekor qilib bo'lmaydi (qolganini qabul qiling yoki holatini o'zgartiring)"}
    conn = db(); c = conn.cursor(); d = today()
    try:
        c.execute("UPDATE transit SET status='bekor', remaining=0 WHERE po_id=? AND status='yolda'", (po_id,))
        c.execute("UPDATE purchase_orders SET status='bekor', closed_date=? WHERE id=? AND status<>'bekor'", (d, po_id))
        if c.rowcount != 1:
            conn.rollback(); conn.close(); return {'ok': False, 'error': "Allaqachon bekor qilingan"}
        if p['tolangan'] > 0.004:
            c.execute('INSERT INTO debts (date, person, amount, type, note) VALUES (?,?,?,?,?)',
                      (d, p['supplier'], p['tolangan'], DEBITOR, f"zavod avansi qaytishi kerak (#Z{po_id} bekor)"))
        if p['xarajat'] > 0.004:
            c.execute('INSERT INTO expenses (date, amount, category, expense_type, note) VALUES (?,?,?,?,?)',
                      (d, p['xarajat'], 'zavod_bekor', 'period', f"#Z{po_id} bekor — bank/yetkazish"))
        _po_log(c, po_id, 'bekor', f"avans {_usd2(p['tolangan'])} → debitorlik" if p['tolangan'] > 0.004 else '', user)
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return {'ok': True, 'avans': p['tolangan'], 'xarajat': p['xarajat']}

def zavod_kechikkanlar():
    """Kutilgan sanasi o'tgan, hali kelmagan buyurtmalar (ertalabki ogohlantirish)."""
    conn = db(); c = conn.cursor()
    c.execute(f"SELECT id, supplier, expected_date FROM purchase_orders WHERE status IN {PO_KELMAGAN} "
              "AND COALESCE(expected_date,'')<>'' AND expected_date < ? ORDER BY expected_date", (today(),))
    rows = c.fetchall(); conn.close()
    return [{'id': r[0], 'supplier': r[1], 'expected': r[2], 'kun': _kun_farq(r[2])} for r in rows]

def zavod_royxat(ochiq=True):
    conn = db(); c = conn.cursor()
    w = f"p.status IN {PO_OCHIQ}" if ochiq else "p.status IN ('yopildi','bekor')"
    c.execute(f"""SELECT p.id, p.date, p.supplier, p.status, COALESCE(p.expected_date,''),
                 COALESCE(SUM(CASE WHEN t.status<>'bekor' THEN t.total_cost END),0),
                 COALESCE(SUM(CASE WHEN t.status<>'bekor' THEN t.remaining END),0),
                 COALESCE(SUM(CASE WHEN t.status<>'bekor' THEN t.qty END),0),
                 COALESCE(SUM(CASE WHEN t.status<>'bekor' THEN t.received_qty END),0)
                 FROM purchase_orders p LEFT JOIN transit t ON t.po_id=p.id WHERE {w} GROUP BY p.id ORDER BY p.id DESC""")
    rows = c.fetchall(); conn.close()
    bugun = today()
    return [{'id': r[0], 'date': r[1], 'supplier': r[2], 'status': r[3], 'expected': r[4], 'jami': round(r[5], 2),
             'qoldiq': round(r[6], 2), 'tolangan': round(r[5] - r[6], 2), 'dona': r[7], 'kelgan': r[8],
             'kech': bool(r[4] and r[4] < bugun and r[3] in PO_KELMAGAN)} for r in rows]

def zavod_balans():
    """Zavodlar bo'yicha: biz qarzmiz (kreditorlik: zavod qoldig'i + qarzlar), ular bizga qarz (masalan qaytariladigan avans)."""
    kre = {norm_ism(k['name']): k for k in kreditorlar()}
    conn = db(); c = conn.cursor()
    c.execute("SELECT DISTINCT supplier FROM purchase_orders UNION SELECT DISTINCT supplier FROM transit")
    sup = {norm_ism(r[0]): r[0] for r in c.fetchall() if r[0]}
    c.execute(f"SELECT person, COALESCE(SUM(amount),0) FROM debts WHERE paid=0 AND type IN {DEBITOR_SQL} GROUP BY person")
    deb = defaultdict(float)
    for p_, s in c.fetchall(): deb[norm_ism(p_)] += s
    c.execute(f"SELECT supplier, COUNT(*) FROM purchase_orders WHERE status IN {PO_OCHIQ} GROUP BY supplier")
    och = defaultdict(int)
    for s_, n in c.fetchall(): och[norm_ism(s_)] += n
    conn.close()
    out = []
    for k in set(sup) | set(kre):
        if k not in sup and k not in och: continue        # zavod bo'lmagan kreditorlar — 👥 Mijozlar → Kreditorlar
        out.append({'name': (kre.get(k) or {}).get('name') or sup.get(k, k), 'kre': round((kre.get(k) or {}).get('sum', 0), 2),
                    'deb': round(deb.get(k, 0), 2), 'ochiq': och.get(k, 0)})
    return sorted(out, key=lambda x: -x['kre'])

# ── UI ──
def _zav_menu():
    o = zavod_royxat(True); k = zavod_kechikkanlar()
    t = (f"🏭 Zavod buyurtmalari\nOchiq: {len(o)} ta · qarzimiz {_usd2(sum(x['qoldiq'] for x in o))}"
         + (f"\n⏰ Kechikkan: {len(k)} ta" if k else ""))
    rows = [[_btn("➕ Yangi buyurtma", "zav:n")],
            [_btn(f"📋 Ochiq ({len(o)})", "zav:o:0"), _btn(f"⏰ Kechikkan ({len(k)})", "zav:k")],
            [_btn("🗂 Yopilganlar", "zav:a:0"), _btn("🏭 Zavodlar balansi", "zav:bal")], _x_btn('zav')]
    return t, rows

def _zav_holat_belgi(x):
    return PO_NOM.get(x['status'], x['status']).split()[0] + (" ⏰" if x.get('kech') else "")

def _zav_royxat_ekran(ochiq, page):
    ps = zavod_royxat(ochiq)
    pages = max(1, math.ceil(len(ps) / POS_SAHIFA)); page = min(max(0, page), pages - 1)
    t = (f"📋 Ochiq buyurtmalar: {len(ps)} ta\nTovar summasi: {_usd2(sum(x['jami'] for x in ps))} · "
         f"to'langan {_usd2(sum(x['tolangan'] for x in ps))} · qarz {_usd2(sum(x['qoldiq'] for x in ps))}"
         if ochiq else f"🗂 Yopilgan / bekor buyurtmalar: {len(ps)} ta")
    if not ps: t += "\n\nHozircha yo'q."
    rows = [[_btn(f"{_zav_holat_belgi(x)} #Z{x['id']} {x['supplier'][:16]} · {x['kelgan']}/{x['dona']} · {_usd2(x['qoldiq'])}",
                  f"zav:c:{x['id']}")] for x in ps[page * POS_SAHIFA:(page + 1) * POS_SAHIFA]]
    nav = "zav:o" if ochiq else "zav:a"
    if pages > 1:
        nv = []
        if page > 0: nv.append(_btn("⬅️", f"{nav}:{page - 1}"))
        nv.append(_btn(f"{page + 1}/{pages}", "pos:noop"))
        if page < pages - 1: nv.append(_btn("➡️", f"{nav}:{page + 1}"))
        rows.append(nv)
    rows.append([_btn("⬅️ Menyu", "zav:menu")] + _x_btn('zav'))
    return t, rows

def _zav_karta(po_id):
    conn = db(); c = conn.cursor(); _po_holat_avto(c, po_id); conn.commit(); conn.close()   # /undo dan keyin holat to'g'rilanadi
    p = po_malumot(po_id)
    if not p: return None, None
    L = [f"🏭 Buyurtma #Z{p['id']} — {p['supplier']}", f"Holat: {PO_NOM.get(p['status'], p['status'])}",
         f"Sana: {p['date']}" + (f" · kutilgan: {p['expected']}" if p['expected'] else "")]
    if p['kech']: L.append(f"⏰ {p['kech']} kun kechikdi!")
    L.append("\nTovarlar:")
    for q in p['qatorlar']:
        bel = "🗑" if q['holat'] == 'bekor' else ("✅" if q['kelgan'] >= q['qty'] else ("🟡" if q['kelgan'] else "⏳"))
        L.append(f"{bel} {q['nom'][:28]}: {q['kelgan']}/{q['qty']} × {_usd2(q['narx'])}"
                 + (f" → tannarx {_usd2(q['tannarx'])}" if abs(q['tannarx'] - q['narx']) > 0.004 else ""))
    L += ["", f"Tovar summasi: {_usd2(p['jami'])}", f"To'langan: {_usd2(p['tolangan'])}", f"Qarzimiz: {_usd2(p['qoldiq'])}"]
    if p['xarajat']: L.append(f"Bank/yetkazish (tannarxga qo'shilgan): {_usd2(p['xarajat'])}")
    L.append(f"Kelgan: {p['kelgan']}/{p['dona']} dona")
    ochiq = p['status'] not in ('yopildi', 'bekor')
    rows = []
    if ochiq:
        rows += [[_btn("🔄 Holat", f"zav:st:{po_id}"), _btn("📦 Qabul qilish", f"zav:r:{po_id}")],
                 [_btn("💵 To'lov", f"zav:p:{po_id}"), _btn("➕ Xarajat", f"zav:f:{po_id}")],
                 [_btn("📜 Tarix", f"zav:h:{po_id}"), _btn("🗑 Bekor qilish", f"zav:cx:{po_id}")]]
    else:
        rows.append([_btn("📜 Tarix", f"zav:h:{po_id}")])
    rows.append([_btn("⬅️ Ro'yxat", "zav:o:0" if ochiq else "zav:a:0")] + _x_btn('zav'))
    return "\n".join(L), rows

def _zav_tarix(po_id):
    p = po_malumot(po_id)
    L = [f"📜 #Z{po_id} tarixi:"] + [f"{ts} · {PO_NOM.get(s, s).split(' ', 1)[-1]}" + (f" — {n}" if n else "") + (f" ({u_})" if u_ else "")
                                     for ts, s, n, u_ in (p['log'] if p else [])[-15:]]
    return "\n".join(L), [[_btn("⬅️ Buyurtma", f"zav:c:{po_id}")] + _x_btn('zav')]

def _zav_sup_ekran(st):
    conn = db(); c = conn.cursor()
    c.execute("SELECT DISTINCT supplier FROM products WHERE active=1 AND TRIM(COALESCE(supplier,''))<>'' "
              "UNION SELECT DISTINCT supplier FROM purchase_orders UNION SELECT DISTINCT supplier FROM transit")
    sups = sorted({r[0] for r in c.fetchall() if r[0] and r[0].strip()}); conn.close()
    st['sups'] = sups[:24]
    rows = [[_btn(s[:30], f"zav:ns:{i}")] for i, s in enumerate(st['sups'])]
    rows.append([_btn("✍️ Boshqa nom yozish", "zav:nsw")])
    rows.append([_btn("⬅️ Menyu", "zav:menu")] + _x_btn('zav'))
    return "➕ Yangi buyurtma — 1/3: zavodni tanlang", rows

def _zav_tovar_ekran(st, page, hammasi):
    d = st['d']; prods = get_products()
    if not hammasi:
        f = [p for p in prods if norm_ism(p['sup'] or '') == norm_ism(d['sup'])]
        if f: prods = f
        else: hammasi = 1
    pages = max(1, math.ceil(len(prods) / POS_SAHIFA)); page = min(max(0, page), pages - 1)
    rows = [[_btn(f"{p['name'][:30]} · {p['qty']} ta", f"zav:pk:{p['id']}")] for p in prods[page * POS_SAHIFA:(page + 1) * POS_SAHIFA]]
    nv = []
    if page > 0: nv.append(_btn("⬅️", f"zav:pp:{page - 1}:{hammasi}"))
    if pages > 1: nv.append(_btn(f"{page + 1}/{pages}", "pos:noop"))
    if page < pages - 1: nv.append(_btn("➡️", f"zav:pp:{page + 1}:{hammasi}"))
    if nv: rows.append(nv)
    rows.append([_btn("📚 Barcha tovarlar" if not hammasi else f"🏭 Faqat {d['sup'][:14]}", f"zav:pp:0:{0 if hammasi else 1}")])
    rows.append(([_btn("📝 Qoralama", "zav:d")] if d['lines'] else []) + _x_btn('zav'))
    return f"➕ {d['sup']} — 2/3: tovarni tanlang" + (f"\nQoralamada: {len(d['lines'])} xil" if d['lines'] else ""), rows

def _zav_qoralama(st):
    d = st['d']; jami = round(sum(x['qty'] * x['cost'] for x in d['lines']), 2)
    L = [f"📝 Buyurtma qoralamasi — {d['sup']}", ""]
    L += [f"{i}. {x['name'][:28]} — {x['qty']} × {_usd2(x['cost'])} = {_usd2(x['qty'] * x['cost'])}" for i, x in enumerate(d['lines'], 1)] or ["(tovar yo'q)"]
    L += ["", f"Tovar summasi: {_usd2(jami)}", f"💵 Avans (hozir to'lanadi): {_usd2(d['dep'])} · qoladigan qarz {_usd2(max(0, jami - d['dep']))}",
          f"🏦 Bank: {_usd2(d['bank'])} · 🚚 Yetkazish: {_usd2(d['del'])} (tannarxga qo'shiladi)",
          f"📅 Kutilgan sana: {d['exp'] or '—'}", f"💳 To'lov usuli: {d['m']}"]
    rows = [[_btn("➕ Tovar", "zav:pp:0:0"), _btn("🗑 Oxirgisini o'chirish", "zav:dl")],
            [_btn("💵 Avans", "zav:nd"), _btn("🏦 Bank", "zav:nb"), _btn("🚚 Yetkazish", "zav:nf")],
            [_btn("📅 Sana", "zav:ne"), _btn(f"💳 {d['m']}", "zav:nm")]]
    if d['lines']: rows.append([_btn("✅ Buyurtmani yaratish", f"zav:nok:{d['tok']}")])
    rows.append([_btn("⬅️ Menyu", "zav:menu")] + _x_btn('zav'))
    return "\n".join(L), rows

def _zav_qabul_ekran(po_id):
    p = po_malumot(po_id)
    qol = [q for q in p['qatorlar'] if q['holat'] == 'yolda' and q['qty'] > q['kelgan']]
    L = [f"📦 #Z{po_id} qabul qilish — {p['supplier']}", "Qisman kelgan bo'lsa — tovarni bosing va sonini yozing.", ""]
    L += [f"• {q['nom'][:28]}: kutilmoqda {q['qty'] - q['kelgan']} ta (tannarx {_usd2(q['tannarx'])})" for q in qol] or ["Hammasi kelgan ✅"]
    rows = [[_btn(f"📦 {q['nom'][:24]} ({q['qty'] - q['kelgan']})", f"zav:rl:{po_id}:{q['tid']}")] for q in qol[:12]]
    if qol: rows.append([_btn("✅ Hammasi keldi", f"zav:ra:{po_id}:{p['kelgan']}")])
    rows.append([_btn("⬅️ Buyurtma", f"zav:c:{po_id}")] + _x_btn('zav'))
    return "\n".join(L), rows

def _zav_tolov_ekran(st):
    p = st['pay']; po = po_malumot(p['po'])
    L = [f"💵 #Z{p['po']} — {po['supplier']} ga to'lov", f"Qarzimiz: {_usd2(po['qoldiq'])}"]
    if p.get('sum'):
        L += [f"Summa: {_usd2(p['sum'])}", f"Usul: {p['m']}"]
        rows = [[_btn(("✅ " if p['m'] == m else "") + m, f"zav:pm:{m}") for m in TOLOV_USULLARI[:3]],
                [_btn(("✅ " if p['m'] == m else "") + m, f"zav:pm:{m}") for m in TOLOV_USULLARI[3:]],
                [_btn("✅ Tasdiqlash", f"zav:pok:{p['tok']}")]]
    else:
        rows = [[_btn(f"To'liq {_usd2(po['qoldiq'])}", f"zav:pa:{p['po']}:all"), _btn("Yarmi", f"zav:pa:{p['po']}:half")],
                [_btn("✍️ Boshqa summa", f"zav:pc:{p['po']}")]]
    rows.append([_btn("⬅️ Buyurtma", f"zav:c:{p['po']}")] + _x_btn('zav'))
    return "\n".join(L), rows

def _zav_balans_ekran():
    bs = zavod_balans()
    L = ["🏭 Zavodlar balansi", ""]
    L += [f"• {b['name']}: biz qarzmiz {_usd2(b['kre'])}" + (f" · ular bizga {_usd2(b['deb'])}" if b['deb'] else "")
          + (f" · ochiq buyurtma {b['ochiq']}" if b['ochiq'] else "") for b in bs] or ["Hozircha zavod yo'q"]
    L += ["", f"Jami zavodlarga qarzimiz: {_usd2(sum(b['kre'] for b in bs))}"]
    return "\n".join(L), [[_btn("💵 To'lash (Kreditorlar)", "zav:kre")], [_btn("⬅️ Menyu", "zav:menu")] + _x_btn('zav')]

async def cmd_zavod_ui(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    _ui_yangi(ctx, 'zav')
    m, r = _zav_menu()
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))

async def zav_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not can(u, 'boshqaruv'):
        await q.answer("Ruxsat yo'q", show_alert=True); return
    parts = (q.data or '').split(':'); act = parts[1] if len(parts) > 1 else ''; arg = parts[2:]
    def _i(k, dflt=0):
        try: return int(arg[k])
        except (IndexError, ValueError): return dflt
    if act == 'x':
        ctx.user_data.pop('zav', None); await q.answer()
        return await _pos_chiqar(q, "🏭 Zavod oynasi yopildi.", None)
    st = _ui_ol(ctx, 'zav')
    if st is None:
        if act == 'menu': st = _ui_yangi(ctx, 'zav')
        else:
            await q.answer(); return await _pos_chiqar(q, "⏰ Oyna eskirgan. Qaytadan: 🏭 Zavod", None)
    st['wait'] = None
    m = r = None; alert = None; user = _ui_user(u)
    d = st.get('d')
    if act == 'menu': m, r = _zav_menu()
    elif act == 'o': m, r = _zav_royxat_ekran(True, _i(0))
    elif act == 'a': m, r = _zav_royxat_ekran(False, _i(0))
    elif act == 'k':
        ks = zavod_kechikkanlar()
        m = "⏰ Kechikkan buyurtmalar:\n" + ("\n".join(f"• #Z{k['id']} {k['supplier']} — kutilgan {k['expected']} ({k['kun']} kun)" for k in ks) or "Yo'q ✅")
        r = [[_btn(f"#Z{k['id']} {k['supplier'][:20]}", f"zav:c:{k['id']}")] for k in ks[:10]] + [[_btn("⬅️ Menyu", "zav:menu")] + _x_btn('zav')]
    elif act == 'bal': m, r = _zav_balans_ekran()
    elif act == 'kre':
        st2 = _ui_yangi(ctx, 'mij'); m, r = _mij_kre_ekran(st2)
    elif act == 'n': m, r = _zav_sup_ekran(st)
    elif act == 'ns':
        sups = st.get('sups') or []
        if _i(0) >= len(sups): alert = "Eskirgan"
        else:
            st['d'] = {'sup': sups[_i(0)], 'lines': [], 'dep': 0.0, 'bank': 0.0, 'del': 0.0, 'exp': '', 'm': 'naqd', 'tok': secrets.token_hex(3)}
            m, r = _zav_tovar_ekran(st, 0, 0)
    elif act == 'nsw':
        st['wait'] = 'sup'; m, r = "✍️ Zavod (yetkazuvchi) nomini yozing:", [[_btn("⬅️ Orqaga", "zav:n")] + _x_btn('zav')]
    elif not d and act in ('pp', 'pk', 'd', 'dl', 'nd', 'nb', 'nf', 'ne', 'nE', 'nEw', 'nm', 'nok'):
        alert = "Qoralama yo'q — ➕ Yangi buyurtma"
    elif act == 'pp': m, r = _zav_tovar_ekran(st, _i(0), _i(1))
    elif act == 'pk':
        p = next((x for x in get_products() if x['id'] == _i(0)), None)
        if not p: alert = "Tovar topilmadi"
        else:
            nar = p.get('factory') or p.get('cost') or 0
            st['wait'] = f"qty:{p['id']}"
            m, r = (f"📦 {p['name']}\nNechta va dona narxi ($)?\nMasalan: 20 {nar:g}\n(narx yozilmasa: {_usd2(nar)} — zavod narxi)",
                    [[_btn("⬅️ Tovarlar", "zav:pp:0:0")] + _x_btn('zav')])
    elif act == 'd': m, r = _zav_qoralama(st)
    elif act == 'dl':
        if d['lines']: d['lines'].pop()
        m, r = _zav_qoralama(st)
    elif act in ('nd', 'nb', 'nf'):
        st['wait'] = {'nd': 'dep', 'nb': 'bank', 'nf': 'del'}[act]
        m, r = ({'nd': "💵 Avans summasini yozing ($, hozir kassadan to'lanadi; 0 — avanssiz):",
                 'nb': "🏦 Bank xarajatini yozing ($):", 'nf': "🚚 Yetkazish xarajatini yozing ($):"}[act],
                [[_btn("⬅️ Qoralama", "zav:d")] + _x_btn('zav')])
    elif act == 'ne':
        m = "📅 Tovar qachon kelishi kutilmoqda?"
        r = [[_btn(f"+{n} kun", f"zav:nE:{n}") for n in (7, 14, 30)], [_btn(f"+{n} kun", f"zav:nE:{n}") for n in (45, 60, 90)],
             [_btn("✍️ Sanani yozish", "zav:nEw"), _btn("⬅️ Qoralama", "zav:d")]]
    elif act == 'nE':
        d['exp'] = _ds(datetime.now() + timedelta(days=_i(0))); m, r = _zav_qoralama(st)
    elif act == 'nEw':
        st['wait'] = 'exp'; m, r = "📅 Sanani yozing (2026-11-20 yoki 20.11.2026):", [[_btn("⬅️ Qoralama", "zav:d")] + _x_btn('zav')]
    elif act == 'nm':
        us = list(TOLOV_USULLARI); d['m'] = us[(us.index(d['m']) + 1) % len(us)] if d['m'] in us else 'naqd'
        m, r = _zav_qoralama(st)
    elif act == 'nok':
        if (arg[0] if arg else '') != d['tok'] or not _ui_done(ctx, 'zavnok' + d['tok']):
            await q.answer("Allaqachon yaratilgan yoki eskirgan", show_alert=True); return
        res = zavod_yarat(d['sup'], [{'pid': x['pid'], 'qty': x['qty'], 'cost': x['cost']} for x in d['lines']],
                          d['dep'], d['bank'], d['del'], d['exp'], d['m'], user)
        if not res['ok']:
            done_ = ctx.user_data.get('ui_done', [])
            if 'zavnok' + d['tok'] in done_: done_.remove('zavnok' + d['tok'])      # xatoni tuzatib qayta bosish mumkin
            alert = res['error']
        else:
            st.pop('d', None)
            m, r = _zav_karta(res['po_id']); m = f"✅ Buyurtma #Z{res['po_id']} yaratildi\n\n" + m
    elif act == 'c':
        m, r = _zav_karta(_i(0))
        if m is None: alert = "Buyurtma topilmadi"
    elif act == 'h': m, r = _zav_tarix(_i(0))
    elif act == 'st':
        p = po_malumot(_i(0))
        if not p: alert = "Topilmadi"
        else:
            m = f"🔄 #Z{p['id']} holati: {PO_NOM.get(p['status'])}\nYangi holatni tanlang:"
            vs = [(k, n) for k, n in PO_HOLATLAR if k not in (p['status'], 'bekor')]
            r = [[_btn(n, f"zav:ss:{p['id']}:{k}") for k, n in vs[i:i + 2]] for i in range(0, len(vs), 2)]
            r.append([_btn("⬅️ Buyurtma", f"zav:c:{p['id']}")] + _x_btn('zav'))
    elif act == 'ss':
        res = zavod_holat(_i(0), arg[1] if len(arg) > 1 else '', user)
        if not res['ok']: alert = res['error']
        else: m, r = _zav_karta(_i(0)); m = f"✅ Holat: {PO_NOM[res['status']]}\n\n" + m
    elif act == 'r': m, r = _zav_qabul_ekran(_i(0))
    elif act == 'rl':
        st['wait'] = f"rqty:{_i(0)}:{_i(1)}"
        m, r = "📦 Nechta keldi? Sonini yozing:", [[_btn("⬅️ Qabul", f"zav:r:{_i(0)}")] + _x_btn('zav')]
    elif act == 'ra':
        if not _ui_done(ctx, f"zavra{st['id']}_{_i(0)}_{_i(1)}"):
            await q.answer("Allaqachon qabul qilingan", show_alert=True); return
        res = zavod_qabul(_i(0), None, user)
        if not res['ok']: alert = res['error']
        else:
            m, r = _zav_karta(_i(0))
            m = "✅ Omborga kirdi: " + ", ".join(f"{o['nom']} × {o['dona']} ({_usd2(o['tannarx'])})" for o in res['qabul']) + "\n\n" + m
            r = sn_kirim_btn([(o.get('pid'), o['dona'], o['nom']) for o in res['qabul']]) + r
    elif act == 'p':
        st['pay'] = {'po': _i(0), 'sum': 0, 'm': 'naqd', 'tok': secrets.token_hex(3)}; m, r = _zav_tolov_ekran(st)
    elif act in ('pa', 'pc', 'pm', 'pok') and not st.get('pay'): alert = "Eskirgan"
    elif act == 'pa':
        po = po_malumot(st['pay']['po']); s = po['qoldiq'] if (arg[1] if len(arg) > 1 else '') == 'all' else round(po['qoldiq'] / 2, 2)
        if s <= 0: alert = "Qarz qolmagan"
        else: st['pay']['sum'] = s; m, r = _zav_tolov_ekran(st)
    elif act == 'pc':
        st['wait'] = 'pay'; m, r = "✍️ Summani yozing ($):", [[_btn("⬅️ Buyurtma", f"zav:c:{st['pay']['po']}")] + _x_btn('zav')]
    elif act == 'pm':
        if arg and arg[0] in TOLOV_USULLARI: st['pay']['m'] = arg[0]
        m, r = _zav_tolov_ekran(st)
    elif act == 'pok':
        p = st['pay']
        if (arg[0] if arg else '') != p['tok'] or not p.get('sum') or not _ui_done(ctx, 'zavpok' + p['tok']):
            await q.answer("Allaqachon saqlangan yoki eskirgan", show_alert=True); return
        res = zavod_tolov(p['po'], p['sum'], p['m'], user)
        if not res.get('ok'): alert = res.get('error', 'Xato')
        else:
            st.pop('pay', None)
            m, r = _zav_karta(p['po'])
            m = f"✅ To'lov saqlandi: {_usd2(res['paid'])} ({res['method']}). Buyurtma qarzi: {_usd2(res['po_qoldiq'])}\n\n" + m
    elif act == 'f':
        m = "➕ Qaysi xarajat? (kelmagan tovar tannarxiga qo'shiladi, kassadan chiqadi)"
        r = [[_btn("🏦 Bank", f"zav:fk:{_i(0)}:bank"), _btn("🚚 Yetkazish", f"zav:fk:{_i(0)}:yetkazish"), _btn("🛃 Bojxona", f"zav:fk:{_i(0)}:bojxona")],
             [_btn("⬅️ Buyurtma", f"zav:c:{_i(0)}")] + _x_btn('zav')]
    elif act == 'fk':
        kind = arg[1] if len(arg) > 1 and arg[1] in ('bank', 'yetkazish', 'bojxona') else 'yetkazish'
        st['wait'] = f"fee:{_i(0)}:{kind}"
        m, r = f"✍️ {kind} summasini yozing ($). Usul kerak bo'lsa: 50 karta", [[_btn("⬅️ Buyurtma", f"zav:c:{_i(0)}")] + _x_btn('zav')]
    elif act == 'cx':
        p = po_malumot(_i(0))
        if not p: alert = "Topilmadi"
        else:
            m = (f"🗑 #Z{p['id']} ni bekor qilasizmi?\n• To'langan {_usd2(p['tolangan'])} → zavodning bizga qarzi (debitorlik)\n"
                 f"• Bank/yetkazish {_usd2(p['xarajat'])} → xarajat\nTovar qisman kelgan bo'lsa bekor qilib bo'lmaydi.")
            r = [[_btn("✅ Ha, bekor qilish", f"zav:cxok:{p['id']}"), _btn("⬅️ Yo'q", f"zav:c:{p['id']}")]]
    elif act == 'cxok':
        res = zavod_bekor(_i(0), user)
        if not res['ok']: alert = res['error']
        else: m, r = _zav_karta(_i(0)); m = "🗑 Bekor qilindi.\n\n" + m
    else: alert = "Eski tugma"
    await q.answer(alert[:190] if alert else None, show_alert=bool(alert))
    if m is not None: await _pos_chiqar(q, m[:4000], r)

def _son(s):
    try: return float(str(s).replace(',', '.').replace('$', '').strip())
    except ValueError: return None

async def zav_matn(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    st0 = ctx.user_data.get('zav')
    if not st0 or not st0.get('wait') or not can(u, 'boshqaruv'): return False
    st = _ui_ol(ctx, 'zav')
    if st is None:
        await u.message.reply_text("⏰ Oyna eskirgan. Qaytadan: 🏭 Zavod"); return True
    w = st['wait']; st['wait'] = None
    msg = (u.message.text or '').strip(); user = _ui_user(u)
    m = r = None; d = st.get('d')
    def qayta(xato):
        st['wait'] = w
        return f"⚠️ {xato}", [_x_btn('zav')]
    if w == 'sup':
        if len(msg) < 2: m, r = qayta("Nom juda qisqa")
        else:
            st['d'] = {'sup': msg[:60], 'lines': [], 'dep': 0.0, 'bank': 0.0, 'del': 0.0, 'exp': '', 'm': 'naqd', 'tok': secrets.token_hex(3)}
            m, r = _zav_tovar_ekran(st, 0, 0)
    elif not d and (w in ('dep', 'bank', 'del', 'exp') or w.startswith('qty:')):
        m, r = "Qoralama eskirgan — ➕ Yangi buyurtma", [_x_btn('zav')]
    elif w.startswith('qty:'):
        pid = int(w.split(':')[1]); p = next((x for x in get_products(active_only=False) if x['id'] == pid), None)
        bo = msg.replace('×', ' ').replace('x', ' ').split()
        n = _son(bo[0]) if bo else None
        narx = _son(bo[1]) if len(bo) > 1 else ((p.get('factory') or p.get('cost') or 0) if p else None)
        if not p or n is None or n <= 0 or n != int(n) or narx is None or narx < 0:
            m, r = qayta("Masalan: 20 45.5 (son va narx)")
        else:
            d['lines'].append({'pid': pid, 'name': p['name'], 'qty': int(n), 'cost': round(narx, 4)})
            m, r = _zav_qoralama(st)
    elif w in ('dep', 'bank', 'del'):
        v = _son(msg)
        if v is None or v < 0: m, r = qayta("Summani raqam bilan yozing")
        else:
            d[w] = round(v, 2); m, r = _zav_qoralama(st)
    elif w == 'exp':
        s = _sana_parse(msg)
        if not s: m, r = qayta("Sana noto'g'ri. Masalan: 2026-11-20")
        else: d['exp'] = _ds(s); m, r = _zav_qoralama(st)
    elif w.startswith('rqty:'):
        _, po, tid = w.split(':'); v = _son(msg)
        if v is None or v <= 0 or v != int(v): m, r = qayta("Butun son yozing")
        else:
            res = zavod_qabul(int(po), {int(tid): int(v)}, user)
            if not res['ok']: m, r = qayta(res['error'])
            else:
                m, r = _zav_karta(int(po))
                m = "✅ Omborga kirdi: " + ", ".join(f"{o['nom']} × {o['dona']} ({_usd2(o['tannarx'])})" for o in res['qabul']) + "\n\n" + m
                r = sn_kirim_btn([(o.get('pid'), o['dona'], o['nom']) for o in res['qabul']]) + r
    elif w == 'pay':
        v = _son(msg); p = st.get('pay')
        if not p: m, r = "Eskirgan", [_x_btn('zav')]
        elif v is None or v <= 0: m, r = qayta("Summani raqam bilan yozing")
        else:
            qol = po_malumot(p['po'])['qoldiq']
            if v > qol + 0.005: m, r = qayta(f"Ortiqcha: bu buyurtma qarzi faqat {_usd2(qol)}")
            else: p['sum'] = round(v, 2); m, r = _zav_tolov_ekran(st)
    elif w.startswith('fee:'):
        _, po, kind = w.split(':'); bo = msg.split()
        v = _son(bo[0]) if bo else None; usul = tolov_usuli(bo[1]) if len(bo) > 1 else 'naqd'
        if v is None or v <= 0 or not usul: m, r = qayta("Masalan: 50 yoki 50 karta")
        else:
            res = zavod_xarajat(int(po), v, kind, usul, user)
            if not res['ok']: m, r = qayta(res['error'])
            else: m, r = _zav_karta(int(po)); m = f"✅ {kind} {_usd2(v)} tannarxga qo'shildi\n\n" + m
    else:
        return False
    await u.message.reply_text(m[:4000], reply_markup=InlineKeyboardMarkup(r) if r else None)
    return True


# ══════════════════════════════════════════════════════════════════
# ── 📢 MARKETING (9-bosqich): kanal posti, Instagram, ochiq katalog, so'rovlar (lead)
# ══════════════════════════════════════════════════════════════════
# Xavfsizlik: post/karta matnlari faqat sotuv narxi (price) dan tuziladi — tannarx (cost/factory)
# hech qachon o'qilmaydi (_mkt_p SELECT'ida cost yo'q). Instagram tokeni hech qachon logga yozilmaydi.
TG_CAPTION_MAX = 1024          # Telegram: media izohi
TG_TEXT_MAX = 4096
IG_CAPTION_MAX = 2200          # Instagram: izoh
IG_HASHTAG_MAX = 30
IG_POLL_SEC = 5                # media konteyner holatini so'rash oralig'i (test: 0)
IG_POLL_TIMEOUT = 300
IG_FON = True                  # Instagram'ga fon vazifada (test: False — kutib turadi)
TG_DL_MAX = 20 * 1024 * 1024   # Bot API getFile chegarasi (20 MB)
SOZ_DEFAULT = {
    'ochiq_qoldiq': '0',       # ochiq kartada aniq dona sonini ko'rsatish
    'lead_sotuvchi': '0',      # so'rovlar sotuvchilarga ham boradimi
    'aloqa_tel': '',           # bo'sh — FIRMA_TEL
    'auto_post': '0',          # kunlik kontent: 1 — oldindan ko'rsatmasdan joylaydi
    'auto_platforma': 'tg',    # tg | ig | both
    'kontent_kunlik': '1',     # kunlik kontent (oldindan ko'rish) yoqilgan
    'kontent_vaqt': '10:00',   # Toshkent vaqti
    'kontent_kun': '14',       # shu kun ichida joylangan tovar takrorlanmaydi
    'manba_korsat': '1',       # "Manba: <brend> rasmiy sayti"
}
PLATFORMA_NOMI = {'tg': 'Telegram', 'ig': 'Instagram', 'both': 'Telegram + Instagram'}


class IgXato(Exception):
    pass


def init_marketing_tables():
    """Additiv va idempotent: sozlamalar, postlar, qoralamalar, so'rovlar, yetkazuvchi kontenti keshi."""
    conn = db(); c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS sozlamalar (kalit TEXT PRIMARY KEY, qiymat TEXT)")
    c.execute('''CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, product_id INTEGER, product TEXT DEFAULT '',
        platform TEXT, status TEXT, message_id TEXT DEFAULT '', link TEXT DEFAULT '', media_type TEXT DEFAULT '',
        caption TEXT DEFAULT '', draft_id INTEGER, source TEXT DEFAULT '', user_id INTEGER DEFAULT 0, error TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS post_drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, source TEXT DEFAULT 'tg', product_id INTEGER,
        media TEXT DEFAULT '[]', caption TEXT DEFAULT '', custom INTEGER DEFAULT 0, show_price INTEGER DEFAULT 1,
        extra TEXT DEFAULT '', video_link TEXT DEFAULT '', manba TEXT DEFAULT '', status TEXT DEFAULT 'qoralama',
        user_id INTEGER DEFAULT 0, chat_id INTEGER DEFAULT 0, note TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, chat_id INTEGER, username TEXT DEFAULT '',
        name TEXT DEFAULT '', phone TEXT DEFAULT '', product_id INTEGER, product TEXT DEFAULT '',
        qty INTEGER DEFAULT 1, status TEXT DEFAULT 'yangi', handled_by TEXT DEFAULT '', note TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS supplier_content (
        product_id INTEGER PRIMARY KEY, url TEXT, fetched TEXT, title TEXT DEFAULT '',
        images TEXT DEFAULT '[]', videos TEXT DEFAULT '[]', text TEXT DEFAULT '',
        status TEXT DEFAULT '', error TEXT DEFAULT '')''')
    for ddl in ("ALTER TABLE products ADD COLUMN public_show INTEGER DEFAULT 1",
                "ALTER TABLE products ADD COLUMN public_price INTEGER DEFAULT 1",
                "ALTER TABLE products ADD COLUMN supplier_url TEXT DEFAULT ''",
                "ALTER TABLE products ADD COLUMN supplier_url_ok INTEGER DEFAULT 0"):
        try: c.execute(ddl)
        except sqlite3.OperationalError: pass
    c.execute("CREATE INDEX IF NOT EXISTS idx_posts_pid ON posts(product_id, created)")
    conn.commit(); conn.close()


def soz(kalit):
    try:
        conn = db(); r = conn.execute("SELECT qiymat FROM sozlamalar WHERE kalit=?", (kalit,)).fetchone(); conn.close()
    except sqlite3.OperationalError:
        r = None
    return r[0] if r and r[0] is not None else SOZ_DEFAULT.get(kalit, '')


def soz_yoz(kalit, qiymat):
    conn = db()
    conn.execute("INSERT INTO sozlamalar (kalit, qiymat) VALUES (?,?) ON CONFLICT(kalit) DO UPDATE SET qiymat=excluded.qiymat",
                 (kalit, str(qiymat)))
    conn.commit(); conn.close()


def _mkt_vaqt(): return _local_now().strftime('%Y-%m-%d %H:%M')


def _mkt_p(pid):
    """Post/karta uchun tovar. ATAYLAB tannarx (cost/factory_price) o'qilmaydi."""
    try: pid = int(pid)
    except (TypeError, ValueError): return None
    conn = db(); c = conn.cursor()
    c.execute("SELECT id,name,cat,supplier,qty,price,warranty_days,active,COALESCE(public_show,1),COALESCE(public_price,1),"
              "COALESCE(supplier_url,''),COALESCE(supplier_url_ok,0) FROM products WHERE id=?", (pid,))
    r = c.fetchone(); conn.close()
    if not r: return None
    return {'id': r[0], 'name': r[1], 'cat': r[2] or '', 'sup': r[3] or '', 'qty': int(r[4] or 0),
            'price': float(r[5] or 0), 'warranty': int(r[6] or 0), 'active': int(r[7] or 0),
            'public_show': int(r[8]), 'public_price': int(r[9]), 'supplier_url': r[10] or '', 'url_ok': int(r[11])}


def _mkt_tel(): return (soz('aloqa_tel') or FIRMA.get('tel') or '').strip()


def _uzs_txt(usd, rate):
    return f"{round(float(usd) * float(rate) / 1000) * 1000:,.0f}".replace(',', ' ')


def _narx_txt(p, rate=None):
    """'$1,250 (~15 625 000 so'm)'"""
    rate = rate or get_exchange_rate()
    return f"{fmt(p['price'])} (~{_uzs_txt(p['price'], rate)} so'm)"


def _kafolat_txt(days):
    d = int(days or 0)
    if d <= 0: return ''
    if d % 365 == 0: return f"{d // 365} yil"
    if d % 30 == 0: return f"{d // 30} oy"
    return f"{d} kun"


def _brend(sup):
    s = (sup or '').lower().replace(' ', '')
    for k, v in SUPPLIER_SAYTLAR.items():
        if k.replace(' ', '') in s: return v['nom']
    return sup or ''


def _heshteg(s):
    t = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_]", '', str(s or '').replace(' ', ''))
    return ('#' + t) if len(t) >= 2 else ''


def _heshteglar(p, ig=False):
    tags = ['#ThermoCrafts', _heshteg(_brend(p['sup'])), _heshteg(p['cat'])]
    sup = (p['sup'] or '').lower()
    if ig:
        tags += ['#Toshkent', '#Uzbekistan', '#biznes']
        if 'tree' in sup: tags += ['#lazerstanok', '#lazergravyor', '#cnc', '#lasercutting', '#laserengraving']
        elif 'freesub' in sup: tags += ['#termopress', '#sublimatsiya', '#heatpress', '#sublimation', '#futbolkapechat']
        tags.append(_heshteg(p['name']))
    out = []
    for t_ in tags:
        if t_ and t_.lower() not in [o.lower() for o in out]: out.append(t_)
    return ' '.join(out[:IG_HASHTAG_MAX if ig else 5])


def _yigish(bosh, ixt, oxir, limit):
    """Majburiy bosh/oxir qatorlari + ixtiyoriy (oxiridan tashlab) — limitga sig'diradi."""
    sp = list(ixt)
    while True:
        t_ = '\n'.join(bosh + sp + oxir)
        t_ = re.sub(r'\n{3,}', '\n\n', t_).strip()
        if len(t_) <= limit or not sp: break
        sp.pop()
    if len(t_) > limit: t_ = t_[:limit - 1].rstrip() + '…'
    return t_


def _narxsiz(s):
    """Begona narxlarni ($499, 499 USD, €…) olib tashlaydi — yetkazuvchi narxi postga tushmasin."""
    s = re.sub(r'(?:US\s*)?[$€£¥]\s?\d[\d,.\s]*', '', str(s or ''))
    return re.sub(r'\b\d[\d,.]*\s?(?:USD|EUR|usd|dollar)\b', '', s)


def post_matn(p, show_price=True, extra='', video_link='', manba='', ig=False, rate=None, bot_user=''):
    """Kanal (ig=False) yoki Instagram (ig=True) uchun tayyor matn (oddiy matn). Tannarx YO'Q."""
    rate = rate or get_exchange_rate()
    brend = _brend(p['sup'])
    bosh = [f"🔥 {p['name']}"]
    if brend or p['cat']: bosh.append("🏷 " + " · ".join(x for x in (brend, p['cat']) if x))
    bosh.append('')
    if show_price and p['price'] > 0: bosh.append(f"💵 Narxi: {_narx_txt(p, rate)}")
    else: bosh.append("💬 Narxi: so'rov bo'yicha")
    bosh.append("✅ Mavjud — Toshkentda" if p['qty'] > 0 else "🕐 Buyurtma asosida")
    ixt = []
    feats = [ln.strip(' •-*\t') for ln in _narxsiz(extra).splitlines() if ln.strip(' •-*\t')]
    if feats:
        ixt += ['', "✨ Afzalliklari:"] + [f"• {ln}" for ln in feats[:8]]
    specs = get_product_specs(p['id'])
    if specs:
        ixt += ['', "⚙️ Xususiyatlari:"] + [f"• {k}: {v}" for k, v in specs[:12]]
    oxir = ['']
    kf = _kafolat_txt(p['warranty'])
    if kf: oxir.append(f"🛡 Kafolat: {kf}")
    if video_link: oxir.append(f"🎬 Video: {video_link}")
    oxir.append(f"📍 {FIRMA.get('manzil') or 'Toshkent'}")
    tel = _mkt_tel()
    if ig:
        oxir.append("📩 Buyurtma: Direct'ga yozing" + (f" yoki 📞 {tel}" if tel else ''))
        if bot_user: oxir.append(f"🤖 Telegram: @{bot_user}")
    else:
        oxir.append((f"📞 {tel} yoki " if tel else "📞 ") + "pastdagi «🛒 Buyurtma berish» tugmasi")
    if manba: oxir.append(f"ℹ️ Manba: {manba} rasmiy sayti")
    oxir += ['', _heshteglar(p, ig)]
    return _yigish(bosh, ixt, oxir, IG_CAPTION_MAX if ig else TG_CAPTION_MAX)


def _tg_html(matn):
    """Birinchi qator qalin, qolgani escape — foydalanuvchi matni HTML sifatida talqin qilinmaydi."""
    bir, _, qol = str(matn).partition('\n')
    return f"<b>{_html.escape(bir)}</b>" + (('\n' + _html.escape(qol)) if qol else '')


def _ig_caption_qoshimcha(caption, p, bot_user=''):
    """Qo'lda yozilgan matn: Instagram uchun tugma o'rniga aloqa + heshteglar qo'shiladi."""
    t_ = re.sub(r".*«🛒 Buyurtma berish».*\n?", '', caption).rstrip()
    tel = _mkt_tel()
    if "Direct" not in t_:
        t_ += "\n\n📩 Buyurtma: Direct'ga yozing" + (f" yoki 📞 {tel}" if tel else '')
        if bot_user: t_ += f"\n🤖 Telegram: @{bot_user}"
    if p and '#' not in t_: t_ += "\n\n" + _heshteglar(p, True)
    return t_[:IG_CAPTION_MAX]


# ── AI bilan matn (ixtiyoriy; ishlamasa — shablon) ──
def _ai_matn(system, user, max_tokens=700):
    try:
        resp = ai.messages.create(model=AI_MODEL, max_tokens=max_tokens, system=system,
                                  messages=[{"role": "user", "content": user}])
        return ''.join(getattr(b, 'text', '') for b in resp.content).strip()
    except Exception as e:
        log.warning("AI matn: %s", type(e).__name__)
        return ''


def _ai_tekshir(matn, p, show_price, limit):
    """AI matni: narx aynan bizniki, boshqa $-summa yo'q, limitga sig'adi."""
    if not matn or len(matn) > limit: return False
    summalar = set(re.findall(r'\$\s?[\d,]+(?:\.\d+)?', matn))
    if show_price and p['price'] > 0:
        return summalar <= {fmt(p['price'])} and fmt(p['price']) in matn
    return not summalar


def ai_post_matn(p, asos, show_price=True, manba_matn=''):
    system = ("Sen ThermoCrafts (Toshkent, lazer/CNC/termopress uskunalari) Telegram kanali uchun o'zbek tilida (lotin) "
              "post yozasan. Qoidalar: faqat berilgan faktlardan foydalan, yangi raqam yoki xususiyat o'ylab topma; "
              "narx qatorini aynan saqla (narx bo'lmasa narx yozma); tannarx, foyda, ulgurji narx haqida hech narsa yozma; "
              "900 belgidan oshmasin; emoji me'yorida; aloqa qatori va heshteglarni saqla. Faqat post matnini qaytar.")
    user = f"Shablon post:\n{asos}"
    if manba_matn:
        user += "\n\nIshlab chiqaruvchi ma'lumoti (inglizcha — kerakli 3-5 ta afzallikni tarjima qilib qo'sh):\n" + _narxsiz(manba_matn)[:2500]
    m = _ai_matn(system, user)
    return m if _ai_tekshir(m, p, show_price, TG_CAPTION_MAX) else ''


def ai_xususiyatlar(matn, n=5):
    """Yetkazuvchi (inglizcha) matnidan 3-5 ta qisqa o'zbekcha afzallik. Ishlamasa — []."""
    if not matn: return []
    m = _ai_matn("Inglizcha texnik matndan uskunaning eng muhim 3-5 ta afzalligini o'zbek tilida (lotin), har birini alohida "
                 "qatorda, qisqa (60 belgigacha) yoz. Narx, chegirma, yetkazib berish, kafolat shartlarini yozma. Faqat ro'yxat.",
                 _narxsiz(matn)[:3000], 400)
    out = [ln.strip(' •-*0123456789.)\t') for ln in m.splitlines()]
    out = [ln[:90] for ln in out if 3 <= len(ln) and '$' not in ln]      # narx qatori bo'lsa — tashlanadi
    return out[:n]


def _matndan_xususiyat(matn, n=5):
    """Shablon (AI yo'q): yetkazuvchi matnidan 'Kalit: qiymat' qatorlari (asl tilda)."""
    out = []
    for ln in _narxsiz(matn).splitlines():
        ln = ln.strip(' •-*\t')
        if 8 <= len(ln) <= 90 and (':' in ln or re.search(r'\d', ln)): out.append(ln)
        if len(out) >= n: break
    return out


# ── Qoralamalar ──
def draft_yarat(source, pid=None, media=None, user_id=0, chat_id=0, extra='', video_link='', manba='', show_price=1):
    conn = db(); c = conn.cursor()
    c.execute("INSERT INTO post_drafts (created,source,product_id,media,show_price,extra,video_link,manba,user_id,chat_id) "
              "VALUES (?,?,?,?,?,?,?,?,?,?)",
              (_mkt_vaqt(), source, pid, json.dumps(media or []), int(show_price), extra or '', video_link or '',
               manba or '', user_id, chat_id))
    did = c.lastrowid; conn.commit(); conn.close()
    if pid: draft_matn_yangila(did)
    return did


def draft_ol(did):
    try: did = int(did)
    except (TypeError, ValueError): return None
    conn = db(); c = conn.cursor()
    c.execute("SELECT id,created,source,product_id,media,caption,custom,show_price,extra,video_link,manba,status,user_id,chat_id,note "
              "FROM post_drafts WHERE id=?", (did,))
    r = c.fetchone(); conn.close()
    if not r: return None
    k = ('id', 'created', 'source', 'pid', 'media', 'caption', 'custom', 'show_price', 'extra', 'video_link', 'manba',
         'status', 'user_id', 'chat_id', 'note')
    d = dict(zip(k, r, strict=True))
    try: d['media'] = json.loads(d['media'] or '[]')
    except ValueError: d['media'] = []
    return d


def draft_yoz(did, **kv):
    ruxsat = {'product_id', 'media', 'caption', 'custom', 'show_price', 'extra', 'video_link', 'manba', 'status', 'note'}
    kv = {k: (json.dumps(v) if k == 'media' else v) for k, v in kv.items() if k in ruxsat}
    if not kv: return
    conn = db()
    conn.execute(f"UPDATE post_drafts SET {', '.join(k + '=?' for k in kv)} WHERE id=?", (*kv.values(), int(did)))
    conn.commit(); conn.close()


def draft_band(did, eski='qoralama', yangi='joylanmoqda'):
    """Atomar holat o'tishi (ikki marta bosishdan himoya)."""
    conn = db(); c = conn.cursor()
    c.execute("UPDATE post_drafts SET status=? WHERE id=? AND status=?", (yangi, int(did), eski))
    n = c.rowcount; conn.commit(); conn.close()
    return n == 1


def draft_matn_yangila(did):
    d = draft_ol(did)
    p = _mkt_p(d['pid']) if d else None
    if not p: return ''
    m = post_matn(p, bool(d['show_price']), d['extra'], d['video_link'], d['manba'])
    draft_yoz(did, caption=m, custom=0)
    return m


def _draft_ig_matn(d, p, bot_user=''):
    if d['custom'] or not p: return _ig_caption_qoshimcha(d['caption'], p, bot_user)
    return post_matn(p, bool(d['show_price']), d['extra'], d['video_link'], d['manba'], ig=True, bot_user=bot_user)


def _media_tavsif(media):
    v = sum(1 for m in media if m.get('type') == 'video'); f = sum(1 for m in media if m.get('type') == 'photo')
    s = ', '.join(x for x in ((f"{v} video" if v else ''), (f"{f} rasm" if f else '')) if x)
    return s or "yo'q (faqat matn)"


def _post_yoz(d, p, platform, status, mid='', link='', caption='', error='', uid=0):
    conn = db()
    conn.execute("INSERT INTO posts (created,product_id,product,platform,status,message_id,link,media_type,caption,draft_id,source,user_id,error) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (_mkt_vaqt(), d.get('pid'), (p or {}).get('name', ''), platform, status, str(mid or ''), link or '',
                  _media_tavsif(d.get('media') or []), caption[:3000], d.get('id'), d.get('source', ''), uid, (error or '')[:300]))
    conn.commit(); conn.close()


def _bot_user(bot):
    try:
        un = getattr(bot, 'username', None)
    except Exception:
        un = None
    return (un or os.getenv('BOT_USERNAME', '')).lstrip('@').strip()


def deep_link(bot, pid):
    un = _bot_user(bot)
    return f"https://t.me/{un}?start=p{int(pid)}" if un else ''


def _kanal_link(ch, mid):
    ch = str(ch or '')
    if ch.startswith('@'): return f"https://t.me/{ch[1:]}/{mid}"
    if ch.startswith('-100'): return f"https://t.me/c/{ch[4:]}/{mid}"
    return ''


def _tg_manba(m, ex):
    """file_id > lokal fayl > URL"""
    if m.get('fid'): return m['fid']
    if m.get('path') and os.path.exists(m['path']): return ex.enter_context(open(m['path'], 'rb'))
    return m.get('url')


async def tg_joyla(bot, d, uid=0):
    """Qoralamani kanalga joylaydi. Qaytaradi {'ok', 'mid', 'link', 'error'}."""
    import contextlib
    ch = get_channel_id()
    p = _mkt_p(d['pid']) if d.get('pid') else None
    if not ch: return {'ok': False, 'error': "CHANNEL_ID sozlanmagan (Railway → Variables)"}
    matn = d['caption'] or (p and post_matn(p)) or ''
    dl = deep_link(bot, d['pid']) if d.get('pid') else ''
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Buyurtma berish", url=dl)]]) if dl else None
    media = [m for m in (d.get('media') or []) if m.get('type') in ('photo', 'video')][:10]

    async def yubor(html_rejim):
        cap = _tg_html(matn) if html_rejim else matn
        pm = 'HTML' if html_rejim else None
        with contextlib.ExitStack() as ex:
            if not media:
                return await bot.send_message(chat_id=ch, text=cap[:TG_TEXT_MAX], parse_mode=pm, reply_markup=kb,
                                              disable_web_page_preview=True)
            if len(media) == 1:
                m = media[0]; src = _tg_manba(m, ex)
                if m['type'] == 'video':
                    return await bot.send_video(chat_id=ch, video=src, caption=cap, parse_mode=pm, reply_markup=kb,
                                                supports_streaming=True)
                return await bot.send_photo(chat_id=ch, photo=src, caption=cap, parse_mode=pm, reply_markup=kb)
            grp = []
            for i, m in enumerate(media):
                src = _tg_manba(m, ex)
                kw = {'caption': cap, 'parse_mode': pm} if i == 0 else {}
                grp.append(InputMediaVideo(src, **kw) if m['type'] == 'video' else InputMediaPhoto(src, **kw))
            res = await bot.send_media_group(chat_id=ch, media=grp)
            if kb:   # albomga tugma qo'yib bo'lmaydi — alohida qisqa xabar
                await bot.send_message(chat_id=ch, text=f"🛒 {p['name'] if p else 'Buyurtma'} — buyurtma berish:", reply_markup=kb)
            return res[0] if isinstance(res, (list, tuple)) and res else res
    try:
        try:
            msg = await yubor(True)
        except BadRequest as e:
            if 'parse' not in str(e).lower() and 'entit' not in str(e).lower(): raise
            msg = await yubor(False)
    except Exception as e:
        err = str(e)[:250]
        log.warning("Kanalga joylash xatosi: %s", err)
        _post_yoz(d, p, 'telegram', 'xato', caption=matn, error=err, uid=uid)
        return {'ok': False, 'error': err}
    mid = getattr(msg, 'message_id', '') or ''
    link = _kanal_link(ch, mid) if mid else ''
    _post_yoz(d, p, 'telegram', 'ok', mid, link, matn, uid=uid)
    return {'ok': True, 'mid': mid, 'link': link}


# ── Vaqtinchalik media URL (Instagram Telegram faylini o'zi yuklab olishi uchun) ──
_MEDIA = {}                       # token -> {'path', 'ctype', 'exp'}
_MEDIA_SRV = {'srv': None}


def _public_base(): return os.getenv('PUBLIC_BASE_URL', '').strip().rstrip('/')


def media_ruxsat(path, ctype, ttl=1800):
    tok = secrets.token_urlsafe(24)
    _MEDIA[tok] = {'path': path, 'ctype': ctype, 'exp': time.time() + ttl}
    return tok


def media_bekor(tok, ochir=True):
    m = _MEDIA.pop(tok, None)
    if m and ochir:
        try: os.remove(m['path'])
        except OSError: pass


def media_javob(method, path, headers=None):
    """(status, headers, body). Faqat GET/HEAD /m/<token>; muddati o'tgan → 404."""
    headers = headers or {}
    for k in [k for k, v in _MEDIA.items() if v['exp'] < time.time()]: media_bekor(k)
    mt = re.fullmatch(r'/m/([A-Za-z0-9_-]{20,64})', path.split('?', 1)[0])
    m = _MEDIA.get(mt.group(1)) if mt else None
    if method not in ('GET', 'HEAD') or not m or not os.path.exists(m['path']):
        return 404, {'Content-Type': 'text/plain'}, b'not found'
    size = os.path.getsize(m['path']); a, b = 0, size - 1; st = 200
    rng = re.fullmatch(r'bytes=(\d*)-(\d*)', (headers.get('range') or '').strip())
    if rng and (rng.group(1) or rng.group(2)):
        if rng.group(1): a = int(rng.group(1)); b = int(rng.group(2)) if rng.group(2) else size - 1
        else: a = max(0, size - int(rng.group(2)))
        b = min(b, size - 1)
        if a > b: return 416, {'Content-Range': f'bytes */{size}'}, b''
        st = 206
    h = {'Content-Type': m['ctype'], 'Content-Length': str(b - a + 1), 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store'}
    if st == 206: h['Content-Range'] = f'bytes {a}-{b}/{size}'
    body = b''
    if method == 'GET':
        with open(m['path'], 'rb') as f:
            f.seek(a); body = f.read(b - a + 1)
    return st, h, body


async def _media_handle(reader, writer):
    try:
        bosh = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 15)
        qatorlar = bosh.decode('latin-1').split('\r\n')
        parts = qatorlar[0].split(' ')
        hdr = {}
        for ln in qatorlar[1:]:
            if ':' in ln:
                k, v = ln.split(':', 1); hdr[k.strip().lower()] = v.strip()
        st, h, body = await asyncio.to_thread(media_javob, parts[0] if parts else '', parts[1] if len(parts) > 1 else '/', hdr)
        sabab = {200: 'OK', 206: 'Partial Content', 404: 'Not Found', 416: 'Range Not Satisfiable'}.get(st, 'OK')
        writer.write((f"HTTP/1.1 {st} {sabab}\r\n" + ''.join(f"{k}: {v}\r\n" for k, v in h.items())
                      + "Connection: close\r\n\r\n").encode('latin-1') + body)
        await writer.drain()
    except Exception:
        pass
    finally:
        try: writer.close()
        except Exception: pass


async def media_server_ishga():
    if _MEDIA_SRV['srv'] is not None: return True
    if not _public_base(): return False
    port = int(os.getenv('PORT', '8080') or 8080)
    _MEDIA_SRV['srv'] = await asyncio.start_server(_media_handle, '0.0.0.0', port)
    log.info("Media URL server: port %s", port)
    return True


# ── Instagram (Meta Graph API) ──
def _ig_cfg():
    uid = os.getenv('IG_USER_ID', '').strip(); tok = os.getenv('IG_ACCESS_TOKEN', '').strip()
    ver = os.getenv('IG_GRAPH_VERSION', '').strip() or 'v26.0'
    if not ver.startswith('v'): ver = 'v' + ver
    host = os.getenv('IG_GRAPH_HOST', '').strip() or ('graph.instagram.com' if tok.startswith('IG') else 'graph.facebook.com')
    return uid, tok, ver, host


def ig_sozlangan():
    uid, tok, _, _ = _ig_cfg()
    return bool(uid and tok)


IG_SOZLASH = ("Instagram sozlanmagan. Railway → Variables: IG_USER_ID, IG_ACCESS_TOKEN (va Telegram'dan yuborilgan "
              "media uchun PUBLIC_BASE_URL). Batafsil: HISOBOT.md → «Instagram sozlash».")


def _ig_tozala(s):
    _, tok, _, _ = _ig_cfg()
    s = str(s)
    if tok: s = s.replace(tok, '***')
    return re.sub(r'access_token=[^&\s"\']+', 'access_token=***', s)[:300]


def _ig_http(method, url, fields):
    """Yagona tarmoq nuqtasi (testda almashtiriladi). Token so'rov tanasida/parametrda; URL logga yozilmaydi."""
    if method == 'POST': r = requests.post(url, data=fields, timeout=30)
    else: r = requests.get(url, params=fields, timeout=30)
    try: j = r.json()
    except ValueError: j = {'error': {'message': f"HTTP {r.status_code}"}}
    return r.status_code, j


def _ig_xato_matn(j, st):
    e = (j or {}).get('error') if isinstance(j, dict) else None
    e = e if isinstance(e, dict) else {}
    code = e.get('code'); sub = e.get('error_subcode'); msg = e.get('error_user_msg') or e.get('message') or f"HTTP {st}"
    if code == 190: s = "Token yaroqsiz yoki muddati tugagan — IG_ACCESS_TOKEN ni yangilang"
    elif code in (10, 200) or (isinstance(code, int) and 200 <= code < 300): s = "Ruxsat yo'q (instagram_content_publish kerak)"
    elif code in (4, 17, 32, 613) or sub == 2207042: s = "Limit: juda ko'p so'rov yoki kunlik joylash chegarasi — keyinroq urinib ko'ring"
    elif code == 9004 or sub in (2207052, 2207003, 2207020): s = "Instagram faylni yuklab ololmadi (URL ochiq emas yoki muddati o'tgan)"
    elif sub in (2207026, 2207004, 2207009): s = "Video formati/hajmi/davomiyligi Instagram talabiga mos emas"
    else: s = "Instagram xatosi"
    return _ig_tozala(f"{s} ({code or st}{'/' + str(sub) if sub else ''}): {msg}")


def _ig_sorov(method, path, **fields):
    uid, tok, ver, host = _ig_cfg()
    fields['access_token'] = tok
    try:
        st, j = _ig_http(method, f"https://{host}/{ver}/{path}", fields)
    except Exception as e:
        raise IgXato(_ig_tozala(f"Tarmoq xatosi: {type(e).__name__}: {e}")) from None
    if st >= 400 or (isinstance(j, dict) and 'error' in j): raise IgXato(_ig_xato_matn(j, st))
    return j if isinstance(j, dict) else {}


def _ig_kut(cid):
    t0 = time.time()
    while True:
        j = _ig_sorov('GET', cid, fields='status_code,status')
        sc = j.get('status_code')
        if sc in ('FINISHED', 'PUBLISHED'): return
        if sc in ('ERROR', 'EXPIRED'):
            raise IgXato(_ig_tozala(f"Instagram media tayyorlay olmadi ({sc}): {j.get('status', '')}"))
        if time.time() - t0 > IG_POLL_TIMEOUT: raise IgXato("Instagram media tayyorlanishi juda uzoq davom etdi (timeout)")
        time.sleep(IG_POLL_SEC)


def ig_joyla_sync(items, caption):
    """items: [{'type': 'photo'|'video', 'url'}]. Konteyner → holat → joylash. Qaytaradi (media_id, permalink)."""
    uid, _, _, _ = _ig_cfg()
    if not items: raise IgXato("Instagram uchun kamida bitta rasm yoki video kerak")
    caption = caption[:IG_CAPTION_MAX]
    if len(items) == 1:
        it = items[0]
        if it['type'] == 'video':
            cid = _ig_sorov('POST', f"{uid}/media", media_type='REELS', video_url=it['url'], caption=caption, share_to_feed='true')['id']
        else:
            cid = _ig_sorov('POST', f"{uid}/media", image_url=it['url'], caption=caption)['id']
        _ig_kut(cid)
    else:
        kids = []
        for it in items[:10]:
            f = {'is_carousel_item': 'true'}
            if it['type'] == 'video': f.update(media_type='VIDEO', video_url=it['url'])
            else: f['image_url'] = it['url']
            kids.append(_ig_sorov('POST', f"{uid}/media", **f)['id'])
        for k in kids: _ig_kut(k)
        cid = _ig_sorov('POST', f"{uid}/media", media_type='CAROUSEL', children=','.join(kids), caption=caption)['id']
        _ig_kut(cid)
    mid = _ig_sorov('POST', f"{uid}/media_publish", creation_id=cid)['id']
    link = ''
    try: link = _ig_sorov('GET', mid, fields='permalink').get('permalink', '')
    except IgXato: pass
    return mid, link


def _ig_url_mos(m):
    u_ = (m.get('url') or '').split('?', 1)[0].lower()
    return u_.endswith(('.mp4', '.mov')) if m.get('type') == 'video' else u_.endswith(('.jpg', '.jpeg'))


def _jpg_qil(path):
    """Instagram faqat JPEG rasm qabul qiladi."""
    with open(path, 'rb') as f:
        if f.read(3) == b'\xff\xd8\xff': return path
    try:
        from PIL import Image
    except ImportError:
        raise IgXato("Rasm JPEG emas va Pillow o'rnatilmagan") from None
    out = path + '.jpg'
    with Image.open(path) as im: im.convert('RGB').save(out, 'JPEG', quality=90)
    return out


def _temp_dir():
    d = os.path.join(tempfile.gettempdir(), 'tc_media'); os.makedirs(d, exist_ok=True)
    return d


async def _tg_yukla(bot, fid, tur):
    f = await bot.get_file(fid)
    if (getattr(f, 'file_size', 0) or 0) > TG_DL_MAX:
        raise IgXato("Telegram bot 20 MB dan katta faylni yuklab ololmaydi — videoni kichikroq yuboring")
    path = os.path.join(_temp_dir(), secrets.token_hex(8) + ('.mp4' if tur == 'video' else '.jpg'))
    await f.download_to_drive(path)
    return path


async def _ig_tayyorla(bot, media):
    items, toks = [], []
    try:
        for m in media[:10]:
            if m.get('url') and _ig_url_mos(m):
                items.append({'type': m['type'], 'url': m['url']}); continue
            if not _public_base():
                raise IgXato("Bu media uchun PUBLIC_BASE_URL kerak (Instagram faylni ochiq URL'dan oladi). HISOBOT.md → Instagram sozlash")
            path = m.get('path') if m.get('path') and os.path.exists(m['path']) else None
            if not path and m.get('fid'): path = await _tg_yukla(bot, m['fid'], m['type'])
            if not path and m.get('url'): path = await asyncio.to_thread(web_yukla, m['url'], WEB_MEDIA_MAX)
            if not path: continue
            if m['type'] == 'photo': path = await asyncio.to_thread(_jpg_qil, path)
            tok = media_ruxsat(path, 'video/mp4' if m['type'] == 'video' else 'image/jpeg'); toks.append(tok)
            items.append({'type': m['type'], 'url': f"{_public_base()}/m/{tok}"})
        if toks and not await media_server_ishga():
            raise IgXato("Media server ishga tushmadi (PUBLIC_BASE_URL/PORT)")
    except Exception:
        for t_ in toks: media_bekor(t_)
        raise
    return items, toks


_IG_ISHDA = set()
_FON = set()


async def ig_post(bot, did, uid=0):
    d = draft_ol(did)
    if not d: return {'ok': False, 'error': "Qoralama topilmadi"}
    p = _mkt_p(d['pid']) if d.get('pid') else None
    if not ig_sozlangan(): return {'ok': False, 'error': IG_SOZLASH}
    cap = _draft_ig_matn(d, p, _bot_user(bot))
    toks = []
    try:
        items, toks = await _ig_tayyorla(bot, d.get('media') or [])
        mid, link = await asyncio.to_thread(ig_joyla_sync, items, cap)
    except IgXato as e:
        _post_yoz(d, p, 'instagram', 'xato', caption=cap, error=str(e), uid=uid)
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        err = _ig_tozala(f"{type(e).__name__}: {e}")
        log.warning("Instagram: %s", err)
        _post_yoz(d, p, 'instagram', 'xato', caption=cap, error=err, uid=uid)
        return {'ok': False, 'error': err}
    finally:
        for t_ in toks: media_bekor(t_)
    _post_yoz(d, p, 'instagram', 'ok', mid, link, cap, uid=uid)
    return {'ok': True, 'mid': mid, 'link': link}


async def _ig_fon(bot, chat_id, did, uid=0, tg_ok=False):
    try:
        r = await ig_post(bot, did, uid)
        if r['ok']:
            if not tg_ok: draft_yoz(did, status='joylandi')
            txt = "📸 Instagram'ga joylandi ✅" + (f"\n{r['link']}" if r.get('link') else '')
            kb = None
        else:
            if not tg_ok: draft_yoz(did, status='qoralama')
            txt = f"📸 Instagram: joylanmadi ❌\n{r['error']}"
            kb = InlineKeyboardMarkup([[_btn("🔁 Instagram'ga qayta urinish", f"mkt:pub:{did}:ig")]])
        if chat_id: await bot.send_message(chat_id=chat_id, text=txt, reply_markup=kb)
    finally:
        _IG_ISHDA.discard(int(did))


def _fon(coro):
    if not IG_FON: return coro
    t_ = asyncio.create_task(coro); _FON.add(t_); t_.add_done_callback(_FON.discard)
    return None


async def mkt_joyla(bot, did, plat, chat_id=0, uid=0):
    """plat: tg | ig | both. Qaytaradi (ok, xabar)."""
    d = draft_ol(did)
    if not d: return False, "Qoralama topilmadi"
    ig_qayta = (plat == 'ig' and d['status'] == 'joylandi')
    if plat in ('ig', 'both'):
        if not ig_sozlangan(): return False, IG_SOZLASH
        if int(did) in _IG_ISHDA: return False, "⏳ Instagram'ga yuborilmoqda…"
    if plat in ('tg', 'both') and not get_channel_id(): return False, "CHANNEL_ID sozlanmagan (Railway → Variables)"
    if ig_qayta:
        conn = db(); bor = conn.execute("SELECT 1 FROM posts WHERE draft_id=? AND platform='instagram' AND status='ok'", (int(did),)).fetchone(); conn.close()
        if bor: return False, "Bu post Instagram'ga allaqachon joylangan"
    elif not draft_band(did):
        return False, "Bu post allaqachon joylangan yoki bekor qilingan"
    natija = []; tg_ok = False
    if plat in ('tg', 'both'):
        r = await tg_joyla(bot, d, uid)
        tg_ok = r['ok']
        natija.append(("📢 Kanalga joylandi ✅" + (f"\n{r['link']}" if r.get('link') else '')) if r['ok']
                      else f"📢 Kanal: joylanmadi ❌\n{r['error']}")
    if plat in ('ig', 'both'):
        _IG_ISHDA.add(int(did))
        if tg_ok: draft_yoz(did, status='joylandi')
        natija.append("📸 Instagram'ga yuborilmoqda… (1–5 daqiqa, natijasini yozaman)")
        c_ = _fon(_ig_fon(bot, chat_id, did, uid, tg_ok or ig_qayta))
        if c_ is not None: await c_
    elif not ig_qayta:
        draft_yoz(did, status='joylandi' if tg_ok else 'qoralama')
    return (tg_ok or plat == 'ig'), '\n'.join(natija)


# ── Oldindan ko'rish ──
def mkt_preview(did, izoh=''):
    d = draft_ol(did)
    p = _mkt_p(d['pid']) if d and d.get('pid') else None
    if not d or not p: return "Qoralama topilmadi", [_x_btn('mkt')]
    cap = d['caption'] or ''
    head = [f"👁 POST KO'RINISHI #{d['id']}" + (" · 🤖 kunlik kontent" if d['source'] == 'kontent' else ''),
            f"📎 Media: {_media_tavsif(d['media'])}"]
    if d['manba'] and d['source'] == 'kontent': head.append(f"🌐 Rasmlar: {d['manba']} rasmiy sayti")
    if d['custom'] == 1: head.append("✏️ Matn qo'lda o'zgartirilgan")
    elif d['custom'] == 2: head.append("✨ Matn AI bilan yaxshilangan")
    if izoh: head.append(izoh)
    m = '\n'.join(head) + "\n━━━━━━━━━━━━\n" + cap + f"\n━━━━━━━━━━━━\n({len(cap)}/{TG_CAPTION_MAX} belgi)"
    did = d['id']
    rows = [[_btn("✅ Telegram", f"mkt:pub:{did}:tg"), _btn("📸 Instagram", f"mkt:pub:{did}:ig"), _btn("🔁 Ikkalasi", f"mkt:pub:{did}:both")],
            [_btn("✏️ Matnni o'zgartirish", f"mkt:ed:{did}"),
             _btn("💲 Narxni ko'rsatma" if d['show_price'] else "💲 Narxni ko'rsat", f"mkt:pr:{did}")],
            [_btn("✨ AI bilan yaxshilash", f"mkt:ai:{did}")]]
    if d['source'] == 'kontent': rows.append([_btn("⏭ Boshqa tovar", f"mkt:skip:{did}"), _btn("❌ Bugun yo'q", f"mkt:no:{did}")])
    else: rows.append([_btn("❌ Bekor", f"mkt:cx:{did}")])
    return m[:TG_TEXT_MAX], rows


# ── Marketing menyusi (egasi/admin) ──
def _mkt_menu():
    auto = soz('auto_post') == '1'
    kun = soz('kontent_kunlik') == '1'
    conn = db()
    n_lead = conn.execute("SELECT COUNT(*) FROM leads WHERE status='yangi'").fetchone()[0]
    n_post = conn.execute("SELECT COUNT(*) FROM posts WHERE status='ok' AND created>=?",
                          ((_local_now() - timedelta(days=7)).strftime('%Y-%m-%d'),)).fetchone()[0]
    conn.close()
    m = ("📢 MARKETING\n\n"
         f"📢 Kanal: {get_channel_id() or '— (CHANNEL_ID yo‘q)'}\n"
         f"📸 Instagram: {'ulangan' if ig_sozlangan() else 'sozlanmagan'}\n"
         f"🗓 Kunlik kontent: {'yoqilgan, ' + soz('kontent_vaqt') if kun else 'o‘chirilgan'}"
         f" · {'🤖 avto-joylash (' + PLATFORMA_NOMI.get(soz('auto_platforma'), 'Telegram') + ')' if auto else '👁 oldindan ko‘rsatadi'}\n"
         f"📈 7 kunda joylangan: {n_post} · 📩 yangi so'rov: {n_lead}\n\n"
         "Yangi post: shu yerga video yoki rasm(lar) yuboring.")
    rows = [[_btn("➕ Yangi post", "mkt:new"), _btn("📋 Oxirgi postlar", "mkt:posts")],
            [_btn("📅 Kontent kalendari", "mkt:cal"), _btn("▶️ Hozir post", "mkt:now")],
            [_btn("🔗 Tovar ↔ sayt", "mkt:map:0"), _btn(f"📩 So'rovlar ({n_lead})", "mkt:leads")],
            [_btn(f"🤖 Avto: {'ON' if auto else 'OFF'}", "mkt:auto"), _btn("⚙️ Kontent sozlamalari", "mkt:ks")],
            [_btn("🌐 Ochiq katalog", "mkt:pubs")], _x_btn('mkt')]
    return m, rows


def _mkt_postlar():
    conn = db()
    rr = conn.execute("SELECT created,product,platform,status,link,error,source FROM posts ORDER BY id DESC LIMIT 12").fetchall(); conn.close()
    if not rr: return "📋 Hali post yo'q.", [[_btn("⬅️ Orqaga", "mkt:menu")]]
    ic = {'telegram': '📢', 'instagram': '📸'}
    out = ["📋 OXIRGI POSTLAR\n"]
    for cr, pr, pl, st, ln, er, so in rr:
        out.append(f"{'✅' if st == 'ok' else '❌'} {cr} {ic.get(pl, '')} {pr or '—'}" + (" 🤖" if so == 'kontent' else '')
                   + (f"\n   {ln}" if ln else '') + (f"\n   ⚠️ {er[:80]}" if st != 'ok' and er else ''))
    return '\n'.join(out), [[_btn("⬅️ Orqaga", "mkt:menu")]]


def _mkt_tovar_cats():
    prods = get_products()
    cats = _omb_cats(prods)
    rows = [[_btn(f"{c_} ({sum(1 for p in prods if (p['cat'] or 'Boshqa') == c_)})", f"mkt:cat:{i}:0")] for i, c_ in enumerate(cats)]
    rows.append([_btn("🔍 Qidirish", "mkt:s"), _btn("❌ Bekor", "mkt:x")])
    return rows


def _mkt_tovarlar(ci, page, prefix='mkt:pk'):
    prods = get_products(); cats = _omb_cats(prods)
    if not (0 <= ci < len(cats)): return [[_btn("⬅️ Orqaga", "mkt:cats")]]
    lst = [p for p in prods if (p['cat'] or 'Boshqa') == cats[ci]]
    sl = lst[page * 8:(page + 1) * 8]
    rows = [[_btn(f"{'✅' if p['qty'] > 0 else '🕐'} {p['name']}", f"{prefix}:{p['id']}")] for p in sl]
    nav = []
    if page > 0: nav.append(_btn("◀️", f"mkt:cat:{ci}:{page - 1}"))
    if (page + 1) * 8 < len(lst): nav.append(_btn("▶️", f"mkt:cat:{ci}:{page + 1}"))
    if nav: rows.append(nav)
    rows.append([_btn("⬅️ Kategoriyalar", "mkt:cats"), _btn("❌ Bekor", "mkt:x")])
    return rows


def _pub_sozlama():
    m = ("🌐 OCHIQ KATALOG (ro'yxatda yo'q mijozlar uchun)\n\n"
         "Mijoz botga tovar nomini yozsa yoki kanaldagi «🛒 Buyurtma berish» tugmasini bossa — tovar kartasi chiqadi.\n"
         "Tannarx hech qachon ko'rsatilmaydi.\n\n"
         f"📦 Aniq qoldiq soni: {'ko‘rsatiladi' if soz('ochiq_qoldiq') == '1' else 'yo‘q (faqat Mavjud/Buyurtma asosida)'}\n"
         f"📩 So'rovlar sotuvchilarga ham: {'ha' if soz('lead_sotuvchi') == '1' else 'yo‘q (egasi va admin)'}\n"
         f"📞 Aloqa telefoni: {_mkt_tel() or '— (kiritilmagan)'}")
    rows = [[_btn("📦 Qoldiq sonini almashtirish", "mkt:oq")], [_btn("📩 Sotuvchilarga: almashtirish", "mkt:ls")],
            [_btn("📞 Telefonni kiritish", "mkt:tel")], [_btn("👁 Tovarlar ko'rinishi / narxi", "mkt:pv:0")],
            [_btn("⬅️ Orqaga", "mkt:menu")]]
    return m, rows


def _pub_tovar_royxat(page):
    conn = db()
    rr = conn.execute("SELECT id,name,COALESCE(public_show,1),COALESCE(public_price,1) FROM products WHERE active=1 ORDER BY cat,name").fetchall()
    conn.close()
    sl = rr[page * 8:(page + 1) * 8]
    m = ("👁 — mijozlarga ko'rinadi / 🙈 — yashirin\n💲 — narx ko'rsatiladi / 🚫 — «narxi so'rov bo'yicha»\n"
         "Tugmani bosib almashtiring.")
    rows = [[_btn(f"{'👁' if sh else '🙈'} {n[:28]}", f"mkt:pvs:{i}:{page}"), _btn('💲' if pr else '🚫', f"mkt:pvp:{i}:{page}")]
            for i, n, sh, pr in sl]
    nav = []
    if page > 0: nav.append(_btn("◀️", f"mkt:pv:{page - 1}"))
    if (page + 1) * 8 < len(rr): nav.append(_btn("▶️", f"mkt:pv:{page + 1}"))
    if nav: rows.append(nav)
    rows.append([_btn("⬅️ Orqaga", "mkt:pubs")])
    return m, rows


def _lead_matn(ld):
    i, cr, chat, un, nm, ph, pid, pr, qt, st = ld[:10]
    p = _mkt_p(pid)
    narx = (f"\n💵 {fmt(p['price'])} × {qt} = {fmt(p['price'] * qt)}" if p and p['price'] else '')
    holat = {'yangi': '🆕 yangi', 'boglanildi': '✅ bog‘lanildi', 'savatda': '🛒 savatga o‘tkazildi', 'bekor': '❌ bekor'}.get(st, st)
    return (f"🛒 BUYURTMA SO'ROVI #L{i}\n🕒 {cr}\n👤 {nm or '—'}" + (f" (@{un})" if un else '')
            + f"\n📞 {ph or '—'}\n📦 {pr} × {qt}{narx}\nHolat: {holat}")


def _lead_kb(lid):
    return [[_btn("🛒 POS savatga", f"lead:pos:{lid}")],
            [_btn("✅ Bog'lanildi", f"lead:ok:{lid}"), _btn("❌ Bekor", f"lead:x:{lid}")]]


def _lead_ol(lid):
    conn = db()
    r = conn.execute("SELECT id,created,chat_id,username,name,phone,product_id,product,qty,status,handled_by FROM leads WHERE id=?", (int(lid),)).fetchone()
    conn.close()
    return r


def _mkt_leads():
    conn = db()
    rr = conn.execute("SELECT id,created,name,product,qty,status FROM leads ORDER BY id DESC LIMIT 10").fetchall(); conn.close()
    if not rr: return "📩 Hali so'rov yo'q.", [[_btn("⬅️ Orqaga", "mkt:menu")]]
    ic = {'yangi': '🆕', 'boglanildi': '✅', 'savatda': '🛒', 'bekor': '❌'}
    rows = [[_btn(f"{ic.get(st, '•')} #L{i} {nm[:12]} — {pr[:18]} ×{qt}", f"lead:c:{i}")] for i, cr, nm, pr, qt, st in rr]
    rows.append([_btn("⬅️ Orqaga", "mkt:menu")])
    return "📩 SO'ROVLAR (oxirgi 10)", rows


async def cmd_marketing(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'marketing'): return
    _ui_yangi(ctx, 'mkt')
    m, r = _mkt_menu()
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))


async def mkt_media(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Egasi/admin video yoki rasm yubordi → qoralama → tovar tanlash → oldindan ko'rish."""
    m = u.message
    if getattr(m, 'video', None):
        item = {'type': 'video', 'fid': m.video.file_id, 'size': getattr(m.video, 'file_size', 0) or 0}
    elif getattr(m, 'photo', None):
        item = {'type': 'photo', 'fid': m.photo[-1].file_id}
    else:
        return
    st = _ui_ol(ctx, 'mkt')
    mg = getattr(m, 'media_group_id', None)
    if st and st.get('draft') and mg and st.get('mg') == mg:          # albomning keyingi bo'laklari
        d = draft_ol(st['draft'])
        if d and d['status'] == 'qoralama' and len(d['media']) < 10:
            draft_yoz(d['id'], media=d['media'] + [item])
            return
    x = xodim(u) or {}
    cap = (m.caption or '').strip()
    did = draft_yarat('tg', media=[item], user_id=x.get('id', 0), chat_id=u.effective_chat.id)
    st = _ui_yangi(ctx, 'mkt', draft=did, mg=mg)
    p = None
    qidir = re.sub(r"(?i)\b(kanal|kanalga|post|e'?lon)\b", ' ', cap).strip()
    if qidir:
        p, _v = match_product(qidir, prefer_stock=True)
    if p:
        draft_yoz(did, product_id=p['id']); draft_matn_yangila(did)
        txt, rows = mkt_preview(did, "📦 Tovar izohdan aniqlandi")
    else:
        txt = (f"📎 Qabul qilindi ({'video' if item['type'] == 'video' else 'rasm'}"
               + (", albomning qolgan rasmlari ham qo'shiladi" if mg else '') + ").\n📦 Qaysi tovar uchun post?")
        rows = _mkt_tovar_cats()
    await m.reply_text(txt, reply_markup=InlineKeyboardMarkup(rows))


async def mkt_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not can(u, 'marketing'):
        await q.answer("Ruxsat yo'q", show_alert=True); return
    p_ = q.data.split(':')
    w = p_[1] if len(p_) > 1 else 'menu'
    st = _ui_ol(ctx, 'mkt') or _ui_yangi(ctx, 'mkt')
    uid = (xodim(u) or {}).get('id', 0)
    chat_id = u.effective_chat.id if getattr(u, 'effective_chat', None) else uid

    def iarg(i, dflt=0):
        try: return int(p_[i])
        except (IndexError, ValueError): return dflt

    if w == 'x':
        st['wait'] = None
        await q.answer(); await _pos_chiqar(q, "Yopildi.", None); return
    if w == 'menu':
        st['wait'] = None; await q.answer(); await _pos_chiqar(q, *_mkt_menu()); return
    if w == 'new':
        st['wait'] = 'media'; st['draft'] = None; await q.answer()
        await _pos_chiqar(q, "📎 Video yoki rasm(lar)ni yuboring (albom ham bo'ladi). Izohga tovar nomini yozsangiz — o'zi topadi.",
                          [[_btn("⬅️ Orqaga", "mkt:menu")]]); return
    if w == 'posts':
        await q.answer(); await _pos_chiqar(q, *_mkt_postlar()); return
    if w == 'leads':
        await q.answer(); await _pos_chiqar(q, *_mkt_leads()); return
    if w == 'cats':
        await q.answer(); await _pos_chiqar(q, "📦 Qaysi tovar uchun post?", _mkt_tovar_cats()); return
    if w == 'cat':
        await q.answer(); await _pos_chiqar(q, "📦 Tovarni tanlang:", _mkt_tovarlar(iarg(2), iarg(3))); return
    if w == 's':
        st['wait'] = 's'; await q.answer()
        await _pos_chiqar(q, "🔍 Tovar nomini yozing:", [[_btn("⬅️ Orqaga", "mkt:cats")]]); return
    if w == 'pk':
        did = st.get('draft'); d = draft_ol(did) if did else None
        p = _mkt_p(iarg(2))
        if not d or d['status'] != 'qoralama' or not p:
            await q.answer("Qoralama topilmadi — media'ni qayta yuboring", show_alert=True); return
        draft_yoz(did, product_id=p['id']); draft_matn_yangila(did); st['wait'] = None
        await q.answer(); await _pos_chiqar(q, *mkt_preview(did)); return
    if w == 'pub':
        did, plat = iarg(2), (p_[3] if len(p_) > 3 else 'tg')
        if plat not in ('tg', 'ig', 'both'): plat = 'tg'
        d = draft_ol(did)
        if not d:
            await q.answer("Qoralama topilmadi", show_alert=True); return
        if d['status'] != 'qoralama' and not (plat == 'ig' and d['status'] == 'joylandi'):
            await q.answer("Bu post allaqachon joylangan yoki bekor qilingan", show_alert=True); return
        if plat in ('ig', 'both') and not ig_sozlangan():
            await q.answer(IG_SOZLASH[:195], show_alert=True); return
        await q.answer("⏳ Joylanmoqda…")
        ok, msg = await mkt_joyla(ctx.bot, did, plat, chat_id, uid)
        if not ok and msg.startswith(("Bu post", "⏳", "CHANNEL_ID", "Qoralama")):
            await q.message.reply_text(msg); return
        if d['source'] == 'kontent' and ok: soz_yoz('kontent_oxirgi', today())
        rows = None if ok else mkt_preview(did)[1]
        await _pos_chiqar(q, f"{msg}\n\n📦 {(_mkt_p(d['pid']) or {}).get('name', '')}", rows); return
    if w in ('ed', 'pr', 'ai', 'cx', 'skip', 'no'):
        did = iarg(2); d = draft_ol(did)
        if not d or d['status'] != 'qoralama':
            await q.answer("Bu post allaqachon joylangan yoki bekor qilingan", show_alert=True); return
        p = _mkt_p(d['pid'])
        if w == 'ed':
            st['wait'] = f'ed:{did}'; await q.answer()
            await q.message.reply_text("✏️ Yangi matnni yuboring (to'liq post matni). Joriy matn:")
            await q.message.reply_text(d['caption'][:TG_TEXT_MAX] or '—'); return
        if w == 'pr':
            draft_yoz(did, show_price=0 if d['show_price'] else 1)
            draft_matn_yangila(did); await q.answer("💲 Narx " + ("yashirildi" if d['show_price'] else "ko'rsatiladi"))
            await _pos_chiqar(q, *mkt_preview(did, "↩️ Matn shablondan qayta tuzildi" if d['custom'] else '')); return
        if w == 'ai':
            if not p:
                await q.answer("Tovar topilmadi", show_alert=True); return
            await q.answer("✨ AI yozmoqda…")
            sm = ''
            if d['source'] == 'kontent':
                kc = await asyncio.to_thread(kontent_kesh, d['pid'])
                sm = (kc or {}).get('text', '')
            m = await asyncio.to_thread(ai_post_matn, p, d['caption'], bool(d['show_price']), sm)
            if not m:
                await q.message.reply_text("⚠️ AI ishlamadi yoki matn tekshiruvdan o'tmadi — shablon matn qoldi."); return
            draft_yoz(did, caption=m, custom=2)
            await _pos_chiqar(q, *mkt_preview(did)); return
        if w == 'cx':
            draft_band(did, 'qoralama', 'bekor'); kontent_tozala(d)
            await q.answer(); await _pos_chiqar(q, "❌ Post bekor qilindi.", None); return
        if w == 'no':
            draft_band(did, 'qoralama', 'bekor'); kontent_tozala(d); soz_yoz('kontent_oxirgi', today())
            await q.answer(); await _pos_chiqar(q, "❌ Bugun kontent joylanmaydi. Ertaga yana taklif qilaman.", None); return
        if w == 'skip':
            if not draft_band(did, 'qoralama', 'bekor'):
                await q.answer("Allaqachon o'tkazilgan", show_alert=True); return
            kontent_tozala(d); kontent_otkaz(d['pid'])
            await q.answer("⏭ Keyingi tovar tayyorlanmoqda…")
            await _pos_chiqar(q, f"⏭ {p['name'] if p else ''} o'tkazib yuborildi. Keyingisi tayyorlanmoqda…", None)
            await kontent_kunlik(ctx.bot, majburiy=True, chat_id=chat_id)
            return
    # ── Kontent (D) ──
    if w in KONTENT_TUGMALAR:
        return await kontent_callback(u, ctx, q, st, p_, w)
    # ── Ochiq katalog sozlamalari ──
    if w == 'pubs':
        await q.answer(); await _pos_chiqar(q, *_pub_sozlama()); return
    if w in ('oq', 'ls'):
        k = 'ochiq_qoldiq' if w == 'oq' else 'lead_sotuvchi'
        soz_yoz(k, '0' if soz(k) == '1' else '1'); await q.answer("✅")
        await _pos_chiqar(q, *_pub_sozlama()); return
    if w == 'tel':
        st['wait'] = 'tel'; await q.answer()
        await _pos_chiqar(q, "📞 Aloqa telefonini yozing (masalan +998 90 123 45 67). O'chirish: -", [[_btn("⬅️ Orqaga", "mkt:pubs")]]); return
    if w == 'pv':
        await q.answer(); await _pos_chiqar(q, *_pub_tovar_royxat(iarg(2))); return
    if w in ('pvs', 'pvp'):
        col = 'public_show' if w == 'pvs' else 'public_price'
        conn = db(); conn.execute(f"UPDATE products SET {col}=1-COALESCE({col},1) WHERE id=?", (iarg(2),)); conn.commit(); conn.close()
        await q.answer("✅"); await _pos_chiqar(q, *_pub_tovar_royxat(iarg(3))); return
    await q.answer()


async def mkt_matn(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Marketing matn kiritish. True — matn shu yerda ishlandi."""
    st = _ui_ol(ctx, 'mkt')
    if not st or not st.get('wait') or not can(u, 'marketing'): return False
    w = st['wait']; t_ = (u.message.text or '').strip()
    if w == 'media': return False                     # media kutilmoqda — matn odatdagidek ishlansin
    if t_ in MENU_MAP:
        st['wait'] = None; return False
    if w == 's':
        prods = get_products(); p, v = match_product(t_, prods=prods)
        lst = [p] if p else [x for x in prods if x['name'] in {c_['name'] for c_ in v}]
        if not lst:
            await u.message.reply_text("Topilmadi. Boshqacha yozing yoki kategoriyadan tanlang.",
                                       reply_markup=InlineKeyboardMarkup(_mkt_tovar_cats())); return True
        st['wait'] = None
        await u.message.reply_text("📦 Tanlang:", reply_markup=InlineKeyboardMarkup(
            [[_btn(x['name'], f"mkt:pk:{x['id']}")] for x in lst[:8]] + [[_btn("❌ Bekor", "mkt:x")]])); return True
    if w.startswith('ed:'):
        did = int(w[3:]); d = draft_ol(did)
        st['wait'] = None
        if not d or d['status'] != 'qoralama':
            await u.message.reply_text("Qoralama topilmadi yoki joylangan."); return True
        if len(t_) > TG_CAPTION_MAX and d['media']:
            st['wait'] = w
            await u.message.reply_text(f"Juda uzun: {len(t_)} belgi. Media bilan post {TG_CAPTION_MAX} belgigacha bo'ladi. Qisqartirib yuboring."); return True
        draft_yoz(did, caption=t_, custom=1)
        m, r = mkt_preview(did)
        await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r)); return True
    if w == 'tel':
        st['wait'] = None
        if t_ == '-': soz_yoz('aloqa_tel', '')
        elif len(re.sub(r'\D', '', t_)) < 7:
            st['wait'] = 'tel'; await u.message.reply_text("Telefon noto'g'ri. Masalan: +998 90 123 45 67"); return True
        else: soz_yoz('aloqa_tel', t_[:40])
        m, r = _pub_sozlama(); await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r)); return True
    if w.startswith(('vaqt', 'url:')):
        return await kontent_matn(u, ctx, st, w, t_)
    return False


# ── 🌐 Ochiq tovar kartasi va so'rov (ro'yxatda yo'q foydalanuvchilar) ──
_RL = {}


def _rl_ok(uid, tur, limit, oyna):
    now = time.time(); k = (uid, tur)
    lst = [t_ for t_ in _RL.get(k, []) if now - t_ < oyna]
    if len(lst) >= limit:
        _RL[k] = lst; return False
    lst.append(now); _RL[k] = lst
    if len(_RL) > 5000:
        for kk in [kk for kk, v in _RL.items() if not v or now - v[-1] > 3600]: _RL.pop(kk, None)
    return True


def _pub_tovarlar():
    conn = db()
    ids = {r[0] for r in conn.execute("SELECT id FROM products WHERE active=1 AND COALESCE(public_show,1)=1").fetchall()}
    conn.close()
    return [p for p in get_products() if p['id'] in ids]


def pub_karta_matn(p, rate=None):
    """Ochiq karta: narx (ruxsat bo'lsa), xususiyatlar, kafolat, mavjudlik. Tannarx YO'Q; dona soni — sozlama bo'yicha."""
    rate = rate or get_exchange_rate()
    out = [f"🔥 {p['name']}"]
    b = _brend(p['sup'])
    if b or p['cat']: out.append("🏷 " + " · ".join(x for x in (b, p['cat']) if x))
    out.append('')
    out.append(f"💵 Narxi: {_narx_txt(p, rate)}" if (p['public_price'] and p['price'] > 0) else "💬 Narxi: so'rov bo'yicha")
    if p['qty'] > 0:
        out.append(f"✅ Mavjud: {p['qty']} dona" if soz('ochiq_qoldiq') == '1' else "✅ Mavjud — Toshkentda")
    else:
        out.append("🕐 Buyurtma asosida")
    specs = get_product_specs(p['id'])
    if specs: out += ['', "⚙️ Xususiyatlari:"] + [f"• {k}: {v}" for k, v in specs[:12]]
    kf = _kafolat_txt(p['warranty'])
    if kf: out += ['', f"🛡 Kafolat: {kf}"]
    out.append(f"📍 {FIRMA.get('manzil') or 'Toshkent'}")
    return '\n'.join(out)


def _pub_kb(pid):
    return InlineKeyboardMarkup([[_btn("📞 Bog'lanish", f"pub:tel:{pid}"), _btn("🛒 Buyurtma qoldirish", f"pub:o:{pid}")],
                                 [_btn("📚 Katalog", "pub:k")]])


async def pub_karta_yubor(bot, chat_id, pid):
    p = _mkt_p(pid)
    if not p or not p['active'] or not p['public_show']:
        await bot.send_message(chat_id=chat_id, text="Bu tovar hozir ko'rsatilmaydi. 📚 Katalog:",
                               reply_markup=InlineKeyboardMarkup([[_btn("📚 Katalog", "pub:k")]])); return False
    matn = pub_karta_matn(p); kb = _pub_kb(p['id'])
    photos = get_product_photos(p['id'])[:5]
    try:
        if len(photos) > 1:
            await bot.send_media_group(chat_id=chat_id, media=[InputMediaPhoto(f) for f in photos])
        elif photos and len(matn) <= TG_CAPTION_MAX:
            await bot.send_photo(chat_id=chat_id, photo=photos[0], caption=matn, reply_markup=kb); return True
        elif photos:
            await bot.send_photo(chat_id=chat_id, photo=photos[0])
    except Exception as e:
        log.warning("ochiq karta rasm: %s", str(e)[:120])
    await bot.send_message(chat_id=chat_id, text=matn[:TG_TEXT_MAX], reply_markup=kb)
    return True


def _pub_katalog(ci=None, page=0):
    prods = _pub_tovarlar(); cats = _omb_cats(prods)
    if ci is None or not (0 <= ci < len(cats)):
        if not prods: return "Katalog hozircha bo'sh.", []
        return ("📚 KATALOG — bo'limni tanlang:",
                [[_btn(f"{c_} ({sum(1 for p in prods if (p['cat'] or 'Boshqa') == c_)})", f"pub:c:{i}:0")] for i, c_ in enumerate(cats)])
    lst = [p for p in prods if (p['cat'] or 'Boshqa') == cats[ci]]
    sl = lst[page * 8:(page + 1) * 8]
    rows = [[_btn(f"{'✅' if p['qty'] > 0 else '🕐'} {p['name']}", f"pub:p:{p['id']}")] for p in sl]
    nav = []
    if page > 0: nav.append(_btn("◀️", f"pub:c:{ci}:{page - 1}"))
    if (page + 1) * 8 < len(lst): nav.append(_btn("▶️", f"pub:c:{ci}:{page + 1}"))
    if nav: rows.append(nav)
    rows.append([_btn("⬅️ Bo'limlar", "pub:k")])
    return f"📚 {cats[ci]}:", rows


async def pub_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; us = u.effective_user
    p_ = q.data.split(':'); w = p_[1] if len(p_) > 1 else ''
    if not _rl_ok(us.id, 'cb', 40, 60):
        await q.answer("Juda tez — biroz kuting", show_alert=True); return

    def iarg(i, dflt=0):
        try: return int(p_[i])
        except (IndexError, ValueError): return dflt
    chat_id = u.effective_chat.id
    if w == 'k':
        await q.answer(); m, r = _pub_katalog(); await _pos_chiqar(q, m, r); return
    if w == 'c':
        await q.answer(); m, r = _pub_katalog(iarg(2), iarg(3)); await _pos_chiqar(q, m, r); return
    if w == 'p':
        await q.answer(); await pub_karta_yubor(ctx.bot, chat_id, iarg(2)); return
    if w == 'tel':
        tel = _mkt_tel()
        await q.answer()
        await q.message.reply_text((f"📞 Qo'ng'iroq qiling: {tel}\n" if tel else '')
                                   + "✍️ Yoki shu yerga savolingizni yozing — javob beramiz.\n"
                                   + "🛒 Tezroq: «Buyurtma qoldirish» — o'zimiz qo'ng'iroq qilamiz.")
        return
    if w == 'o':
        p = _mkt_p(iarg(2))
        if not p or not p['active'] or not p['public_show']:
            await q.answer("Tovar topilmadi", show_alert=True); return
        await q.answer()
        ctx.user_data['pub'] = {'ts': time.time(), 'pid': p['id'], 'wait': None}
        await q.message.reply_text(f"🛒 {p['name']}\nNechta kerak?", reply_markup=InlineKeyboardMarkup(
            [[_btn(str(n), f"pub:q:{p['id']}:{n}") for n in (1, 2, 3, 5)], [_btn("❌ Bekor", "pub:x")]]))
        return
    if w == 'q':
        st = ctx.user_data.get('pub') or {}
        if st.get('pid') != iarg(2):
            await q.answer("Qaytadan «Buyurtma qoldirish» ni bosing", show_alert=True); return
        st.update(qty=max(1, min(99, iarg(3, 1))), wait='name', ts=time.time())
        await q.answer(); await _pos_chiqar(q, f"Soni: {st['qty']} ta.\n👤 Ismingizni yozing:", None); return
    if w == 'x':
        ctx.user_data.pop('pub', None); await q.answer()
        await _pos_chiqar(q, "Bekor qilindi. 📚 Katalog: /start", None); return
    if w == 'ok':
        st = ctx.user_data.get('pub') or {}
        if not st.get('phone') or st.get('tok') != (p_[2] if len(p_) > 2 else None):
            await q.answer("So'rov topilmadi yoki allaqachon yuborilgan", show_alert=True); return
        ctx.user_data.pop('pub', None)
        if not _rl_ok(us.id, 'lead', 3, 3600):
            await q.answer("Bir soatda 3 tadan ko'p so'rov yuborib bo'lmaydi. Biz bilan bog'laning.", show_alert=True); return
        await q.answer()
        lid = await lead_yarat(ctx.bot, us, st)
        await _pos_chiqar(q, f"✅ So'rovingiz qabul qilindi (#L{lid}). Tez orada qo'ng'iroq qilamiz!", None); return
    await q.answer()


async def pub_matn(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ochiq foydalanuvchi so'rovi: ism → telefon. True — ishlandi."""
    st = ctx.user_data.get('pub')
    if not st or not st.get('wait'): return False
    if time.time() - st.get('ts', 0) > UI_TTL:
        ctx.user_data.pop('pub', None); return False
    st['ts'] = time.time()
    t_ = (u.message.text or '').strip()
    if st['wait'] == 'name':
        if not (2 <= len(t_) <= 60):
            await u.message.reply_text("Ismingizni yozing (2–60 belgi):"); return True
        st['name'] = t_; st['wait'] = 'phone'
        await u.message.reply_text("📞 Telefon raqamingizni yozing yoki pastdagi tugmani bosing:",
                                   reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📱 Raqamni yuborish", request_contact=True)]],
                                                                    resize_keyboard=True, one_time_keyboard=True))
        return True
    if st['wait'] == 'phone':
        return await _pub_tel(u, ctx, st, t_)
    return False


async def _pub_tel(u, ctx, st, tel):
    raqam = re.sub(r'[^\d+]', '', tel or '')
    if len(re.sub(r'\D', '', raqam)) < 9:
        await u.message.reply_text("Raqam noto'g'ri. Masalan: +998 90 123 45 67"); return True
    st['phone'] = raqam[:20]; st['wait'] = None; st['tok'] = secrets.token_hex(4)
    p = _mkt_p(st['pid'])
    await u.message.reply_text("✅ Rahmat!", reply_markup=ReplyKeyboardRemove())
    await u.message.reply_text(f"Tekshiring:\n📦 {p['name'] if p else '—'} × {st.get('qty', 1)}\n👤 {st.get('name')}\n📞 {st['phone']}",
                               reply_markup=InlineKeyboardMarkup([[_btn("✅ Yuborish", f"pub:ok:{st['tok']}"), _btn("❌ Bekor", "pub:x")]]))
    return True


async def pub_contact(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    st = ctx.user_data.get('pub')
    if not st or st.get('wait') != 'phone': return
    c_ = u.message.contact
    if c_ and getattr(c_, 'user_id', None) not in (None, u.effective_user.id):
        await u.message.reply_text("Iltimos, o'zingizning raqamingizni yuboring."); return
    await _pub_tel(u, ctx, st, getattr(c_, 'phone_number', ''))


async def lead_yarat(bot, us, st):
    p = _mkt_p(st['pid'])
    conn = db(); c = conn.cursor()
    c.execute("INSERT INTO leads (created,chat_id,username,name,phone,product_id,product,qty) VALUES (?,?,?,?,?,?,?,?)",
              (_mkt_vaqt(), us.id, us.username or '', st.get('name', ''), st.get('phone', ''), st['pid'],
               p['name'] if p else '', int(st.get('qty', 1))))
    lid = c.lastrowid; conn.commit(); conn.close()
    try: sub_add(us.id, st.get('name', ''), us.username or '', 'lead')
    except Exception: pass
    matn = _lead_matn(_lead_ol(lid)); kb = InlineKeyboardMarkup(_lead_kb(lid))
    kimga = {OWNER_ID} | {x['id'] for x in xodimlar_royxati() if x['active'] and
                          (x['role'] == 'admin' or (x['role'] == 'sotuvchi' and soz('lead_sotuvchi') == '1'))}
    for cid in sorted(kimga):
        if not cid: continue
        try: await bot.send_message(chat_id=cid, text=matn, reply_markup=kb)
        except Exception: log.warning("lead xabari yetmadi: %s", cid)
    return lid


def _lead_mijoz(nom, tel):
    """Telefon bo'yicha mavjud mijoz yoki yangi (bir xil ismli boshqa mijozning telefoni ustidan yozilmaydi)."""
    oxir = re.sub(r'\D', '', tel or '')[-9:]
    conn = db(); rr = conn.execute("SELECT id,name,phone,type FROM customers").fetchall(); conn.close()
    for i, n, ph, ty in rr:
        if oxir and re.sub(r'\D', '', ph or '')[-9:] == oxir: return {'id': i, 'name': n, 'phone': ph, 'type': ty or 'B2C'}
    nom = (nom or 'Mijoz').strip()
    if any((n or '').strip().lower() == nom.lower() for _, n, _, _ in rr): nom = f"{nom} ({oxir[-4:]})"
    _, cid = add_customer(nom, tel or '', 'B2C', 'Telegram so‘rov')
    return {'id': cid, 'name': nom, 'phone': tel or '', 'type': 'B2C'}


async def lead_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    p_ = q.data.split(':'); w = p_[1] if len(p_) > 1 else ''
    try: lid = int(p_[2])
    except (IndexError, ValueError): lid = 0
    sotuvchi_ok = soz('lead_sotuvchi') == '1' and can(u, 'pos')
    if not (can(u, 'marketing') or sotuvchi_ok):
        await q.answer("Ruxsat yo'q", show_alert=True); return
    ld = _lead_ol(lid) if lid else None
    if not ld:
        await q.answer("So'rov topilmadi", show_alert=True); return
    x = xodim(u) or {}
    if w == 'c':
        await q.answer(); await _pos_chiqar(q, _lead_matn(ld), _lead_kb(lid) + [[_btn("⬅️ Orqaga", "mkt:leads")]]); return
    if w in ('ok', 'x'):
        yangi = 'boglanildi' if w == 'ok' else 'bekor'
        conn = db(); conn.execute("UPDATE leads SET status=?, handled_by=? WHERE id=?", (yangi, x.get('name', ''), lid)); conn.commit(); conn.close()
        await q.answer("✅"); await _pos_chiqar(q, _lead_matn(_lead_ol(lid)) + f"\n👷 {x.get('name', '')}", None); return
    if w == 'pos':
        if not can(u, 'pos'):
            await q.answer("Ruxsat yo'q", show_alert=True); return
        if ld[9] == 'savatda':
            await q.answer("Bu so'rov allaqachon savatga o'tkazilgan", show_alert=True); return
        p = next((pp for pp in get_products() if pp['id'] == ld[6]), None)
        if not p:
            await q.answer("Tovar topilmadi yoki nofaol", show_alert=True); return
        cm = _lead_mijoz(ld[4], ld[5])
        pos = _pos_yangi(ctx)
        _pos_qosh(pos, p, max(1, int(ld[8] or 1)))
        pos['cust'] = cm
        conn = db(); conn.execute("UPDATE leads SET status='savatda', handled_by=? WHERE id=?", (x.get('name', ''), lid)); conn.commit(); conn.close()
        await q.answer("🛒 Savatga qo'shildi")
        m, r = pos_ekran_savat(pos, get_exchange_rate(), f"🛒 So'rov #L{lid}: {cm['name']} ({cm['phone']})")
        await q.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r)); return
    await q.answer()


async def pub_start_link(u: Update, ctx: ContextTypes.DEFAULT_TYPE, payload):
    """/start p<ID> (kanal tugmasi) yoki /start katalog. True — ishlandi."""
    mt = re.fullmatch(r'p(\d{1,9})', payload or '')
    if not mt and payload != 'katalog': return False
    us = u.effective_user
    if not _rl_ok(us.id, 'msg', 20, 60): return True
    nomi = ((us.first_name or '') + (' ' + us.last_name if us.last_name else '')).strip()
    yangi = sub_add(us.id, nomi, us.username or '', 'deeplink')
    if yangi:
        try: await ctx.bot.send_message(OWNER_ID, f"👤 Yangi obunachi (kanal tugmasi): {nomi or 'ismsiz'}"
                                        + (f" (@{us.username})" if us.username else ''))
        except Exception: pass
    if mt:
        await pub_karta_yubor(ctx.bot, u.effective_chat.id, int(mt.group(1)))
    else:
        m, r = _pub_katalog(); await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r) if r else None)
    return True


async def pub_qidir(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ochiq foydalanuvchi tovar nomini yozdi → karta / variantlar. True — ishlandi."""
    t_ = (u.message.text or '').strip()
    if len(t_) < 2 or len(t_) > 80: return False
    prods = _pub_tovarlar()
    if not prods: return False
    p, v = match_product(t_, prods=prods)
    if p:
        await pub_karta_yubor(ctx.bot, u.effective_chat.id, p['id']); return True
    lst = [x for x in prods if x['name'] in {c_['name'] for c_ in v}]
    if not lst:
        yaqin = difflib.get_close_matches(_nrm(t_), [_nrm(x['name']) for x in prods], n=3, cutoff=0.72)
        lst = [x for x in prods if _nrm(x['name']) in yaqin]
    if not lst: return False
    await u.message.reply_text("🔍 Shulardan qaysi biri?", reply_markup=InlineKeyboardMarkup(
        [[_btn(f"{'✅' if x['qty'] > 0 else '🕐'} {x['name']}", f"pub:p:{x['id']}")] for x in lst[:8]] + [[_btn("📚 Katalog", "pub:k")]]))
    return True


# ══════════════════════════════════════════════════════════════════
# ── 🗓 KUNLIK KONTENT (yetkazuvchi saytlaridan): Two Trees, Freesub
# ══════════════════════════════════════════════════════════════════
# Faqat ochiq sahifalar; robots.txt hurmat qilinadi; har saytga so'rovlar orasida >= WEB_DELAY soniya;
# timeout; hammasi alohida oqimda (asyncio.to_thread). Sayt tuzilishi o'zgarsa — o'tkazib yuboriladi + egasiga izoh.
SUPPLIER_SAYTLAR = {
    'two trees': {'nom': 'Two Trees', 'base': 'https://twotrees3d.com', 'tur': 'shopify'},
    'freesub': {'nom': 'Freesub', 'base': 'https://www.freesub.com', 'tur': 'sitemap', 'sitemap': '/product-sitemap.xml'},
}
WEB_UA = "ThermoCraftsBot/1.0 (dealer content fetcher; +https://t.me/ThermoCrafts)"
WEB_TIMEOUT = 15
WEB_DELAY = 2.0                       # bir saytga so'rovlar orasidagi minimal pauza (s)
WEB_HTML_MAX = 3 * 1024 * 1024
WEB_MEDIA_MAX = 50 * 1024 * 1024
TG_UPLOAD_MAX = 50 * 1024 * 1024      # Bot API: bot yuboradigan fayl chegarasi
TG_PHOTO_MAX = 10 * 1024 * 1024       # Bot API: rasm chegarasi
KONTENT_KESH_KUN = 7
XARITA_AVTO_BALL = 0.8
_WEB = {'last': {}, 'robots': {}, 'katalog': {}}
_WEB_LOCK = threading.Lock()
KONTENT_TUGMALAR = {'cal', 'now', 'auto', 'autop', 'ks', 'kun', 'man', 'days', 'vaqt', 'map', 'mp', 'mc', 'mok', 'mu', 'mx', 'mf', 'mr'}
_AKSESSUAR = ('blade', 'bit', 'bits', 'set', 'module', 'kit', 'spare', 'replacement', 'belt', 'lens', 'nozzle', 'cable',
              'collet', 'end mill', 'clamp', 'honeycomb', 'enclosure', 'rotary', 'roller', 'paper', 'tape', 'ink', 'filter')


class KontentXato(Exception):
    pass


def _web_xom(url, max_bytes):
    """Yagona tarmoq nuqtasi (testda almashtiriladi). Qaytaradi (status, {header: qiymat}, bytes)."""
    with requests.get(url, headers={'User-Agent': WEB_UA, 'Accept': '*/*'}, timeout=WEB_TIMEOUT, stream=True) as r:
        h = {k.lower(): v for k, v in r.headers.items()}
        if r.status_code != 200: return r.status_code, h, b''
        cl = int(h.get('content-length') or 0)
        if cl and cl > max_bytes: raise KontentXato(f"juda katta ({cl / 1048576:.0f} MB)")
        buf = bytearray()
        for ch in r.iter_content(65536):
            buf += ch
            if len(buf) > max_bytes: raise KontentXato(f"juda katta (>{max_bytes / 1048576:.0f} MB)")
        return r.status_code, h, bytes(buf)


def _url_qism(url):
    from urllib.parse import urlsplit
    s = urlsplit(url)
    return f"{s.scheme}://{s.netloc}", (s.path or '/') + (('?' + s.query) if s.query else '')


def robots_qoidalar(matn):
    """robots.txt → [(allow, pattern)] — bizning UA guruhi bo'lsa o'sha, aks holda '*'."""
    guruhlar = []; joriy = None; qoida_boshlandi = False
    for ln in str(matn or '').splitlines():
        ln = ln.split('#', 1)[0].strip()
        if ':' not in ln: continue
        k, v = ln.split(':', 1); k = k.strip().lower(); v = v.strip()
        if k == 'user-agent':
            if joriy is None or qoida_boshlandi:
                joriy = {'ua': [], 'q': []}; guruhlar.append(joriy); qoida_boshlandi = False
            joriy['ua'].append(v.lower())
        elif k in ('allow', 'disallow') and joriy is not None:
            qoida_boshlandi = True
            if v: joriy['q'].append((k == 'allow', v))
    bizniki = [g for g in guruhlar if any(a and a != '*' and a in WEB_UA.lower() for a in g['ua'])]
    tanlov = bizniki or [g for g in guruhlar if '*' in g['ua']]
    return [q for g in tanlov for q in g['q']]


def robots_ruxsat(qoidalar, path):
    eng = None   # (uzunlik, allow)
    for allow, pat in qoidalar:
        rx = '^' + re.escape(pat).replace(r'\*', '.*')
        if rx.endswith(r'\$'): rx = rx[:-2] + '$'
        if re.match(rx, path):
            n = len(pat)
            if eng is None or n > eng[0] or (n == eng[0] and allow): eng = (n, allow)
    return True if eng is None else eng[1]


def robots_ok(url):
    base, path = _url_qism(url)
    kesh = _WEB['robots'].get(base)
    if not kesh or time.time() - kesh[0] > 86400:
        try:
            _web_pauza(base)
            st, _h, body = _web_xom(base + '/robots.txt', 512 * 1024)
            if st == 200: q = robots_qoidalar(body.decode('utf-8', 'replace'))
            elif 400 <= st < 500: q = []                          # robots.txt yo'q → ruxsat
            else: q = [(False, '/')]                               # 5xx → hozircha hech narsa olmaymiz
        except Exception:
            q = [(False, '/')]
        kesh = (time.time(), q); _WEB['robots'][base] = kesh
    return robots_ruxsat(kesh[1], path)


def _web_pauza(base):
    with _WEB_LOCK:
        kut = WEB_DELAY - (time.time() - _WEB['last'].get(base, 0))
        _WEB['last'][base] = time.time() + max(0, kut)
    if kut > 0: time.sleep(kut)


def web_ol(url, max_bytes=WEB_HTML_MAX):
    if not re.match(r'^https?://', url or ''): raise KontentXato("URL noto'g'ri")
    if not robots_ok(url): raise KontentXato("robots.txt ruxsat bermaydi")
    base, _ = _url_qism(url)
    _web_pauza(base)
    try:
        st, _h, body = _web_xom(url, max_bytes)
    except KontentXato:
        raise
    except Exception as e:
        raise KontentXato(f"tarmoq: {type(e).__name__}") from None
    if st != 200: raise KontentXato(f"HTTP {st}")
    return body


def web_yukla(url, max_bytes):
    body = web_ol(url, max_bytes)
    ext = os.path.splitext(url.split('?', 1)[0])[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov', '.gif'): ext = '.bin'
    path = os.path.join(_temp_dir(), secrets.token_hex(8) + ext)
    with open(path, 'wb') as f: f.write(body)
    return path


def _sayt(sup):
    s = (sup or '').lower().replace(' ', '')
    for k, v in SUPPLIER_SAYTLAR.items():
        if k.replace(' ', '') in s: return k, v
    return None, None


def _sayt_url(url):
    for k, v in SUPPLIER_SAYTLAR.items():
        if (url or '').startswith(v['base']): return k, v
    return None, None


KATALOG_KESH_KUN = 7


def _sahifa_model(url):
    """Sahifadagi 'Model Number: F137' (Freesub sahifalarida bor, URL'da yo'q)."""
    t_ = _html_matn(web_ol(url).decode('utf-8', 'replace'))
    m = re.search(r'\bModel\s*(?:Number|No\.?)?\s*[:：]?\s*([A-Za-z]{1,4}[- ]?\d{2,5}[A-Za-z0-9-]*)', t_, re.I)
    return m.group(1).strip() if m else ''


def sayt_katalog(kalit):
    """Yetkazuvchi tovarlari ro'yxati [{'title', 'url'}]. Xotira + bazada 7 kun kesh (sozlamalar: katalog:<kalit>)."""
    s = SUPPLIER_SAYTLAR[kalit]
    kesh = _WEB['katalog'].get(kalit)
    if not kesh:
        try:
            j = json.loads(soz('katalog:' + kalit) or '{}')
            if j.get('items'): kesh = (float(j.get('ts', 0)), j['items'])
        except ValueError:
            kesh = None
    if kesh and time.time() - kesh[0] < KATALOG_KESH_KUN * 86400: return kesh[1]
    items = []
    if s['tur'] == 'shopify':
        for page in range(1, 6):
            j = json.loads(web_ol(f"{s['base']}/products.json?limit=250&page={page}").decode('utf-8', 'replace'))
            prods = j.get('products') or []
            for p in prods:
                if p.get('handle') and p.get('title'):
                    items.append({'title': p['title'], 'url': f"{s['base']}/products/{p['handle']}"})
            if len(prods) < 250: break
    else:
        xml = web_ol(s['base'] + s['sitemap']).decode('utf-8', 'replace')
        for loc in re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', xml)[:120]:
            if not loc.startswith(s['base']): continue
            slug = re.sub(r'\.(html?|php)$', '', loc.rstrip('/').rsplit('/', 1)[-1])
            title = slug.replace('-', ' ').strip()
            try:
                model = _sahifa_model(loc)          # URL'da model raqami yo'q — sahifadan (sekin, shuning uchun 7 kun kesh)
                if model: title += ' ' + model
            except Exception:
                pass
            items.append({'title': title, 'url': loc})
    _WEB['katalog'][kalit] = (time.time(), items)
    try: soz_yoz('katalog:' + kalit, json.dumps({'ts': time.time(), 'items': items}))
    except Exception: pass
    return items


def _model_kodlar(s):
    t_ = re.sub(r'[^a-z0-9]+', ' ', str(s or '').lower())
    out = set()
    for m in re.findall(r'[a-z]{0,6} ?\d+[a-z]{0,4}', t_):
        m = m.replace(' ', '')
        if re.fullmatch(r'\d+(w|kw|mm|cm|m|v|l|kg|g|pcs|oz|in)', m): continue   # 500W, 20oz — model emas, o'lcham
        if len(m) >= 3 and len(re.sub(r'\D', '', m)) >= 2: out.add(m)     # 'in1' (3-in-1) kabi soxta kodlar emas
    return out


_SINONIM = {'kepka': 'cap hat', 'krujka': 'mug cup', 'stakan': 'tumbler cup', 'futbolka': 'shirt', 'termopress': 'heat press',
            'lazer': 'laser', 'gravyor': 'engraver', 'kombo': 'combo', 'avtomat': 'automatic', 'shpindel': 'spindle'}


def moslik_ball(nom, sarlavha):
    """0..1: model raqami (TTS-20, P8100 ...) mos kelsa yuqori; aksessuar sahifalari jarimalanadi."""
    brend_soz = r'\b(two ?trees|twotrees|freesub)\b'
    n = re.sub(brend_soz, ' ', str(nom or '').lower()); s_ = re.sub(brend_soz, ' ', str(sarlavha or '').lower())
    n = ' '.join(_SINONIM.get(w, w) for w in re.split(r'\s+', n))
    nc, sc = _nrm(n), _nrm(s_)
    if not nc or not sc: return 0.0
    ball = 0.0
    kodlar = _model_kodlar(n)
    sarlavha_kodlar = _model_kodlar(s_)
    for k in kodlar:
        for c_ in sarlavha_kodlar:                  # 'tts20' ~ 'tts20pro', lekin 'tts20' != 'tts2000'
            i = c_.find(k)
            if i >= 0 and not c_[i - 1:i].isdigit() and not c_[i + len(k):i + len(k) + 1].isdigit():
                ball = max(ball, 0.65)
    nw = {w for w in re.findall(r'[a-z0-9]+', n) if len(w) > 1}
    sw = {w for w in re.findall(r'[a-z0-9]+', s_) if len(w) > 1}
    if nw: ball += 0.25 * (len(nw & sw) / len(nw))
    ball += 0.10 * difflib.SequenceMatcher(None, nc, sc).ratio()
    n1, s1 = re.findall(r'(\d+) ?in ?1\b', n), re.findall(r'(\d+) ?in ?1\b', s_)     # "11 in 1" kombo
    if n1 and s1:                                   # model kodi aniq mos bo'lsa, "N in 1" farqi jarimalanmaydi
        ball += 0.15 if set(n1) & set(s1) else (0.0 if ball >= 0.65 else -0.1)
    if not kodlar: ball = min(ball, 0.6)
    if any(a in s_ for a in _AKSESSUAR) and not any(a in n for a in _AKSESSUAR): ball -= 0.3
    return round(max(0.0, min(1.0, ball)), 3)


def moslash(nom, katalog, n=5):
    sc = sorted(((moslik_ball(nom, it['title']), it) for it in katalog), key=lambda x: -x[0])
    return [(b, it) for b, it in sc[:n] if b >= 0.08]      # takliflar (egasi tanlaydi); avto — faqat >= 0.8


def _html_matn(h):
    h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h or '')
    h = re.sub(r'(?i)<br\s*/?>|</(p|li|tr|h[1-6]|div)>', '\n', h)
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    h = _html.unescape(h)
    return '\n'.join(re.sub(r'[ \t\u00a0]+', ' ', ln).strip() for ln in h.splitlines() if ln.strip())


def _abs(u_, base):
    from urllib.parse import urljoin
    u_ = (u_ or '').strip()
    if u_.startswith('//'): return 'https:' + u_
    return urljoin(base, u_)


def _video_topish(h, base):
    vids = []
    for vid in re.findall(r'(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?v=)|youtu\.be/)([A-Za-z0-9_-]{11})', h):
        u_ = f"https://www.youtube.com/watch?v={vid}"
        if u_ not in vids: vids.append(u_)
    for mp in re.findall(r'(?:https?:)?//[^\s"\'<>()]+?\.mp4(?:\?[^\s"\'<>()]*)?', h):
        u_ = _abs(mp, base)
        if u_ not in vids: vids.append(u_)
    return vids[:4]


def parse_html_kontent(h, url):
    """Umumiy sahifa: og:*, JSON-LD Product, jadval qatorlari, rasm va videolar."""
    def meta(prop):
        return [_html.unescape(m) for m in re.findall(
            r'<meta[^>]+(?:property|name)=["\']' + re.escape(prop) + r'["\'][^>]*content=["\']([^"\']*)["\']', h, re.I)]
    title = (meta('og:title') or [''])[0]
    desc = (meta('og:description') or meta('description') or [''])[0]
    imgs = [_abs(x, url) for x in meta('og:image')]
    for blok in re.findall(r'(?is)<script[^>]+application/ld\+json[^>]*>(.*?)</script>', h):
        try: j = json.loads(blok.strip())
        except ValueError: continue
        nodes = j if isinstance(j, list) else (j.get('@graph') or [j]) if isinstance(j, dict) else []
        for nd in nodes:
            if not isinstance(nd, dict) or 'Product' not in str(nd.get('@type', '')): continue
            title = nd.get('name') or title
            desc = (nd.get('description') or '') if len(nd.get('description') or '') > len(desc) else desc
            im = nd.get('image')
            for x in (im if isinstance(im, list) else [im]):
                x = x.get('url') if isinstance(x, dict) else x
                if isinstance(x, str): imgs.append(_abs(x, url))
    tana = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h)
    for src in re.findall(r'<img[^>]+(?:data-src|src)=["\']([^"\']+\.(?:jpe?g|png|webp)(?:\?[^"\']*)?)["\']', tana, re.I):
        if not re.search(r'logo|icon|avatar|flag|payment|sprite|banner-?nav|loading', src, re.I): imgs.append(_abs(src, url))
    rasmlar = []
    for x in imgs:
        if x and x.startswith('http') and x not in rasmlar: rasmlar.append(x)
    jadval = []
    for tr in re.findall(r'(?is)<tr[^>]*>(.*?)</tr>', tana)[:40]:
        cells = [_html_matn(c) for c in re.findall(r'(?is)<t[hd][^>]*>(.*?)</t[hd]>', tr)]
        cells = [c.replace('\n', ' ') for c in cells if c]
        if len(cells) >= 2 and len(cells[0]) <= 40: jadval.append(f"{cells[0]}: {' '.join(cells[1:])[:80]}")
    title = _html_matn(title).replace('\n', ' ').strip()
    if not title and not rasmlar: raise KontentXato("sahifa tuzilishi tanilmadi")
    matn = '\n'.join(x for x in [title, _html_matn(desc)] + jadval if x)
    return {'title': title[:200], 'images': rasmlar[:8], 'videos': _video_topish(h, url), 'text': matn[:4000]}


def parse_shopify_js(j, base):
    if not isinstance(j, dict) or not j.get('title'): raise KontentXato("Shopify javobi tanilmadi")
    imgs = []
    for x in j.get('images') or []:
        x = _abs(x if isinstance(x, str) else (x or {}).get('src', ''), base)
        if x not in imgs: imgs.append(x)
    vids = []
    for m in j.get('media') or []:
        if m.get('media_type') == 'video':
            src = [s_ for s_ in (m.get('sources') or []) if 'mp4' in str(s_.get('format', '')) or str(s_.get('url', '')).split('?')[0].endswith('.mp4')]
            if src:
                ok_ = [s_ for s_ in src if (s_.get('height') or 0) <= 1080]
                tan = max(ok_, key=lambda s_: s_.get('height') or 0) if ok_ else min(src, key=lambda s_: s_.get('height') or 0)
                vids.append(_abs(tan['url'], base))
        elif m.get('media_type') == 'external_video' and m.get('host') == 'youtube' and m.get('external_id'):
            vids.append(f"https://www.youtube.com/watch?v={m['external_id']}")
    body = j.get('description') or ''
    for v in _video_topish(body, base):
        if v not in vids: vids.append(v)
    return {'title': j['title'][:200], 'images': imgs[:8], 'videos': vids[:4], 'text': (j['title'] + '\n' + _html_matn(body))[:4000]}


def sahifa_kontent(url):
    k, s = _sayt_url(url)
    if s and s['tur'] == 'shopify' and '/products/' in url:
        js = url.split('?', 1)[0].rstrip('/') + '.js'
        try: j = json.loads(web_ol(js).decode('utf-8', 'replace'))
        except ValueError: raise KontentXato("Shopify javobi JSON emas") from None
        return parse_shopify_js(j, s['base'])
    return parse_html_kontent(web_ol(url).decode('utf-8', 'replace'), url)


# ── Kesh ──
def kontent_kesh(pid):
    try:
        conn = db()
        r = conn.execute("SELECT url,fetched,title,images,videos,text,status,error FROM supplier_content WHERE product_id=?", (int(pid),)).fetchone()
        conn.close()
    except (sqlite3.OperationalError, TypeError, ValueError):
        return None
    if not r: return None
    try: imgs, vids = json.loads(r[3] or '[]'), json.loads(r[4] or '[]')
    except ValueError: imgs, vids = [], []
    return {'url': r[0], 'fetched': r[1], 'title': r[2], 'images': imgs, 'videos': vids, 'text': r[5] or '',
            'status': r[6], 'error': r[7] or ''}


def _kesh_yoz(pid, url, k=None, xato=''):
    conn = db()
    conn.execute("INSERT OR REPLACE INTO supplier_content (product_id,url,fetched,title,images,videos,text,status,error) "
                 "VALUES (?,?,?,?,?,?,?,?,?)",
                 (int(pid), url, _mkt_vaqt(), (k or {}).get('title', ''), json.dumps((k or {}).get('images', [])),
                  json.dumps((k or {}).get('videos', [])), (k or {}).get('text', ''), 'xato' if xato else 'ok', xato[:300]))
    conn.commit(); conn.close()


def kontent_ol(pid, majburiy=False):
    """Tovar sahifasidan kontent (kesh 7 kun). Hech qachon exception tashlamaydi: {'status': 'ok'|'xato', ...} yoki None."""
    p = _mkt_p(pid)
    if not p or not p['supplier_url']: return None
    k = kontent_kesh(pid)
    if (k and not majburiy and k['url'] == p['supplier_url'] and k['status'] == 'ok'
            and k['fetched'] >= (_local_now() - timedelta(days=KONTENT_KESH_KUN)).strftime('%Y-%m-%d %H:%M')):
        return k
    try:
        yangi = sahifa_kontent(p['supplier_url'])
        _kesh_yoz(pid, p['supplier_url'], yangi)
    except Exception as e:
        xato = str(e) if isinstance(e, KontentXato) else f"{type(e).__name__}"
        log.warning("Kontent (%s): %s", p['name'], xato)
        _kesh_yoz(pid, p['supplier_url'], None, xato)
    return kontent_kesh(pid)


# ── Moslash (tovar ↔ sayt sahifasi) ──
def xarita_yoz(pid, url, ok=1):
    conn = db()
    conn.execute("UPDATE products SET supplier_url=?, supplier_url_ok=? WHERE id=?", (url or '', int(ok) if url else 0, int(pid)))
    if not url: conn.execute("DELETE FROM supplier_content WHERE product_id=?", (int(pid),))
    conn.commit(); conn.close()


def xarita_takliflar(pid):
    p = _mkt_p(pid)
    k, _s = _sayt(p['sup']) if p else (None, None)
    if not k: return []
    return moslash(p['name'], sayt_katalog(k))


def xarita_avto():
    """Omborda bor, yetkazuvchisi tanilgan va URL'i yo'q tovarlarga ishonchli moslikni yozadi (tasdiqlanmagan)."""
    conn = db()
    rr = conn.execute("SELECT id,name,supplier FROM products WHERE active=1 AND qty>0 AND COALESCE(supplier_url,'')=''").fetchall()
    conn.close()
    n = 0
    for pid, nom, sup in rr:
        k, _s = _sayt(sup)
        if not k: continue
        try: tk = moslash(nom, sayt_katalog(k), 2)
        except Exception as e:
            log.warning("katalog %s: %s", k, e); continue
        if tk and tk[0][0] >= XARITA_AVTO_BALL and (len(tk) < 2 or tk[0][0] - tk[1][0] >= 0.1):
            xarita_yoz(pid, tk[0][1]['url'], 0); n += 1
    return n


# ── Navbat (rotatsiya) ──
def kontent_otkaz(pid):
    try: d = json.loads(soz('kontent_otkaz') or '{}')
    except ValueError: d = {}
    if d.get('sana') != today(): d = {'sana': today(), 'pids': []}
    if int(pid) not in d['pids']: d['pids'].append(int(pid))
    soz_yoz('kontent_otkaz', json.dumps(d))


def kontent_navbat(n=7):
    """Omborda bor, faol, ochiq; supplier_url yoki o'z rasmi bor; oxirgi N kunda joylanmagan; bugun o'tkazilmagan.
    Tartib: eng uzoq vaqt joylanmagan (hech qachon — birinchi), keyin id."""
    try: kun = max(1, int(soz('kontent_kun') or 14))
    except ValueError: kun = 14
    chegara = (_local_now() - timedelta(days=kun)).strftime('%Y-%m-%d %H:%M')
    try: ot = json.loads(soz('kontent_otkaz') or '{}')
    except ValueError: ot = {}
    otkaz = set(ot.get('pids') or []) if ot.get('sana') == today() else set()
    conn = db()
    oxirgi = dict(conn.execute("SELECT product_id, MAX(created) FROM posts WHERE status='ok' GROUP BY product_id").fetchall())
    rasm = {r[0] for r in conn.execute("SELECT DISTINCT product_id FROM product_photos").fetchall()}
    rr = conn.execute("SELECT id,name,COALESCE(supplier_url,''),COALESCE(supplier_url_ok,0) FROM products "
                      "WHERE active=1 AND qty>0 AND COALESCE(public_show,1)=1").fetchall()
    conn.close()
    out = []
    for pid, nom, url, ok in rr:
        if pid in otkaz or not (url or pid in rasm): continue
        if oxirgi.get(pid) and oxirgi[pid] >= chegara: continue
        out.append({'id': pid, 'name': nom, 'url': url, 'url_ok': ok, 'oxirgi': oxirgi.get(pid) or ''})
    out.sort(key=lambda x: (x['oxirgi'], x['id']))
    return out[:n]


def kontent_tozala(d):
    for m in (d or {}).get('media') or []:
        if m.get('path') and os.path.dirname(m['path']) == _temp_dir():
            try: os.remove(m['path'])
            except OSError: pass


def _temp_tozala(soat=24):
    d = _temp_dir(); chegara = time.time() - soat * 3600
    for f in os.listdir(d):
        fp = os.path.join(d, f)
        try:
            if os.path.getmtime(fp) < chegara and not any(v['path'] == fp for v in _MEDIA.values()): os.remove(fp)
        except OSError: pass


# ── Qoralama (kunlik post) ──
async def kontent_qoralama(pid, avto=False):
    """Qaytaradi (draft_id, izoh). Tarmoq/sayt xatosi — post tovarning o'z rasmlari bilan tuziladi."""
    p = _mkt_p(pid)
    media, video_link, extra, manba, izoh = [], '', [], '', []
    k = None
    if p['supplier_url'] and (p['url_ok'] or not avto):
        k = await asyncio.to_thread(kontent_ol, pid)
        if not p['url_ok']: izoh.append("❔ Sayt sahifasi avtomatik moslangan — 🔗 Tovar ↔ sayt'da tasdiqlang")
    brend = _brend(p['sup'])
    if k and k['status'] == 'ok':
        if soz('manba_korsat') == '1': manba = brend
        mp4 = [v for v in k['videos'] if v.split('?', 1)[0].lower().endswith('.mp4')]
        yt = [v for v in k['videos'] if 'youtu' in v]
        if mp4:
            try:
                path = await asyncio.to_thread(web_yukla, mp4[0], TG_UPLOAD_MAX)
                media = [{'type': 'video', 'path': path, 'url': mp4[0]}]
            except Exception as e:
                video_link = mp4[0]
                izoh.append(f"🎬 Video {e if isinstance(e, KontentXato) else 'yuklanmadi'} — rasmlar + video havolasi")
        if not media:
            for img in k['images'][:6]:
                if len(media) >= 4: break
                try: media.append({'type': 'photo', 'path': await asyncio.to_thread(web_yukla, img, TG_PHOTO_MAX), 'url': img})
                except Exception: continue
            if not video_link and yt: video_link = yt[0]
        extra = await asyncio.to_thread(ai_xususiyatlar, k['text']) or _matndan_xususiyat(k['text'])
    elif k:
        izoh.append(f"⚠️ {brend} saytidan ma'lumot olinmadi ({k['error']}) — tovarning o'z rasmlari ishlatildi")
    if not media:
        media = [{'type': 'photo', 'fid': f} for f in get_product_photos(pid)[:4]]
    did = draft_yarat('kontent', pid, media, user_id=OWNER_ID, chat_id=OWNER_ID, extra='\n'.join(extra),
                      video_link=video_link, manba=manba)
    return did, '\n'.join(izoh)


async def kontent_preview_yubor(bot, did, chat_id, izoh=''):
    """Media'ni egasiga yuboradi (file_id'lar saqlanadi — kanalga qayta yuklanmaydi), keyin matn + tugmalar."""
    import contextlib
    d = draft_ol(did); media = d['media']
    try:
        with contextlib.ExitStack() as ex:
            if len(media) == 1:
                m = media[0]; src = _tg_manba(m, ex)
                msg = await (bot.send_video(chat_id=chat_id, video=src, supports_streaming=True) if m['type'] == 'video'
                             else bot.send_photo(chat_id=chat_id, photo=src))
                obj = getattr(msg, 'video', None) if m['type'] == 'video' else (getattr(msg, 'photo', None) or [None])[-1]
                if getattr(obj, 'file_id', None): m['fid'] = obj.file_id
            elif media:
                res = await bot.send_media_group(chat_id=chat_id, media=[
                    InputMediaVideo(_tg_manba(m, ex)) if m['type'] == 'video' else InputMediaPhoto(_tg_manba(m, ex)) for m in media])
                for m, msg in zip(media, res or [], strict=False):
                    obj = getattr(msg, 'video', None) if m['type'] == 'video' else (getattr(msg, 'photo', None) or [None])[-1]
                    if getattr(obj, 'file_id', None): m['fid'] = obj.file_id
        draft_yoz(did, media=media)
    except Exception as e:
        izoh = (izoh + '\n' if izoh else '') + f"⚠️ Media ko'rinishi yuborilmadi: {str(e)[:120]}"
    txt, rows = mkt_preview(did, izoh)
    await bot.send_message(chat_id=chat_id, text=txt, reply_markup=InlineKeyboardMarkup(rows))


async def kontent_kunlik(bot, majburiy=False, chat_id=None):
    """Kunlik post: navbatdagi tovar → qoralama → egasiga ko'rinish (yoki AUTO_POST bo'lsa — darhol joylash)."""
    chat_id = chat_id or OWNER_ID
    if not majburiy and soz('kontent_kunlik') != '1': return None
    try: await asyncio.to_thread(_temp_tozala)
    except Exception: pass
    try: await asyncio.to_thread(xarita_avto)
    except Exception: log.warning("xarita_avto ishlamadi")
    nav = await asyncio.to_thread(kontent_navbat, 1)
    if not nav:
        if majburiy:
            await bot.send_message(chat_id=chat_id, text=(f"📭 Hozir joylash uchun tovar yo'q: omborda bor, ochiq, rasmi yoki sayt sahifasi bor "
                                                          f"va oxirgi {soz('kontent_kun')} kunda joylanmagan tovar topilmadi."))
        return None
    avto = (soz('auto_post') == '1' and not majburiy)
    try:
        did, izoh = await kontent_qoralama(nav[0]['id'], avto)
    except Exception as e:
        log.exception("kontent qoralama")
        await bot.send_message(chat_id=chat_id, text=f"⚠️ Kunlik kontent tayyorlanmadi: {str(e)[:150]}")
        return None
    if avto:
        plat = soz('auto_platforma') if soz('auto_platforma') in ('tg', 'ig', 'both') else 'tg'
        if plat != 'tg' and not ig_sozlangan():
            plat = 'tg'; izoh = (izoh + '\n' if izoh else '') + "📸 Instagram sozlanmagan — faqat kanalga"
        if plat in ('tg', 'both') and not get_channel_id():
            await kontent_preview_yubor(bot, did, chat_id, "⚠️ CHANNEL_ID yo'q — avto-joylash o'rniga ko'rinish"); return did
        ok, msg = await mkt_joyla(bot, did, plat, chat_id, OWNER_ID)
        if plat == 'tg': kontent_tozala(draft_ol(did))
        await bot.send_message(chat_id=chat_id, text=f"🤖 Avto-post: {nav[0]['name']}\n{msg}" + (f"\n{izoh}" if izoh else ''))
        return did
    await kontent_preview_yubor(bot, did, chat_id, izoh)
    return did


# ── Kontent ekranlari ──
def _kontent_sozlama():
    m = ("⚙️ KUNLIK KONTENT SOZLAMALARI\n\n"
         f"🗓 Kunlik: {'yoqilgan' if soz('kontent_kunlik') == '1' else 'o‘chirilgan'} · ⏰ {soz('kontent_vaqt')} (Toshkent)\n"
         f"🔁 Takrorlamaslik: {soz('kontent_kun')} kun\n"
         f"🤖 Avto-joylash: {'ON' if soz('auto_post') == '1' else 'OFF (oldindan ko‘rsatadi)'} → {PLATFORMA_NOMI.get(soz('auto_platforma'), 'Telegram')}\n"
         f"ℹ️ «Manba: brend rasmiy sayti»: {'ko‘rsatiladi' if soz('manba_korsat') == '1' else 'yo‘q'}\n\n"
         "Avto rejimda faqat ✅ tasdiqlangan sayt sahifalari ishlatiladi.")
    rows = [[_btn("🗓 Kunlik: almashtirish", "mkt:kun"), _btn("⏰ Vaqt", "mkt:vaqt")],
            [_btn(f"🔁 {soz('kontent_kun')} kun → keyingi", "mkt:days"), _btn("🤖 Avto: almashtirish", "mkt:auto")],
            [_btn("📡 Avto platforma", "mkt:autop"), _btn("ℹ️ Manba: almashtirish", "mkt:man")],
            [_btn("⬅️ Orqaga", "mkt:menu")]]
    return m, rows


def _kontent_kalendar():
    nav = kontent_navbat(7)
    if not nav:
        return ("📅 Navbat bo'sh: omborda bor, ochiq va rasmi/sayt sahifasi bor tovar yo'q "
                f"(yoki hammasi oxirgi {soz('kontent_kun')} kunda joylangan).", [[_btn("⬅️ Orqaga", "mkt:menu")]])
    bosh = 0 if soz('kontent_ishladi') != today() else 1
    out = [f"📅 KONTENT KALENDARI (har kuni {soz('kontent_vaqt')})\n"]
    for i, x in enumerate(nav):
        kun = (_local_now() + timedelta(days=i + bosh)).strftime('%d.%m')
        belgi = '✅' if x['url'] and x['url_ok'] else ('❔' if x['url'] else '📷')
        out.append(f"{kun} — {belgi} {x['name']}" + (f" (oxirgi: {x['oxirgi'][:10]})" if x['oxirgi'] else ''))
    out.append("\n✅ sayt tasdiqlangan · ❔ avtomatik moslangan · 📷 faqat o'z rasmlari")
    return '\n'.join(out), [[_btn("▶️ Hozir post", "mkt:now"), _btn("🔗 Tovar ↔ sayt", "mkt:map:0")], [_btn("⬅️ Orqaga", "mkt:menu")]]


def _xarita_royxat(page):
    conn = db()
    rr = conn.execute("SELECT id,name,supplier,COALESCE(supplier_url,''),COALESCE(supplier_url_ok,0) FROM products "
                      "WHERE active=1 AND qty>0 ORDER BY supplier,name").fetchall()
    conn.close()
    rr = [r for r in rr if _sayt(r[2])[0]]
    if not rr:
        return "🔗 Omborda Two Trees / Freesub tovari yo'q.", [[_btn("⬅️ Orqaga", "mkt:menu")]]
    sl = rr[page * 8:(page + 1) * 8]
    rows = [[_btn(f"{'✅' if u_ and ok else ('❔' if u_ else '➖')} {n[:30]}", f"mkt:mp:{i}")] for i, n, s_, u_, ok in sl]
    nav = []
    if page > 0: nav.append(_btn("◀️", f"mkt:map:{page - 1}"))
    if (page + 1) * 8 < len(rr): nav.append(_btn("▶️", f"mkt:map:{page + 1}"))
    if nav: rows.append(nav)
    rows.append([_btn("⬅️ Orqaga", "mkt:menu")])
    return ("🔗 TOVAR ↔ YETKAZUVCHI SAYTI\n✅ tasdiqlangan · ❔ avtomatik (tasdiqlang) · ➖ yo'q\n"
            "Rasmlar, video va xususiyatlar shu sahifadan olinadi."), rows


def _xarita_karta(pid, izoh=''):
    p = _mkt_p(pid)
    if not p: return "Tovar topilmadi", [[_btn("⬅️ Orqaga", "mkt:map:0")]]
    k = kontent_kesh(pid)
    m = [f"🔗 {p['name']}", f"🏭 {p['sup'] or '—'}",
         f"🌐 {p['supplier_url'] or '— (moslanmagan)'}" + ((' ✅' if p['url_ok'] else ' ❔') if p['supplier_url'] else '')]
    if k and k['url'] == p['supplier_url']:
        m.append(f"📦 Kesh: {k['fetched']} — " + (f"{len(k['images'])} rasm, {len(k['videos'])} video, {len(k['text'])} belgi matn"
                                                  if k['status'] == 'ok' else f"⚠️ {k['error']}"))
    if izoh: m.append(izoh)
    rows = [[_btn("🔍 Saytdan qidirish", f"mkt:mf:{pid}"), _btn("✏️ URL kiritish", f"mkt:mu:{pid}")]]
    if p['supplier_url']:
        rows.append([_btn("✅ Tasdiqlash", f"mkt:mok:{pid}"), _btn("🔄 Kontentni yangilash", f"mkt:mr:{pid}")])
        rows.append([_btn("🗑 Moslikni o'chirish", f"mkt:mx:{pid}")])
    rows.append([_btn("⬅️ Ro'yxat", "mkt:map:0")])
    return '\n'.join(m), rows


async def kontent_callback(u, ctx, q, st, p_, w):
    def iarg(i, dflt=0):
        try: return int(p_[i])
        except (IndexError, ValueError): return dflt
    chat_id = u.effective_chat.id if getattr(u, 'effective_chat', None) else OWNER_ID
    if w == 'cal':
        await q.answer(); await _pos_chiqar(q, *(await asyncio.to_thread(_kontent_kalendar))); return
    if w == 'now':
        if not _ui_done(ctx, f"know{int(time.time() // 20)}"):
            await q.answer("⏳ Tayyorlanmoqda…"); return
        await q.answer("⏳ Tayyorlanmoqda (sayt bilan 10–60 soniya)…")
        await _pos_chiqar(q, "⏳ Kunlik post tayyorlanmoqda…", None)
        await kontent_kunlik(ctx.bot, majburiy=True, chat_id=chat_id); return
    if w in ('auto', 'kun', 'man'):
        k = {'auto': 'auto_post', 'kun': 'kontent_kunlik', 'man': 'manba_korsat'}[w]
        soz_yoz(k, '0' if soz(k) == '1' else '1'); await q.answer("✅")
        await _pos_chiqar(q, *(_mkt_menu() if w == 'auto' and len(p_) < 3 and st.get('ekran') != 'ks' else _kontent_sozlama())); return
    if w == 'ks':
        st['ekran'] = 'ks'; await q.answer(); await _pos_chiqar(q, *_kontent_sozlama()); return
    if w == 'days':
        tartib = ['7', '14', '21', '30']; joriy = soz('kontent_kun')
        soz_yoz('kontent_kun', tartib[(tartib.index(joriy) + 1) % 4] if joriy in tartib else '14')
        await q.answer("✅"); await _pos_chiqar(q, *_kontent_sozlama()); return
    if w == 'autop':
        tartib = ['tg', 'ig', 'both']; joriy = soz('auto_platforma')
        soz_yoz('auto_platforma', tartib[(tartib.index(joriy) + 1) % 3] if joriy in tartib else 'tg')
        await q.answer("✅"); await _pos_chiqar(q, *_kontent_sozlama()); return
    if w == 'vaqt':
        st['wait'] = 'vaqt'; await q.answer()
        await _pos_chiqar(q, "⏰ Vaqtni yozing (Toshkent), masalan 10:00", [[_btn("⬅️ Orqaga", "mkt:ks")]]); return
    if w == 'map':
        st['ekran'] = 'map'; await q.answer(); await _pos_chiqar(q, *_xarita_royxat(iarg(2))); return
    pid = iarg(2)
    if w == 'mp':
        await q.answer(); await _pos_chiqar(q, *_xarita_karta(pid)); return
    if w == 'mf':
        await q.answer("🔍 Saytdan qidirilmoqda…")
        try: tk = await asyncio.to_thread(xarita_takliflar, pid)
        except Exception as e:
            await _pos_chiqar(q, *_xarita_karta(pid, f"⚠️ Sayt ochilmadi: {str(e)[:120]}")); return
        if not tk:
            await _pos_chiqar(q, *_xarita_karta(pid, "Mos sahifa topilmadi — ✏️ URL kiriting.")); return
        st.setdefault('cands', {})[str(pid)] = [it['url'] for _b, it in tk]
        m, rows = _xarita_karta(pid, "Mos keladiganini tanlang:")
        rows = [[_btn(f"{int(b * 100)}% {it['title'][:40]}", f"mkt:mc:{pid}:{i}")] for i, (b, it) in enumerate(tk)] + rows
        await _pos_chiqar(q, m, rows); return
    if w == 'mc':
        lst = (st.get('cands') or {}).get(str(pid)) or []
        i = iarg(3, -1)
        if not (0 <= i < len(lst)):
            await q.answer("Ro'yxat eskirgan — qayta qidiring", show_alert=True); return
        xarita_yoz(pid, lst[i], 1); await q.answer("✅ Saqlandi")
        await _pos_chiqar(q, *_xarita_karta(pid, "✅ Moslik saqlandi")); return
    if w == 'mok':
        p = _mkt_p(pid)
        if p and p['supplier_url']: xarita_yoz(pid, p['supplier_url'], 1)
        await q.answer("✅"); await _pos_chiqar(q, *_xarita_karta(pid, "✅ Tasdiqlandi")); return
    if w == 'mx':
        xarita_yoz(pid, '', 0); await q.answer("🗑")
        await _pos_chiqar(q, *_xarita_karta(pid)); return
    if w == 'mu':
        st['wait'] = f'url:{pid}'; await q.answer()
        await _pos_chiqar(q, "✏️ Tovarning yetkazuvchi saytidagi sahifa manzilini yuboring (https://…)",
                          [[_btn("⬅️ Orqaga", f"mkt:mp:{pid}")]]); return
    if w == 'mr':
        await q.answer("🔄 Yuklanmoqda…")
        k = await asyncio.to_thread(kontent_ol, pid, True)
        iz = "Moslik yo'q" if not k else (f"✅ {len(k['images'])} rasm, {len(k['videos'])} video" if k['status'] == 'ok' else f"⚠️ {k['error']}")
        await _pos_chiqar(q, *_xarita_karta(pid, iz)); return
    await q.answer()


async def kontent_matn(u, ctx, st, w, t_):
    if w == 'vaqt':
        mt = re.fullmatch(r'(\d{1,2})[:.](\d{2})', t_)
        if not mt or int(mt.group(1)) > 23 or int(mt.group(2)) > 59:
            await u.message.reply_text("Format: 10:00"); return True
        st['wait'] = None; soz_yoz('kontent_vaqt', f"{int(mt.group(1)):02d}:{mt.group(2)}")
        m, r = _kontent_sozlama(); await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r)); return True
    if w.startswith('url:'):
        pid = int(w[4:])
        if not re.fullmatch(r'https?://[^\s]{4,500}', t_):
            await u.message.reply_text("URL noto'g'ri. https:// bilan boshlansin."); return True
        st['wait'] = None; xarita_yoz(pid, t_, 1)
        m, r = _xarita_karta(pid, "✅ URL saqlandi. «🔄 Kontentni yangilash» bilan tekshiring.")
        await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r)); return True
    return False


# ══════════════════════════════════════════════════════════════════
# 10-bosqich: 💾 Zaxira · 📥 Qaytarish · 🧾 Smena (kassa yopish) · 🔢 Serial/kafolat · 🏷 Shtrix-kod/QR
# Qoidalar: jadval/ustunlar faqat QO'SHILADI (idempotent); har pul/astatka amali BITTA tranzaksiyada;
# davr yopilgan bo'lsa yozilmaydi; /undo bilan qaytariladi. Yangi majburiy env yo'q.
# ══════════════════════════════════════════════════════════════════
SOZ_DEFAULT.update({
    'zaxira_kunlik': '1',      # har kuni avtomatik zaxira
    'zaxira_vaqt': '23:30',    # Toshkent vaqti
    'zaxira_soni': '7',        # serverda (Volume) nechta oxirgi nusxa saqlanadi
    'zaxira_tg': '1',          # zaxira fayli egasiga Telegram orqali yuboriladi
})
TG_DOC_MAX = 49 * 1024 * 1024          # Bot API: hujjat yuborish chegarasi 50 MB (zaxira uchun 1 MB joy qoldiramiz)
QAYTARISH_SABABLARI = (('brak', '🔧 Brak (nosoz)'), ('yoqmadi', "🙅 Yoqmadi"), ('notogri', "🔀 Noto'g'ri tovar"), ('boshqa', '✍️ Boshqa'))
QAYTARISH_SABAB_NOMI = {k: v.split(' ', 1)[1] for k, v in QAYTARISH_SABABLARI}
OMBOR_TURLARI.setdefault('qaytarish', 'Mijoz qaytardi')
SERIAL_HOLAT = {'omborda': '📦 Omborda', 'sotilgan': '✅ Sotilgan', 'brak': '🔧 Brak', 'chiqarildi': '🗑 Hisobdan chiqarilgan'}


class _SerialXato(Exception):
    """POS: tanlangan serial band/topilmadi — savat saqlanmaydi."""
    pass


def init_b10_tables():
    """Additiv va idempotent (har ishga tushishda xavfsiz). Eski ma'lumot o'zgarmaydi."""
    conn = db(); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS zaxiralar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, fayl TEXT, hajm INTEGER DEFAULT 0, db_hajm INTEGER DEFAULT 0,
        sha TEXT DEFAULT '', sabab TEXT DEFAULT '', holat TEXT DEFAULT 'ok', yuborildi INTEGER DEFAULT 0, xato TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, date TEXT, customer TEXT DEFAULT '', customer_id INTEGER DEFAULT 0,
        reason TEXT DEFAULT '', note TEXT DEFAULT '', method TEXT DEFAULT '', total REAL DEFAULT 0, cogs REAL DEFAULT 0,
        refund_cash REAL DEFAULT 0, refund_debt REAL DEFAULT 0, brak INTEGER DEFAULT 0, status TEXT DEFAULT 'ok',
        requested_by INTEGER DEFAULT 0, requested_name TEXT DEFAULT '', approved_by INTEGER DEFAULT 0, approved_name TEXT DEFAULT '',
        op_id INTEGER DEFAULT 0, plan TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS return_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT, return_id INTEGER, sale_id INTEGER, product_id INTEGER, product TEXT,
        qty INTEGER, revenue REAL, unit_cost REAL, profit REAL, return_sale_id INTEGER, brak INTEGER DEFAULT 0, serials TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS brak_tovarlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, product_id INTEGER, product TEXT, qty INTEGER, unit_cost REAL,
        manba TEXT DEFAULT 'qaytarish', return_id INTEGER DEFAULT 0, expense_id INTEGER DEFAULT 0, serials TEXT DEFAULT '',
        status TEXT DEFAULT 'brak', note TEXT DEFAULT '', updated TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS smenalar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, user_name TEXT DEFAULT '', opened_at TEXT, opening_cash REAL DEFAULT 0,
        closed_at TEXT DEFAULT '', closed_by INTEGER DEFAULT 0, closed_name TEXT DEFAULT '',
        expected_naqd REAL DEFAULT 0, expected_karta REAL DEFAULT 0, counted_naqd REAL, counted_karta REAL,
        diff_naqd REAL DEFAULT 0, diff_karta REAL DEFAULT 0, boshqa TEXT DEFAULT '{}', status TEXT DEFAULT 'ochiq',
        note TEXT DEFAULT '', booking TEXT DEFAULT '', booking_ref TEXT DEFAULT '', booked_by TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS serials (
        id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, product TEXT DEFAULT '', serial TEXT NOT NULL,
        status TEXT DEFAULT 'omborda', kirim_date TEXT DEFAULT '', kirim_ref TEXT DEFAULT '', sale_id INTEGER DEFAULT 0,
        sold_date TEXT DEFAULT '', customer TEXT DEFAULT '', customer_id INTEGER DEFAULT 0, warranty_end TEXT DEFAULT '',
        note TEXT DEFAULT '', created TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS serial_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, serial_id INTEGER, date TEXT, event TEXT, ref TEXT DEFAULT '',
        note TEXT DEFAULT '', user_name TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS kafolat_murojaat (
        id INTEGER PRIMARY KEY AUTOINCREMENT, serial_id INTEGER DEFAULT 0, warranty_id INTEGER DEFAULT 0, product TEXT DEFAULT '',
        customer TEXT DEFAULT '', opened TEXT, opened_by TEXT DEFAULT '', status TEXT DEFAULT 'ochiq', note TEXT DEFAULT '',
        closed TEXT DEFAULT '', closed_by TEXT DEFAULT '', result TEXT DEFAULT '', tarix TEXT DEFAULT '')''')
    for ddl in ("ALTER TABLE sales ADD COLUMN return_of INTEGER DEFAULT 0",
                "ALTER TABLE products ADD COLUMN serialli INTEGER DEFAULT 0",
                "ALTER TABLE products ADD COLUMN barcode TEXT DEFAULT ''",
                "ALTER TABLE warranties ADD COLUMN serial TEXT DEFAULT ''"):
        try: c.execute(ddl)
        except sqlite3.OperationalError: pass          # ustun allaqachon bor
    for ddl in ("CREATE UNIQUE INDEX IF NOT EXISTS ux_serials_serial ON serials(serial COLLATE NOCASE)",
                "CREATE INDEX IF NOT EXISTS ix_serials_pid ON serials(product_id, status)",
                "CREATE INDEX IF NOT EXISTS ix_serials_sale ON serials(sale_id)",
                "CREATE INDEX IF NOT EXISTS ix_sales_return_of ON sales(return_of)",
                "CREATE INDEX IF NOT EXISTS ix_return_lines_sale ON return_lines(sale_id)",
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_products_barcode ON products(barcode) WHERE COALESCE(barcode,'')<>''"):
        try: c.execute(ddl)
        except sqlite3.OperationalError as e: log.warning("index: %s", e)
    conn.commit(); conn.close()


def _hm(): return datetime.now().strftime('%Y-%m-%d %H:%M')


async def _b10_chiqar(u, matn, rows):
    """Callback → tahrirlaydi; matn xabari → javob yozadi."""
    q = getattr(u, 'callback_query', None)
    if q is not None:
        return await _pos_chiqar(q, matn, rows)
    await u.message.reply_text(matn[:4000], reply_markup=InlineKeyboardMarkup(rows) if rows else None)


def _som(usd, rate=None):
    try: return f"{float(usd) * (rate or get_exchange_rate()):,.0f} so'm".replace(',', ' ')
    except Exception: return ''


def _pul_kirit(s):
    """'450', '450$', '1 250 000' (so'm → $) → float yoki None."""
    t = re.sub(r'[^\d.,]', '', str(s or '')).replace(',', '.')
    if not t or t.count('.') > 1: return None
    try: v = float(t)
    except ValueError: return None
    return round(_to_usd(v, 0, get_exchange_rate()), 2) if v >= 5000 else round(v, 2)


# ── 💾 ZAXIRA: kunlik zip nusxa → egasiga Telegram + Volume'da oxirgi N ta ──────────────
# Nusxa sqlite3 backup API bilan olinadi (bot yozib turgan paytda ham izchil). Fayl — zip ichida baza +
# zaxira.json (sana, sha256). Shu faylni botga qayta yuborsa — tekshiradi va tasdiqdan keyin tiklaydi.
ZAXIRA_RE = re.compile(r'^thermocrafts_\d{8}_\d{6}(?:_\d+)?\.zip$')


def _zaxira_dir():
    d = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), 'zaxira')
    os.makedirs(d, exist_ok=True)
    return d


def _db_nomi():
    return os.path.basename(DB_PATH) or 'thermocraft.db'


def _fayl_sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()


def _mb(n): return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{max(1, n // 1024)} KB"


def _zx_log(**kv):
    try:
        conn = db()
        conn.execute("INSERT INTO zaxiralar (created,fayl,hajm,db_hajm,sha,sabab,holat,xato) VALUES (?,?,?,?,?,?,?,?)",
                     (_hm(), kv.get('fayl', ''), kv.get('hajm', 0), kv.get('db_hajm', 0), kv.get('sha', ''),
                      kv.get('sabab', ''), kv.get('holat', 'ok'), kv.get('xato', '')[:300]))
        conn.commit(); conn.close()
    except Exception:
        log.exception("zaxiralar log")


def zaxira_yarat(sabab="qo'lda"):
    """Izchil nusxa → integrity_check → zip → zaxira/ papka. Qaytaradi {'ok', 'path','name','size','db_size','sha','soni'}."""
    if not os.path.exists(DB_PATH):
        return {'ok': False, 'error': "Baza fayli topilmadi"}
    d = _zaxira_dir()
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = f"thermocrafts_{stamp}.zip"; k = 1
    while os.path.exists(os.path.join(d, name)):
        k += 1; name = f"thermocrafts_{stamp}_{k}.zip"
    path = os.path.join(d, name)
    fd, tmpdb = tempfile.mkstemp(suffix='.db', dir=d); os.close(fd)
    tmpzip = path + '.tmp'
    if not _BK_LOCK.acquire(timeout=180):
        return {'ok': False, 'error': "Boshqa zaxira/tiklash jarayoni tugamadi"}
    try:
        src = sqlite3.connect(DB_PATH, timeout=30); dst = sqlite3.connect(tmpdb)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        chk = sqlite3.connect(tmpdb)
        try:
            ic = chk.execute("PRAGMA integrity_check").fetchone()[0]
            jad = {r[0] for r in chk.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            soni = {t: chk.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in ('sales', 'products', 'cash_box') if t in jad}
        finally:
            chk.close()
        if ic != 'ok':
            raise RuntimeError(f"baza butunligi tekshiruvi: {ic}")
        db_hajm = os.path.getsize(tmpdb); sha = _fayl_sha(tmpdb)
        meta = {'dastur': 'ThermoCrafts', 'yaratildi': now_t(), 'sabab': sabab, 'db': _db_nomi(), 'db_hajm': db_hajm,
                'sha256': sha, 'soni': soni}
        with zipfile.ZipFile(tmpzip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.write(tmpdb, _db_nomi())
            z.writestr('zaxira.json', json.dumps(meta, ensure_ascii=False, indent=1))
        os.replace(tmpzip, path)
    except Exception as e:
        log.exception("zaxira_yarat")
        _zx_log(sabab=sabab, holat='xato', xato=str(e))
        return {'ok': False, 'error': str(e)[:200]}
    finally:
        _BK_LOCK.release()
        for p_ in (tmpdb, tmpzip):
            try: os.remove(p_)
            except OSError: pass
    hajm = os.path.getsize(path)
    _zx_log(fayl=name, hajm=hajm, db_hajm=db_hajm, sha=sha, sabab=sabab)
    ochdi = _zaxira_tozala()
    return {'ok': True, 'path': path, 'name': name, 'size': hajm, 'db_size': db_hajm, 'sha': sha, 'soni': soni,
            'ochirildi': ochdi, 'sabab': sabab}


def _zaxira_soni():
    try: return max(1, min(60, int(soz('zaxira_soni'))))
    except (TypeError, ValueError): return 7


def zaxira_royxat():
    d = _zaxira_dir()
    out = []
    for n in os.listdir(d):
        if ZAXIRA_RE.match(n):
            p_ = os.path.join(d, n)
            out.append({'name': n, 'path': p_, 'size': os.path.getsize(p_), 'mtime': os.path.getmtime(p_)})
    out.sort(key=lambda x: x['name'], reverse=True)
    try:
        conn = db()
        yub = {r[0] for r in conn.execute("SELECT fayl FROM zaxiralar WHERE yuborildi=1")}
        conn.close()
    except sqlite3.OperationalError:
        yub = set()
    for x in out:
        x['yuborildi'] = x['name'] in yub
        s = x['name'][13:28]
        x['vaqt'] = f"{s[6:8]}.{s[4:6]}.{s[:4]} {s[9:11]}:{s[11:13]}"
    return out


def _zaxira_tozala():
    """Oxirgi N tadan eskilarini o'chiradi (faqat bizning nomdagi fayllar)."""
    fl = zaxira_royxat(); n = _zaxira_soni(); ochdi = []
    for x in fl[n:]:
        try: os.remove(x['path']); ochdi.append(x['name'])
        except OSError: log.warning("zaxira o'chmadi: %s", x['name'])
    return ochdi


def zaxira_ochish(raw, fname=''):
    """Yuborilgan fayl (.zip yoki .db) → tekshiradi. {'ok','db': bytes,'info': {...}} yoki {'ok': False,'error'}."""
    raw = bytes(raw or b''); meta = {}
    try:
        if raw[:4] == b'PK\x03\x04':
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                azo = [i for i in z.infolist() if i.filename.lower().endswith(('.db', '.sqlite', '.sqlite3'))]
                if not azo: return {'ok': False, 'error': "zip ichida baza fayli (.db) yo'q"}
                if azo[0].file_size > 1024 * 1048576: return {'ok': False, 'error': "baza juda katta (1 GB dan ortiq)"}
                data = z.read(azo[0])
                if 'zaxira.json' in z.namelist():
                    try: meta = json.loads(z.read('zaxira.json').decode('utf-8'))
                    except Exception: meta = {}
        elif raw[:15] == b'SQLite format 3':
            data = raw
        else:
            return {'ok': False, 'error': "fayl zaxira emas (.zip yoki .db kutilgan)"}
    except zipfile.BadZipFile:
        return {'ok': False, 'error': "zip fayl buzilgan"}
    if data[:15] != b'SQLite format 3':
        return {'ok': False, 'error': "ichidagi fayl SQLite baza emas"}
    if meta.get('sha256') and hashlib.sha256(data).hexdigest() != meta['sha256']:
        return {'ok': False, 'error': "fayl buzilgan (sha256 mos emas)"}
    fd, tmp = tempfile.mkstemp(suffix='.db'); os.close(fd)
    try:
        with open(tmp, 'wb') as f: f.write(data)
        con = sqlite3.connect(tmp)
        try:
            ic = con.execute("PRAGMA integrity_check").fetchone()[0]
            jad = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if ic != 'ok': return {'ok': False, 'error': f"baza butunligi buzilgan: {ic}"}
            yoq = {'sales', 'products', 'cash_box'} - jad
            if yoq: return {'ok': False, 'error': "bu ThermoCrafts bazasi emas (" + ", ".join(sorted(yoq)) + " jadvali yo'q)"}
            info = {'sotuv': con.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                    'tovar': con.execute("SELECT COUNT(*) FROM products").fetchone()[0],
                    'kassa': round(con.execute("SELECT COALESCE(SUM(CASE WHEN type='kirim' THEN amount ELSE -amount END),0) "
                                               "FROM cash_box").fetchone()[0] or 0, 2),
                    'oxirgi_sotuv': (con.execute("SELECT MAX(date) FROM sales").fetchone()[0] or '—'),
                    'yaratildi': meta.get('yaratildi', ''), 'hajm': len(data)}
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        return {'ok': False, 'error': f"baza ochilmadi: {str(e)[:100]}"}
    finally:
        try: os.remove(tmp)
        except OSError: pass
    return {'ok': True, 'db': data, 'info': info}


def zaxira_tikla(data):
    """Avval hozirgi bazani zaxiralaydi, keyin almashtiradi (/restore bilan bir xil yo'l: init + baseline).
    backup_seq oshiriladi — keyingi restartda GitHub'dagi eski nusxa buni bosib ketmasin."""
    pre = zaxira_yarat('tiklashdan oldin')
    cur_seq = max(0, _db_seq_of(DB_PATH))
    with _BK_LOCK:
        _write_db_file(data)
        init_all_tables()
        _set_meta('backup_seq', max(cur_seq, _db_seq_of(DB_PATH), 0) + 1)
        _set_meta('restored_at', now_t())
        _BK['blocked'] = ''; _BK['restore_msg'] = ''
        _bk_set_baseline()
    _BK['migrate'] = True                 # GITHUB_TOKEN bo'lsa — tiklangan baza GitHub'ga ham yoziladi
    return {'ok': True, 'oldingi': pre.get('name') if pre.get('ok') else None,
            'oldingi_xato': None if pre.get('ok') else pre.get('error'), 'kassa': round(get_cash_balance(), 2)}


async def zaxira_yubor(bot, res, chat_id=None):
    """Zip faylni hujjat sifatida yuboradi. 50 MB dan katta bo'lsa — ogohlantiradi (fayl serverda qoladi)."""
    chat_id = chat_id or OWNER_ID
    if res['size'] > TG_DOC_MAX:
        await bot.send_message(chat_id=chat_id, text=(
            f"⚠️ Zaxira fayli {_mb(res['size'])} — Telegram 50 MB chegarasidan katta, yuborilmadi.\n"
            f"Nusxa serverda saqlandi: {res['name']}" + (" (Volume)" if db_on_volume() else "") +
            ("\nGitHub zaxira ham ishlaydi." if GITHUB_TOKEN else "")))
        return False
    soni = res.get('soni') or {}
    cap = (f"💾 Zaxira · {now_t()} · {_mb(res['size'])}\n"
           f"Sotuvlar: {soni.get('sales', '?')} · tovarlar: {soni.get('products', '?')} · sabab: {res.get('sabab', '')}\n"
           "♻️ Tiklash: shu faylni botga qayta yuboring (faqat egasi)."
           + ("\n⚠️ 20 MB dan katta fayl botga qayta yuklanmaydi — Railway Volume'dagi nusxadan foydalaning."
              if res['size'] > TG_DL_MAX else ""))
    with open(res['path'], 'rb') as fh:
        await bot.send_document(chat_id=chat_id, document=fh, filename=res['name'], caption=cap[:1000])
    try:
        conn = db(); conn.execute("UPDATE zaxiralar SET yuborildi=1 WHERE fayl=?", (res['name'],)); conn.commit(); conn.close()
    except Exception:
        log.exception("zaxira yuborildi belgisi")
    return True


async def _egaga(bot, matn):
    try: await bot.send_message(chat_id=OWNER_ID, text=matn[:4000])
    except Exception: log.exception("egaga xabar")


async def zaxira_kunlik(bot):
    """Rejalashtiruvchi chaqiradi: yaratadi → (sozlama bo'yicha) Telegram'ga → xato bo'lsa egasiga ogohlantirish."""
    try:
        res = await asyncio.to_thread(zaxira_yarat, 'kunlik')
    except Exception as e:
        res = {'ok': False, 'error': str(e)[:200]}
    if not res.get('ok'):
        await _egaga(bot, f"⚠️ Kunlik zaxira BAJARILMADI: {res.get('error')}\nQo'lda urinib ko'ring: 💾 Zaxira → Hozir zaxira")
        return res
    if soz('zaxira_tg') == '1':
        try:
            await zaxira_yubor(bot, res)
        except Exception as e:
            log.exception("zaxira yuborish")
            await _egaga(bot, f"⚠️ Zaxira yaratildi ({res['name']}), lekin Telegram'ga yuborib bo'lmadi: {str(e)[:150]}")
    return res


def zaxira_vaqti_keldimi(now=None):
    """Bugun hali qilinmagan va belgilangan vaqt o'tgan bo'lsa True (bot o'sha daqiqada o'chiq bo'lsa ham bugun qiladi)."""
    if soz('zaxira_kunlik') != '1': return False
    now = now or datetime.now()
    return soz('zaxira_ishladi') != now.strftime('%Y-%m-%d') and now.strftime('%H:%M') >= _hhmm(soz('zaxira_vaqt'))


# ── UI ──
def _zx_menu():
    fl = zaxira_royxat()
    on, tg = soz('zaxira_kunlik') == '1', soz('zaxira_tg') == '1'
    m = ["💾 ZAXIRA (bazaning to'liq nusxasi)", ""]
    m.append(f"Oxirgi: {fl[0]['vaqt']} · {_mb(fl[0]['size'])}" if fl else "Hali zaxira yo'q")
    m.append(f"🗓 Avtomatik: {'har kuni ' + soz('zaxira_vaqt') + ' (Toshkent)' if on else 'o‘chirilgan'}")
    m.append(f"📤 Telegram'ga yuborish: {'ha' if tg else 'yo‘q'}")
    m.append(f"📁 Serverda saqlanadi: oxirgi {_zaxira_soni()} ta (hozir {len(fl)} ta)")
    m.append(f"💽 Disk: {'Volume (doimiy)' if db_on_volume() else 'vaqtinchalik — Telegramdagi nusxa muhim!'}")
    m.append(f"☁️ GitHub zaxira: {'ulangan' if GITHUB_TOKEN else 'sozlanmagan (ixtiyoriy)'}")
    m.append("\n♻️ Tiklash: zaxira faylini (.zip) shu chatga yuboring — tekshirib, tasdiq so'rayman.")
    rows = [[_btn("💾 Hozir zaxira", "zx:now"), _btn("📋 Oxirgi zaxiralar", "zx:ls")],
            [_btn(f"⏰ Vaqt: {soz('zaxira_vaqt')}", "zx:t"), _btn(f"🔢 Saqlash: {_zaxira_soni()} ta", "zx:n")],
            [_btn(f"🗓 Avto: {'ON' if on else 'OFF'}", "zx:d"), _btn(f"📤 Telegram: {'ON' if tg else 'OFF'}", "zx:tg")],
            _x_btn('zx')]
    return "\n".join(m), rows


def _zx_royxat():
    fl = zaxira_royxat()
    if not fl: return "📋 Hali zaxira yo'q.", [[_btn("⬅️ Orqaga", "zx:menu")]]
    m = ["📋 OXIRGI ZAXIRALAR (bosing — fayl qayta yuboriladi):"]
    rows = [[_btn(f"{'📤' if x['yuborildi'] else '📁'} {x['vaqt']} · {_mb(x['size'])}", f"zx:s:{x['name'][13:-4]}")] for x in fl[:10]]
    m.append("📤 — Telegram'ga yuborilgan · 📁 — faqat serverda")
    rows.append([_btn("⬅️ Orqaga", "zx:menu")] + _x_btn('zx'))
    return "\n".join(m), rows


async def cmd_zaxira(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """💾 Zaxira tugmasi / /zaxira — faqat egasi"""
    if not can(u, 'zaxira'):
        if user_role(u): await u.message.reply_text("💾 Zaxira bo'limi faqat egasiga ochiq.")
        return
    _ui_yangi(ctx, 'zx')
    m, r = _zx_menu()
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))


async def zaxira_hujjat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Egasi zaxira faylini (.zip/.db) yubordi → tekshiradi → tasdiq tugmasi."""
    if not can(u, 'system'):
        await u.message.reply_text("♻️ Zaxiradan tiklash faqat egasiga ruxsat etilgan."); return
    doc = u.message.document
    if (getattr(doc, 'file_size', 0) or 0) > TG_DL_MAX:
        await u.message.reply_text("❌ Fayl 20 MB dan katta — Telegram bot uni yuklab ololmaydi.\n"
                                   "Railway Volume'dagi zaxira/ papkasidan yoki GitHub zaxirasidan (/restore ha) foydalaning.")
        return
    await u.message.reply_text("⏳ Zaxira fayli tekshirilmoqda...")
    try:
        f = await ctx.bot.get_file(doc.file_id)
        raw = bytes(await f.download_as_bytearray())
    except Exception as e:
        await u.message.reply_text(f"❌ Faylni Telegram'dan yuklab bo'lmadi: {str(e)[:150]}"); return
    res = await asyncio.to_thread(zaxira_ochish, raw, doc.file_name or '')
    if not res['ok']:
        await u.message.reply_text(f"❌ Tiklab bo'lmaydi: {res['error']}.\nHozirgi baza o'zgarmadi."); return
    tok = secrets.token_hex(4)
    path = os.path.join(_zaxira_dir(), f"tiklash_{tok}.db")
    with open(path, 'wb') as fh: fh.write(res['db'])
    _ui_yangi(ctx, 'zx', rs=path, rs_tok=tok)
    i = res['info']
    m = (f"♻️ ZAXIRADAN TIKLASH\n\nFayl: {doc.file_name}\n" + (f"Yaratilgan: {i['yaratildi']}\n" if i['yaratildi'] else "") +
         f"Sotuvlar: {i['sotuv']} ta (oxirgisi {i['oxirgi_sotuv']})\nTovarlar: {i['tovar']} ta\nKassa: {_usd2(i['kassa'])}\n"
         f"Baza hajmi: {_mb(i['hajm'])}\n\n⚠️ Hozirgi baza SHU nusxa bilan almashtiriladi. Undan keyingi yozuvlar yo'qoladi.\n"
         "Xavfsizlik uchun hozirgi holat avval avtomatik zaxiralanadi.")
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(
        [[_btn("♻️ Ha, shu nusxani tiklash", f"zx:rs:{tok}")], [_btn("❌ Bekor", "zx:rx")]]))


async def zx_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not can(u, 'zaxira'):
        await q.answer("Faqat egasi", show_alert=True); return
    parts = (q.data or '').split(':'); act = parts[1] if len(parts) > 1 else ''; arg = parts[2:]
    if act == 'x':
        ctx.user_data.pop('zx', None); await q.answer()
        return await _pos_chiqar(q, "💾 Zaxira oynasi yopildi.", None)
    st = _ui_ol(ctx, 'zx') or _ui_yangi(ctx, 'zx')
    st['wait'] = None
    m = r = None; alert = None
    if act == 'menu':
        m, r = _zx_menu()
    elif act == 'now':
        if not _ui_done(ctx, 'zxnow' + str(int(time.time() // 20))):
            await q.answer("⏳ Zaxira allaqachon tayyorlanmoqda"); return
        await q.answer("⏳ Zaxira tayyorlanmoqda...")
        res = await asyncio.to_thread(zaxira_yarat, "qo'lda")
        if not res['ok']:
            m, r = f"❌ Zaxira xatosi: {res['error']}", [[_btn("⬅️ Orqaga", "zx:menu")]]
        else:
            try:
                yub = await zaxira_yubor(ctx.bot, res, u.effective_chat.id)
            except Exception as e:
                log.exception("zaxira yuborish"); yub = False
                await q.message.reply_text(f"⚠️ Faylni yuborib bo'lmadi: {str(e)[:150]}")
            m0, r = _zx_menu()
            m = f"✅ Zaxira tayyor: {res['name']} ({_mb(res['size'])})" + (" — fayl yuqorida" if yub else "") + "\n\n" + m0
        return await _pos_chiqar(q, m, r)
    elif act == 'ls':
        m, r = _zx_royxat()
    elif act == 's':
        name = f"thermocrafts_{arg[0] if arg else ''}.zip"
        fl = {x['name']: x for x in zaxira_royxat()}
        if not ZAXIRA_RE.match(name) or name not in fl:
            alert = "Fayl topilmadi (eskirgan bo'lishi mumkin)"
        else:
            await q.answer("📤 Yuborilmoqda...")
            x = fl[name]
            try:
                await zaxira_yubor(ctx.bot, {'path': x['path'], 'name': name, 'size': x['size'], 'sabab': 'qayta yuborish'},
                                   u.effective_chat.id)
            except Exception as e:
                await q.message.reply_text(f"⚠️ Yuborib bo'lmadi: {str(e)[:150]}")
            return
    elif act == 't':
        st['wait'] = 'vaqt'
        m, r = "⏰ Zaxira vaqtini yozing (Toshkent), masalan 23:30:", [[_btn("⬅️ Orqaga", "zx:menu")]]
    elif act == 'n':
        qator = [3, 7, 14, 30]; cur = _zaxira_soni()
        soz_yoz('zaxira_soni', next((v for v in qator if v > cur), qator[0]))
        m, r = _zx_menu()
    elif act in ('d', 'tg'):
        kalit = 'zaxira_kunlik' if act == 'd' else 'zaxira_tg'
        soz_yoz(kalit, '0' if soz(kalit) == '1' else '1'); m, r = _zx_menu()
    elif act == 'rx':
        p_ = st.pop('rs', None)
        if p_:
            try: os.remove(p_)
            except OSError: pass
        m, r = "❎ Tiklash bekor qilindi. Baza o'zgarmadi.", None
    elif act == 'rs':
        tok = arg[0] if arg else ''
        p_ = st.get('rs')
        if not p_ or st.get('rs_tok') != tok or not os.path.exists(p_) or not _ui_done(ctx, 'zxrs' + tok):
            await q.answer("Eskirgan yoki allaqachon bajarilgan. Faylni qayta yuboring.", show_alert=True); return
        await q.answer("⏳ Tiklanmoqda...")
        with open(p_, 'rb') as fh: data = fh.read()
        try:
            res = await asyncio.to_thread(zaxira_tikla, data)
        except Exception as e:
            log.exception("zaxira_tikla")
            return await _pos_chiqar(q, f"❌ Tiklashda xato: {str(e)[:200]}", None)
        finally:
            try: os.remove(p_)
            except OSError: pass
            st.pop('rs', None)
        m = ("✅ Baza zaxiradan tiklandi.\n" + (f"Oldingi holat nusxasi: {res['oldingi']}\n" if res['oldingi'] else
                                              f"⚠️ Oldingi holatni zaxiralab bo'lmadi: {res['oldingi_xato']}\n") +
             f"💵 Kassa: {_usd2(res['kassa'])}\nXodimlar /start bossin (menyu yangilanadi).")
        return await _pos_chiqar(q, m, None)
    else:
        alert = "Eski tugma"
    await q.answer(alert[:190] if alert else None, show_alert=bool(alert))
    if m is not None: await _pos_chiqar(q, m, r)


async def zx_matn(u, ctx, msg):
    st = _ui_ol(ctx, 'zx')
    if not st or st.get('wait') != 'vaqt' or not can(u, 'zaxira'): return False
    mt = re.fullmatch(r'\s*([01]?\d|2[0-3])[:.]([0-5]\d)\s*', msg or '')
    if not mt:
        await u.message.reply_text("⚠️ Vaqtni HH:MM ko'rinishida yozing, masalan 23:30"); return True
    st['wait'] = None
    soz_yoz('zaxira_vaqt', f"{int(mt.group(1)):02d}:{mt.group(2)}")
    m, r = _zx_menu()
    await u.message.reply_text("✅ Vaqt saqlandi.\n\n" + m, reply_markup=InlineKeyboardMarkup(r))
    return True


# ── 📥 QAYTARISH (to'liq / qisman) ────────────────────────────────────────────────────
# Usul: qaytarish sanasida MANFIY sotuv qatori (qty<0, revenue<0, profit<0, return_of=<asl sotuv>) yoziladi.
# Shu sabab barcha hisobotlar (P&L, sotuvchi, TOP tovar, mijoz, kunlik) o'zgartirishsiz to'g'ri chiqadi va
# yopilgan o'tgan oy raqamlari o'zgarmaydi. Tushum/tannarx asl sotuvga PROPORSIONAL (chegirma ham shunday).
_SOTUV_KEYS = ('id', 'date', 'time', 'product', 'qty', 'unit_cost', 'revenue', 'profit', 'discount', 'customer',
               'customer_type', 'reversed', 'seller_id', 'seller_name', 'customer_id', 'return_of')


def _sotuv_qator(c, sid):
    c.execute("SELECT id,date,time,product,qty,COALESCE(unit_cost,0),COALESCE(revenue,0),COALESCE(profit,0),COALESCE(discount,0),"
              "COALESCE(customer,''),COALESCE(customer_type,'B2C'),reversed,COALESCE(seller_id,0),COALESCE(seller_name,''),"
              "COALESCE(customer_id,0),COALESCE(return_of,0) FROM sales WHERE id=?", (int(sid),))
    r = c.fetchone()
    return dict(zip(_SOTUV_KEYS, r)) if r else None


def _qaytgan(c, sid):
    c.execute("SELECT COALESCE(SUM(-qty),0), COALESCE(SUM(-revenue),0) FROM sales WHERE return_of=? AND reversed=0", (int(sid),))
    n, s = c.fetchone()
    return int(n or 0), round(s or 0, 2)


def _sotuv_pid(c, sid, product):
    c.execute("SELECT product_id FROM stock_moves WHERE kind='sotuv' AND ref=? ORDER BY id DESC LIMIT 1", (f's{sid}',))
    r = c.fetchone()
    if r: return r[0]
    c.execute('SELECT id FROM products WHERE name=?', (product,)); r = c.fetchone()
    return r[0] if r else None


def _sotuv_naqdmi(c, sid):
    """Sotuv puli kassaga tushganmi → (True, usul). Tushmagan (nasiya/eski import) → (False, None)."""
    c.execute("SELECT COALESCE(NULLIF(payment_method,''),'naqd') FROM cash_box WHERE type='kirim' AND note LIKE ? ORDER BY id LIMIT 1",
              (f'%(#{int(sid)})',))
    r = c.fetchone()
    return (True, r[0]) if r else (False, None)


def _nasiya_qarz_top(c, sid, s):
    """Nasiya sotuvning ochiq debitorligi → (debt_id, qoldiq) yoki None (_nasiya_qaytar bilan bir xil qidiruv)."""
    c.execute(f"SELECT id, amount, note FROM debts WHERE paid=0 AND type IN {DEBITOR_SQL} AND note LIKE ? ORDER BY id DESC",
              (f'%#s{int(sid)}%',))
    tag = re.compile(rf"#s{int(sid)}(?!\d)")
    hit = next((r for r in c.fetchall() if tag.search(r[2] or '')), None)
    if not hit and (s.get('customer') or '').strip():
        c.execute(f"SELECT id, amount, note FROM debts WHERE paid=0 AND type IN {DEBITOR_SQL} "
                  "AND person=? AND date=? AND note LIKE ? AND note NOT LIKE '%#s%' ORDER BY id DESC LIMIT 1",
                  (s['customer'], s['date'], f"nasiya:%{s['product']} x{s['qty']}%"))
        hit = c.fetchone()
    return (hit[0], round(hit[1] or 0, 2)) if hit else None


def _qaytarish_reja(c, plan):
    """Tekshiradi va hisoblaydi (yozmaydi). ValueError — foydalanuvchiga ko'rsatiladigan sabab."""
    lines, seen = [], set()
    for ln in plan.get('lines') or []:
        sid = int(ln['sale_id']); n = int(ln.get('qty') or 0)
        if n <= 0: continue
        if sid in seen: raise ValueError("Bitta sotuv qatori ikki marta tanlangan")
        seen.add(sid)
        s = _sotuv_qator(c, sid)
        if not s: raise ValueError(f"Sotuv #{sid} topilmadi")
        if s['reversed']: raise ValueError(f"Sotuv #{sid} bekor qilingan")
        if s['return_of'] or s['qty'] <= 0: raise ValueError(f"#{sid} — bu qaytarish yozuvi, sotuv emas")
        qn, qs = _qaytgan(c, sid)
        mavjud = s['qty'] - qn
        if n > mavjud:
            raise ValueError(f"{s['product']}: faqat {max(0, mavjud)} ta qaytarish mumkin" + (f" ({qn} tasi avval qaytgan)" if qn else ""))
        rev = round(s['revenue'] - qs, 2) if n == mavjud else round(s['revenue'] * n / s['qty'], 2)
        cogs = round((s['unit_cost'] or 0) * n, 2)
        c.execute("SELECT id, serial FROM serials WHERE sale_id=? AND status='sotilgan' ORDER BY id", (sid,))
        sotilgan = dict(c.fetchall())
        sers = [int(x) for x in (ln.get('serials') or [])]
        if sotilgan:
            if not sers and n == len(sotilgan): sers = list(sotilgan)
            if len(set(sers)) != n or any(x not in sotilgan for x in sers):
                raise ValueError(f"{s['product']}: qaytariladigan serial raqamni tanlang ({n} ta)")
        else:
            sers = []
        naqd, usul = _sotuv_naqdmi(c, sid)
        lines.append({'sale': s, 'sid': sid, 'qty': n, 'rev': rev, 'cogs': cogs, 'pid': _sotuv_pid(c, sid, s['product']),
                      'serials': sers, 'serial_txt': [sotilgan[x] for x in sers], 'naqd': naqd, 'usul': usul, 'mavjud': mavjud})
    if not lines: raise ValueError("Qaytariladigan tovar tanlanmagan")
    qarz_reja = {}
    for L in lines:
        L['qarzdan'] = 0.0; L['did'] = None
        if not L['naqd']:
            hit = _nasiya_qarz_top(c, L['sid'], L['sale'])
            if hit:
                did, amt = hit
                part = round(min(L['rev'], max(0.0, round(amt - qarz_reja.get(did, 0), 2))), 2)
                if part > 0:
                    qarz_reja[did] = round(qarz_reja.get(did, 0) + part, 2); L['qarzdan'] = part; L['did'] = did
        L['naqddan'] = round(L['rev'] - L['qarzdan'], 2)
    usul = next((L['usul'] for L in lines if L['naqd']), None)
    return {'lines': lines, 'jami': round(sum(L['rev'] for L in lines), 2), 'cogs': round(sum(L['cogs'] for L in lines), 2),
            'qarzdan': round(sum(qarz_reja.values()), 2), 'naqd_qaytar': round(sum(L['naqddan'] for L in lines), 2),
            'qarz_reja': qarz_reja, 'asl_usul': usul or 'naqd'}


def qaytarish_hisob(plan):
    """Oldindan ko'rish: {'ok', ...reja} yoki {'ok': False, 'error'}."""
    conn = db(); c = conn.cursor()
    try:
        R = _qaytarish_reja(c, plan); R['ok'] = True; return R
    except ValueError as e:
        return {'ok': False, 'error': str(e)}
    finally:
        conn.close()


def _serial_log(c, serial_id, event, ref='', note='', user=None):
    c.execute("INSERT INTO serial_log (serial_id,date,event,ref,note,user_name) VALUES (?,?,?,?,?,?)",
              (serial_id, _hm(), event, ref, (note or '')[:300], (user or (0, ''))[1] if user else ''))


def _sabab_matn(plan):
    k = plan.get('reason') or 'boshqa'
    t = (plan.get('reason_text') or '').strip()
    return (QAYTARISH_SABAB_NOMI.get(k, k) + (f": {t}" if t else ''))[:200]


def qaytarish_bajar(plan, user=None, return_id=None):
    """BITTA tranzaksiya: manfiy sotuv qatori + astatka (yoki brak) + pul (kassadan / qarzdan) + serial/kafolat + op_log.
    return_id — sotuvchi so'rovini tasdiqlash (status 'kutilmoqda' → 'ok')."""
    if is_closed(today()):
        return {'ok': False, 'error': f"{today()[:7]} davri yopilgan — qaytarish yozib bo'lmaydi (/och {today()[:7]})"}
    user = user or (0, '')
    now = datetime.now(); d, t = now.strftime('%Y-%m-%d'), now.strftime('%H:%M')
    sabab = _sabab_matn(plan); brak = bool(plan.get('brak'))
    conn = db(); c = conn.cursor(); cids = set()
    try:
        R = _qaytarish_reja(c, plan)
        method = tolov_usuli(plan.get('method') or '') or R['asl_usul']
        if method not in TOLOV_USULLARI: method = 'naqd'
        first = R['lines'][0]['sale']
        if return_id:
            c.execute("UPDATE returns SET status='ok', approved_by=?, approved_name=?, date=?, created=? WHERE id=? AND status='kutilmoqda'",
                      (int(user[0] or 0), user[1] or '', d, f"{d} {t}", int(return_id)))
            if c.rowcount != 1: raise ValueError("So'rov allaqachon ko'rib chiqilgan")
            rid = int(return_id)
        else:
            c.execute("INSERT INTO returns (created,date,customer,customer_id,reason,note,status,approved_by,approved_name,plan) "
                      "VALUES (?,?,?,?,?,?,'ok',?,?,?)", (f"{d} {t}", d, first['customer'], first['customer_id'], sabab,
                                                          (plan.get('note') or '')[:300], int(user[0] or 0), user[1] or '',
                                                          json.dumps(plan, ensure_ascii=False)))
            rid = c.lastrowid
        c.execute('INSERT INTO op_log (date,time,op_type,data_json) VALUES (?,?,?,?)', (d, t, 'return', '{}'))
        op_id = c.lastrowid
        data = {'rid': rid, 'sale_rows': [], 'moves': [], 'cash_ids': [], 'cash_sum': 0.0, 'method': method, 'debts': [],
                'expense_ids': [], 'brak_ids': [], 'warranty': [], 'serials': [], 'jami': R['jami'],
                'product': ", ".join(f"{L['sale']['product']} x{L['qty']}" for L in R['lines'])}
        for L in R['lines']:
            s = L['sale']; uc = s['unit_cost'] or 0; n = L['qty']
            c.execute("INSERT INTO sales (date,time,product,qty,unit_cost,revenue,profit,discount,customer,customer_type,reversed,"
                      "seller_id,seller_name,customer_id,return_of) VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?,?)",
                      (d, t, s['product'], -n, uc, -L['rev'], -round(L['rev'] - L['cogs'], 2), s['discount'], s['customer'],
                       s['customer_type'], s['seller_id'], s['seller_name'], s['customer_id'], L['sid']))
            rsid = c.lastrowid; data['sale_rows'].append(rsid)
            if s['customer_id']: cids.add(s['customer_id'])
            if L['pid']:
                if not brak:
                    c.execute('SELECT COALESCE(qty,0), COALESCE(cost,0) FROM products WHERE id=?', (L['pid'],))
                    q0, c0 = c.fetchone(); baza = max(0, q0)
                    new_cost = round((baza * c0 + n * uc) / (baza + n), 2) if baza + n > 0 else uc
                    res = stock_move(c, L['pid'], n, 'qaytarish', f"#R{rid}: {sabab}"[:120], f'r{rid}', user, uc, new_cost)
                    if res: data['moves'].append({'id': res[0], 'tur': 'yaxshi'})
                else:
                    m1 = stock_move(c, L['pid'], n, 'qaytarish', f"#R{rid}: {sabab} (brak)"[:120], f'r{rid}', user, uc)
                    m2 = stock_move(c, L['pid'], -n, 'chiqim', f"Brak: qaytarish #R{rid}", f'r{rid}', user, uc, allow_negative=True)
                    if m1 and m2: data['moves'] += [{'id': m1[0], 'tur': 'brak'}, {'id': m2[0], 'tur': 'brak'}]
                    summa = round(uc * n, 2); eid = None
                    if summa > 0:
                        c.execute('INSERT INTO expenses (date,amount,category,expense_type,note) VALUES (?,?,?,?,?)',
                                  (d, summa, 'spisanie', 'period', f"Brak qaytarish: {s['product']} x{n} (#R{rid})"))
                        eid = c.lastrowid; data['expense_ids'].append(eid)
                    c.execute("INSERT INTO brak_tovarlar (date,product_id,product,qty,unit_cost,manba,return_id,expense_id,serials,note) "
                              "VALUES (?,?,?,?,?,'qaytarish',?,?,?,?)",
                              (d, L['pid'], s['product'], n, uc, rid, eid or 0, ",".join(map(str, L['serials'])), sabab))
                    data['brak_ids'].append(c.lastrowid)
            for sr in L['serials']:
                c.execute("SELECT status, sale_id, sold_date, customer, customer_id, warranty_end, serial FROM serials WHERE id=?", (sr,))
                old = list(c.fetchone())
                data['serials'].append({'id': sr, 'old': old[:6]})
                c.execute("UPDATE serials SET status=?, sale_id=0, sold_date='', customer='', customer_id=0, warranty_end='' WHERE id=?",
                          ('brak' if brak else 'omborda', sr))
                _serial_log(c, sr, 'qaytarildi', f'#R{rid}', sabab + (" · brak" if brak else " · omborga"), user)
                c.execute("SELECT id, status FROM warranties WHERE sale_id=? AND serial=?", (L['sid'], old[6]))
                for wid, wst in c.fetchall():
                    data['warranty'].append({'id': wid, 'old': wst})
                    c.execute("UPDATE warranties SET status='returned' WHERE id=?", (wid,))
            if n == L['mavjud']:                       # qator to'liq qaytdi — seriallsiz kafolat ham yopiladi
                c.execute("SELECT id, status FROM warranties WHERE sale_id=? AND COALESCE(serial,'')='' AND status='active'", (L['sid'],))
                for wid, wst in c.fetchall():
                    data['warranty'].append({'id': wid, 'old': wst})
                    c.execute("UPDATE warranties SET status='returned' WHERE id=?", (wid,))
            c.execute("INSERT INTO return_lines (return_id,sale_id,product_id,product,qty,revenue,unit_cost,profit,return_sale_id,brak,serials) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (rid, L['sid'], L['pid'] or 0, s['product'], n, L['rev'], uc,
                                                         round(L['rev'] - L['cogs'], 2), rsid, 1 if brak else 0,
                                                         ", ".join(L['serial_txt'])))
        for did, part in R['qarz_reja'].items():
            c.execute("SELECT amount, paid, note FROM debts WHERE id=?", (did,))
            a, pd, nt = c.fetchone()
            yangi = round((a or 0) - part, 2)
            c.execute("UPDATE debts SET amount=?, paid=?, note=? WHERE id=?",
                      (max(0.0, yangi), 1 if yangi <= 0.005 else 0, f"{nt or ''} | -{part:.2f}: qaytarish #R{rid}", did))
            data['debts'].append({'id': did, 'part': part, 'old_amount': a, 'old_paid': pd, 'old_note': nt})
        if R['naqd_qaytar'] > 0:
            c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                      (d, t, 'chiqim', R['naqd_qaytar'], 'qaytarish', f"Qaytarish #R{rid}: {data['product']}"[:200], method))
            data['cash_ids'].append(c.lastrowid); data['cash_sum'] = R['naqd_qaytar']
        c.execute("UPDATE returns SET total=?, cogs=?, refund_cash=?, refund_debt=?, method=?, brak=?, op_id=? WHERE id=?",
                  (R['jami'], R['cogs'], R['naqd_qaytar'], R['qarzdan'], method, 1 if brak else 0, op_id, rid))
        c.execute('UPDATE op_log SET data_json=? WHERE id=?', (json.dumps(data, ensure_ascii=False), op_id))
        conn.commit()
    except ValueError as e:
        conn.rollback(); conn.close()
        return {'ok': False, 'error': str(e)}
    except Exception:
        conn.rollback(); conn.close()
        raise
    conn.close()
    for cid in cids:
        try: yangila_jami(cid)
        except Exception as e: log.warning(f'yangila_jami: {e}')
    return {'ok': True, 'rid': rid, 'op_id': op_id, 'jami': R['jami'], 'naqd': R['naqd_qaytar'], 'qarzdan': R['qarzdan'],
            'method': method, 'brak': brak, 'sabab': sabab, 'customer': first['customer'], 'sana': f"{d} {t}",
            'qatorlar': [{'nom': L['sale']['product'], 'qty': L['qty'], 'summa': L['rev'], 'sid': L['sid'],
                          'serial': L['serial_txt']} for L in R['lines']]}


def reverse_return(op_id):
    """Qaytarishni bekor qiladi (/undo) — BITTA tranzaksiyada hamma narsa teskari."""
    conn = db(); c = conn.cursor()
    try:
        c.execute("SELECT date, data_json FROM op_log WHERE id=? AND op_type='return' AND reversed=0", (op_id,))
        r = c.fetchone()
        if not r: conn.close(); return False, "Topilmadi yoki allaqachon qaytarilgan"
        for s_ in (r[0], today()):
            if is_closed(s_):
                conn.close(); return False, f"{s_[:7]} davri yopilgan — qaytarishni bekor qilib bo'lmaydi (/och {s_[:7]})"
        d = json.loads(r[1] or '{}'); rid = d.get('rid')
        c.execute("UPDATE op_log SET reversed=1 WHERE id=? AND reversed=0", (op_id,))
        if c.rowcount != 1: raise ValueError("Topilmadi yoki allaqachon qaytarilgan")
        for bid in d.get('brak_ids', []):
            c.execute("SELECT status FROM brak_tovarlar WHERE id=?", (bid,))
            b = c.fetchone()
            if b and b[0] != 'brak': raise ValueError("Brak tovar holati o'zgargan (tuzatilgan/zavodga) — bekor qilib bo'lmaydi")
            c.execute("UPDATE brak_tovarlar SET status='bekor', updated=? WHERE id=?", (_hm(), bid))
        for mv in reversed(d.get('moves', [])):
            c.execute("SELECT product_id, qty, unit_cost FROM stock_moves WHERE id=?", (mv['id'],))
            m = c.fetchone()
            if not m: continue
            pid, qty, uc = m
            if mv['tur'] == 'yaxshi' and qty > 0:
                c.execute('SELECT COALESCE(qty,0), COALESCE(cost,0) FROM products WHERE id=?', (pid,))
                q0, c0 = c.fetchone(); q1 = q0 - qty
                nc = round((max(0, q0) * c0 - qty * (uc or 0)) / q1, 2) if q1 > 0 else c0
                res = stock_move(c, pid, -qty, 'tuzatish', f"bekor: qaytarish #R{rid}", f'r{rid}u', unit_cost=uc,
                                 new_cost=(nc if nc > 0 else c0))
            else:
                res = stock_move(c, pid, -qty, 'tuzatish', f"bekor: qaytarish #R{rid}", f'r{rid}u', unit_cost=uc, allow_negative=qty < 0)
            if res is None: raise ValueError("Astatka yetmaydi — qaytgan tovar allaqachon sotilgan")
        for sid_ in d.get('sale_rows', []):
            c.execute("UPDATE sales SET reversed=1 WHERE id=?", (sid_,))
        for eid in d.get('expense_ids', []):
            c.execute("UPDATE expenses SET reversed=1 WHERE id=?", (eid,))
        for w in d.get('warranty', []):
            c.execute("UPDATE warranties SET status=? WHERE id=?", (w['old'], w['id']))
        for s in d.get('serials', []):
            c.execute("SELECT status, sale_id FROM serials WHERE id=?", (s['id'],))
            cur = c.fetchone()
            if not cur or cur[0] not in ('omborda', 'brak') or cur[1]:
                raise ValueError("Qaytgan serial qayta sotilgan — bekor qilib bo'lmaydi")
            o = s['old']
            c.execute("UPDATE serials SET status=?, sale_id=?, sold_date=?, customer=?, customer_id=?, warranty_end=? WHERE id=?",
                      (o[0], o[1], o[2], o[3], o[4], o[5], s['id']))
            _serial_log(c, s['id'], 'qaytarish bekor', f'#R{rid}')
        for db_ in d.get('debts', []):
            c.execute("UPDATE debts SET amount=ROUND(amount+?,2), paid=0, note=COALESCE(note,'') || ? WHERE id=?",
                      (db_['part'], f" | bekor #R{rid}", db_['id']))
        if d.get('cash_sum'):
            now = datetime.now()
            c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                      (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'), 'kirim', d['cash_sum'], 'qaytarish',
                       f"qaytarish bekor (#R{rid})", d.get('method') or 'naqd'))
        c.execute("UPDATE returns SET status='bekor' WHERE id=?", (rid,))
        c.execute("SELECT DISTINCT COALESCE(customer_id,0) FROM sales WHERE id IN (%s)" % ",".join("?" * len(d.get('sale_rows') or [0])),
                  d.get('sale_rows') or [0])
        cids = [x[0] for x in c.fetchall() if x[0]]
        conn.commit()
    except ValueError as e:
        conn.rollback(); conn.close()
        return False, str(e)
    except Exception:
        conn.rollback(); conn.close()
        raise
    conn.close()
    for cid in cids:
        try: yangila_jami(cid)
        except Exception: pass
    return True, "qaytarildi"


def qaytarish_sorov(plan, user):
    """Sotuvchi: so'rov yaratadi (hech narsa o'zgarmaydi). Egasi/admin tasdiqlasa — qaytarish_bajar(return_id=...)."""
    R = qaytarish_hisob(plan)
    if not R['ok']: return R
    if is_closed(today()): return {'ok': False, 'error': f"{today()[:7]} davri yopilgan"}
    first = R['lines'][0]['sale']
    conn = db(); c = conn.cursor()
    c.execute("INSERT INTO returns (created,date,customer,customer_id,reason,note,total,refund_cash,refund_debt,brak,status,"
              "requested_by,requested_name,plan) VALUES (?,?,?,?,?,?,?,?,?,?,'kutilmoqda',?,?,?)",
              (_hm(), today(), first['customer'], first['customer_id'], _sabab_matn(plan), (plan.get('note') or '')[:300],
               R['jami'], R['naqd_qaytar'], R['qarzdan'], 1 if plan.get('brak') else 0, int(user[0] or 0), user[1] or '',
               json.dumps(plan, ensure_ascii=False)))
    rid = c.lastrowid; conn.commit(); conn.close()
    R['rid'] = rid
    return R


def qaytarish_rad(rid, user):
    conn = db(); c = conn.cursor()
    c.execute("UPDATE returns SET status='rad', approved_by=?, approved_name=? WHERE id=? AND status='kutilmoqda'",
              (int(user[0] or 0), user[1] or '', int(rid)))
    n = c.rowcount; conn.commit(); conn.close()
    return n == 1


def brak_holat(bid, yangi, user=None):
    """Brak tovar: 'tuzatildi' — sotuvga qaytadi (astatka +, spisanie xarajati bekor); 'zavodga' — faqat holat."""
    if yangi not in ('tuzatildi', 'zavodga'): return {'ok': False, 'error': "Holat noma'lum"}
    if is_closed(today()): return {'ok': False, 'error': f"{today()[:7]} davri yopilgan"}
    conn = db(); c = conn.cursor()
    try:
        c.execute("SELECT product_id, product, qty, unit_cost, expense_id, serials, status FROM brak_tovarlar WHERE id=?", (bid,))
        r = c.fetchone()
        if not r or r[6] != 'brak': conn.close(); return {'ok': False, 'error': "Topilmadi yoki allaqachon ko'rib chiqilgan"}
        pid, nom, n, uc, eid, sers, _ = r
        sers = [int(x) for x in (sers or '').split(',') if x.strip().isdigit()]
        if yangi == 'tuzatildi':
            if eid:
                c.execute("SELECT date FROM expenses WHERE id=?", (eid,)); e = c.fetchone()
                if e and is_closed(e[0]):
                    conn.close(); return {'ok': False, 'error': f"Xarajat {e[0][:7]} davrida (yopilgan) — 📦 Ombor → Kirim orqali qo'shing"}
                c.execute("UPDATE expenses SET reversed=1 WHERE id=?", (eid,))
            c.execute('SELECT COALESCE(qty,0), COALESCE(cost,0) FROM products WHERE id=?', (pid,))
            q0, c0 = c.fetchone(); baza = max(0, q0)
            nc = round((baza * c0 + n * uc) / (baza + n), 2) if baza + n > 0 else uc
            stock_move(c, pid, n, 'kirim', f"brak tuzatildi #B{bid}", f'b{bid}', user, uc, nc)
            for sr in sers:
                c.execute("UPDATE serials SET status='omborda' WHERE id=? AND status='brak'", (sr,))
                _serial_log(c, sr, 'brak tuzatildi', f'#B{bid}', '', user)
        else:
            for sr in sers:
                c.execute("UPDATE serials SET status='chiqarildi' WHERE id=? AND status='brak'", (sr,))
                _serial_log(c, sr, 'zavodga qaytarildi', f'#B{bid}', '', user)
        c.execute("UPDATE brak_tovarlar SET status=?, updated=? WHERE id=?", (yangi, _hm(), bid))
        conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return {'ok': True, 'nom': nom, 'qty': n}


# ── 📥 Qaytarish: chek, ro'yxatlar va tugmali oyna (prefiks 'qr:') ─────────────────────
def qaytarish_chek(rid, rate=None):
    conn = db(); c = conn.cursor()
    c.execute("SELECT created,customer,reason,method,total,refund_cash,refund_debt,brak,status,approved_name,requested_name,plan "
              "FROM returns WHERE id=?", (rid,))
    r = c.fetchone()
    if not r: conn.close(); return "Qaytarish topilmadi"
    c.execute("SELECT sale_id, product, qty, revenue, serials FROM return_lines WHERE return_id=? ORDER BY id", (rid,))
    lines = c.fetchall(); conn.close()
    rate = rate or get_exchange_rate()
    st = r[8]
    sar = {'ok': "🧾 QAYTARISH CHEKI", 'kutilmoqda': "⏳ QAYTARISH SO'ROVI", 'rad': "🚫 RAD ETILGAN SO'ROV",
           'bekor': "↩️ BEKOR QILINGAN QAYTARISH"}.get(st, "🧾 QAYTARISH")
    out = [f"{sar} №R-{rid}", r[0] or '']
    if r[1]: out.append(f"Mijoz: {r[1]}")
    if not lines:                                         # so'rov — reja bo'yicha
        R = qaytarish_hisob(json.loads(r[11] or '{}'))
        if R.get('ok'):
            lines = [(L['sid'], L['sale']['product'], L['qty'], L['rev'], ", ".join(L['serial_txt'])) for L in R['lines']]
    sids = sorted({x[0] for x in lines})
    if sids: out.append("Asl sotuv: " + ", ".join(f"#{s}" for s in sids))
    out.append("──────────────")
    for n, (sid, nom, q, rev, ser) in enumerate(lines, 1):
        out.append(f"{n}. {nom} × {q} = {_usd2(rev)}" + (f"\n   SN: {ser}" if ser else ""))
    out.append("──────────────")
    out.append(f"JAMI QAYTARISH: {_usd2(r[4] or 0)} ≈ {_som(r[4] or 0, rate)}")
    if (r[5] or 0) > 0: out.append(f"💵 Pul qaytariladi: {_usd2(r[5])} ({POS_USUL_NOMI.get(r[3], r[3] or 'naqd')})")
    if (r[6] or 0) > 0: out.append(f"📝 Mijoz qarzidan ayiriladi: {_usd2(r[6])}")
    out.append(f"Sabab: {r[2]}")
    out.append("Holati: " + ("🔧 brak — hisobdan chiqarildi" if r[7] else "📦 omborga qaytdi (sotuvga yaroqli)"))
    if r[10]: out.append(f"So'radi: {r[10]}")
    if r[9] and st != 'kutilmoqda': out.append(f"{'Rad etdi' if st == 'rad' else 'Tasdiqladi'}: {r[9]}")
    if st == 'ok': out.append("Xato bo'lsa: /undo")
    return "\n".join(out)


_QR_COLS = "id,date,time,product,qty,revenue,COALESCE(customer,''),COALESCE(customer_id,0),COALESCE(seller_id,0),COALESCE(seller_name,'')"


def _sot_guruhla(rows):
    """rows id DESC. Ketma-ket id + bir xil sana/vaqt/sotuvchi/mijoz → bitta chek (№S-<birinchi id>)."""
    gs = []
    for r in rows:
        key = (r[1], r[2], r[8], r[7], r[6])
        if gs and gs[-1]['key'] == key and gs[-1]['ids'][-1] - r[0] == 1:
            gs[-1]['ids'].append(r[0]); gs[-1]['rows'].append(r)
        else:
            gs.append({'key': key, 'ids': [r[0]], 'rows': [r]})
    for g in gs:
        g['ids'].reverse(); g['rows'].reverse(); g['first'] = g['ids'][0]
    return gs


def _qaytgan_map(c, ids):
    if not ids: return {}
    out = {}
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        c.execute(f"SELECT return_of, SUM(-qty) FROM sales WHERE reversed=0 AND return_of IN ({','.join('?' * len(part))}) "
                  "GROUP BY return_of", part)
        out.update({a: int(b or 0) for a, b in c.fetchall()})
    return out


def sotuv_guruhlari(seller_id=None, customer_id=None, limit=8, offset=0, kun=90):
    since = (datetime.now() - timedelta(days=kun)).strftime('%Y-%m-%d')
    sql = f"SELECT {_QR_COLS} FROM sales WHERE reversed=0 AND COALESCE(return_of,0)=0 AND qty>0 AND date>=?"
    args = [since]
    if seller_id: sql += " AND seller_id=?"; args.append(int(seller_id))
    if customer_id: sql += " AND customer_id=?"; args.append(int(customer_id))
    conn = db(); c = conn.cursor()
    c.execute(sql + " ORDER BY id DESC LIMIT 800", args)
    rows = c.fetchall()
    qm = _qaytgan_map(c, [r[0] for r in rows]); conn.close()
    gs = [g for g in _sot_guruhla(rows) if any(r[4] - qm.get(r[0], 0) > 0 for r in g['rows'])]
    for g in gs:
        g['qoldi'] = {r[0]: r[4] - qm.get(r[0], 0) for r in g['rows']}
    return gs[offset:offset + limit], len(gs)


def sotuv_guruhi(sid):
    """Sotuv id → shu sotuv kirgan chek (guruh) yoki None."""
    conn = db(); c = conn.cursor()
    c.execute(f"SELECT {_QR_COLS} FROM sales WHERE id=? AND reversed=0 AND COALESCE(return_of,0)=0 AND qty>0", (int(sid),))
    t = c.fetchone()
    if not t: conn.close(); return None
    c.execute(f"SELECT {_QR_COLS} FROM sales WHERE reversed=0 AND COALESCE(return_of,0)=0 AND qty>0 AND date=? AND time=? "
              "AND COALESCE(seller_id,0)=? AND COALESCE(customer_id,0)=? AND COALESCE(customer,'')=? AND id BETWEEN ? AND ? "
              "ORDER BY id DESC", (t[1], t[2], t[8], t[7], t[6], t[0] - 80, t[0] + 80))
    rows = c.fetchall()
    qm = _qaytgan_map(c, [r[0] for r in rows]); conn.close()
    g = next((g for g in _sot_guruhla(rows) if sid in g['ids']), None)
    if g: g['qoldi'] = {r[0]: r[4] - qm.get(r[0], 0) for r in g['rows']}
    return g


def _qr_serials(sid):
    conn = db(); c = conn.cursor()
    c.execute("SELECT id, serial FROM serials WHERE sale_id=? AND status='sotilgan' ORDER BY id", (int(sid),))
    r = c.fetchall(); conn.close(); return r


def _qr_rol(u):
    if can(u, 'qaytarish'): return 'bajar'
    if can(u, 'qaytarish_sorov'): return 'sorov'
    return None


def _qr_kutilmoqda_soni():
    try:
        conn = db(); n = conn.execute("SELECT COUNT(*) FROM returns WHERE status='kutilmoqda'").fetchone()[0]; conn.close()
        return n
    except sqlite3.OperationalError:
        return 0


def _qr_menu(u):
    rows = [[_btn("🕘 Oxirgi sotuvlar", "qr:la:0"), _btn("👤 Mijoz bo'yicha", "qr:cs")],
            [_btn("🔎 Chek № / serial", "qr:fd")]]
    if can(u, 'qaytarish'):
        rows.append([_btn(f"⏳ So'rovlar ({_qr_kutilmoqda_soni()})", "qr:rq"), _btn("📜 Tarix", "qr:hs:0")])
        rows.append([_btn("🔧 Brak tovarlar", "qr:br")])
    rows.append(_x_btn('qr'))
    m = ("📥 QAYTARISH\n\nMijoz tovarni qaytardimi? Avval sotuvni toping:\n"
         "• Oxirgi sotuvlar ro'yxatidan\n• Mijoz ismi bo'yicha\n• Chek raqami (S-123) yoki serial raqam bo'yicha")
    if _qr_rol(u) == 'sorov':
        m += "\n\nℹ️ Siz so'rov yuborasiz — egasi/admin tasdiqlagach pul va astatka o'zgaradi."
    return m, rows


def _qr_guruh_btn(g):
    d = g['rows'][0]
    jami = sum(r[5] for r in g['rows'])
    return _btn(f"S-{g['first']} · {d[1][8:10]}.{d[1][5:7]} {d[2]} · {(d[6] or 'mijozsiz')[:16]} · {_usd2(jami)}", f"qr:g:{g['first']}")


def _qr_royxat(u, page=0, cid=None):
    x = xodim(u) or {}
    gs, n = sotuv_guruhlari(seller_id=(x.get('id') if _qr_rol(u) == 'sorov' else None), customer_id=cid,
                            limit=8, offset=page * 8)
    sar = "👤 Mijoz sotuvlari" if cid else "🕘 Oxirgi sotuvlar (90 kun)"
    if not gs:
        return f"{sar}: qaytariladigan sotuv topilmadi.", [[_btn("⬅️ Orqaga", "qr:menu")] + _x_btn('qr')]
    rows = [[_qr_guruh_btn(g)] for g in gs]
    nav = []
    cb = (lambda p: f"qr:cu:{cid}:{p}") if cid else (lambda p: f"qr:la:{p}")
    if page > 0: nav.append(_btn("◀️", cb(page - 1)))
    if (page + 1) * 8 < n: nav.append(_btn("▶️", cb(page + 1)))
    if nav: rows.append(nav)
    rows.append([_btn("⬅️ Orqaga", "qr:menu")] + _x_btn('qr'))
    return f"{sar} — chekni tanlang ({n} ta):", rows


def _qr_chek_ekran(st):
    g = sotuv_guruhi(st['g'])
    if not g: return "Bu sotuv topilmadi yoki bekor qilingan.", [[_btn("⬅️ Orqaga", "qr:menu")] + _x_btn('qr')]
    d = g['rows'][0]
    st['ids'] = list(g['ids'])
    m = [f"🧾 CHEK №S-{g['first']} · {d[1]} {d[2]}", f"Mijoz: {d[6] or '—'} · Sotuvchi: {d[9] or '—'}", ""]
    rows = []
    sel = st.setdefault('sel', {})
    for i, r in enumerate(g['rows'], 1):
        qoldi = g['qoldi'][r[0]]
        tan = sel.get(r[0], 0)
        m.append(f"{i}. {r[3]} × {r[4]} = {_usd2(r[5])}" + (f" (qaytgan: {r[4] - qoldi})" if qoldi < r[4] else ""))
        if qoldi > 0:
            rows.append([_btn(f"{'✅' if tan else '↩️'} {i}. {r[3][:22]} — {tan}/{qoldi}", f"qr:l:{r[0]}")])
    m.append("\nQaytariladigan qatorni bosing va sonini tanlang.")
    if any(sel.get(i, 0) for i in st['ids']):
        rows.append([_btn(f"➡️ Davom etish ({sum(sel.get(i, 0) for i in st['ids'])} dona)", "qr:nx")])
    rows.append([_btn("⬅️ Orqaga", "qr:menu")] + _x_btn('qr'))
    return "\n".join(m), rows


def _qr_qator_ekran(st, sid):
    g = sotuv_guruhi(st['g'])
    if not g or sid not in g['ids']: return _qr_chek_ekran(st)
    r = next(x for x in g['rows'] if x[0] == sid)
    qoldi = g['qoldi'][sid]
    sers = _qr_serials(sid)
    if sers:
        tan = st.setdefault('ser', {}).setdefault(sid, [])
        rows = [[_btn(f"{'✅' if s_id in tan else '⬜'} {sn}", f"qr:sn:{sid}:{s_id}")] for s_id, sn in sers[:20]]
        rows.append([_btn("✔ Tayyor", f"qr:g:{st['g']}")])
        return f"🔢 {r[3]}: qaytariladigan serial raqam(lar)ni belgilang:", rows
    m = f"↩️ {r[3]}\nSotilgan: {r[4]} ta · qaytarish mumkin: {qoldi} ta\nNechta qaytariladi?"
    nums = [_btn(str(k), f"qr:lq:{sid}:{k}") for k in range(1, min(qoldi, 8) + 1)]
    rows = [nums[i:i + 4] for i in range(0, len(nums), 4)]
    if qoldi > 8: rows.append([_btn(f"Hammasi ({qoldi})", f"qr:lq:{sid}:{qoldi}")])
    rows.append([_btn("0 — qaytarilmaydi", f"qr:lq:{sid}:0"), _btn("⬅️ Orqaga", f"qr:g:{st['g']}")])
    return m, rows


def _qr_plan(st):
    return {'lines': [{'sale_id': sid, 'qty': n, 'serials': st.get('ser', {}).get(sid, [])}
                      for sid, n in st.get('sel', {}).items() if n > 0 and sid in st.get('ids', [])],
            'reason': st.get('reason') or 'boshqa', 'reason_text': st.get('reason_text') or '',
            'brak': bool(st.get('brak')), 'method': st.get('method') or '', 'note': ''}


def _qr_sabab_ekran():
    rows = [[_btn(t, f"qr:rs:{k}")] for k, t in QAYTARISH_SABABLARI]
    rows.append([_btn("⬅️ Orqaga", "qr:back")] + _x_btn('qr'))
    return "❓ Qaytarish sababi:", rows


def _qr_holat_ekran(st):
    rows = [[_btn("📦 Sotuvga yaroqli — omborga", "qr:bk:0")], [_btn("🔧 Brak — hisobdan chiqarish", "qr:bk:1")],
            [_btn("⬅️ Orqaga", "qr:nx")] + _x_btn('qr')]
    return (f"Sabab: {_sabab_matn(_qr_plan(st))}\n\n📦 Tovar holati qanday?\n"
            "• Yaroqli — omborga qaytadi, yana sotiladi\n• Brak — tannarxi xarajat (spisanie) bo'ladi, 🔧 Brak ro'yxatiga tushadi"), rows


def _qr_usul_ekran(st, R):
    cur = st.get('method') or R['asl_usul']
    rows = [[_btn(("✅ " if k == cur else "") + t, f"qr:mt:{k}") for k, t in POS_USULLAR[i:i + 2] if k != 'nasiya']
            for i in range(0, 6, 2)]
    rows = [r for r in rows if r]
    rows.append([_btn("➡️ Davom etish", "qr:ok0")])
    rows.append([_btn("⬅️ Orqaga", "qr:rs:" + (st.get('reason') or 'boshqa'))] + _x_btn('qr'))
    return f"💵 Mijozga {_usd2(R['naqd_qaytar'])} qaytariladi. Qaysi usulda?\n(Sotuvdagi usul: {POS_USUL_NOMI.get(R['asl_usul'])})", rows


def _qr_tasdiq_ekran(u, st):
    plan = _qr_plan(st)
    R = qaytarish_hisob(plan)
    if not R['ok']: return f"⚠️ {R['error']}", [[_btn("⬅️ Chekka qaytish", f"qr:g:{st['g']}")] + _x_btn('qr')]
    rate = get_exchange_rate()
    m = ["📥 QAYTARISHNI TASDIQLANG", ""]
    for L in R['lines']:
        m.append(f"• {L['sale']['product']} × {L['qty']} = {_usd2(L['rev'])}" + (f"\n   SN: {', '.join(L['serial_txt'])}" if L['serial_txt'] else ""))
    m.append(f"\nJAMI: {_usd2(R['jami'])} ≈ {_som(R['jami'], rate)}")
    if R['naqd_qaytar'] > 0:
        m.append(f"💵 Kassadan qaytariladi: {_usd2(R['naqd_qaytar'])} ({POS_USUL_NOMI.get(plan['method'] or R['asl_usul'])})")
    if R['qarzdan'] > 0: m.append(f"📝 Mijoz qarzidan ayiriladi: {_usd2(R['qarzdan'])}")
    m.append(f"Sabab: {_sabab_matn(plan)}")
    m.append("Holati: " + ("🔧 brak (hisobdan chiqariladi)" if plan['brak'] else "📦 omborga qaytadi"))
    st['tok'] = secrets.token_hex(3)
    if _qr_rol(u) == 'bajar':
        rows = [[_btn("✅ Tasdiqlash — qaytarish", f"qr:ok:{st['tok']}")]]
    else:
        rows = [[_btn("📨 Tasdiqlashga yuborish", f"qr:ok:{st['tok']}")]]
        m.append("\nℹ️ Egasi/admin tasdiqlagach bajariladi.")
    rows.append([_btn("⬅️ Orqaga", "qr:bk:" + ('1' if plan['brak'] else '0'))] + _x_btn('qr'))
    return "\n".join(m), rows


def _qr_tasdiqchilar():
    ids = [OWNER_ID] if OWNER_ID else []
    try:
        conn = db()
        ids += [r[0] for r in conn.execute("SELECT telegram_id FROM users WHERE role='admin' AND active=1")]
        conn.close()
    except sqlite3.OperationalError:
        pass
    return list(dict.fromkeys(i for i in ids if i))


async def _qr_sorov_yubor(bot, rid):
    m = qaytarish_chek(rid)
    kb = InlineKeyboardMarkup([[_btn("✅ Tasdiqlash", f"qr:ap:{rid}"), _btn("❌ Rad etish", f"qr:rj:{rid}")]])
    for tid in _qr_tasdiqchilar():
        try: await bot.send_message(chat_id=tid, text=m[:4000], reply_markup=kb)
        except Exception as e: log.warning("qaytarish so'rovi yuborilmadi %s: %s", tid, e)


def _qr_sorovlar():
    conn = db()
    rows = conn.execute("SELECT id, created, customer, total, requested_name FROM returns WHERE status='kutilmoqda' ORDER BY id DESC LIMIT 15").fetchall()
    conn.close()
    if not rows: return "⏳ Kutilayotgan so'rov yo'q.", [[_btn("⬅️ Orqaga", "qr:menu")] + _x_btn('qr')]
    m = ["⏳ KUTILAYOTGAN QAYTARISH SO'ROVLARI:"]
    kb = []
    for r in rows:
        m.append(f"R-{r[0]} · {r[1]} · {r[2] or 'mijozsiz'} · {_usd2(r[3] or 0)} · {r[4]}")
        kb.append([_btn(f"👁 R-{r[0]}", f"qr:v:{r[0]}"), _btn("✅", f"qr:ap:{r[0]}"), _btn("❌", f"qr:rj:{r[0]}")])
    kb.append([_btn("⬅️ Orqaga", "qr:menu")] + _x_btn('qr'))
    return "\n".join(m), kb


def _qr_tarix(page=0):
    conn = db()
    rows = conn.execute("SELECT id, created, customer, total, status FROM returns WHERE status<>'kutilmoqda' ORDER BY id DESC "
                        "LIMIT 9 OFFSET ?", (page * 8,)).fetchall()
    conn.close()
    belgi = {'ok': '✅', 'rad': '🚫', 'bekor': '↩️'}
    kb = [[_btn(f"{belgi.get(r[4], '•')} R-{r[0]} · {r[1][5:16]} · {(r[2] or 'mijozsiz')[:14]} · {_usd2(r[3] or 0)}", f"qr:v:{r[0]}")]
          for r in rows[:8]]
    nav = ([_btn("◀️", f"qr:hs:{page - 1}")] if page else []) + ([_btn("▶️", f"qr:hs:{page + 1}")] if len(rows) > 8 else [])
    if nav: kb.append(nav)
    kb.append([_btn("⬅️ Orqaga", "qr:menu")] + _x_btn('qr'))
    return ("📜 QAYTARISHLAR TARIXI" if rows else "📜 Hali qaytarish yo'q."), kb


def _qr_brak():
    conn = db()
    rows = conn.execute("SELECT id, date, product, qty, unit_cost FROM brak_tovarlar WHERE status='brak' ORDER BY id DESC LIMIT 15").fetchall()
    conn.close()
    if not rows: return "🔧 Brak tovar yo'q.", [[_btn("⬅️ Orqaga", "qr:menu")] + _x_btn('qr')]
    m = ["🔧 BRAK TOVARLAR (hisobdan chiqarilgan):", "✅ Tuzatildi — omborga qaytadi (spisanie bekor)", "🏭 Zavodga — faqat belgi", ""]
    kb = []
    for r in rows:
        m.append(f"B-{r[0]} · {r[1]} · {r[2]} × {r[3]} · {_usd2((r[4] or 0) * r[3])}")
        kb.append([_btn(f"✅ B-{r[0]} tuzatildi", f"qr:bt:{r[0]}"), _btn(f"🏭 B-{r[0]} zavodga", f"qr:bz:{r[0]}")])
    kb.append([_btn("⬅️ Orqaga", "qr:menu")] + _x_btn('qr'))
    return "\n".join(m), kb


async def cmd_qaytarish(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """📥 Qaytarish tugmasi / /qaytarish"""
    if not _qr_rol(u):
        if user_role(u): await u.message.reply_text("Qaytarish uchun ruxsat yo'q.")
        return
    _ui_yangi(ctx, 'qr')
    m, r = _qr_menu(u)
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))


async def qr_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    rol = _qr_rol(u)
    if not rol:
        await q.answer("Ruxsat yo'q", show_alert=True); return
    parts = (q.data or '').split(':'); act = parts[1] if len(parts) > 1 else ''; arg = parts[2:]
    if act == 'x':
        ctx.user_data.pop('qr', None); await q.answer()
        return await _pos_chiqar(q, "📥 Qaytarish oynasi yopildi.", None)
    # ── tasdiqlash / rad (holatsiz — xabardagi tugmalar) ──
    if act in ('ap', 'rj', 'v', 'bt', 'bz', 'rq', 'hs', 'br') and rol != 'bajar':
        await q.answer("Faqat egasi/admin", show_alert=True); return
    if act in ('ap', 'rj'):
        rid = int(arg[0]); user = _ui_user(u)
        if not _ui_done(ctx, f"qr{act}{rid}"):
            await q.answer("Allaqachon bajarilgan"); return
        conn = db(); r = conn.execute("SELECT status, plan, requested_by FROM returns WHERE id=?", (rid,)).fetchone(); conn.close()
        if not r or r[0] != 'kutilmoqda':
            await q.answer("So'rov allaqachon ko'rib chiqilgan", show_alert=True)
            return await _pos_chiqar(q, qaytarish_chek(rid), None)
        if act == 'rj':
            qaytarish_rad(rid, user); await q.answer("Rad etildi")
            matn = qaytarish_chek(rid)
        else:
            res = qaytarish_bajar(json.loads(r[1] or '{}'), user, return_id=rid)
            if not res['ok']:
                ctx.user_data.get('ui_done', []).remove(f"qrap{rid}")
                await q.answer(res['error'][:190], show_alert=True); return
            await q.answer("✅ Bajarildi")
            matn = qaytarish_chek(rid)
        await _pos_chiqar(q, matn, None)
        if r[2] and r[2] != _uid(u):
            try: await ctx.bot.send_message(chat_id=r[2], text=matn[:4000])
            except Exception as e: log.warning("so'rovchiga xabar: %s", e)
        return
    st = _ui_ol(ctx, 'qr')
    if st is None:
        st = _ui_yangi(ctx, 'qr')
        if act not in ('menu', 'la', 'cs', 'fd', 'cu', 'g', 'rq', 'hs', 'br', 'v', 'sr'):
            await q.answer("Oyna eskirgan — qaytadan boshlang", show_alert=True)
            m, r_ = _qr_menu(u); return await _pos_chiqar(q, m, r_)
    st['wait'] = None
    m = rows = None; alert = None
    if act == 'menu':
        m, rows = _qr_menu(u)
    elif act == 'la':
        m, rows = _qr_royxat(u, int(arg[0]) if arg else 0)
    elif act == 'cu':
        m, rows = _qr_royxat(u, int(arg[1]) if len(arg) > 1 else 0, cid=int(arg[0]))
    elif act == 'cs':
        st['wait'] = 'cust'; m, rows = "👤 Mijoz ismi yoki telefonini yozing:", [[_btn("⬅️ Orqaga", "qr:menu")]]
    elif act == 'fd':
        st['wait'] = 'find'
        m, rows = ("🔎 Chek raqami (masalan S-123) yoki serial raqamni yozing.\n📷 Shtrix-kod/QR rasmini ham yuborsangiz bo'ladi.",
                   [[_btn("⬅️ Orqaga", "qr:menu")]])
    elif act == 'g':
        sid = int(arg[0])
        if st.get('g') != sid:
            st.update({'g': sid, 'sel': {}, 'ser': {}, 'reason': None, 'reason_text': '', 'brak': None, 'method': None})
        m, rows = _qr_chek_ekran(st)
    elif act == 'l':
        m, rows = _qr_qator_ekran(st, int(arg[0]))
    elif act == 'lq':
        sid, n = int(arg[0]), int(arg[1])
        st.setdefault('sel', {})[sid] = n
        m, rows = _qr_chek_ekran(st)
    elif act == 'sn':
        sid, s_id = int(arg[0]), int(arg[1])
        tan = st.setdefault('ser', {}).setdefault(sid, [])
        if s_id in tan: tan.remove(s_id)
        else: tan.append(s_id)
        st.setdefault('sel', {})[sid] = len(tan)
        m, rows = _qr_qator_ekran(st, sid)
    elif act in ('nx', 'back'):
        if act == 'back' or not any(st.get('sel', {}).get(i, 0) for i in st.get('ids', [])):
            m, rows = _qr_chek_ekran(st) if st.get('g') else _qr_menu(u)
        else:
            m, rows = _qr_sabab_ekran()
    elif act == 'rs':
        k = arg[0] if arg else 'boshqa'
        st['reason'] = k
        if k == 'boshqa' and not st.get('reason_text'):
            st['wait'] = 'reason'
            m, rows = "✍️ Sababni qisqa yozing:", [[_btn("⬅️ Orqaga", "qr:nx")]]
        else:
            if k != 'boshqa': st['reason_text'] = ''
            m, rows = _qr_holat_ekran(st)
    elif act == 'bk':
        st['brak'] = arg[0] == '1'
        R = qaytarish_hisob(_qr_plan(st))
        if R['ok'] and R['naqd_qaytar'] > 0:
            m, rows = _qr_usul_ekran(st, R)
        else:
            m, rows = _qr_tasdiq_ekran(u, st)
    elif act == 'mt':
        st['method'] = arg[0] if arg and arg[0] in TOLOV_USULLARI else None
        m, rows = _qr_tasdiq_ekran(u, st)
    elif act == 'ok0':
        m, rows = _qr_tasdiq_ekran(u, st)
    elif act == 'ok':
        if not arg or arg[0] != st.get('tok') or not _ui_done(ctx, 'qrok' + arg[0]):
            await q.answer("Eskirgan tugma", show_alert=True); return
        plan = _qr_plan(st); user = _ui_user(u)
        if rol == 'bajar':
            res = qaytarish_bajar(plan, user)
            if not res['ok']:
                await q.answer(); return await _pos_chiqar(q, f"❌ {res['error']}", [[_btn("⬅️ Chekka qaytish", f"qr:g:{st['g']}")] + _x_btn('qr')])
            ctx.user_data.pop('qr', None)
            await q.answer("✅ Qaytarildi")
            return await _pos_chiqar(q, qaytarish_chek(res['rid']), [[_btn("📥 Yana qaytarish", "qr:menu")]])
        res = qaytarish_sorov(plan, user)
        if not res['ok']:
            await q.answer(); return await _pos_chiqar(q, f"❌ {res['error']}", [[_btn("⬅️ Orqaga", f"qr:g:{st['g']}")]])
        ctx.user_data.pop('qr', None)
        await q.answer("📨 Yuborildi")
        await _pos_chiqar(q, f"📨 So'rov R-{res['rid']} egasi/admin'ga yuborildi. Tasdiqlansa sizga xabar keladi.", None)
        return await _qr_sorov_yubor(ctx.bot, res['rid'])
    elif act == 'sr':                                         # 🔢 Serial kartasidan "📥 Qaytarish"
        sr = serial_ol(int(arg[0])) if arg and arg[0].isdigit() else None
        g = sotuv_guruhi(sr['sale_id']) if sr and sr['sale_id'] else None
        if not g: alert = "Bu serialning faol sotuvi topilmadi"
        else:
            st.update({'g': g['first'], 'sel': {sr['sale_id']: 1}, 'ser': {sr['sale_id']: [sr['id']]}, 'reason': None,
                       'reason_text': '', 'brak': None, 'method': None})
            m, rows = _qr_chek_ekran(st)
    elif act == 'rq':
        m, rows = _qr_sorovlar()
    elif act == 'hs':
        m, rows = _qr_tarix(int(arg[0]) if arg else 0)
    elif act == 'v':
        m, rows = qaytarish_chek(int(arg[0])), [[_btn("⬅️ Orqaga", "qr:hs:0")] + _x_btn('qr')]
    elif act == 'br':
        m, rows = _qr_brak()
    elif act in ('bt', 'bz'):
        res = brak_holat(int(arg[0]), 'tuzatildi' if act == 'bt' else 'zavodga', _ui_user(u))
        alert = (f"✅ {res['nom']} × {res['qty']} — " + ("omborga qaytdi" if act == 'bt' else "zavodga belgilandi")) if res['ok'] else res['error']
        m, rows = _qr_brak()
    else:
        alert = "Eski tugma"
    await q.answer(alert[:190] if alert else None, show_alert=bool(alert))
    if m is not None: await _pos_chiqar(q, m, rows)


def _chek_raqam(msg):
    mt = re.fullmatch(r'\s*(?:[sS][-\s]?|#|№\s*)?(\d{1,9})\s*', msg or '')
    return int(mt.group(1)) if mt else None


async def qr_matn(u, ctx, msg):
    st = _ui_ol(ctx, 'qr')
    if not st or not st.get('wait') or not _qr_rol(u): return False
    w = st['wait']
    if w == 'cust':
        topildi = mijoz_qidir(msg)[:8]
        if not topildi:
            await u.message.reply_text("Mijoz topilmadi. Boshqacha yozib ko'ring:"); return True
        st['wait'] = None
        await u.message.reply_text("👤 Mijozni tanlang:", reply_markup=InlineKeyboardMarkup(
            [[_btn(f"{c_['nom']}" + (f" · {c_['tel']}" if c_['tel'] else ''), f"qr:cu:{c_['id']}:0")] for c_ in topildi]
            + [[_btn("⬅️ Orqaga", "qr:menu")]]))
        return True
    if w == 'find':
        return await qr_kod_top(u, ctx, msg)
    if w == 'reason':
        st['reason_text'] = (msg or '').strip()[:150]; st['wait'] = None
        m, rows = _qr_holat_ekran(st)
        await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(rows)); return True
    return False


async def qr_kod_top(u, ctx, msg):
    """Chek raqami / serial / shtrix-kod → sotuv cheki oynasi."""
    st = _ui_ol(ctx, 'qr') or _ui_yangi(ctx, 'qr')
    sid = None
    sr = serial_top(msg)
    if sr and sr['sale_id']: sid = sr['sale_id']
    elif sr:
        await u.message.reply_text(f"🔢 {sr['serial']} — {SERIAL_HOLAT.get(sr['status'], sr['status'])}, sotilmagan. Boshqa raqam yozing:")
        return True
    else:
        sid = _chek_raqam(msg)
    g = sotuv_guruhi(sid) if sid else None
    if not g:
        await u.message.reply_text("Bunday sotuv topilmadi (yoki to'liq qaytarilgan/bekor qilingan). Qayta yozing yoki ⬅️ Orqaga:",
                                   reply_markup=InlineKeyboardMarkup([[_btn("⬅️ Orqaga", "qr:menu")]]))
        return True
    st.update({'wait': None, 'g': g['first'], 'sel': {}, 'ser': {}, 'reason': None, 'reason_text': '', 'brak': None, 'method': None})
    if sr and sr['sale_id']:
        st['sel'][sr['sale_id']] = 1; st['ser'][sr['sale_id']] = [sr['id']]
    m, rows = _qr_chek_ekran(st)
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(rows))
    return True


# ── 🧾 SMENA / KASSA YOPISH (Z-hisobot) ──────────────────────────────────────────────
# Do'kon bo'yicha BITTA ochiq smena. Kutilgan naqd = ochilishdagi naqd + smena davomidagi kassa (naqd) harakati
# (cash_box id oralig'i bo'yicha — vaqt bir xil daqiqada bo'lsa ham adashmaydi). Karta — alohida.
_SM_COLS = ("id,user_id,user_name,opened_at,opening_cash,closed_at,closed_by,closed_name,expected_naqd,expected_karta,"
            "counted_naqd,counted_karta,diff_naqd,diff_karta,boshqa,status,note,booking,booking_ref,booked_by")


def _sm_dict(r):
    if not r: return None
    d = dict(zip(_SM_COLS.split(','), r))
    try: d['meta'] = json.loads(d['boshqa'] or '{}')
    except ValueError: d['meta'] = {}
    return d


def smena_ol(sid):
    conn = db(); r = conn.execute(f"SELECT {_SM_COLS} FROM smenalar WHERE id=?", (int(sid),)).fetchone(); conn.close()
    return _sm_dict(r)


def smena_ochiq():
    conn = db(); r = conn.execute(f"SELECT {_SM_COLS} FROM smenalar WHERE status='ochiq' ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return _sm_dict(r)


def smena_och(user, opening=0.0):
    try: opening = round(float(opening or 0), 2)
    except (TypeError, ValueError): return {'ok': False, 'error': "Summa noto'g'ri"}
    if opening < 0: return {'ok': False, 'error': "Summa manfiy bo'lmasin"}
    conn = db(); c = conn.cursor()
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute("SELECT id, user_name FROM smenalar WHERE status='ochiq' LIMIT 1")
        r = c.fetchone()
        if r: conn.rollback(); conn.close(); return {'ok': False, 'error': f"Smena allaqachon ochiq (#{r[0]}, {r[1]})"}
        c.execute("SELECT COALESCE(MAX(id),0) FROM cash_box"); cf = c.fetchone()[0]
        c.execute("INSERT INTO smenalar (user_id,user_name,opened_at,opening_cash,boshqa,status) VALUES (?,?,?,?,?,'ochiq')",
                  (int(user[0] or 0), user[1] or '', _hm(), opening, json.dumps({'cash_from': cf})))
        sid = c.lastrowid; conn.commit()
    except Exception:
        conn.rollback(); conn.close(); raise
    conn.close()
    return {'ok': True, 'id': sid, 'opening': opening}


def smena_kutilgan(sm, cash_to=None):
    """{'naqd': kutilgan naqd, 'karta':..., 'usullar': {usul: (kirim, chiqim)}, 'cash_to': id}"""
    cf = int(sm['meta'].get('cash_from', 0))
    conn = db(); c = conn.cursor()
    if cash_to is None:
        c.execute("SELECT COALESCE(MAX(id),0) FROM cash_box"); cash_to = c.fetchone()[0]
    c.execute("SELECT COALESCE(NULLIF(payment_method,''),'naqd'), SUM(CASE WHEN type='kirim' THEN amount ELSE 0 END), "
              "SUM(CASE WHEN type='chiqim' THEN amount ELSE 0 END), COUNT(*) FROM cash_box WHERE id>? AND id<=? GROUP BY 1",
              (cf, cash_to))
    us = {r[0]: (round(r[1] or 0, 2), round(r[2] or 0, 2), r[3]) for r in c.fetchall()}
    c.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM cash_box WHERE id>? AND id<=? AND type='kirim' AND category='sotuv'",
              (cf, cash_to))
    sn, ss = c.fetchone(); conn.close()
    net = lambda k: round(us.get(k, (0, 0, 0))[0] - us.get(k, (0, 0, 0))[1], 2)
    return {'naqd': round((sm['opening_cash'] or 0) + net('naqd'), 2), 'karta': net('karta'), 'usullar': us,
            'cash_to': cash_to, 'sotuv_soni': sn, 'sotuv_summa': round(ss or 0, 2)}


def smena_yop(sid, user, counted_naqd, counted_karta=None, note=''):
    """Atomar: faqat 'ochiq' smena yopiladi (ikki marta yopib bo'lmaydi)."""
    sm = smena_ol(sid)
    if not sm: return {'ok': False, 'error': "Smena topilmadi"}
    if sm['status'] != 'ochiq': return {'ok': False, 'error': "Bu smena allaqachon yopilgan"}
    k = smena_kutilgan(sm)
    dn = round(float(counted_naqd) - k['naqd'], 2)
    dk = round(float(counted_karta) - k['karta'], 2) if counted_karta is not None else 0.0
    meta = dict(sm['meta']); meta.update({'cash_to': k['cash_to'], 'sotuv_soni': k['sotuv_soni'], 'sotuv_summa': k['sotuv_summa'],
                                          'usullar': {a: list(b) for a, b in k['usullar'].items()}})
    booking = 'teng' if abs(dn) < 0.01 and abs(dk) < 0.01 else ''
    conn = db(); c = conn.cursor()
    c.execute("UPDATE smenalar SET status='yopilgan', closed_at=?, closed_by=?, closed_name=?, expected_naqd=?, expected_karta=?, "
              "counted_naqd=?, counted_karta=?, diff_naqd=?, diff_karta=?, boshqa=?, note=?, booking=? WHERE id=? AND status='ochiq'",
              (_hm(), int(user[0] or 0), user[1] or '', k['naqd'], k['karta'], round(float(counted_naqd), 2),
               None if counted_karta is None else round(float(counted_karta), 2), dn, dk, json.dumps(meta), (note or '')[:300],
               booking, int(sid)))
    n = c.rowcount; conn.commit(); conn.close()
    if n != 1: return {'ok': False, 'error': "Bu smena allaqachon yopilgan"}
    return {'ok': True, 'sm': smena_ol(sid)}


def smena_hisobla(sid, tanlov, user):
    """Egasi: farqni qanday yozish. tanlov: 'kassa' — kamomad → xarajat (kassadan chiqim) / ortiqcha → kassaga kirim;
    'izoh' — faqat belgi. Atomar: bir marta."""
    if tanlov not in ('kassa', 'izoh'): return {'ok': False, 'error': "Tanlov noma'lum"}
    if tanlov == 'kassa' and is_closed(today()):
        return {'ok': False, 'error': f"{today()[:7]} davri yopilgan"}
    conn = db(); c = conn.cursor()
    c.execute("UPDATE smenalar SET booking='jarayonda', booked_by=? WHERE id=? AND status='yopilgan' AND COALESCE(booking,'')=''",
              (user[1] or '', int(sid)))
    n = c.rowcount; conn.commit(); conn.close()
    if n != 1: return {'ok': False, 'error': "Allaqachon hal qilingan"}
    sm = smena_ol(sid); d = round(sm['diff_naqd'] or 0, 2); ref = ''
    try:
        if tanlov == 'kassa' and d < 0:
            eid = add_expense(abs(d), 'kassa_kamomad', 'period', f"Smena #{sid} kamomad ({sm['closed_name']})", cash=True)
            ref = f"x{eid}"; bk = 'xarajat'
        elif tanlov == 'kassa' and d > 0:
            add_cash(d, 'kirim', 'kassa_ortiqcha', f"Smena #{sid} ortiqcha ({sm['closed_name']})", 'naqd'); bk = 'kirim'
        else:
            bk = 'izoh'
    except Exception:
        conn = db(); conn.execute("UPDATE smenalar SET booking='' WHERE id=?", (int(sid),)); conn.commit(); conn.close()
        raise
    conn = db(); conn.execute("UPDATE smenalar SET booking=?, booking_ref=? WHERE id=?", (bk, ref, int(sid))); conn.commit(); conn.close()
    return {'ok': True, 'booking': bk, 'summa': d}


def _farq_matn(d):
    if abs(d or 0) < 0.01: return "✅ teng"
    return f"🔻 kamomad {_usd2(abs(d))}" if d < 0 else f"🔺 ortiqcha {_usd2(d)}"


def smena_matn(sm, rate=None):
    rate = rate or get_exchange_rate()
    m = [f"🧾 SMENA #{sm['id']} — {'🟢 ochiq' if sm['status'] == 'ochiq' else '🔒 yopilgan'}",
         f"Ochdi: {sm['user_name']} · {sm['opened_at']}", f"Ochilishdagi naqd: {_usd2(sm['opening_cash'] or 0)}"]
    if sm['status'] != 'ochiq':
        mt = sm['meta']
        m.append(f"Yopdi: {sm['closed_name']} · {sm['closed_at']}")
        m.append(f"Sotuvlar: {mt.get('sotuv_soni', 0)} ta · {_usd2(mt.get('sotuv_summa', 0))} (kassaga tushgan)")
        m.append("")
        m.append(f"💵 Naqd: kutilgan {_usd2(sm['expected_naqd'])} · sanalgan {_usd2(sm['counted_naqd'] or 0)} → {_farq_matn(sm['diff_naqd'])}")
        if abs(sm['diff_naqd'] or 0) >= 0.01: m.append(f"   ≈ {_som(abs(sm['diff_naqd']), rate)}")
        if sm['counted_karta'] is not None:
            m.append(f"💳 Karta: kutilgan {_usd2(sm['expected_karta'])} · terminal {_usd2(sm['counted_karta'])} → {_farq_matn(sm['diff_karta'])}")
        boshqa = {k: v for k, v in (mt.get('usullar') or {}).items() if k not in ('naqd', 'karta')}
        for k, v in boshqa.items():
            m.append(f"{POS_USUL_NOMI.get(k, k)}: +{_usd2(v[0])} / −{_usd2(v[1])}")
        if sm['note']: m.append(f"📝 {sm['note']}")
        bk = {'teng': '', 'xarajat': "📕 Kamomad xarajat sifatida yozildi", 'kirim': "📗 Ortiqcha kassaga kirim qilindi",
              'izoh': "📝 Faqat qayd etildi (kassaga yozilmadi)", '': "⏳ Egasi qarorini kutmoqda", 'jarayonda': '⏳'}.get(sm['booking'] or '', '')
        if bk: m.append(bk)
    return "\n".join(m)


def _sm_egasi_kb(sm):
    if sm['booking'] or abs(sm['diff_naqd'] or 0) < 0.01: return None
    t = "📕 Xarajat qilib yozish" if sm['diff_naqd'] < 0 else "📗 Kassaga kirim qilish"
    return [[_btn(t, f"sm:bk:{sm['id']}:kassa")], [_btn("📝 Faqat qayd (kassaga tegmasin)", f"sm:bk:{sm['id']}:izoh")]]


def _sm_menu(u):
    sm = smena_ochiq(); rows = []
    if sm:
        m = [smena_matn(sm)]
        if can(u, 'boshqaruv'):                        # sotuvchi "ko'r" sanaydi — kutilgan summani ko'rmaydi
            k = smena_kutilgan(sm)
            m.append(f"\nHozir kutilmoqda: 💵 {_usd2(k['naqd'])} · 💳 {_usd2(k['karta'])}")
            m.append(f"Sotuvlar: {k['sotuv_soni']} ta · {_usd2(k['sotuv_summa'])}")
        rows.append([_btn("🔒 Smenani yopish (kassani sanash)", "sm:cl")])
    else:
        m = ["🧾 SMENA\n\nHozir ochiq smena yo'q.", "Kun boshida oching (kassadagi boshlang'ich naqdni yozing)."]
        rows.append([_btn("🔓 Smena ochish", "sm:op")])
    rows.append([_btn("📋 Kunlik hisobot", "sm:rp:0"), _btn("📅 7 kun", "sm:rp:7")])
    rows.append(_x_btn('sm'))
    return "\n".join(m), rows


def _sm_hisobot(kun):
    if kun == 0: since, sar = today(), "BUGUN"
    elif kun == 1: since, sar = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'), "KECHA VA BUGUN"
    else: since, sar = (datetime.now() - timedelta(days=kun - 1)).strftime('%Y-%m-%d'), f"OXIRGI {kun} KUN"
    conn = db()
    rows = conn.execute(f"SELECT {_SM_COLS} FROM smenalar WHERE status='yopilgan' AND substr(closed_at,1,10)>=? ORDER BY id DESC",
                        (since,)).fetchall()
    conn.close()
    sms = [_sm_dict(r) for r in rows]
    m = [f"📋 KASSA YOPILISHLARI — {sar}"]
    if not sms: m.append("\nYopilgan smena yo'q.")
    kb = []
    for s in sms[:15]:
        m.append(f"\n#{s['id']} · {s['closed_at'][5:]} · {s['closed_name']}\n   💵 {_usd2(s['counted_naqd'] or 0)} → {_farq_matn(s['diff_naqd'])}")
        kb.append([_btn(f"👁 #{s['id']} · {s['closed_at'][5:]} · {_farq_matn(s['diff_naqd'])}", f"sm:v:{s['id']}")])
    if sms:
        m.append(f"\nJami farq (naqd): {_farq_matn(round(sum(s['diff_naqd'] or 0 for s in sms), 2))}")
    kb.append([_btn("Bugun", "sm:rp:0"), _btn("Kecha", "sm:rp:1"), _btn("7 kun", "sm:rp:7"), _btn("30 kun", "sm:rp:30")])
    kb.append([_btn("⬅️ Orqaga", "sm:menu")] + _x_btn('sm'))
    return "\n".join(m), kb


async def cmd_smena(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """🧾 Smena tugmasi / /smena"""
    if not can(u, 'smena'): return
    _ui_yangi(ctx, 'sm')
    m, r = _sm_menu(u)
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))


def _sm_tasdiq_ekran(u, st):
    sm = smena_ochiq()
    if not sm: return "Ochiq smena yo'q.", [[_btn("⬅️ Orqaga", "sm:menu")]]
    k = smena_kutilgan(sm)
    dn = round(st['naqd'] - k['naqd'], 2)
    m = [f"🔒 SMENA #{sm['id']} YOPILADI", "", f"💵 Sanalgan naqd: {_usd2(st['naqd'])} ≈ {_som(st['naqd'])}"]
    if st.get('karta') is not None: m.append(f"💳 Terminal (karta): {_usd2(st['karta'])}")
    if can(u, 'boshqaruv'):
        m.append(f"Kutilgan naqd: {_usd2(k['naqd'])} → {_farq_matn(dn)}")
    if st.get('note'): m.append(f"📝 {st['note']}")
    m.append("\nTasdiqlaysizmi?")
    st['tok'] = secrets.token_hex(3)
    return "\n".join(m), [[_btn("✅ Yopish", f"sm:cf:{st['tok']}")], [_btn("📝 Izoh qo'shish", "sm:nt"), _btn("✏️ Qayta sanash", "sm:cl")],
                          _x_btn('sm')]


async def sm_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not can(u, 'smena'):
        await q.answer("Ruxsat yo'q", show_alert=True); return
    parts = (q.data or '').split(':'); act = parts[1] if len(parts) > 1 else ''; arg = parts[2:]
    if act == 'x':
        ctx.user_data.pop('sm', None); await q.answer()
        return await _pos_chiqar(q, "🧾 Smena oynasi yopildi.", None)
    if act == 'bk':                                         # egasining qarori (bildirishnomadagi tugma)
        if user_role(u) != 'owner':
            await q.answer("Faqat egasi hal qiladi", show_alert=True); return
        res = smena_hisobla(int(arg[0]), arg[1] if len(arg) > 1 else '', _ui_user(u))
        await q.answer(("✅ Saqlandi" if res['ok'] else res['error'])[:190], show_alert=not res['ok'])
        sm = smena_ol(int(arg[0]))
        if sm: await _pos_chiqar(q, smena_matn(sm), _sm_egasi_kb(sm))
        return
    st = _ui_ol(ctx, 'sm') or _ui_yangi(ctx, 'sm')
    st['wait'] = None
    m = rows = None; alert = None
    if act == 'menu':
        m, rows = _sm_menu(u)
    elif act == 'op':
        if smena_ochiq(): m, rows = _sm_menu(u); alert = "Smena allaqachon ochiq"
        else:
            conn = db(); r = conn.execute("SELECT counted_naqd FROM smenalar WHERE status='yopilgan' ORDER BY id DESC LIMIT 1").fetchone(); conn.close()
            st['wait'] = 'open'
            rows = [[_btn("0 bilan ochish", "sm:o:0")]]
            if r and (r[0] or 0) > 0: rows.insert(0, [_btn(f"Oxirgi yopilishdagi {_usd2(r[0])} bilan", f"sm:o:{r[0]}")])
            rows.append([_btn("⬅️ Orqaga", "sm:menu")])
            m = "🔓 Kassadagi boshlang'ich naqd pulni yozing ($ yoki so'm, masalan 50 yoki 600000) yoki tugmani bosing:"
    elif act == 'o':
        res = smena_och(_ui_user(u), float(arg[0]) if arg else 0)
        alert = None if res['ok'] else res['error']
        m, rows = _sm_menu(u)
    elif act == 'cl':
        if not smena_ochiq():
            alert = "Ochiq smena yo'q"; m, rows = _sm_menu(u)
        else:
            st['wait'] = 'naqd'
            m, rows = ("💵 Kassadagi NAQD pulni sanang va yozing ($ yoki so'm):", [[_btn("⬅️ Orqaga", "sm:menu")]])
    elif act == 'ks':
        st['karta'] = None
        if 'naqd' not in st: m, rows = _sm_menu(u)
        else: m, rows = _sm_tasdiq_ekran(u, st)
    elif act == 'nt':
        st['wait'] = 'note'; m, rows = "📝 Izohni yozing:", [[_btn("⬅️ Orqaga", "sm:back")]]
    elif act == 'back':
        m, rows = _sm_tasdiq_ekran(u, st) if 'naqd' in st else _sm_menu(u)
    elif act == 'cf':
        sm = smena_ochiq()
        if not arg or arg[0] != st.get('tok') or 'naqd' not in st or not sm or not _ui_done(ctx, 'smcf' + arg[0]):
            await q.answer("Eskirgan tugma", show_alert=True); return
        res = smena_yop(sm['id'], _ui_user(u), st['naqd'], st.get('karta'), st.get('note', ''))
        if not res['ok']:
            alert = res['error']; m, rows = _sm_menu(u)
        else:
            s2 = res['sm']; ctx.user_data.pop('sm', None)
            await q.answer("✅ Smena yopildi")
            egasi = user_role(u) == 'owner'
            await _pos_chiqar(q, smena_matn(s2), _sm_egasi_kb(s2) if egasi else None)
            if not egasi and OWNER_ID:
                try: await ctx.bot.send_message(chat_id=OWNER_ID, text="🔔 Kassa yopildi\n\n" + smena_matn(s2),
                                                reply_markup=InlineKeyboardMarkup(_sm_egasi_kb(s2)) if _sm_egasi_kb(s2) else None)
                except Exception as e: log.warning("smena egasiga: %s", e)
            return
    elif act == 'rp':
        m, rows = _sm_hisobot(int(arg[0]) if arg else 0)
    elif act == 'v':
        sm = smena_ol(int(arg[0]))
        if sm:
            m = smena_matn(sm)
            rows = (_sm_egasi_kb(sm) or []) if user_role(u) == 'owner' else []
            rows = rows + [[_btn("⬅️ Orqaga", "sm:rp:0")]]
        else: alert = "Topilmadi"
    else:
        alert = "Eski tugma"
    await q.answer(alert[:190] if alert else None, show_alert=bool(alert))
    if m is not None: await _pos_chiqar(q, m, rows)


async def sm_matn(u, ctx, msg):
    st = _ui_ol(ctx, 'sm')
    if not st or not st.get('wait') or not can(u, 'smena'): return False
    w = st['wait']
    if w == 'note':
        st['note'] = (msg or '').strip()[:300]; st['wait'] = None
        m, rows = _sm_tasdiq_ekran(u, st)
        await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(rows)); return True
    v = _pul_kirit(msg)
    if v is None or v < 0:
        await u.message.reply_text("⚠️ Summani raqam bilan yozing (masalan 120 yoki 1 500 000):"); return True
    if w == 'open':
        st['wait'] = None
        res = smena_och(_ui_user(u), v)
        m, rows = _sm_menu(u)
        await u.message.reply_text((f"✅ Smena ochildi ({_usd2(v)})\n\n" if res['ok'] else f"⚠️ {res['error']}\n\n") + m,
                                   reply_markup=InlineKeyboardMarkup(rows))
        return True
    if w == 'naqd':
        st['naqd'] = v; st['wait'] = 'karta'
        await u.message.reply_text(f"💵 Naqd: {_usd2(v)}\n\n💳 Karta terminali bo'yicha summa (Z-chek)? Yozing yoki o'tkazib yuboring:",
                                   reply_markup=InlineKeyboardMarkup([[_btn("⏭ Karta yo'q / o'tkazib yuborish", "sm:ks")]]))
        return True
    if w == 'karta':
        st['karta'] = v; st['wait'] = None
        m, rows = _sm_tasdiq_ekran(u, st)
        await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(rows)); return True
    return False


# ── 🔢 SERIAL RAQAMLAR VA KAFOLAT ────────────────────────────────────────────────────
# products.serialli=1 bo'lsa: kirimda seriallar kiritiladi, POS'da serial tanlanmasa sotilmaydi,
# har serialga alohida kafolat (warranties.serial). Matnli/AI sotuv eskicha ishlaydi (serialsiz).
SERIAL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9\-_/.]{2,39}$')
_SR_COLS = "id,product_id,product,serial,status,kirim_date,kirim_ref,sale_id,sold_date,customer,customer_id,warranty_end,note,created"


def _serialli(pid):
    try:
        conn = db(); r = conn.execute("SELECT COALESCE(serialli,0) FROM products WHERE id=?", (int(pid),)).fetchone(); conn.close()
        return bool(r and r[0])
    except (sqlite3.OperationalError, TypeError, ValueError):
        return False


def serial_ajrat(matn):
    out = []
    for s in re.split(r'[\s,;]+', (matn or '').strip()):
        s = s.strip().strip('.')
        if s and s.upper() not in {x.upper() for x in out}: out.append(s)
    return out


def _sr_dict(r):
    return dict(zip(_SR_COLS.split(','), r)) if r else None


def serial_top(matn):
    s = (matn or '').strip()
    if not s or len(s) > 60: return None
    try:
        conn = db(); r = conn.execute(f"SELECT {_SR_COLS} FROM serials WHERE serial=? COLLATE NOCASE", (s,)).fetchone(); conn.close()
    except sqlite3.OperationalError:
        return None
    return _sr_dict(r)


def serial_ol(sr_id):
    conn = db(); r = conn.execute(f"SELECT {_SR_COLS} FROM serials WHERE id=?", (int(sr_id),)).fetchone(); conn.close()
    return _sr_dict(r)


def serial_omborda(pid, limit=200):
    conn = db()
    r = conn.execute("SELECT id, serial FROM serials WHERE product_id=? AND status='omborda' ORDER BY id LIMIT ?", (int(pid), limit)).fetchall()
    conn.close(); return r


def serial_holat_soni(pid):
    conn = db()
    r = dict(conn.execute("SELECT status, COUNT(*) FROM serials WHERE product_id=? GROUP BY status", (int(pid),)).fetchall())
    q = conn.execute("SELECT COALESCE(qty,0) FROM products WHERE id=?", (int(pid),)).fetchone()
    conn.close()
    r['_qty'] = q[0] if q else 0
    r['_bosh'] = max(0, r['_qty'] - r.get('omborda', 0))         # astatkada bor, lekin serial kiritilmagan
    return r


def serial_qosh(pid, matn, user=None, ref='', c=None):
    """Bir nechta serial (vergul/probel/yangi qator bilan). Sig'im: astatka − omborda ro'yxatdagi seriallar.
    Qaytaradi {'ok', 'qoshildi': [...], 'band': [...], 'xato': [...], 'ortiqcha': [...]}."""
    royxat = serial_ajrat(matn)
    if not royxat: return {'ok': False, 'error': "Serial raqam topilmadi", 'qoshildi': [], 'band': [], 'xato': [], 'ortiqcha': []}
    own = c is None
    conn = db() if own else None
    cur = c or conn.cursor()
    cur.execute("SELECT name, COALESCE(qty,0) FROM products WHERE id=?", (int(pid),))
    p = cur.fetchone()
    if not p:
        if own: conn.close()
        return {'ok': False, 'error': "Mahsulot topilmadi", 'qoshildi': [], 'band': [], 'xato': [], 'ortiqcha': []}
    cur.execute("SELECT COUNT(*) FROM serials WHERE product_id=? AND status='omborda'", (int(pid),))
    joy = max(0, p[1] - cur.fetchone()[0])
    out = {'ok': True, 'qoshildi': [], 'band': [], 'xato': [], 'ortiqcha': [], 'ids': []}
    for s in royxat:
        if not SERIAL_RE.match(s): out['xato'].append(s); continue
        if len(out['qoshildi']) >= joy: out['ortiqcha'].append(s); continue
        try:
            cur.execute("INSERT INTO serials (product_id,product,serial,status,kirim_date,kirim_ref,created) VALUES (?,?,?,'omborda',?,?,?)",
                        (int(pid), p[0], s, today(), ref, _hm()))
        except sqlite3.IntegrityError:
            out['band'].append(s); continue
        out['qoshildi'].append(s); out['ids'].append(cur.lastrowid)
        _serial_log(cur, cur.lastrowid, 'kirim', ref, '', user)
    if own:
        conn.commit(); conn.close()
    return out


def serial_qosh_matn(res, nom=''):
    m = []
    if res.get('error'): return f"⚠️ {res['error']}"
    if res['qoshildi']: m.append(f"✅ Qo'shildi: {len(res['qoshildi'])} ta" + (f" ({nom})" if nom else ""))
    if res['band']: m.append("⛔ Allaqachon bor: " + ", ".join(res['band'][:10]))
    if res['xato']: m.append("⚠️ Noto'g'ri format: " + ", ".join(res['xato'][:10]) + " (3–40 belgi: harf, raqam, - _ / .)")
    if res['ortiqcha']: m.append("⚠️ Astatkadan ortiq (avval kirim qiling): " + ", ".join(res['ortiqcha'][:10]))
    return "\n".join(m) or "Hech narsa qo'shilmadi"


def serial_rejim(pid, on=None):
    """Serialli rejimni yoqadi/o'chiradi (on=None — teskari). Yangi holatni qaytaradi."""
    conn = db(); c = conn.cursor()
    c.execute("SELECT COALESCE(serialli,0) FROM products WHERE id=?", (int(pid),)); r = c.fetchone()
    if not r: conn.close(); return None
    yangi = (0 if r[0] else 1) if on is None else (1 if on else 0)
    c.execute("UPDATE products SET serialli=? WHERE id=?", (yangi, int(pid))); conn.commit(); conn.close()
    return bool(yangi)


def _sotuv_seriallar(c, sale_id, pid, serials, d, customer, end, user):
    """_sotuv_tx ichida: tanlangan seriallarni 'sotilgan' qiladi. Band bo'lsa _SerialXato (butun savat bekor)."""
    for sr in serials:
        c.execute("UPDATE serials SET status='sotilgan', sale_id=?, sold_date=?, customer=?, warranty_end=? "
                  "WHERE id=? AND product_id=? AND status='omborda'", (sale_id, d, customer or '', end or '', int(sr), int(pid)))
        if c.rowcount != 1:
            c.execute("SELECT serial FROM serials WHERE id=?", (int(sr),)); r = c.fetchone()
            raise _SerialXato(r[0] if r else str(sr))
        _serial_log(c, int(sr), 'sotildi', f'#s{sale_id}', customer or '', user)


def kafolat_qoldi(end):
    if not end: return None
    try: return (datetime.strptime(end[:10], '%Y-%m-%d').date() - datetime.now().date()).days
    except ValueError: return None


def serial_karta(sr):
    """Serial kartasi matni: tovar, holat, kim/qachon oldi, kafolat qoldig'i, murojaatlar, tarix."""
    conn = db(); c = conn.cursor()
    m = [f"🔢 SERIAL: {sr['serial']}", f"📦 {sr['product']}", f"Holat: {SERIAL_HOLAT.get(sr['status'], sr['status'])}"]
    if sr['kirim_date']: m.append(f"Kirim: {sr['kirim_date']}" + (f" ({sr['kirim_ref']})" if sr['kirim_ref'] else ""))
    if sr['sale_id']:
        c.execute("SELECT date, time, revenue, qty, COALESCE(seller_name,''), COALESCE(customer,'') FROM sales WHERE id=?", (sr['sale_id'],))
        s = c.fetchone()
        if s:
            m.append(f"\n🛒 Sotilgan: {s[0]} {s[1]} · chek #{sr['sale_id']} · {_usd2((s[2] or 0) / max(1, s[3] or 1))}")
            m.append(f"👤 Xaridor: {sr['customer'] or s[5] or '—'}" + (f" · sotuvchi: {s[4]}" if s[4] else ""))
        qol = kafolat_qoldi(sr['warranty_end'])
        if qol is None: m.append("🛡 Kafolat: yo'q")
        elif qol >= 0: m.append(f"🛡 Kafolat: {sr['warranty_end']} gacha — {qol} kun qoldi ✅")
        else: m.append(f"🛡 Kafolat: {sr['warranty_end']} da tugagan ({-qol} kun oldin) ❌")
    c.execute("SELECT id, opened, status, note, closed, result FROM kafolat_murojaat WHERE serial_id=? ORDER BY id DESC LIMIT 5", (sr['id'],))
    mur = c.fetchall()
    if mur:
        m.append("\n🛠 Murojaatlar:")
        for r in mur:
            m.append(f"• #{r[0]} {r[1]} — {'🟡 ochiq' if r[2] == 'ochiq' else '✅ yopilgan'}: {r[3]}" + (f"\n   Natija ({r[4]}): {r[5]}" if r[2] != 'ochiq' else ""))
    c.execute("SELECT date, event, ref, user_name FROM serial_log WHERE serial_id=? ORDER BY id DESC LIMIT 6", (sr['id'],))
    lg = c.fetchall(); conn.close()
    if lg:
        m.append("\n📜 Tarix:")
        m += [f"• {r[0]} — {r[1]}" + (f" {r[2]}" if r[2] else "") + (f" ({r[3]})" if r[3] else "") for r in lg]
    return "\n".join(m)


def murojaat_och(sr_id, note, user):
    sr = serial_ol(sr_id)
    if not sr: return {'ok': False, 'error': "Serial topilmadi"}
    conn = db(); c = conn.cursor()
    c.execute("SELECT id FROM warranties WHERE sale_id=? AND serial=? ORDER BY id DESC LIMIT 1", (sr['sale_id'] or -1, sr['serial']))
    w = c.fetchone()
    c.execute("INSERT INTO kafolat_murojaat (serial_id,warranty_id,product,customer,opened,opened_by,status,note) VALUES (?,?,?,?,?,?,'ochiq',?)",
              (sr['id'], w[0] if w else 0, sr['product'], sr['customer'], _hm(), (user or (0, ''))[1], (note or '')[:500]))
    mid = c.lastrowid
    _serial_log(c, sr['id'], 'kafolat murojaati', f'#M{mid}', note, user)
    conn.commit(); conn.close()
    return {'ok': True, 'id': mid}


def murojaat_yop(mid, natija, user):
    conn = db(); c = conn.cursor()
    c.execute("UPDATE kafolat_murojaat SET status='yopilgan', closed=?, closed_by=?, result=? WHERE id=? AND status='ochiq'",
              (_hm(), (user or (0, ''))[1], (natija or '')[:500], int(mid)))
    ok = c.rowcount == 1
    if ok:
        c.execute("SELECT serial_id FROM kafolat_murojaat WHERE id=?", (int(mid),)); r = c.fetchone()
        if r and r[0]: _serial_log(c, r[0], 'murojaat yopildi', f'#M{mid}', natija, user)
    conn.commit(); conn.close()
    return ok


# ── 🔢 Serial: tugmali oyna (prefiks 'sn:') + POS va Ombor ulanishlari ─────────────────
def sn_kirim_btn(items):
    """Kirim/zavod qabulidan keyin: serialli tovarlar uchun 'seriallarni kiritish' tugmasi."""
    rows = []
    for pid, n, nom in items:
        if pid and _serialli(pid):
            rows.append([_btn(f"🔢 {str(nom)[:22]}: {n} ta serial kiritish", f"sn:in:{pid}:{n}")])
    return rows


def _omb_karta_b10(u, pid, out, rows):
    """📦 Tovar kartasiga: serial holati, shtrix-kod va tugmalar (ro'yxatlarni joyida to'ldiradi)."""
    try:
        conn = db(); r = conn.execute("SELECT COALESCE(serialli,0), COALESCE(barcode,'') FROM products WHERE id=?", (pid,)).fetchone(); conn.close()
    except sqlite3.OperationalError:
        return
    if not r: return
    if r[0]:
        s = serial_holat_soni(pid)
        out.append(f"🔢 Serialli: omborda {s.get('omborda', 0)} ta serial" + (f" · ⚠️ {s['_bosh']} tasiga serial kiritilmagan" if s['_bosh'] else ""))
    if r[1]: out.append(f"🏷 Shtrix-kod: {r[1]}")
    b = [_btn("🔢 Seriallar", f"sn:pp:{pid}")]
    if can(u, 'ombor'): b.append(_btn("🏷 Yorliq", f"kod:p:{pid}"))
    rows.append(b)


def _sn_menu(u):
    rows = [[_btn("📋 Serialli tovarlar", "sn:pl:0"), _btn("🛠 Ochiq murojaatlar", "sn:mo")], _x_btn('sn')]
    return ("🔢 SERIAL / KAFOLAT\n\nSerial raqamni yozing (yoki shtrix-kod/QR rasmini yuboring) — kim, qachon olgani va "
            "kafolat qancha qolgani chiqadi."), rows


def _sn_tovarlar(u, page=0):
    conn = db()
    rows_ = conn.execute("SELECT id, name, COALESCE(qty,0), COALESCE(serialli,0) FROM products WHERE COALESCE(active,1)=1 "
                         "ORDER BY serialli DESC, name").fetchall()
    sn = dict(conn.execute("SELECT product_id, COUNT(*) FROM serials WHERE status='omborda' GROUP BY product_id").fetchall())
    conn.close()
    per = 10; pages = max(1, math.ceil(len(rows_) / per)); page = min(max(0, page), pages - 1)
    kb = []
    for pid, nom, q, s in rows_[page * per:(page + 1) * per]:
        kb.append([_btn(f"{'🔢' if s else '▫️'} {nom[:28]} · {q} ta" + (f" · SN {sn.get(pid, 0)}" if s else ""), f"sn:pp:{pid}")])
    nav = ([_btn("◀️", f"sn:pl:{page - 1}")] if page else []) + ([_btn("▶️", f"sn:pl:{page + 1}")] if page < pages - 1 else [])
    if nav: kb.append(nav)
    kb.append([_btn("⬅️ Orqaga", "sn:menu")] + _x_btn('sn'))
    return "📋 Tovarlar (🔢 — serialli). Tovarni bosing:", kb


def _sn_tovar(u, pid):
    p = _omb_mahsulot(pid)
    if not p: return "Topilmadi", [[_btn("⬅️ Orqaga", "sn:pl:0")]]
    on = _serialli(pid); s = serial_holat_soni(pid)
    m = [f"🔢 {p['name']}", f"Serialli rejim: {'✅ yoqilgan' if on else '⛔ o‘chiq'}", f"Astatka: {p['qty']} ta"]
    if on or any(k for k in s if not k.startswith('_')):
        m.append("Seriallar: " + ", ".join(f"{SERIAL_HOLAT.get(k, k)} {v}" for k, v in s.items() if not k.startswith('_')) if len(s) > 2 else "Seriallar: hali yo'q")
        if s['_bosh']: m.append(f"⚠️ {s['_bosh']} ta tovarga serial kiritilmagan (POS'da yozilganda avtomatik qo'shiladi)")
        om = serial_omborda(pid, 30)
        if om: m.append("\nOmborda: " + ", ".join(x[1] for x in om) + (" ..." if len(om) == 30 else ""))
    kb = []
    if can(u, 'ombor'):
        kb.append([_btn("➕ Serial qo'shish", f"sn:in:{pid}:0"), _btn(f"{'⛔ O‘chirish' if on else '✅ Yoqish'} (serialli)", f"sn:tg:{pid}")])
    om = serial_omborda(pid, 8)
    kb += [[_btn(f"🔎 {x[1]}", f"sn:v:{x[0]}")] for x in om[:6]]
    kb.append([_btn("⬅️ Orqaga", "sn:pl:0")] + _x_btn('sn'))
    if not on: m.append("\nYoqilsa: kirimda seriallar so'raladi, 🛒 Sotuvda serial tanlanmasa sotilmaydi, kafolat serial bo'yicha yuritiladi.")
    return "\n".join(m), kb


def _sn_karta_kb(u, sr):
    kb = []
    if sr['status'] == 'sotilgan':
        kb.append([_btn("🛠 Kafolat murojaati ochish", f"sn:mn:{sr['id']}")])
        if _qr_rol(u): kb.append([_btn("📥 Qaytarish", f"qr:sr:{sr['id']}")])
    conn = db(); ochiq = conn.execute("SELECT id FROM kafolat_murojaat WHERE serial_id=? AND status='ochiq'", (sr['id'],)).fetchall(); conn.close()
    if can(u, 'boshqaruv'):
        kb += [[_btn(f"✅ Murojaat #{r[0]} ni yopish", f"sn:mc:{r[0]}")] for r in ochiq]
    kb.append([_btn("⬅️ Orqaga", "sn:menu")] + _x_btn('sn'))
    return kb


def _sn_murojaatlar():
    conn = db()
    rows = conn.execute("SELECT m.id, m.opened, m.product, m.customer, m.note, m.serial_id, COALESCE(s.serial,'') FROM kafolat_murojaat m "
                        "LEFT JOIN serials s ON s.id=m.serial_id WHERE m.status='ochiq' ORDER BY m.id DESC LIMIT 15").fetchall()
    conn.close()
    if not rows: return "🛠 Ochiq kafolat murojaati yo'q.", [[_btn("⬅️ Orqaga", "sn:menu")] + _x_btn('sn')]
    m = ["🛠 OCHIQ KAFOLAT MUROJAATLARI:"]
    kb = []
    for r in rows:
        m.append(f"#{r[0]} · {r[1]} · {r[2]} · SN {r[6]} · {r[3] or '—'}\n   {r[4]}")
        if r[5]: kb.append([_btn(f"🔎 #{r[0]} · {r[6]}", f"sn:v:{r[5]}")])
    kb.append([_btn("⬅️ Orqaga", "sn:menu")] + _x_btn('sn'))
    return "\n".join(m), kb


async def cmd_serial(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """🔢 Serial tugmasi / /serial [raqam]"""
    if not can(u, 'stock_view'): return
    st = _ui_yangi(ctx, 'sn', wait='find')
    arg = " ".join(ctx.args or []) if getattr(ctx, 'args', None) else ''
    if arg:
        st['wait'] = None
        return await kod_natija(u, ctx, arg, 'sn')
    m, r = _sn_menu(u)
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))


async def sn_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not can(u, 'stock_view'):
        await q.answer("Ruxsat yo'q", show_alert=True); return
    parts = (q.data or '').split(':'); act = parts[1] if len(parts) > 1 else ''; arg = parts[2:]
    if act == 'x':
        ctx.user_data.pop('sn', None); await q.answer()
        return await _pos_chiqar(q, "🔢 Serial oynasi yopildi.", None)
    st = _ui_ol(ctx, 'sn') or _ui_yangi(ctx, 'sn')
    st['wait'] = None
    m = rows = None; alert = None

    def _i(k, d=0):
        try: return int(arg[k])
        except (IndexError, ValueError): return d
    if act == 'menu':
        st['wait'] = 'find'; m, rows = _sn_menu(u)
    elif act == 'pl':
        m, rows = _sn_tovarlar(u, _i(0))
    elif act == 'pp':
        m, rows = _sn_tovar(u, _i(0))
    elif act == 'tg':
        if not can(u, 'ombor'): alert = "Faqat egasi/admin"
        else:
            yangi = serial_rejim(_i(0)); alert = None if yangi is None else ("✅ Serialli rejim yoqildi" if yangi else "Serialli rejim o'chirildi")
            m, rows = _sn_tovar(u, _i(0))
    elif act == 'in':
        if not can(u, 'ombor'): alert = "Faqat egasi/admin"
        else:
            p = _omb_mahsulot(_i(0))
            if not p: alert = "Mahsulot topilmadi"
            else:
                if not _serialli(p['id']): serial_rejim(p['id'], True)
                st['wait'] = f"in:{p['id']}"
                s = serial_holat_soni(p['id'])
                m = (f"🔢 {p['name']} — serial raqamlarni yuboring" + (f" ({_i(1)} ta keldi)" if _i(1) else "") + ".\n"
                     f"Bir xabarda bir nechta: har birini yangi qatorga yoki vergul bilan.\n📷 Shtrix-kod rasmini ham yuborsa bo'ladi.\n"
                     f"Serial kutilmoqda: {s['_bosh']} ta")
                rows = [[_btn("✔ Tayyor", f"sn:pp:{p['id']}")]]
    elif act == 'v':
        sr = serial_ol(_i(0))
        if not sr: alert = "Topilmadi"
        else: m, rows = serial_karta(sr), _sn_karta_kb(u, sr)
    elif act == 'mn':
        sr = serial_ol(_i(0))
        if not sr: alert = "Topilmadi"
        else:
            st['wait'] = f"mn:{sr['id']}"
            m, rows = f"🛠 {sr['serial']} — muammoni qisqa yozing (masalan: 'qizimayapti'):", [[_btn("⬅️ Orqaga", f"sn:v:{sr['id']}")]]
    elif act == 'mc':
        if not can(u, 'boshqaruv'): alert = "Faqat egasi/admin"
        else:
            st['wait'] = f"mc:{_i(0)}"
            m, rows = f"✅ Murojaat #{_i(0)} — natijani yozing (masalan: 'almashtirildi', 'ta'mirlandi'):", [[_btn("⬅️ Orqaga", "sn:mo")]]
    elif act == 'mo':
        m, rows = _sn_murojaatlar()
    else:
        alert = "Eski tugma"
    await q.answer(alert[:190] if alert else None, show_alert=bool(alert))
    if m is not None: await _pos_chiqar(q, m, rows)


async def sn_matn(u, ctx, msg):
    st = _ui_ol(ctx, 'sn')
    if not st or not st.get('wait') or not can(u, 'stock_view'): return False
    w = st['wait']
    if w == 'find':
        return await kod_natija(u, ctx, msg, 'sn')
    if w.startswith('in:'):
        if not can(u, 'ombor'): return False
        pid = int(w.split(':')[1]); p = _omb_mahsulot(pid)
        res = serial_qosh(pid, msg, _ui_user(u), ref='qo\'lda')
        s = serial_holat_soni(pid)
        await u.message.reply_text(serial_qosh_matn(res, p['name'] if p else '') + f"\n\nYana serial kutilmoqda: {s['_bosh']} ta. Davom eting yoki ✔ Tayyor.",
                                   reply_markup=InlineKeyboardMarkup([[_btn("✔ Tayyor", f"sn:pp:{pid}")]]))
        return True
    if w.startswith('mn:'):
        st['wait'] = None
        res = murojaat_och(int(w.split(':')[1]), msg, _ui_user(u))
        sr = serial_ol(int(w.split(':')[1]))
        await u.message.reply_text((f"✅ Murojaat #{res['id']} ochildi.\n\n" if res['ok'] else f"⚠️ {res['error']}\n\n") + (serial_karta(sr) if sr else ''),
                                   reply_markup=InlineKeyboardMarkup(_sn_karta_kb(u, sr)) if sr else None)
        if res['ok'] and OWNER_ID and _uid(u) != OWNER_ID and sr:
            try: await ctx.bot.send_message(chat_id=OWNER_ID, text=f"🛠 Yangi kafolat murojaati #{res['id']}\n{sr['product']} · SN {sr['serial']}\n{sr['customer'] or ''}\n📝 {msg[:300]}")
            except Exception as e: log.warning("murojaat egaga: %s", e)
        return True
    if w.startswith('mc:'):
        if not can(u, 'boshqaruv'): return False
        st['wait'] = None
        ok = murojaat_yop(int(w.split(':')[1]), msg, _ui_user(u))
        m, rows = _sn_murojaatlar()
        await u.message.reply_text(("✅ Murojaat yopildi.\n\n" if ok else "⚠️ Allaqachon yopilgan.\n\n") + m, reply_markup=InlineKeyboardMarkup(rows))
        return True
    return False


# ── POS: serialli tovar ──
def _pos_sn_hook(pos, act, arg):
    try: pid = int(arg[0])
    except (IndexError, ValueError): return False
    return _serialli(pid)


def pos_ekran_serial(pos, p, izoh=''):
    it = _pos_qator(pos, p['id'])
    tanlangan = list(zip(it.get('serials', []), it.get('sn', []))) if it else []
    band = {s for s, _ in tanlangan}
    om = [x for x in serial_omborda(p['id'], 60) if x[0] not in band]
    s = serial_holat_soni(p['id'])
    m = [f"🔢 {p['name']} — serialli tovar", f"Narx: {_usd2(p['price'] or 0)}", ""]
    if izoh: m.insert(0, izoh + "\n")
    m.append("Savatda: " + (", ".join(sn for _, sn in tanlangan) if tanlangan else "hali yo'q"))
    m.append("Serialni tanlang yoki yozing / skanerlang (📷 rasm ham bo'ladi).")
    if s['_bosh'] > 0: m.append(f"ℹ️ {s['_bosh']} ta tovar seriali kiritilmagan — yozsangiz shu yerning o'zida qo'shiladi.")
    rows = [[_btn(f"✅ {sn} (olib tashlash)", f"pos:sn:{p['id']}:{sid}")] for sid, sn in tanlangan[:8]]
    btns = [_btn(sn[:20], f"pos:sn:{p['id']}:{sid}") for sid, sn in om[:18]]
    rows += [btns[i:i + 2] for i in range(0, len(btns), 2)]
    rows.append([_btn("✍️ Serial yozish / skaner", f"pos:snw:{p['id']}")])
    rows.append([_btn("⬅️ Orqaga", "pos:cats")] + _pos_savat_btn(pos))
    rows.append(_pos_bekor())
    return "\n".join(m), rows


def _pos_sn_qosh(pos, p, sid, sn):
    """True — qo'shildi; False — savatda bor; None — astatka yetmaydi."""
    it = _pos_qator(pos, p['id'])
    if it and sid in it.get('serials', []): return False
    if _pos_mavjud(pos, p['id'], p['qty']) <= 0: return None
    if not it:
        pos['items'].append({'pid': p['id'], 'name': p['name'], 'qty': 0, 'list': float(p['price'] or 0),
                             'price': float(p['price'] or 0), 'serials': [], 'sn': []})
        it = pos['items'][-1]
    it.setdefault('serials', []); it.setdefault('sn', [])
    if sid in it['serials']: return False
    it['serials'].append(sid); it['sn'].append(sn); it['qty'] = len(it['serials'])
    return True


def _pos_sn_ol(pos, pid, sid):
    it = _pos_qator(pos, pid)
    if not it or sid not in it.get('serials', []): return False
    i = it['serials'].index(sid); it['serials'].pop(i); it['sn'].pop(i); it['qty'] = len(it['serials'])
    if it['qty'] <= 0: pos['items'].remove(it)
    return True


def _pos_sn_xato(pos):
    for it in pos['items']:
        if _serialli(it['pid']) and len(set(it.get('serials') or [])) != it['qty']:
            return f"{it['name']}: serial raqam tanlanmagan ({len(it.get('serials') or [])}/{it['qty']}) — savatdan o'chirib, qayta qo'shing"
    return None


async def pos_sn_callback(u, ctx, pos, act, arg):
    q = u.callback_query
    try: pid = int(arg[0])
    except (IndexError, ValueError):
        await q.answer("Xato"); return
    p = _pos_mahsulot(pid)
    if not p:
        await q.answer("Mahsulot topilmadi", show_alert=True); return
    izoh = ''
    if act == 'sn':
        try: sid = int(arg[1])
        except (IndexError, ValueError): sid = 0
        if _pos_sn_ol(pos, pid, sid): izoh = "🗑 Olib tashlandi"
        else:
            sr = serial_ol(sid) if sid else None
            if not sr or sr['status'] != 'omborda' or sr['product_id'] != pid:
                await q.answer("Bu serial endi mavjud emas", show_alert=True)
            else:
                ok_ = _pos_sn_qosh(pos, p, sid, sr['serial'])
                izoh = f"✅ {sr['serial']} qo'shildi" if ok_ else ("⛔ Astatka yetmaydi" if ok_ is None else "")
    elif act == 'snw':
        pos['wait'] = f"sn:{pid}"
        await q.answer()
        return await _pos_chiqar(q, f"✍️ {p['name']} — serial raqamni yozing yoki skanerlang (bir nechtasini vergul bilan ham bo'ladi).\n📷 Shtrix-kod rasmini yuborsangiz ham bo'ladi.",
                                 [[_btn("⬅️ Orqaga", f"pos:p:{pid}")], _pos_bekor()])
    elif act == 'ei' and arg[1:2] == ['-1']:
        it = _pos_qator(pos, pid)
        if it and it.get('serials'): _pos_sn_ol(pos, pid, it['serials'][-1]); izoh = "➖ Oxirgi serial olib tashlandi"
    else:
        izoh = "🔢 Serialli tovar — sonini serial tanlab belgilang"
    await q.answer()
    m, r = pos_ekran_serial(pos, p, izoh)
    await _pos_chiqar(q, m, r)


async def pos_kod_matn(u, ctx, pos, msg, w):
    """POS: serial/shtrix-kod matni (yozilgan, skaner ilovasi yoki rasm). True qaytaradi."""
    rate = get_exchange_rate()
    pid0 = int(w.split(':')[1]) if w.startswith('sn:') else None
    natija = []; ochiladi = None
    kodlar = serial_ajrat(msg) if pid0 else [msg.strip()]
    for kod in kodlar[:30]:
        sr = serial_top(kod)
        if sr:
            if pid0 and sr['product_id'] != pid0: natija.append(f"⛔ {kod} — boshqa tovar ({sr['product']})"); continue
            if sr['status'] != 'omborda':
                natija.append(f"⛔ {kod} — {SERIAL_HOLAT.get(sr['status'], sr['status'])}" + (f" ({sr['sold_date']}, {sr['customer'] or '—'})" if sr['sale_id'] else "")); continue
            p = _pos_mahsulot(sr['product_id'])
            if not p: natija.append(f"⛔ {kod} — tovar topilmadi"); continue
            ok_ = _pos_sn_qosh(pos, p, sr['id'], sr['serial'])
            natija.append(f"✅ {sr['serial']} — {p['name']}" if ok_ else
                          (f"⛔ {sr['serial']} — astatka yetmaydi" if ok_ is None else f"ℹ️ {sr['serial']} savatda bor"))
            ochiladi = ochiladi or p
            continue
        k = kod_top(kod) if not pid0 else None
        if k and k['tur'] == 'tovar':
            p = _pos_mahsulot(k['pid'])
            if p:
                pos['wait'] = None
                if _serialli(p['id']):
                    m, r = pos_ekran_serial(pos, p, f"🏷 {kod} → {p['name']}")
                elif _pos_mavjud(pos, p['id'], p['qty']) <= 0:
                    m, r = f"❌ {p['name']} — astatkada yo'q", [[_btn("⬅️ Kategoriyalar", "pos:cats")], _pos_bekor()]
                else:
                    m, r = pos_ekran_son(pos, p, rate); m = f"🏷 {kod} → {p['name']}\n\n" + m
                await u.message.reply_text(m[:4000], reply_markup=InlineKeyboardMarkup(r)); return True
        if pid0:
            res = serial_qosh(pid0, kod, _ui_user(u), ref='pos')
            if res['qoshildi']:
                p = _pos_mahsulot(pid0)
                ok_ = _pos_sn_qosh(pos, p, res['ids'][0], res['qoshildi'][0]); ochiladi = ochiladi or p
                natija.append(f"✅ {kod} — ro'yxatga olindi va savatga qo'shildi" if ok_ else f"✅ {kod} — ro'yxatga olindi (savatga: astatka yetmaydi)")
            else:
                natija.append(f"⛔ {kod} — " + ("astatkadan ortiq (avval kirim qiling)" if res['ortiqcha'] else
                                               "noto'g'ri format" if res['xato'] else "allaqachon bor" if res['band'] else "qo'shilmadi"))
        else:
            natija.append(f"⛔ '{kod[:30]}' — bunday kod/serial topilmadi")
    p = ochiladi or (_pos_mahsulot(pid0) if pid0 else None)
    if p:
        if pid0: pos['wait'] = f"sn:{pid0}"          # ketma-ket skanerlash davom etadi
        m, r = pos_ekran_serial(pos, p, "\n".join(natija))
    else:
        pos['wait'] = 'search'
        m, r = "\n".join(natija) + "\n\nQaytadan yozing (nom, serial yoki shtrix-kod):", [[_btn("⬅️ Kategoriyalar", "pos:cats")], _pos_bekor()]
    await u.message.reply_text(m[:4000], reply_markup=InlineKeyboardMarkup(r))
    return True


# ── 🏷 SHTRIX-KOD / QR: yaratish, yorliq varaqlari, rasmdan o'qish ─────────────────────
# zxing-cpp (pip, tizim kutubxonasi kerak emas) bo'lsa — QR/Code128 yaratish va rasmdan o'qish.
# Bo'lmasa: Code128 o'zimizning sof-Python chizgich bilan, QR — 'qrcode' kutubxonasi bo'lsa; o'qish — opencv/pyzbar
# bo'lsa, aks holda foydalanuvchi kodni yozadi (telefondagi skaner ilovasi ham matn yuboradi).
try:
    import zxingcpp as _zx
except Exception:                                    # o'rnatilmagan — fallback
    _zx = None
KOD_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9\-_/.+]{2,47}$')
_C128 = ("212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 221312 231212 112232 122132 122231 113222 "
         "123122 123221 223211 221132 221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 212123 212321 "
         "232121 111323 131123 131321 112313 132113 132311 211313 231113 231311 112133 112331 132131 113123 113321 133121 "
         "313121 211331 231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 314111 221411 431111 111224 "
         "111422 121124 121421 141122 141221 112214 112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 "
         "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 214121 412121 111143 111341 131141 114113 "
         "114311 411113 411311 113141 114131 311141 411131 211412 211214 211232").split()
_C128_STOP = "2331112"


def _c128_modullar(matn):
    """Code128-B: [qora/oq kengliklar] ro'yxati (sof Python)."""
    vals = [104] + [ord(ch) - 32 for ch in matn]
    chk = (104 + sum(i * v for i, v in enumerate(vals[1:], 1))) % 103
    out = []
    for v in vals + [chk]: out += [int(x) for x in _C128[v]]
    return out + [int(x) for x in _C128_STOP]


def _pil():
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except Exception:
        return None


def _shrift(size, bold=False):
    _, _, ImageFont = _pil()
    try:
        import matplotlib
        f = os.path.join(matplotlib.get_data_path(), 'fonts', 'ttf', 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')
        return ImageFont.truetype(f, size)
    except Exception:
        try: return ImageFont.load_default(size=size)
        except Exception: return ImageFont.load_default()


def kod_rasm(kod, tur='code128', balandlik=120, modul=3):
    """PIL rasm (oq fonda qora). tur: 'code128' | 'qr'. Imkon bo'lmasa None."""
    P = _pil()
    if not P or not kod: return None
    Image, ImageDraw, _ = P
    if _zx is not None:
        try:
            fmt = _zx.BarcodeFormat.QRCode if tur == 'qr' else _zx.BarcodeFormat.Code128
            b = _zx.create_barcode(kod, fmt)
            import numpy as _np
            im = Image.fromarray(_np.array(b.to_image(scale=(8 if tur == 'qr' else modul), add_quiet_zones=True))).convert('L')
            if tur != 'qr' and im.height != balandlik:
                im = im.resize((im.width, balandlik), Image.NEAREST)
            return im
        except Exception as e:
            log.warning("zxing yaratish: %s", e)
    if tur == 'qr':
        try:
            import qrcode
            return qrcode.make(kod, box_size=8, border=2).get_image().convert('L')
        except Exception:
            tur = 'code128'                              # QR imkoni yo'q — Code128
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in kod): return None
    w = _c128_modullar(kod); q = 10
    im = Image.new('L', ((sum(w) + 2 * q) * modul, balandlik), 255)
    d = ImageDraw.Draw(im); x = q * modul
    for i, wd in enumerate(w):
        if i % 2 == 0: d.rectangle([x, 0, x + wd * modul - 1, balandlik - 1], fill=0)
        x += wd * modul
    return im


def kod_oqi(raw):
    """Rasm baytlari → topilgan kodlar matni ro'yxati (bo'sh — o'qilmadi yoki kutubxona yo'q)."""
    P = _pil()
    if not P or not raw: return []
    Image = P[0]
    try:
        im = Image.open(io.BytesIO(bytes(raw))); im.load(); im = im.convert('RGB')
    except Exception:
        return []
    out = []
    if _zx is not None:
        try:
            for variant in (im, im.convert('L').resize((im.width * 2, im.height * 2)) if max(im.size) < 900 else None):
                if variant is None: continue
                out = [r.text for r in _zx.read_barcodes(variant) if r.text]
                if out: return list(dict.fromkeys(out))
        except Exception as e:
            log.warning("zxing o'qish: %s", e)
    try:
        import cv2, numpy as _np
        arr = cv2.cvtColor(_np.array(im), cv2.COLOR_RGB2BGR)
        t, *_ = cv2.QRCodeDetector().detectAndDecode(arr)
        if t: return [t]
        if hasattr(cv2, 'barcode'):
            ok, infos, *_ = cv2.barcode.BarcodeDetector().detectAndDecode(arr)
            vals = [x for x in (infos if isinstance(infos, (list, tuple)) else [infos]) if x]
            if vals: return list(dict.fromkeys(vals))
    except Exception:
        pass
    try:
        from pyzbar import pyzbar
        out = [r.data.decode('utf-8', 'ignore') for r in pyzbar.decode(im)]
        if out: return list(dict.fromkeys(out))
    except Exception:
        pass
    return []


def kod_oqish_mavjud():
    if _zx is not None: return 'zxing-cpp'
    for mod in ('cv2', 'pyzbar'):
        try:
            __import__(mod); return mod
        except Exception:
            pass
    return None


def tovar_kodi(pid, yarat=True):
    """Tovarning shtrix-kodi; bo'sh bo'lsa ichki 'TC000123' beriladi (yarat=True)."""
    conn = db(); c = conn.cursor()
    c.execute("SELECT COALESCE(barcode,'') FROM products WHERE id=?", (int(pid),)); r = c.fetchone()
    if not r: conn.close(); return None
    if r[0] or not yarat: conn.close(); return r[0] or None
    kod = f"TC{int(pid):06d}"
    for k in range(5):
        try:
            c.execute("UPDATE products SET barcode=? WHERE id=? AND COALESCE(barcode,'')=''", (kod, int(pid))); conn.commit(); break
        except sqlite3.IntegrityError:
            kod = f"TC{int(pid):06d}{k + 1}"
    c.execute("SELECT COALESCE(barcode,'') FROM products WHERE id=?", (int(pid),)); kod = c.fetchone()[0]
    conn.close()
    return kod or None


def tovar_kodi_ornat(pid, kod):
    kod = (kod or '').strip()
    if not KOD_RE.match(kod): return {'ok': False, 'error': "Kod 3–48 belgi bo'lsin (harf, raqam, - _ / . +)"}
    sr = serial_top(kod)
    if sr: return {'ok': False, 'error': f"Bu kod {sr['product']} seriali sifatida ro'yxatda"}
    conn = db(); c = conn.cursor()
    try:
        c.execute("UPDATE products SET barcode=? WHERE id=?", (kod, int(pid))); conn.commit()
    except sqlite3.IntegrityError:
        c.execute("SELECT name FROM products WHERE barcode=? COLLATE NOCASE", (kod,)); r = c.fetchone(); conn.close()
        return {'ok': False, 'error': f"Bu kod allaqachon boshqa tovarda: {r[0] if r else '?'}"}
    conn.close()
    return {'ok': True, 'kod': kod}


def kod_top(matn):
    """Matn → {'tur': 'serial', 'sr': {...}} | {'tur': 'tovar', 'pid', 'nom', 'kod'} | None."""
    s = (matn or '').strip()
    if not s or len(s) > 60 or '\n' in s: return None
    sr = serial_top(s)
    if sr: return {'tur': 'serial', 'sr': sr}
    try:
        conn = db(); c = conn.cursor()
        c.execute("SELECT id, name, barcode FROM products WHERE COALESCE(barcode,'')<>'' AND barcode=? COLLATE NOCASE", (s,))
        r = c.fetchone()
        if not r:
            mt = re.fullmatch(r'TC(\d{6})\d?', s, re.I)
            if mt:
                c.execute("SELECT id, name, COALESCE(barcode,'') FROM products WHERE id=?", (int(mt.group(1)),)); r = c.fetchone()
        conn.close()
    except sqlite3.OperationalError:
        return None
    return {'tur': 'tovar', 'pid': r[0], 'nom': r[1], 'kod': r[2] or s} if r else None


def _yorliq_bitta(nom, narx, kod, tur, w, h, rate):
    """Bitta yorliq rasmi (w×h px): nom, narx ($ + so'm), shtrix-kod/QR, kod matni."""
    Image, ImageDraw, _ = _pil()
    im = Image.new('L', (w, h), 255); d = ImageDraw.Draw(im)
    f1, f2, f3 = _shrift(max(14, h // 11), True), _shrift(max(13, h // 12)), _shrift(max(11, h // 15))
    pad = max(6, w // 40)
    qatorlar, cur = [], ''
    for so in str(nom).split():
        t = (cur + ' ' + so).strip()
        if d.textlength(t, font=f1) <= w - 2 * pad: cur = t
        else:
            if cur: qatorlar.append(cur)
            cur = so
    if cur: qatorlar.append(cur)
    y = pad
    for ql in qatorlar[:2]:
        d.text((pad, y), ql, font=f1, fill=0); y += f1.size + 3
    if narx:
        d.text((pad, y), f"${narx:,.2f}" + (f" · {narx * rate:,.0f} so'm".replace(',', ' ') if rate else ''), font=f2, fill=0)
        y += f2.size + 4
    br = kod_rasm(kod, tur)
    joy_h = h - y - f3.size - 2 * pad
    if br is not None and joy_h > 20:
        k = min((w - 2 * pad) / br.width, joy_h / br.height)
        if tur == 'qr' or k < 1:
            br = br.resize((max(1, int(br.width * k)), max(1, int(br.height * k))), Image.NEAREST)
        else:
            br = br.resize((min(w - 2 * pad, br.width), joy_h), Image.NEAREST)
        im.paste(br, ((w - br.width) // 2, y)); y += br.height + 2
    d.text(((w - d.textlength(kod, font=f3)) / 2, min(y, h - f3.size - pad)), kod, font=f3, fill=0)
    d.rectangle([0, 0, w - 1, h - 1], outline=180)
    return im


def yorliq_varaq(elementlar, tur='code128', fayl=None, yakka=False):
    """elementlar: [(nom, narx_usd, kod)] → A4 PDF (3×8 = 24 ta/sahifa) yoki yakka=True — bitta yorliq PNG (58×40 mm).
    Qaytaradi fayl yo'li yoki None (Pillow yo'q)."""
    if not _pil() or not elementlar: return None
    Image = _pil()[0]
    rate = get_exchange_rate()
    if yakka:
        nom, narx, kod = elementlar[0]
        im = _yorliq_bitta(nom, narx, kod, tur, 464, 320, rate)          # 58×40 mm @ 203 dpi (termoprinter)
        fayl = fayl or os.path.join(tempfile.gettempdir(), f"yorliq_{secrets.token_hex(3)}.png")
        im.save(fayl, 'PNG', dpi=(203, 203)); return fayl
    W, H, kol, qat, chet = 1654, 2339, 3, 8, 50                           # A4 @ 200 dpi
    lw, lh = (W - 2 * chet) // kol, (H - 2 * chet) // qat
    sahifalar = []
    for i in range(0, len(elementlar), kol * qat):
        pg = Image.new('L', (W, H), 255)
        for j, (nom, narx, kod) in enumerate(elementlar[i:i + kol * qat]):
            pg.paste(_yorliq_bitta(nom, narx, kod, tur, lw - 10, lh - 10, rate), (chet + (j % kol) * lw + 5, chet + (j // kol) * lh + 5))
        sahifalar.append(pg.convert('RGB'))
    fayl = fayl or os.path.join(tempfile.gettempdir(), f"yorliqlar_{secrets.token_hex(3)}.pdf")
    sahifalar[0].save(fayl, 'PDF', resolution=200.0, save_all=True, append_images=sahifalar[1:])
    return fayl


# ── 🏷 Yorliqlar oynasi (prefiks 'kod:'), skanerlash va umumiy matn dispetcheri ────────
def _kod_menu(st):
    tur = st.get('tur', 'code128'); tan = st.setdefault('tan', {})
    m = ["🏷 YORLIQLAR (shtrix-kod / QR)", "",
         "Tovarlarni belgilang → 🖨 PDF (A4, 24 ta/varaq). Yorliqda: nom, narx ($ va so'm), kod.",
         f"Kod turi: {'QR' if tur == 'qr' else 'Shtrix-kod (Code128)'}",
         f"Tanlangan: {len(tan)} tovar, {sum(tan.values())} ta yorliq"]
    if not kod_oqish_mavjud(): m.append("ℹ️ Rasmdan o'qish kutubxonasi yo'q — kodni yozing yoki telefon skaner ilovasidan yuboring.")
    rows = [[_btn("📋 Tovar tanlash", "kod:pl:0"), _btn("🗂 Astatkadagi hammasi", "kod:all")],
            [_btn(f"🔁 Turi: {'QR' if tur == 'qr' else 'Code128'}", "kod:fmt"), _btn("📷 Skanerlash", "kod:sc")]]
    if tan: rows.append([_btn(f"🖨 PDF ({sum(tan.values())} ta)", "kod:pdf"), _btn("🧹 Tozalash", "kod:clr")])
    rows.append(_x_btn('kod'))
    return "\n".join(m), rows


def _kod_tovarlar(st, page=0):
    prods = sorted(get_products(), key=lambda p: p['name'])
    per = 10; pages = max(1, math.ceil(len(prods) / per)); page = min(max(0, page), pages - 1)
    tan = st.setdefault('tan', {})
    rows = [[_btn(f"{'✅ ' + str(tan[p['id']]) + '× ' if p['id'] in tan else '▫️ '}{p['name'][:28]} · {p['qty'] or 0} ta",
                  f"kod:t:{p['id']}:{page}")] for p in prods[page * per:(page + 1) * per]]
    nav = ([_btn("◀️", f"kod:pl:{page - 1}")] if page else []) + [_btn(f"{page + 1}/{pages}", "pos:noop")] + \
          ([_btn("▶️", f"kod:pl:{page + 1}")] if page < pages - 1 else [])
    rows.append(nav)
    rows.append([_btn("✔ Tayyor", "kod:menu")] + _x_btn('kod'))
    return "Bosing: 1 → 2 → 5 → 10 → olib tashlash (yorliq soni):", rows


def _kod_tovar(pid):
    p = _omb_mahsulot(pid)
    if not p: return "Topilmadi", [[_btn("⬅️ Orqaga", "kod:menu")]]
    kod = tovar_kodi(pid, yarat=False)
    s = serial_holat_soni(pid)
    m = [f"🏷 {p['name']}", f"Narx: {_usd2(p['price'])} · astatka {p['qty']} ta",
         f"Shtrix-kod: {kod or 'yo‘q (yorliq chiqarilsa TC' + format(pid, '06d') + ' beriladi)'}"]
    rows = [[_btn(f"🖨 {n} ta", f"kod:pp:{pid}:{n}") for n in (1, 5, 10)] + ([_btn(f"🖨 {p['qty']} ta", f"kod:pp:{pid}:{p['qty']}")] if p['qty'] > 1 else []),
            [_btn("🖼 Yakka yorliq PNG", f"kod:png:{pid}"), _btn("✍️ Kodni o'rnatish", f"kod:set:{pid}")]]
    if s.get('omborda'): rows.append([_btn(f"🔢 Serial yorliqlari ({s['omborda']} ta, QR)", f"kod:sl:{pid}")])
    rows.append([_btn("⬅️ Ombor kartasi", f"omb:p:{pid}")] + _x_btn('kod'))
    return "\n".join(m), rows


async def _kod_yubor(u, ctx, q, elementlar, tur, yakka=False, nom='yorliqlar'):
    if not _pil():
        await q.message.reply_text("⚠️ Rasm kutubxonasi (Pillow) o'rnatilmagan. Kodlar:\n" + "\n".join(f"{e[0]}: {e[2]}" for e in elementlar[:50]))
        return
    fayl = await asyncio.to_thread(yorliq_varaq, elementlar, tur, None, yakka)
    try:
        with open(fayl, 'rb') as fh:
            await ctx.bot.send_document(chat_id=u.effective_chat.id, document=fh, filename=f"{nom}.{'png' if yakka else 'pdf'}",
                                            caption=f"🏷 {len(elementlar)} ta yorliq · {'QR' if tur == 'qr' else 'Code128'}")
    finally:
        try: os.remove(fayl)
        except OSError: pass


async def cmd_yorliq(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """🏷 Yorliqlar / /yorliq"""
    if not can(u, 'ombor'):
        if user_role(u): await u.message.reply_text("🏷 Yorliqlar — faqat egasi/admin.")
        return
    st = _ui_yangi(ctx, 'kod', tur='code128', tan={})
    m, r = _kod_menu(st)
    await u.message.reply_text(m, reply_markup=InlineKeyboardMarkup(r))


async def kod_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    parts = (q.data or '').split(':'); act = parts[1] if len(parts) > 1 else ''; arg = parts[2:]
    if act == 'x':
        ctx.user_data.pop('kod', None); await q.answer()
        return await _pos_chiqar(q, "🏷 Oyna yopildi.", None)
    if not (can(u, 'ombor') or (act == 'sc' and can(u, 'stock_view'))):
        await q.answer("Faqat egasi/admin", show_alert=True); return
    st = _ui_ol(ctx, 'kod') or _ui_yangi(ctx, 'kod', tur='code128', tan={})
    st['wait'] = None
    m = rows = None; alert = None

    def _i(k, d=0):
        try: return int(arg[k])
        except (IndexError, ValueError): return d
    if act == 'menu':
        m, rows = _kod_menu(st)
    elif act == 'pl':
        m, rows = _kod_tovarlar(st, _i(0))
    elif act == 't':
        tan = st.setdefault('tan', {}); pid = _i(0)
        nxt = {None: 1, 1: 2, 2: 5, 5: 10}.get(tan.get(pid))
        if nxt: tan[pid] = nxt
        else: tan.pop(pid, None)
        m, rows = _kod_tovarlar(st, _i(1))
    elif act == 'all':
        st['tan'] = {p['id']: 1 for p in get_products() if (p['qty'] or 0) > 0}
        m, rows = _kod_menu(st)
    elif act == 'clr':
        st['tan'] = {}; m, rows = _kod_menu(st)
    elif act == 'fmt':
        st['tur'] = 'code128' if st.get('tur') == 'qr' else 'qr'; m, rows = _kod_menu(st)
    elif act == 'sc':
        st['wait'] = 'scan'
        m, rows = "📷 Shtrix-kod/QR rasmini yuboring yoki kodni yozing (telefon skaner ilovasi ham bo'ladi):", [_x_btn('kod')]
    elif act in ('pdf', 'pp', 'png', 'sl'):
        if act == 'pdf':
            reja = list(st.get('tan', {}).items())
        elif act == 'pp':
            reja = [(_i(0), max(1, min(200, _i(1, 1))))]
        else:
            reja = [(_i(0), 1)]
        by = {p['id']: p for p in get_products()}
        el = []
        if act == 'sl':
            p = by.get(_i(0))
            el = [(p['name'], p['price'] or 0, sn) for _, sn in serial_omborda(_i(0), 500)] if p else []
        else:
            for pid, n in reja:
                p = by.get(pid)
                if not p: continue
                kod = tovar_kodi(pid)
                el += [(p['name'], p['price'] or 0, kod)] * n
        if not el: alert = "Tanlangan tovar yo'q"
        elif len(el) > 1000: alert = "Juda ko'p (1000 dan ortiq) — kamroq tanlang"
        else:
            await q.answer("⏳ Tayyorlanmoqda...")
            try:
                await _kod_yubor(u, ctx, q, el, 'qr' if act == 'sl' else st.get('tur', 'code128'), yakka=(act == 'png'))
            except Exception as e:
                log.exception("yorliq"); await q.message.reply_text(f"⚠️ Yorliq xatosi: {str(e)[:150]}")
            return
    elif act == 'p':
        m, rows = _kod_tovar(_i(0))
    elif act == 'set':
        st['wait'] = f"set:{_i(0)}"
        m, rows = ("✍️ Tovar qutisidagi shtrix-kodni yozing yoki rasmini yuboring (masalan EAN-13 raqami):",
                   [[_btn("⬅️ Orqaga", f"kod:p:{_i(0)}")]])
    else:
        alert = "Eski tugma"
    await q.answer(alert[:190] if alert else None, show_alert=bool(alert))
    if m is not None: await _pos_chiqar(q, m, rows)


async def kod_natija(u, ctx, msg, joy='sn'):
    """Kod/serial → karta (tovar yoki serial). Topilmasa xabar. True qaytaradi."""
    k = kod_top(msg)
    if not k:
        await u.message.reply_text(f"🔎 '{(msg or '')[:40]}' — bunday serial yoki shtrix-kod topilmadi. Qaytadan yozing:",
                                   reply_markup=InlineKeyboardMarkup([_x_btn(joy if joy in ('sn', 'kod') else 'sn')]))
        st = _ui_ol(ctx, joy)
        if st is not None: st['wait'] = 'find' if joy == 'sn' else ('scan' if joy == 'kod' else 'search')
        return True
    if k['tur'] == 'serial':
        _ui_ol(ctx, 'sn') or _ui_yangi(ctx, 'sn')
        await u.message.reply_text(serial_karta(k['sr']), reply_markup=InlineKeyboardMarkup(_sn_karta_kb(u, k['sr'])))
    else:
        _ui_ol(ctx, 'omb') or _ui_yangi(ctx, 'omb')
        m, r = _omb_karta(u, k['pid'])
        await u.message.reply_text(f"🏷 {k['kod']}\n" + m, reply_markup=InlineKeyboardMarkup(r))
    return True


async def kod_matn(u, ctx, msg):
    st = _ui_ol(ctx, 'kod')
    if not st or not st.get('wait'): return False
    w = st['wait']
    if w == 'scan':
        if not can(u, 'stock_view'): return False
        st['wait'] = None
        return await kod_natija(u, ctx, msg, 'kod')
    if w.startswith('set:') and can(u, 'ombor'):
        pid = int(w.split(':')[1])
        res = tovar_kodi_ornat(pid, msg)
        if not res['ok']:
            await u.message.reply_text(f"⚠️ {res['error']}\nQaytadan yozing:"); return True
        st['wait'] = None
        m, r = _kod_tovar(pid)
        await u.message.reply_text(f"✅ Shtrix-kod saqlandi: {res['kod']}\n\n" + m, reply_markup=InlineKeyboardMarkup(r))
        return True
    return False


def _skan_holat(ctx):
    """Rasm kutayotgan oyna: (joy, wait) yoki None."""
    pos = ctx.user_data.get('pos')
    if pos and (pos.get('wait') == 'search' or str(pos.get('wait') or '').startswith('sn:')):
        return 'pos', pos['wait']
    for joy, mos in (('omb', ('search',)), ('sn', ('find', 'in:')), ('kod', ('scan', 'set:')), ('qr', ('find',))):
        st = ctx.user_data.get(joy)
        w = str((st or {}).get('wait') or '')
        if w and any(w == x or (x.endswith(':') and w.startswith(x)) for x in mos):
            if time.time() - st.get('ts', 0) <= UI_TTL: return joy, w
    return None


async def skan_rasm(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """handle_photo_ai boshida: skaner kutilayotgan bo'lsa — rasmdagi shtrix-kod/QR'ni o'qiydi. True = ishlatildi."""
    if not getattr(u, 'message', None) or not u.message.photo: return False
    h = _skan_holat(ctx)
    if not h or not can(u, 'stock_view'): return False
    joy, w = h
    try:
        f = await ctx.bot.get_file(u.message.photo[-1].file_id)
        raw = bytes(await f.download_as_bytearray())
    except Exception as e:
        await u.message.reply_text(f"⚠️ Rasmni yuklab bo'lmadi: {str(e)[:120]}"); return True
    kodlar = await asyncio.to_thread(kod_oqi, raw)
    if not kodlar:
        kut = kod_oqish_mavjud()
        await u.message.reply_text("📷 Rasmdan kod o'qilmadi." + (" Yaqinroq, tekis va yorug' joyda suratga oling" if kut else
                                   " (serverda o'qish kutubxonasi yo'q)") + " yoki kodni yozib yuboring.")
        return True
    matn = "\n".join(kodlar)
    await u.message.reply_text("📷 O'qildi: " + ", ".join(kodlar)[:300])
    if joy == 'pos':
        pos = _pos_ol(ctx)
        if not pos: return True
        pos['wait'] = None
        return await pos_kod_matn(u, ctx, pos, matn if w.startswith('sn:') else kodlar[0], w)
    if joy == 'omb':
        return await kod_natija(u, ctx, kodlar[0], 'omb')
    if joy == 'qr':
        return await qr_kod_top(u, ctx, kodlar[0])
    if joy == 'sn':
        return await sn_matn(u, ctx, matn if w.startswith('in:') else kodlar[0])
    return await kod_matn(u, ctx, kodlar[0])


async def b10_matn(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """10-bosqich oynalari yozma kiritish kutayotgan bo'lsa (handle_text zanjirida)."""
    if not any(ctx.user_data.get(k) for k in ('zx', 'qr', 'sm', 'sn', 'kod')): return False
    msg = (u.message.text or '').strip()
    return (await zx_matn(u, ctx, msg) or await qr_matn(u, ctx, msg) or await sm_matn(u, ctx, msg)
            or await sn_matn(u, ctx, msg) or await kod_matn(u, ctx, msg))


async def kod_erkin(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Hech qaysi oyna kutmayotganda: xabar AYNAN ro'yxatdagi serial yoki shtrix-kod bo'lsa — kartasi.
    (Telefon skaner ilovasi kodni matn qilib yuboradi.) Boshqa barcha matn — eskicha AI/buyruqlarga."""
    msg = (u.message.text or '').strip()
    if not (6 <= len(msg) <= 48) or ' ' in msg or not can(u, 'stock_view'): return False
    harf, raqam = any(ch.isalpha() for ch in msg), any(ch.isdigit() for ch in msg)
    if not ((harf and raqam) or (msg.isdigit() and len(msg) >= 8)): return False
    if not kod_top(msg): return False
    return await kod_natija(u, ctx, msg, 'sn')


async def on_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    # Faqat egasi: aks holda kanal/forward qilingan xabardagi tugma orqali begona odam
    # hisobot ko'rishi, sotuvni bekor qilishi yoki tovarni "keldi" qilishi mumkin edi
    if not can(u, 'boshqaruv'): return
    data = q.data or ''
    msg = q.message

    async def fake_cmd(cmd_fn):
        class FakeUpdate:
            effective_user = u.effective_user
            message = msg
        await cmd_fn(FakeUpdate(), ctx)

    if data == 'stock': await fake_cmd(cmd_astatka)
    elif data == 'today': await fake_cmd(cmd_bugun)
    elif data == 'month': await fake_cmd(cmd_oy)
    elif data == 'year': await fake_cmd(cmd_yil)
    elif data == 'transit': await fake_cmd(cmd_yolda)
    elif data == 'supplier_debt': await fake_cmd(cmd_zavod_qarz)
    elif data == 'prices': await fake_cmd(cmd_narxlar)
    elif data == 'analiz': await fake_cmd(cmd_analiz)
    elif data == 'customers': await fake_cmd(cmd_mijozlar_yangi)
    elif data == 'debts': await fake_cmd(cmd_qarzlar)
    elif data == 'expenses': await fake_cmd(cmd_xarajatlar)
    elif data == 'warranties': await fake_cmd(cmd_kafolat)
    elif data == 'cashflow': await fake_cmd(cmd_cashflow)
    elif data == 'trend': await fake_cmd(cmd_trend)
    elif data == 'target': await fake_cmd(cmd_maqsad)
    elif data == 'olx': await fake_cmd(cmd_olx)
    elif data == 'undo_list': await fake_cmd(cmd_undo_list)
    elif data == 'close': await msg.delete()
    elif data.startswith('undo_'):
        # Bitta umumiy funksiya (_undo_op) — AI agent bilan bir xil mantiq, ulanish ochiq qolib bazani qulflamaydi
        try: op_id = int(data.split('_')[1])
        except (ValueError, IndexError): return
        ok, why = await asyncio.to_thread(_undo_op, op_id)
        if ok:
            await msg.reply_text(f"✅ Operatsiya #{op_id} qaytarildi!")
        elif why.startswith('Topilmadi'):
            await msg.reply_text("❌ Topilmadi yoki allaqachon qaytarilgan")
        else:
            await msg.reply_text("❌ Qaytarib bo'lmadi!" + ("" if why == "qaytarib bo'lmadi" else f"\n{why}"))
    elif data.startswith('add_photo_'):
        pid = int(data.split('_')[2])
        ctx.user_data['photo_product_id'] = pid
        await msg.reply_text("📸 Rasmlarni yuboring. Tugatish: /tayyor")
    elif data.startswith('arrive_'):
        tid = int(data.split('_')[1])
        result = arrive_transit(tid)
        if result:
            await msg.reply_text(
                f"✅ *Tovar keldi!*\n{result['product']}: {result['qty']} ta\n"
                f"Haqiqiy sebest: {fmt(result['real_cost'])}/ta\n" +
                ("Astatka yangilandi!" if result.get('found', True) else _ARRIVE_NOT_FOUND),
                parse_mode='Markdown')
        else:
            await msg.reply_text("❌ Topilmadi yoki allaqachon kelgan!")
    elif data.startswith('xlimp_'):
        await xl_callback(u, ctx, data)
    elif data.startswith('delcust_'):
        await _mijoz_ochirish_callback(q, data)
    elif data.startswith('cat_') or data.startswith('sup_') or data.startswith('photos_'):
        pass  # ConversationHandler handles these

_ARRIVE_NOT_FOUND = "⚠️ Astatkada bu nomli mahsulot topilmadi — astatka o'zgarmadi."

# ── TEXT MESSAGE HANDLER ──────────────────────────────────────────
async def handle_text(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rol = user_role(u)
    if not rol: return
    msg = u.message.text
    if msg in MENU_MAP:
        for _k in ('pos', 'omb', 'mij', 'his', 'zav', 'mkt', 'zx', 'qr', 'sm', 'sn', 'kod'):  # menyu bosildi — kutish bekor
            if ctx.user_data.get(_k): ctx.user_data[_k]['wait'] = None
    elif (await pos_matn(u, ctx) or await omb_matn(u, ctx) or await mij_matn(u, ctx)
          or await his_matn_kirit(u, ctx) or await zav_matn(u, ctx) or await mkt_matn(u, ctx)
          or await b10_matn(u, ctx) or await kod_erkin(u, ctx)):
        return
    if rol == 'sotuvchi':
        await sotuvchi_matn(u, ctx, msg); return
    if not can(u, 'boshqaruv'): return
    prods = get_products()

    # Foto qo'shish rejimi (menyu tugmasi bosilsa rejimdan chiqadi)
    if ctx.user_data.get('photo_product_id') and msg not in MENU_MAP:
        return
    ctx.user_data.pop('photo_product_id', None)

    # Menyu tugmalari
    if msg in MENU_MAP:
        await route_menu(u, ctx, msg)
        return

    # Oy tafsil: /oy_tafsil 2026-04
    if msg.startswith('/oy_tafsil '):
        month = msg.split(' ')[1].strip()
        await cmd_oy_tafsil(u, ctx, month=month)
        return

    # Oy buyrug'i: /oy 2026-07
    if msg.startswith('/oy '):
        month = msg.split(' ')[1].strip()
        await cmd_oy(u, ctx, month=month)
        return

    await u.message.chat.send_action('typing')
    # ── TO'LIQ AI REJIMI ──
    if AI_MODE == 'agent':
        await ctx.bot.send_chat_action(chat_id=u.effective_chat.id, action='typing')
        try:
            reply = await ai_agent(u.effective_user.id, msg, ctx)
        except Exception as e:
            log.exception("agent")
            reply = f"\u26a0\ufe0f AI xatosi: {str(e)[:200]}"
        await u.message.reply_text(reply)
        return

    parsed = await asyncio.to_thread(ai_parse, msg, prods)   # sinxron API chaqiruvi butun botni to'xtatmasin
    action = parsed.get('action', 'unknown')
    log.info(f"Action: {action} | {parsed}")

    if action == 'sell':
        prod = find_product(parsed.get('product',''))
        qty = max(1, int(parsed.get('qty', 1)))
        price = float(parsed.get('price', 0))
        # So'mda kiritilgan bo'lsa dollarga o'giramiz
        cur = str(parsed.get('currency', 'USD')).upper()
        uzs_note = ''
        if price > 0 and (cur == 'UZS' or price >= 5000):
            rate = get_exchange_rate()
            uzs_sum = price
            price = round(price / rate, 2)
            uzs_note = f"\n\U0001F4B1 {uzs_sum:,.0f} so'm -> {fmt(price)} (kurs {rate:,.0f})"
        discount = float(parsed.get('discount', 0))
        customer = parsed.get('customer', '')
        ctype = parsed.get('type', 'B2C')
        if not prod:
            await u.message.reply_text(f"❓ Topilmadi: {parsed.get('product','')}"); return
        if prod['qty'] < qty:
            await u.message.reply_text(f"❌ Yetarli yo'q! {prod['name']}: {prod['qty']} ta"); return
        if price <= 0: price = prod['price']
        if discount > 0: price = price * (1 - discount/100)
        ok, sale_id = save_sale(prod['id'], prod['name'], qty, price, prod['cost'], discount, customer, ctype)
        if ok:
            profit = (price - prod['cost']) * qty
            disc_txt = (uzs_note or '') + (f"\n🏷️ Chegirma: {discount}%" if discount else "")
            cust_txt = f"\n👤 {customer} ({ctype})" if customer else ""
            await u.message.reply_text(
                f"✅ *Sotuv qayd!*\n\n📦 {prod['name']}\n"
                f"🔢 {qty} ta × {fmt(price)} = *{fmt(price*qty)}*\n"
                f"✅ Foyda: *{fmt(profit)}*{disc_txt}{cust_txt}\n"
                f"📊 Qoldi: {prod['qty']-qty} ta",
                parse_mode='Markdown')
        else:
            await u.message.reply_text("❌ Xatolik!")

    elif action == 'add':
        prod = find_product(parsed.get('product',''))
        qty = max(1, int(parsed.get('qty', 1)))
        if not prod:
            await u.message.reply_text(f"❓ Topilmadi: {parsed.get('product','')}"); return
        add_qty(prod['id'], qty)
        await u.message.reply_text(
            f"✅ *Astatka yangilandi!*\n📦 {prod['name']}: +{qty} ta → {prod['qty']+qty} ta",
            parse_mode='Markdown')

    elif action == 'stock': await cmd_astatka(u, ctx)
    elif action == 'prices': await cmd_narxlar(u, ctx)
    elif action == 'analiz': await cmd_analiz(u, ctx)
    elif action == 'cashflow': await cmd_cashflow(u, ctx)
    elif action == 'trend': await cmd_trend(u, ctx)
    elif action == 'rate': await cmd_rate(u, ctx)
    elif action == 'warranties': await cmd_kafolat(u, ctx)
    elif action == 'customers': await cmd_mijozlar_yangi(u, ctx)
    elif action == 'debts': await cmd_qarzlar(u, ctx)

    elif action == 'report':
        period = parsed.get('period', 'today')
        if period == 'year': await cmd_yil(u, ctx)
        elif period == 'month':
            month = parsed.get('month', this_month())
            await cmd_oy(u, ctx, month=month)
        else: await cmd_bugun(u, ctx)

    elif action == 'expense':
        amount = float(parsed.get('amount', 0))
        cat = parsed.get('category', 'boshqa')
        etype = parsed.get('type', 'period')
        note = parsed.get('note', '')
        if amount > 0:
            add_expense(amount, cat, etype, note)
            type_labels = {'cogs_bank':'🏦 Bank to\'lovi','cogs_delivery':'🚚 Dostavka','period':'📋 Davr xarajati'}
            await u.message.reply_text(
                f"💸 *Xarajat qayd!*\n{type_labels.get(etype,etype)}\n"
                f"📁 {cat}: *{fmt(amount)}*\n📝 {note}",
                parse_mode='Markdown')
        else: await u.message.reply_text("❌ Summa noto'g'ri")

    elif action == 'transit_add':
        supplier = parsed.get('supplier', 'Two Trees')
        product = parsed.get('product', '')
        qty = int(parsed.get('qty', 1))
        unit_cost = float(parsed.get('unit_cost', 0))
        deposit = float(parsed.get('deposit', 0))
        bank_fee = float(parsed.get('bank_fee', 0))
        delivery_fee = float(parsed.get('delivery_fee', 0))
        if not product or unit_cost <= 0:
            await u.message.reply_text("❌ Mahsulot va narx kiriting"); return
        if is_closed(today()):
            await u.message.reply_text(f"❌ {today()[:7]} davri yopilgan (/och)"); return
        tid = add_transit(supplier, product, qty, unit_cost, deposit, bank_fee, delivery_fee, cash_method='naqd')
        total = qty * unit_cost
        real = unit_cost + (bank_fee+delivery_fee)/qty if qty else unit_cost
        kb = [[InlineKeyboardButton(f"✅ #{tid} Keldi", callback_data=f"arrive_{tid}")]]
        await u.message.reply_text(
            f"🚚 *Zakaz qayd!*\n\n🏭 {supplier}\n📦 {product}: {qty} ta\n"
            f"💵 {fmt(unit_cost)}/ta = *{fmt(total)}*\n"
            f"💳 Deposit: {fmt(deposit)} | 💸 Qolgan: {fmt(total-deposit)}\n"
            f"🏦 Bank: {fmt(bank_fee)} | 🚚 Dostavka: {fmt(delivery_fee)}\n"
            f"📊 Haqiqiy sebest: *{fmt(real)}/ta*",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif action == 'transit_arrive':
        tid = int(parsed.get('id', 0))
        if not tid:
            conn = db(); c = conn.cursor()
            c.execute("SELECT id FROM transit WHERE status='yolda' ORDER BY id DESC LIMIT 1")
            row = c.fetchone(); conn.close()
            if row: tid = row[0]
        if tid:
            result = arrive_transit(tid)
            if result:
                await u.message.reply_text(
                    f"✅ *Tovar keldi!*\n\n📦 {result['product']}: {result['qty']} ta\n"
                    f"📊 Sebest: {fmt(result['real_cost'])}/ta\n" +
                    ("✅ Astatka yangilandi!" if result.get('found', True) else _ARRIVE_NOT_FOUND),
                    parse_mode='Markdown')
            else:
                await u.message.reply_text("❌ Topilmadi!")
        else:
            await u.message.reply_text("Zakaz ID ni yozing: 'Zakaz #3 keldi'")

    elif action == 'transit_pay':
        tid = int(parsed.get('id', 0))
        amount = float(parsed.get('amount', 0))
        if tid and amount > 0:
            r = await asyncio.to_thread(pay_debt, 'kreditorlik', '', amount, 'naqd', f"zakaz #{tid}", [tid])
            if r.get('ok'):
                await u.message.reply_text(
                    f"✅ *To'lov qayd!*\nZakaz #{tid}: +{fmt(r['paid'])} to'landi (kassadan)\nQolgan qarz: {fmt(r['qoldiq'])}",
                    parse_mode='Markdown')
            else:
                await u.message.reply_text("❌ " + r.get('error', 'Xato'))
        else:
            await u.message.reply_text("❌ Zakaz ID va summa kiriting")

    elif action == 'transit_list': await cmd_yolda(u, ctx)
    elif action == 'supplier_debt': await cmd_zavod_qarz(u, ctx)

    elif action == 'add_customer':
        name = parsed.get('name', '')
        phone = parsed.get('phone', '')
        ctype = parsed.get('ctype', '')
        if name:
            holat, _cid = add_customer(name, phone, ctype)
            if holat == 'qoshildi':
                await u.message.reply_text(f"👤 {name} ({ctype}) qo'shildi!")
            elif holat == 'yangilandi':
                await u.message.reply_text(f"👤 {name} ma'lumoti yangilandi")
            else:
                await u.message.reply_text("❌ Saqlanmadi — ism bo'sh")
        else:
            await u.message.reply_text("❌ Ism kiriting")

    elif action == 'debt':
        person = parsed.get('person', '')
        amount = float(parsed.get('amount', 0))
        # noma'lum bo'lsa — debitorlik (avvalgi standart ham "biz berdik" edi)
        dtype = debt_turi(parsed.get('type')) or DEBITOR
        note = parsed.get('note', '')
        if person and amount > 0:
            add_debt(person, amount, dtype, note)
            emoji = "📥" if dtype == DEBITOR else "📤"
            txt = "— Debitorlik (bizga qarz)" if dtype == DEBITOR else "— Kreditorlik (biz qarzmiz)"
            await u.message.reply_text(
                f"{emoji} *Qarz qayd!*\n👤 {person}: {fmt(amount)} {txt}",
                parse_mode='Markdown')

    elif action == 'debt_pay':
        try: summa = _to_usd(parsed.get('amount', 0))
        except Exception: summa = 0
        turi = debt_turi(parsed.get('kind')) or DEBITOR
        r = await asyncio.to_thread(pay_debt, turi, parsed.get('person', ''), summa, parsed.get('method') or 'naqd')
        await u.message.reply_text(_tolov_javob(r))

    elif action == 'set_target':
        revenue = float(parsed.get('revenue', 0))
        profit = float(parsed.get('profit', 0))
        now = datetime.now()
        set_target(now.year, now.month, revenue, profit)
        await u.message.reply_text(
            f"🎯 *Maqsad qo'yildi!*\n💵 Tushum: {fmt(revenue)}\n✅ Foyda: {fmt(profit)}",
            parse_mode='Markdown')

    elif action == 'competitor':
        comp = parsed.get('competitor', 'raqobatchi')
        product = parsed.get('product', '')
        price = float(parsed.get('price', 0))
        if product and price:
            add_competitor(comp, product, price)
            our = find_product(product)
            diff = (our['price'] - price) if our else 0
            emoji = "✅ Arzonsiz" if diff > 0 else "❌ Qimmatsiz"
            await u.message.reply_text(
                f"🔍 *Raqobatchi qayd!*\n{comp}: {product} = {fmt(price)}\n"
                f"Biz: {fmt(our['price'] if our else 0)} | {emoji} ({fmt(abs(diff))} farq)",
                parse_mode='Markdown')

    elif action == 'olx_update':
        product = parsed.get('product', '')
        calls = int(parsed.get('calls', 0))
        if product:
            update_olx(product, calls)
            await u.message.reply_text(
                f"📢 *OLX yangilandi!*\n{product}\n📞 {calls} qo'ng'iroq",
                parse_mode='Markdown')

    elif action == 'catalog':
        pname = parsed.get('product', '')
        prod = find_product(pname)
        if prod:
            ctx.args = prod['name'].split()
            await cmd_katalog(u, ctx)
        else:
            await u.message.reply_text(f"❓ Topilmadi: {pname}")

    elif action == 'new_product':
        await conv_start(u, ctx)

    elif action == 'undo':
        await cmd_undo_list(u, ctx)

    elif action == 'channel_post':
        await cmd_post_kanal(u, ctx)

    elif action == 'kassa_op':
        amount = float(parsed.get('amount', 0))
        ktype = parsed.get('type', 'kirim')
        method = parsed.get('method', 'naqd')
        note = parsed.get('note', '')
        if amount > 0:
            add_cash(amount, ktype, note or ktype, note, method)
            balance = get_cash_balance()
            e = "📥" if ktype == 'kirim' else "📤"
            await u.message.reply_text(
                f"{e} *Kassa yangilandi!*\n\n"
                f"{'Kirim' if ktype=='kirim' else 'Chiqim'}: *{fmt(amount)}* ({method})\n"
                f"💰 Joriy qoldiq: *{fmt(balance)}*",
                parse_mode='Markdown')
        else:
            await cmd_kassa(u, ctx)

    elif action == 'nelikvid':
        await cmd_nelikvid(u, ctx)

    elif action == 'oy_tafsil':
        month = parsed.get('month', this_month())
        await cmd_oy_tafsil(u, ctx, month=month)

    elif action == 'eslatmalar':
        await cmd_eslatmalar(u, ctx)

    elif action == 'send_ads':
        await u.message.reply_text(
            "📣 *Reklama yuborish*\n\nFormat: `/reklama Xabar matni`",
            parse_mode='Markdown')

    else:
        reply = parsed.get('reply', "Tushunmadim 🤔\n/yordam buyrug'ini ko'ring")
        await u.message.reply_text(reply)

# Foto qabul qilish (astatka qo'shish vaqtida)
async def handle_photo(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    pid = ctx.user_data.get('photo_product_id')
    if pid and u.message.photo:
        file_id = u.message.photo[-1].file_id
        add_photo(pid, file_id)
        count = len(get_product_photos(pid))
        await u.message.reply_text(f"✅ Rasm {count} qo'shildi. Davom eting yoki /tayyor")

async def handle_photo_done(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    pid = ctx.user_data.pop('photo_product_id', None)
    if pid:
        count = len(get_product_photos(pid))
        await u.message.reply_text(f"✅ Jami {count} ta rasm saqlandi!")
    elif 'name' in ctx.user_data:
        await conv_finish(u, ctx)
    else:
        # avval: user_data['name'] yo'qligi sababli KeyError → "Xato yuz berdi"
        await u.message.reply_text("ℹ️ Hozir tugatiladigan jarayon yo'q.")





async def cmd_oy_tafsil(u: Update, ctx: ContextTypes.DEFAULT_TYPE, month=None):
    """Oylik batafsil mahsulot tahlili"""
    if not can(u, 'boshqaruv'): return
    if not month:
        args = ctx.args if ctx.args else []
        month = args[0] if args else this_month()

    conn = db(); c = conn.cursor()
    c.execute("""SELECT product, SUM(qty), SUM(revenue), SUM(profit), COUNT(*)
                 FROM sales
                 WHERE date LIKE ? AND reversed=0
                 GROUP BY product
                 ORDER BY SUM(revenue) DESC""", (month+'%',))
    rows = c.fetchall()

    total_rev = c.execute("SELECT SUM(revenue) FROM sales WHERE date LIKE ? AND reversed=0", (month+'%',)).fetchone()[0] or 0
    total_profit = c.execute("SELECT SUM(profit) FROM sales WHERE date LIKE ? AND reversed=0", (month+'%',)).fetchone()[0] or 0
    conn.close()

    label = month
    text = f"📊 *{label} — Tafsil*\n\n"

    if not rows:
        text += "Bu oy sotuv yo'q."
    else:
        for i, row in enumerate(rows, 1):
            name, qty, rev, profit, cnt = row
            unit = rev/qty if qty else 0
            text += f"{i}. *{name}*\n"
            text += f"   {qty} ta × {fmt(unit)} = *{fmt(rev)}* (+{fmt(profit)})\n"

        text += f"\n💵 *Jami tushum: {fmt(total_rev)}*"
        text += f"\n✅ *Jami foyda: {fmt(total_profit)}*"
        text += f"\n📦 *{len(rows)} xil mahsulot*"

    await u.message.reply_text(text, parse_mode='Markdown')

# ── KASSA BUYRUQLARI ──────────────────────────────────────────────
async def cmd_kassa(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    balance = get_cash_balance()
    month_hist = get_cash_history(this_month())
    today_hist = get_cash_history(today())

    t_kirim  = sum(r[4] for r in today_hist if r[3]=='kirim')
    t_chiqim = sum(r[4] for r in today_hist if r[3]=='chiqim')
    m_kirim  = sum(r[4] for r in month_hist if r[3]=='kirim')
    m_chiqim = sum(r[4] for r in month_hist if r[3]=='chiqim')

    text = "💵 *KASSA HOLATI*\n\n"
    text += f"💰 *Joriy qoldiq: {fmt(balance)}*\n\n"
    text += "*Bugun:*\n"
    text += f"  📥 Kirim: {fmt(t_kirim)}\n"
    text += f"  📤 Chiqim: {fmt(t_chiqim)}\n\n"
    text += "*Bu oy:*\n"
    text += f"  📥 Kirim: {fmt(m_kirim)}\n"
    text += f"  📤 Chiqim: {fmt(m_chiqim)}\n\n"

    # So'nggi 5 ta operatsiya
    recent = get_cash_history()[:5]
    if recent:
        text += "*So'nggi operatsiyalar:*\n"
        for r in recent:
            e = "📥" if r[3]=='kirim' else "📤"
            text += f"{e} {r[5]}: *{fmt(r[4])}* ({r[7]})\n"

    text += "\n_Yozish: 'Naqd $260 kassa kirim' yoki 'Payme $150 chiqim'_"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_nelikvid(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    items = get_nelikvid(60)
    if not items:
        await u.message.reply_text("✅ *Nelikvid yo'q!*\n\nBarcha tovarlar 2 oy ichida sotilgan.", parse_mode='Markdown')
        return
    text = "📉 *NELIKVID TOVARLAR (2+ oy sotilmagan)*\n\n"
    total_cost = 0
    for item in items:
        days = item['days_since']
        e = "🔴" if days > 90 else "🟡"
        text += f"{e} *{item['name']}*\n"
        text += f"  {item['qty']} ta | {fmt(item['price'])} | {days} kun\n"
        text += f"  Oxirgi sotuv: {item['last_sale']}\n\n"
        total_cost += item['qty'] * item['cost']
    text += f"💸 Jami muzlatilgan kapital: *{fmt(total_cost)}*\n"
    text += "💡 *Tavsiya:* Chegirma yoki qaytarish ko'ring"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_eslatmalar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    text = "🔔 *ESLATMALAR*\n\n"
    has_alert = False

    # 1. Kafolat tugayaptilar
    conn = db(); c = conn.cursor()
    soon = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
    c.execute("SELECT * FROM warranties WHERE status='active' AND end_date <= ? ORDER BY end_date", (soon,))
    warr = c.fetchall()
    if warr:
        text += "🔧 *Kafolat tugayapti:*\n"
        for w in warr:
            days = (datetime.strptime(w[5],'%Y-%m-%d') - datetime.now()).days
            kim = w[3] or "noma'lum"   # f-string ichida \' Python 3.11 da SyntaxError
            text += f"  • {w[2]} ({kim}) — {days} kun\n"
        text += "\n"
        has_alert = True

    # 2. OLX yangilanmagan (7+ kun)
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    c.execute("SELECT * FROM olx_listings WHERE last_updated <= ? AND status='active'", (week_ago,))
    old_olx = c.fetchall()
    if old_olx:
        text += "📢 *OLX yangilash kerak:*\n"
        for o in old_olx:
            days = (datetime.now() - datetime.strptime(o[2],'%Y-%m-%d')).days
            text += f"  • {o[1]}: {days} kun yangilanmagan\n"
        text += "\n"
        has_alert = True

    # 3. Tugayotgan tovarlar
    prods = get_products()
    low = [p for p in prods if p['qty'] == 1]
    if low:
        text += "⚠️ *Tugayapti (1 ta qoldi):*\n"
        for p in low:
            text += f"  • {p['name']}\n"
        text += "\n"
        has_alert = True

    # 4. Zavod qarzi
    conn2 = db(); c2 = conn2.cursor()
    c2.execute("SELECT SUM(remaining) FROM transit WHERE remaining > 0")
    debt = c2.fetchone()[0] or 0
    conn2.close()
    if debt > 0:
        text += f"💳 *Zavod qarzi: {fmt(debt)}*\n\n"
        has_alert = True

    conn.close()
    if not has_alert:
        text += "✅ Hozircha hech qanday eslatma yo'q!"

    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_reklama(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Obunachilarga xabar yuborish"""
    if not can(u, 'boshqaruv'): return
    n = sub_count()
    if not ctx.args:
        me = await ctx.bot.get_me()
        await u.message.reply_text(
            f"\U0001F4E3 Mijozlarga xabar\n\n"
            f"\U0001F465 Obunachilar: {n} ta\n\n"
            f"Yuborish: /reklama Xabar matni\n"
            f"Misol: /reklama Yangi TTS 20 Pro keldi! Narx $490\n\n"
            f"\U0001F517 Obuna havolasi (mijozlarga tarqating):\n"
            f"https://t.me/{me.username}\n\n"
            f"Mijoz shu havolaga kirib Start bossa \u2014 obunachi bo'ladi va xabar oladi.\n"
            f"Telegram qoidasiga ko'ra bot faqat shunday odamlarga yoza oladi.")
        return
    if n == 0:
        me = await ctx.bot.get_me()
        await u.message.reply_text(
            f"\u274C Obunachi yo'q.\n\nMijozlarga shu havolani yuboring:\n"
            f"https://t.me/{me.username}\n\nStart bosgach xabar ola boshlaydi.")
        return

    matn = ' '.join(ctx.args)
    full = f"\U0001F4E3 ThermoCrafts\n\n{matn}\n\n\U0001F4CD Yunusobod, Toshkent\n\U0001F4DE Savollar uchun shu yerga yozing"
    await u.message.reply_text(f"\u23F3 {n} ta obunachiga yuborilmoqda...")
    yub = xato = blok = 0
    for chat_id, nomi, uname, joined, act in sub_list():
        try:
            await ctx.bot.send_message(chat_id=chat_id, text=full)
            yub += 1
        except Exception as e:
            s = str(e).lower()
            if 'blocked' in s or 'not found' in s or 'deactivated' in s or 'initiate' in s:
                sub_off(chat_id); blok += 1
            else:
                xato += 1
        await asyncio.sleep(0.05)
    conn = db(); cc = conn.cursor()
    cc.execute("UPDATE subscribers SET last_sent=? WHERE active=1", (today(),))
    conn.commit(); conn.close()
    res = f"\U0001F4E3 Natija\n\n\u2705 Yuborildi: {yub} ta"
    if blok: res += f"\n\U0001F6AB Bloklagan: {blok} ta (ro'yxatdan chiqarildi)"
    if xato: res += f"\n\u26A0\uFE0F Xato: {xato} ta"
    await u.message.reply_text(res)

async def cmd_obunachilar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Obunachilar ro'yxati"""
    if not can(u, 'boshqaruv'): return
    subs = sub_list()
    me = await ctx.bot.get_me()
    if not subs:
        await u.message.reply_text(
            f"\U0001F465 Obunachi yo'q.\n\nHavola:\nhttps://t.me/{me.username}\n\n"
            f"Buni OLX e'lonlaringizga, kanal tavsifiga va mijozlarga yuboring.")
        return
    text = f"\U0001F465 OBUNACHILAR: {len(subs)} ta\n\n"
    for cid, nomi, uname, joined, act in subs[:40]:
        text += f"\u2022 {nomi or 'ismsiz'}"
        if uname: text += f" (@{uname})"
        text += f" \u2014 {joined}\n"
    if len(subs) > 40: text += f"\n...va yana {len(subs)-40} ta\n"
    text += f"\n\U0001F517 https://t.me/{me.username}"
    await u.message.reply_text(text)

async def cmd_reklama_preview(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Reklama ko'rinishini oldindan ko'rish"""
    if not can(u, 'boshqaruv'): return
    if not ctx.args:
        await u.message.reply_text("Format: `/reklama_preview Xabar matni`", parse_mode='Markdown')
        return
    text = ' '.join(ctx.args)
    preview = (
        f"📣 *ThermoCrafts*\n\n"
        f"{text}\n\n"
        f"📍 Yunusobod, Toshkent\n"
        f"#ThermoCrafts"
    )
    await u.message.reply_text(
        f"*Ko'rinishi:*\n\n{preview}\n\n"
        f"_Yuborish uchun: /reklama {text}_",
        parse_mode='Markdown')


# ── RASM/VIDEO BILAN KANAL POST ──────────────────────────────────
async def handle_photo_post(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    ch = get_channel_id()
    if not ch:
        await u.message.reply_text("CHANNEL_ID sozlanmagan!")
        return
    photo = u.message.photo[-1]
    caption = u.message.caption or ""
    if not caption:
        caption = "ThermoCrafts\n\nYunusobod, Toshkent\n#ThermoCrafts #lazer #termopress"
    else:
        caption = caption + "\n\nYunusobod, Toshkent\n#ThermoCrafts"
    try:
        await ctx.bot.send_photo(chat_id=ch, photo=photo.file_id, caption=caption)
        await u.message.reply_text("Rasm kanalga yuborildi!")
    except Exception as e:
        await u.message.reply_text(f"Xato: {e}")

async def handle_video_post(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Egasi/admin video yubordi → 📢 Marketing: tovar tanlash → oldindan ko'rish → Telegram/Instagram."""
    if not can(u, 'marketing'): return
    await mkt_media(u, ctx)

# ── SELF-UPDATE (GitHub API) ──────────────────────────────────────
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
GITHUB_REPO  = os.getenv('GITHUB_REPO', 'ilyosbekdot/thermocraft-bot')
# Railway qaysi faylni ishga tushirayotgan bo'lsa — yangilanish o'sha faylga yoziladi
BOT_FILENAME = os.getenv('BOT_FILENAME') or os.path.basename(os.path.abspath(__file__))

# ── BAZA ZAXIRASI (GitHub) ────────────────────────────────────────
# MUHIM: zaxira ALOHIDA branch'ga ("db-backup") yoziladi, main'ga EMAS.
# Avval zaxira main'ga commit qilinardi → Railway har commitda qayta deploy qilardi →
# yangi bot ishga tushishi bilan yana zaxira → yana deploy... Bot har ~45 soniyada
# o'chib-yoqilib, oxirgi zaxiradan keyingi barcha yozuvlar (sotuv, kassa) yo'qolardi.
DB_BACKUP_PATH   = os.getenv('DB_BACKUP_PATH', 'data/thermocraft.db')
DB_BACKUP_BRANCH = os.getenv('DB_BACKUP_BRANCH', 'db-backup')
_BK = {'hash': None, 'cur_hash': None, 'mtime': None, 'last': 0.0, 'fail': 0,
       'next_try': 0.0, 'blocked': '', 'branch_ok': False, 'restore_msg': '',
       'default_branch': '', 'source': ''}
_BK_LOCK = threading.Lock()

def _gh_headers(raw=False):
    return {"Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}

def _gh_api(path=''):
    base = f"https://api.github.com/repos/{GITHUB_REPO}"
    return f"{base}/{path}" if path else base

def _gh_default_branch():
    if _BK['default_branch']: return _BK['default_branch']
    try:
        r = requests.get(_gh_api(), headers=_gh_headers(), timeout=20)
        if r.status_code == 200:
            _BK['default_branch'] = r.json().get('default_branch') or 'main'
    except Exception:
        pass
    return _BK['default_branch'] or 'main'

# ── Baza ichidagi belgi: har zaxirada +1 (qaysi nusxa yangiroq ekanini bilish uchun)
def _meta_get(conn, key, default=None):
    try:
        r = conn.execute("SELECT value FROM _meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else default
    except Exception:
        return default

def _db_seq_of(path):
    """Fayldagi zaxira raqami; 0 — eski (raqamsiz) nusxa; -1 — yaroqsiz fayl"""
    try:
        conn = sqlite3.connect(path)
        try:
            conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
            return int(_meta_get(conn, 'backup_seq', 0) or 0)
        finally:
            conn.close()
    except Exception:
        return -1

def _db_content_hash(path=None):
    """Baza MAZMUNI xeshi (_meta jadvalisiz) — haqiqiy o'zgarish bo'lganini aniqlash uchun"""
    h = hashlib.sha256()
    conn = sqlite3.connect(path or DB_PATH)
    try:
        for line in conn.iterdump():
            if line.startswith('INSERT INTO "_meta"') or line.startswith('CREATE TABLE _meta'):
                continue
            h.update(line.encode('utf-8', 'replace')); h.update(b'\n')
    finally:
        conn.close()
    return h.hexdigest()

def _db_snapshot():
    """Izchil nusxa (SQLite backup API — yozish paytida ham buzilmaydi) → (bytes, mazmun_xeshi)"""
    fd, tmp = tempfile.mkstemp(suffix='.db'); os.close(fd)
    try:
        src = sqlite3.connect(DB_PATH); dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        h = _db_content_hash(tmp)
        with open(tmp, 'rb') as f: raw = f.read()
        return raw, h
    finally:
        try: os.remove(tmp)
        except Exception: pass

def _bk_set_baseline():
    """Hozirgi holatni 'zaxirada bor' deb belgilaydi (ishga tushganda / tiklagandan keyin)"""
    try:
        if os.path.exists(DB_PATH):
            _BK['mtime'] = os.path.getmtime(DB_PATH)
            _BK['hash'] = _BK['cur_hash'] = _db_content_hash()
    except Exception:
        log.exception("baseline")

def _bk_check_dirty():
    """True — oxirgi muvaffaqiyatli zaxiradan keyin baza mazmuni o'zgargan"""
    if not os.path.exists(DB_PATH): return False
    mt = os.path.getmtime(DB_PATH)
    if mt != _BK['mtime'] or _BK['cur_hash'] is None:
        _BK['mtime'] = mt
        _BK['cur_hash'] = _db_content_hash()
    return _BK['cur_hash'] != _BK['hash']

def _gh_ensure_branch(branch):
    """Zaxira branch'i bo'lmasa — asosiy branch'dan yaratadi (bu deploy qilmaydi)"""
    if _BK['branch_ok']: return True, ''
    r = requests.get(_gh_api(f"branches/{branch}"), headers=_gh_headers(), timeout=20)
    if r.status_code == 200:
        _BK['branch_ok'] = True; return True, ''
    if r.status_code != 404:
        return False, f"branch tekshiruvi: GitHub {r.status_code}"
    base = _gh_default_branch()
    r = requests.get(_gh_api(f"git/ref/heads/{base}"), headers=_gh_headers(), timeout=20)
    if r.status_code != 200:
        return False, f"{base} topilmadi: GitHub {r.status_code}"
    sha = r.json()['object']['sha']
    r = requests.post(_gh_api("git/refs"), headers=_gh_headers(), timeout=20,
                      json={"ref": f"refs/heads/{branch}", "sha": sha})
    if r.status_code in (201, 422):        # 422 — allaqachon bor
        _BK['branch_ok'] = True; return True, ''
    try: err = r.json().get('message', '')[:120]
    except Exception: err = r.text[:120]
    return False, f"branch yaratib bo'lmadi: GitHub {r.status_code} {err}"

def _gh_file_sha(path, branch):
    """(status, sha) — katta (1 MB+) fayllarda ham ishlaydi: papka ro'yxatidan oladi"""
    folder, _, fname = path.rpartition('/')
    r = requests.get(_gh_api(f"contents/{folder}" if folder else "contents"),
                     headers=_gh_headers(), params={"ref": branch}, timeout=20)
    if r.status_code == 404: return 404, None
    if r.status_code != 200: return r.status_code, None
    for it in (r.json() if isinstance(r.json(), list) else []):
        if it.get('name') == fname: return 200, it.get('sha')
    return 404, None

def _gh_put_file(path, raw, message, branch):
    ok, err = _gh_ensure_branch(branch)
    if not ok: return False, err
    api = _gh_api(f"contents/{path}")
    for attempt in range(3):
        st, sha = _gh_file_sha(path, branch)
        if st not in (200, 404):
            return False, f"GitHub {st}"
        payload = {"message": message, "content": base64.b64encode(raw).decode(), "branch": branch}
        if sha: payload["sha"] = sha
        r = requests.put(api, json=payload, headers=_gh_headers(), timeout=120)
        if r.status_code in (200, 201): return True, ''
        if r.status_code in (409, 422) and attempt < 2:      # sha eskirgan — qayta urinish
            time.sleep(2); continue
        try: err = r.json().get('message', '')[:120]
        except Exception: err = r.text[:120]
        return False, f"GitHub {r.status_code}: {err}"
    return False, "GitHub: urinishlar tugadi"

def _set_meta(key, value):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT)")
        if value is None:
            conn.execute("DELETE FROM _meta WHERE key=?", (key,))
        else:
            conn.execute("INSERT OR REPLACE INTO _meta (key,value) VALUES (?,?)", (key, str(value)))
        conn.commit()
    finally:
        conn.close()

def _gh_json(r):
    try: return r.json()
    except Exception: return {}

def _gh_err(r):
    """GitHub xatosini o'qiladigan qilib beradi (javob JSON bo'lmasa ham yiqilmaydi)"""
    j = _gh_json(r)
    m = (j.get('message') if isinstance(j, dict) else '') or (r.text or '').strip()[:120]
    return f"GitHub {r.status_code}" + (f": {m}" if m else "")

def _gh_commit_contents(path, data, message, branch):
    """Contents API orqali yozish → (ok, xato, status)"""
    st, sha = _gh_file_sha(path, branch)
    if st not in (200, 404): return False, f"GitHub {st}", st
    payload = {"message": message, "content": base64.b64encode(data).decode(), "branch": branch}
    if sha: payload["sha"] = sha
    r = requests.put(_gh_api(f"contents/{path}"), json=payload, headers=_gh_headers(), timeout=120)
    if r.status_code in (200, 201): return True, '', r.status_code
    return False, _gh_err(r), r.status_code

def _gh_commit_gitdata(path, data, message, branch):
    """Zaxira yo'l — Git Data API (blob → tree → commit → ref). Contents API 5xx bersa ishlatiladi."""
    H = _gh_headers()
    r = requests.post(_gh_api("git/blobs"), headers=H, timeout=120,
                      json={"content": base64.b64encode(data).decode(), "encoding": "base64"})
    if r.status_code != 201: return False, "blob: " + _gh_err(r)
    blob = _gh_json(r).get('sha')
    for attempt in range(3):
        r = requests.get(_gh_api(f"git/ref/heads/{branch}"), headers=H, timeout=20)
        if r.status_code != 200: return False, "ref: " + _gh_err(r)
        head = (_gh_json(r).get('object') or {}).get('sha')
        r = requests.get(_gh_api(f"git/commits/{head}"), headers=H, timeout=20)
        if r.status_code != 200: return False, "commit: " + _gh_err(r)
        base_tree = (_gh_json(r).get('tree') or {}).get('sha')
        r = requests.post(_gh_api("git/trees"), headers=H, timeout=60, json={
            "base_tree": base_tree,
            "tree": [{"path": path, "mode": "100644", "type": "blob", "sha": blob}]})
        if r.status_code != 201: return False, "tree: " + _gh_err(r)
        r = requests.post(_gh_api("git/commits"), headers=H, timeout=30,
                          json={"message": message, "tree": _gh_json(r).get('sha'), "parents": [head]})
        if r.status_code != 201: return False, "commit: " + _gh_err(r)
        new = _gh_json(r).get('sha')
        r = requests.patch(_gh_api(f"git/refs/heads/{branch}"), headers=H, timeout=20,
                           json={"sha": new, "force": False})
        if r.status_code == 200: return True, ''
        if r.status_code == 422 and attempt < 2:        # branch shu orada siljidi — qayta
            time.sleep(2); continue
        return False, "ref: " + _gh_err(r)
    return False, "urinishlar tugadi"

def gh_commit_file(path, data, message, branch=None):
    """Faylni GitHub'ga yozadi: 3 marta urinish, 5xx bo'lsa zaxira yo'l. → (ok, xabar)"""
    branch = branch or _gh_default_branch()
    last, st = '', 0
    for wait in (0, 4, 10):
        if wait: time.sleep(wait)
        try:
            ok, err, st = _gh_commit_contents(path, data, message, branch)
        except Exception as e:
            ok, err, st = False, str(e)[:120], 0
        if ok: return True, ''
        last = err
        if not (st == 0 or st >= 500 or st in (409, 422)): break     # 401/403/404 — qayta urinish befoyda
    if st == 0 or st >= 500:
        try:
            ok, err = _gh_commit_gitdata(path, data, message, branch)
            if ok: return True, ''
            last = f"{last}; {err}"
        except Exception as e:
            last = f"{last}; {str(e)[:120]}"
    return False, last

def db_backup_to_github(reason='', force=False):
    """Bazani GitHub'dagi ALOHIDA branch'ga zaxiralaydi (main'ga emas — deploy bo'lmaydi)"""
    if not GITHUB_TOKEN: return False, "GITHUB_TOKEN sozlanmagan"
    if _BK['blocked'] and not force:
        return False, f"Avto-zaxira to'xtatilgan: {_BK['blocked']}"
    if not _BK_LOCK.acquire(timeout=180):
        return False, "Boshqa zaxira jarayoni tugamadi"
    try:
        if not os.path.exists(DB_PATH): return False, "Baza fayli yo'q"
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT)")
            seq = int(_meta_get(conn, 'backup_seq', 0) or 0) + 1
            conn.execute("INSERT OR REPLACE INTO _meta (key,value) VALUES ('backup_seq',?)", (str(seq),))
            conn.execute("INSERT OR REPLACE INTO _meta (key,value) VALUES ('backup_at',?)", (now_t(),))
            conn.commit()
        finally:
            conn.close()
        raw, h = _db_snapshot()
        if len(raw) < 100: return False, "Baza bo'sh"
        msg = f"DB backup #{seq} {datetime.now().strftime('%Y-%m-%d %H:%M')} {reason}".strip()
        ok, err = _gh_put_file(DB_BACKUP_PATH, raw, msg, DB_BACKUP_BRANCH)
        if ok:
            _BK['hash'] = h; _BK['last'] = time.time(); _BK['fail'] = 0; _BK['next_try'] = 0.0
            return True, f"{max(1, len(raw)//1024)} KB zaxiralandi (#{seq})"
        _BK['fail'] += 1
        return False, err
    except Exception as e:
        _BK['fail'] += 1
        log.exception("db backup"); return False, str(e)[:150]
    finally:
        _BK_LOCK.release()

def _gh_download(path, ref):
    r = requests.get(_gh_api(f"contents/{path}"), headers=_gh_headers(raw=True),
                     params={"ref": ref}, timeout=90)
    if r.status_code != 200:
        return r.status_code, None
    data = r.content or b''
    if data[:15] != b'SQLite format 3':
        # GitHub JSON qaytargan bo'lsa (base64 yoki katta fayl uchun download_url)
        try:
            j = r.json()
            if isinstance(j, dict) and j.get('content') and j.get('encoding') == 'base64':
                data = base64.b64decode(j['content'])
            elif isinstance(j, dict) and j.get('download_url'):
                data = requests.get(j['download_url'], headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
                                    timeout=90).content
        except Exception:
            pass
    if len(data) >= 100 and data[:15] == b'SQLite format 3':
        return 200, data
    return 422, None            # fayl bor, lekin SQLite emas

def db_fetch_remote():
    """GitHub'dagi eng so'nggi zaxira: avval db-backup branch, u yo'q bo'lsa — eski joy (main).
    Qaytaradi: ('ok', bytes, manba) | ('none', None, '') | ('error', None, sabab)"""
    if not GITHUB_TOKEN: return 'error', None, "GITHUB_TOKEN sozlanmagan"
    try:
        st, raw = _gh_download(DB_BACKUP_PATH, DB_BACKUP_BRANCH)
    except Exception as e:
        return 'error', None, f"{DB_BACKUP_BRANCH}: {str(e)[:100]}"
    if st == 200: return 'ok', raw, DB_BACKUP_BRANCH
    if st != 404:            # branch bor-u o'qib bo'lmadi — eski nusxaga o'tib ketmaymiz
        return 'error', None, f"{DB_BACKUP_BRANCH}: GitHub {st}"
    base = _gh_default_branch()
    try:
        st, raw = _gh_download(DB_BACKUP_PATH, base)
    except Exception as e:
        return 'error', None, f"{base}: {str(e)[:100]}"
    if st == 200: return 'ok', raw, base
    if st == 404: return 'none', None, ''
    return 'error', None, f"{base}: GitHub {st}"

def _write_db_file(raw):
    d = os.path.dirname(DB_PATH)
    if d: os.makedirs(d, exist_ok=True)
    tmp = DB_PATH + '.tmp'
    with open(tmp, 'wb') as f: f.write(raw)
    for ext in ('-journal', '-wal', '-shm'):
        try: os.remove(DB_PATH + ext)
        except Exception: pass
    os.replace(tmp, DB_PATH)

def db_is_empty():
    """Baza yo'q yoki ma'lumotsizmi"""
    if not os.path.exists(DB_PATH): return True
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sales'")
        if not c.fetchone(): conn.close(); return True
        n = 0
        for t in ('sales', 'cash_box', 'expenses'):
            try:
                c.execute(f"SELECT COUNT(*) FROM {t}"); n += c.fetchone()[0]
            except Exception: pass
        conn.close(); return n == 0
    except Exception:
        return True

def db_autorestore():
    """Ishga tushganda: GitHub'dagi zaxira mahalliy bazadan yangiroq bo'lsa — tiklaydi.
    Zaxirani o'qib bo'lmasa — avto-zaxirani to'xtatadi: aks holda bo'sh/eski baza
    GitHub'dagi yaxshi zaxirani bosib ketadi (25-sentyabrda shunday bo'lgan)."""
    if not GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN yo'q — zaxira va tiklash o'chirilgan"); return
    local_empty = db_is_empty()
    local_seq = -1 if local_empty else _db_seq_of(DB_PATH)
    status, raw, info = 'error', None, ''
    for i in range(5):
        status, raw, info = db_fetch_remote()
        if status != 'error': break
        log.warning("Zaxirani olish %d/5: %s", i + 1, info)
        time.sleep(3 * (i + 1))
    if status == 'none':
        log.info("GitHub'da zaxira yo'q — yangi baza bilan ishlanadi")
        return
    if status == 'error':
        _BK['blocked'] = f"ishga tushishda zaxirani o'qib bo'lmadi ({info})"
        if local_empty:
            _BK['restore_msg'] = ("⚠️ Bot ishga tushdi, lekin GitHub'dagi zaxirani o'qib bo'lmadi:\n" + info +
                                  "\n\nBaza bo'sh holatda boshlandi. Avto-zaxira to'xtatildi — bo'sh baza "
                                  "GitHub'dagi yaxshi zaxirani bosib ketmasligi uchun.\n"
                                  "GitHub ishlaganda: /restore ha (zaxiradan tiklash).")
        else:
            _BK['restore_msg'] = ("⚠️ GitHub'dagi zaxirani tekshirib bo'lmadi (" + info + ").\n"
                                  "Diskdagi baza bilan ishlayapman — ma'lumotlar joyida. Avto-zaxira vaqtincha to'xtatildi.\n"
                                  "GitHub ishlaganda: /backup ha (/restore ni BOSMANG — u eski nusxani qo'yadi).")
        log.error("Tiklash xatosi: %s", info)
        return
    fd, tmp = tempfile.mkstemp(suffix='.db'); os.close(fd)
    try:
        with open(tmp, 'wb') as f: f.write(raw)
        remote_seq = _db_seq_of(tmp)
    finally:
        try: os.remove(tmp)
        except Exception: pass
    if remote_seq < 0:
        _BK['blocked'] = "GitHub'dagi zaxira fayli yaroqsiz"
        _BK['restore_msg'] = "⚠️ GitHub'dagi zaxira fayli yaroqsiz. Avto-zaxira to'xtatildi. /restore ha yoki /backup ha"
        return
    if local_empty or remote_seq > local_seq or (remote_seq == 0 and local_seq <= 0):
        _write_db_file(raw)
        _BK['source'] = info
        log.info("Baza GitHub'dan tiklandi: %s (#%s), %d KB", info, remote_seq, len(raw) // 1024)
    else:
        log.info("Mahalliy baza yangiroq yoki teng (#%s ≥ #%s) — tiklanmadi", local_seq, remote_seq)
    if info != DB_BACKUP_BRANCH:
        _BK['migrate'] = True        # birinchi zaxira db-backup branch'ini yaratadi

async def cmd_backup(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'boshqaruv'): return
    force = bool(ctx.args) and ctx.args[0].lower() in ('ha', 'yes')
    if _BK['blocked'] and not force:
        await u.message.reply_text(
            f"⚠️ Avto-zaxira to'xtatilgan: {_BK['blocked']}\n\n"
            "Hozirgi bazani baribir GitHub'ga yozish (eski zaxira ustidan): /backup ha\n"
            "Yoki avval zaxiradan tiklash: /restore ha")
        return
    await u.message.reply_text("⏳ Zaxiralanmoqda...")
    ok, msg = await asyncio.to_thread(db_backup_to_github, "qo'lda", force)
    if ok and force: _BK['blocked'] = ''
    await u.message.reply_text(("✅ " if ok else "❌ ") + msg)

async def cmd_restore(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can(u, 'system'): return
    args = ctx.args or []
    if not args or args[0].lower() not in ('ha', 'yes'):
        await u.message.reply_text(
            "⚠️ Bu hozirgi bazani GitHub dagi zaxira bilan ALMASHTIRADI.\n"
            "Hozirgi ma'lumotlar yo'qoladi.\n\nTasdiqlash: /restore ha\n\n"
            "💾 Telegram'dagi zaxira faylidan (.zip) tiklash: faylni shu chatga yuboring.")
        return
    status, raw, info = await asyncio.to_thread(db_fetch_remote)
    if status != 'ok':
        await u.message.reply_text("❌ " + ("GitHub'da zaxira yo'q" if status == 'none' else info))
        return
    def _apply():
        with _BK_LOCK:
            _write_db_file(raw)
            init_all_tables()
            _BK['blocked'] = ''; _BK['restore_msg'] = ''
            _bk_set_baseline()
    await asyncio.to_thread(_apply)
    if info != DB_BACKUP_BRANCH: _BK['migrate'] = True
    await u.message.reply_text(f"✅ {max(1, len(raw)//1024)} KB tiklandi ({info}).\n"
                               f"💵 Kassa: {fmt(get_cash_balance())}")


# ── BOT KODINI YANGILASH (Telegram'ga .py yuborish yoki /update <url>) ─────────
def _git_blob_sha(data):
    """GitHub'dagi fayl sha si bilan bir xil hisoblanadi (git blob sha1)"""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()

def _check_bot_code(data):
    """Yangi kodni GitHub'ga yuborishdan OLDIN tekshiradi → (ok, sabab).
    Buzuq fayl yuklansa Railway uni ishga tushira olmaydi va bot to'xtab qoladi."""
    if len(data) < 20000:
        return False, f"fayl juda kichik ({len(data) // 1024} KB) — chala yuklangan yoki boshqa fayl"
    try:
        src = data.decode('utf-8')
    except UnicodeDecodeError:
        return False, "fayl matn (UTF-8) emas"
    try:
        compile(src, BOT_FILENAME, 'exec')
    except SyntaxError as e:
        return False, f"kodda xato: {e.msg} ({e.lineno}-qator) — bu fayl bilan bot ishga tushmaydi"
    for need in ('def main(', 'Application.builder', 'BOT_TOKEN'):
        if need not in src:
            return False, f"bu ThermoCrafts bot fayliga o'xshamaydi ('{need}' yo'q)"
    return True, ''

def _check_update_marker():
    """Ishga tushganda: yangilash belgisi bo'lsa → (belgi, ishlayotgan_fayl_sha), belgini o'chiradi"""
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            v = _meta_get(conn, 'pending_update')
            if not v: return None
            conn.execute("DELETE FROM _meta WHERE key='pending_update'"); conn.commit()
        finally:
            conn.close()
    except Exception:
        return None
    try: d = json.loads(v)
    except Exception: d = {}
    try:
        with open(os.path.abspath(__file__), 'rb') as f: running = _git_blob_sha(f.read())
    except Exception: running = ''
    return d, running

async def _deploy_bot_code(msg, data, source):
    """Tekshiradi → bazani zaxiralaydi → GitHub'ga yozadi (Railway o'zi qayta deploy qiladi)"""
    if not GITHUB_TOKEN:
        await msg.reply_text("❌ GITHUB_TOKEN Railway'da sozlanmagan."); return False
    ok, why = _check_bot_code(data)
    if not ok:
        await msg.reply_text(f"❌ Yuklanmadi: {why}.\nHozirgi bot o'zgarishsiz ishlayapti."); return False
    new_sha = _git_blob_sha(data)
    branch = await asyncio.to_thread(_gh_default_branch)
    try:
        cur = (await asyncio.to_thread(_gh_file_sha, BOT_FILENAME, branch))[1]
    except Exception:
        cur = None
    if cur and cur == new_sha:
        await msg.reply_text(f"ℹ️ Bu fayl GitHub'dagi {BOT_FILENAME} bilan bir xil — yangilash shart emas."); return False
    await msg.reply_text(f"✅ Kod tekshirildi: {len(data) // 1024} KB, xatosiz.\n⏳ Avval baza zaxiralanmoqda...")
    _set_meta('pending_update', json.dumps({'sha': new_sha, 'at': now_t(), 'src': source}, ensure_ascii=False))
    bok, bmsg = await asyncio.to_thread(db_backup_to_github, "yangilanishdan oldin")
    await msg.reply_text(("💾 " if bok else "⚠️ Zaxira: ") + bmsg + f"\n⏳ {BOT_FILENAME} GitHub'ga yuklanmoqda...")
    cmsg = f"Bot update via Telegram — {datetime.now().strftime('%Y-%m-%d %H:%M')} ({source})"
    ok, info = await asyncio.to_thread(gh_commit_file, BOT_FILENAME, data, cmsg, branch)
    if ok:
        await msg.reply_text(f"✅ {BOT_FILENAME} GitHub'ga yuklandi.\n"
                             f"🚀 Railway 2–3 daqiqada yangi versiyani ishga tushiradi — bot ishga tushgach o'zi xabar beradi.")
        return True
    _set_meta('pending_update', None)
    await msg.reply_text(
        f"❌ GitHub faylni qabul qilmadi ({info}).\n"
        "Odatda bu GitHub tomonidagi vaqtinchalik muammo. Hozirgi bot o'zgarishsiz ishlayapti.\n\n"
        "• 15–30 daqiqadan keyin faylni qayta yuboring, yoki\n"
        f"• sayt orqali yuklang: github.com/{GITHUB_REPO}/upload/{branch} (fayl nomi aynan {BOT_FILENAME})")
    return False

async def cmd_update(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/update <raw_url> — kodni havoladan olib yangilaydi"""
    if not can(u, 'system'): return
    if not ctx.args:
        await u.message.reply_text("Bot yangilash: .py faylni shu chatga yuboring, yoki /update <raw_url>"); return
    await u.message.reply_text("⏳ Kod yuklab olinmoqda...")
    try:
        r = await asyncio.to_thread(requests.get, ctx.args[0], timeout=30)
    except Exception as e:
        await u.message.reply_text(f"❌ Havolani ochib bo'lmadi: {str(e)[:150]}"); return
    if r.status_code != 200:
        await u.message.reply_text(f"❌ Havola ishlamadi: HTTP {r.status_code}"); return
    await _deploy_bot_code(u.message, r.content, 'url')


# ── FAYL ORQALI AUTO-UPDATE ───────────────────────────────────────
async def handle_document(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """.xlsx — Excel import (astatka/sotuv/kassa); .py — bot o'zini yangilaydi"""
    if not can(u, 'boshqaruv'): return
    doc = u.message.document
    fname = ((doc.file_name if doc else '') or '').lower()
    if fname.endswith(('.xlsx', '.xlsm')):
        return await handle_excel(u, ctx)
    if fname.endswith(('.zip', '.db', '.sqlite', '.sqlite3')):
        return await zaxira_hujjat(u, ctx)                 # 💾 zaxira faylidan tiklash (faqat egasi, tasdiq bilan)
    if fname.endswith(('.xls', '.csv', '.ods', '.numbers')):
        await u.message.reply_text("📥 Excel faylni .xlsx formatida saqlab yuboring (Fayl → Saqlash → Excel .xlsx).")
        return
    if fname.endswith('.py') and not can(u, 'system'):
        await u.message.reply_text("Bot kodini yangilash faqat egasiga ruxsat etilgan."); return
    if not doc or not fname.endswith('.py'):
        await u.message.reply_text("Qabul qilinadigan fayllar:\n• .xlsx — Excel jadval (astatka, sotuv, xarajat, kassa import)\n"
                                   "• .zip — 💾 zaxira faylidan tiklash (faqat egasi)\n"
                                   "• .py — bot kodini yangilash")
        return
    await u.message.reply_text(f"⏳ {doc.file_name} qabul qilindi, tekshirilmoqda...")
    try:
        f = await ctx.bot.get_file(doc.file_id)
        data = bytes(await f.download_as_bytearray())
    except Exception as e:
        await u.message.reply_text(f"❌ Faylni Telegram'dan yuklab bo'lmadi: {str(e)[:150]}"); return
    try:
        await _deploy_bot_code(u.message, data, doc.file_name or 'telegram')
    except Exception as e:
        log.exception("deploy")
        await u.message.reply_text(f"❌ Yangilashda kutilmagan xato: {str(e)[:200]}\nHozirgi bot o'zgarishsiz ishlayapti.")


# ══════════════════════════════════════════════════════════════════
# EXCEL IMPORT — oylik jadval: astatka, sotuv, xarajat, kassa, zavod qarzi
# Fayl shu chatga yuboriladi → bot ko'rib chiqadi → "✅ Import" tugmasi bilan yoziladi.
# Kutubxona kerak emas (.xlsx = zip + xml).
# ══════════════════════════════════════════════════════════════════
class XLError(Exception):
    pass

_XL_M = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
_XL_R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

def init_excel_tables():
    conn = db(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS excel_imports (
        period TEXT PRIMARY KEY, imported_at TEXT, sheet TEXT,
        opening_cash REAL, summary TEXT)""")
    conn.commit(); conn.close()

def _xl_ref(ref):
    """'AB12' → (12, 28)"""
    m = re.match(r'^([A-Z]+)(\d+)$', ref or '')
    if not m: return None
    col = 0
    for ch in m.group(1): col = col * 26 + (ord(ch) - 64)
    return int(m.group(2)), col

def xlsx_oqi(raw):
    """.xlsx → [(varaq_nomi, {(qator, ustun): qiymat})] (qator/ustun 1 dan)"""
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = set(z.namelist())
        if 'xl/workbook.xml' not in names: raise zipfile.BadZipFile('workbook yo\'q')
    except zipfile.BadZipFile:
        raise XLError("Bu fayl .xlsx emas yoki buzilgan. Excel'da \"Saqlash → .xlsx\" qilib qayta yuboring.")
    shared = []
    if 'xl/sharedStrings.xml' in names:
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(_XL_M + 'si'):
            parts = [t.text or '' for t in si.findall(_XL_M + 't')]
            for r in si.findall(_XL_M + 'r'):
                parts += [t.text or '' for t in r.findall(_XL_M + 't')]
            shared.append(''.join(parts))
    rmap = {}
    if 'xl/_rels/workbook.xml.rels' in names:
        for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')):
            rmap[r.get('Id')] = r.get('Target', '')
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    sheets = wb.find(_XL_M + 'sheets')
    out = []
    for sh in (list(sheets) if sheets is not None else []):
        target = rmap.get(sh.get(_XL_R + 'id'), '')
        if not target: continue
        path = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        path = os.path.normpath(path).replace('\\', '/')
        if path not in names: continue
        cells = {}
        sd = ET.fromstring(z.read(path)).find(_XL_M + 'sheetData')
        rown = 0
        for row in (list(sd) if sd is not None else []):
            if row.tag != _XL_M + 'row': continue
            rown = int(row.get('r') or (rown + 1))
            coln = 0
            for c in row:
                if c.tag != _XL_M + 'c': continue
                rc = _xl_ref(c.get('r'))
                coln = rc[1] if rc else coln + 1
                t = c.get('t', 'n'); v = c.find(_XL_M + 'v')
                if t == 'inlineStr':
                    isel = c.find(_XL_M + 'is')
                    val = ''.join(x.text or '' for x in isel.iter(_XL_M + 't')) if isel is not None else ''
                elif v is None or v.text is None:
                    continue
                elif t == 's':
                    i = int(v.text); val = shared[i] if 0 <= i < len(shared) else ''
                elif t in ('str', 'e'):
                    val = v.text
                elif t == 'b':
                    val = 1.0 if v.text == '1' else 0.0
                else:
                    try: val = float(v.text)
                    except ValueError: val = v.text
                if val is None or (isinstance(val, str) and not val.strip()): continue
                cells[(rown, coln)] = val
        out.append((sh.get('name') or '', cells))
    return out

_XL_HDR = {'boshqoldi': 'bosh', 'sebestda': 'bosh_sebest', 'bittasebest': 'unit',
           'sotildisht': 'sold_qty', 'sotildisebest': 'sold_cost', 'sotildinarx': 'sold_rev',
           'qoldisht': 'end_qty', 'qoldisebest': 'end_cost'}
_OY_UZ = {'yanvar': 1, 'fevral': 2, 'mart': 3, 'aprel': 4, 'may': 5, 'iyun': 6, 'iyul': 7,
          'avgust': 8, 'sentyabr': 9, 'sentabr': 9, 'oktyabr': 10, 'oktabr': 10,
          'noyabr': 11, 'dekabr': 12}
_OY_NOMI = ['', 'Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun', 'Iyul', 'Avgust',
            'Sentyabr', 'Oktyabr', 'Noyabr', 'Dekabr']

def _hn(s):
    return re.sub(r'[^a-z]', '', str(s).lower())

def _xnum(v):
    if v is None or v == '': return None
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace(' ', '').replace(' ', '').replace('$', '').replace(',', '.')
    try: return float(s)
    except ValueError: return None

def _xl_period(text):
    """'01,09,2026' → '2026-09'; '2026-08' / '08.2026' / 'sentyabr' → oy"""
    s = str(text or '')
    m = re.search(r'(\d{1,2})\D+(\d{1,2})\D+(\d{4})', s)
    if m and 1 <= int(m.group(2)) <= 12 and 2000 <= int(m.group(3)) <= 2100:
        return f"{int(m.group(3))}-{int(m.group(2)):02d}"
    m = re.search(r'(\d{4})\D+(\d{1,2})(?!\d)', s)
    if m and 1 <= int(m.group(2)) <= 12 and 2000 <= int(m.group(1)) <= 2100:
        return f"{int(m.group(1))}-{int(m.group(2)):02d}"
    m = re.search(r'(?<!\d)(\d{1,2})\D+(\d{4})', s)
    if m and 1 <= int(m.group(1)) <= 12 and 2000 <= int(m.group(2)) <= 2100:
        return f"{int(m.group(2))}-{int(m.group(1)):02d}"
    low = s.lower()
    for k, mo in _OY_UZ.items():
        if re.search(r'\b' + k, low):
            y = re.search(r'(20\d\d)', low)
            return f"{y.group(1) if y else datetime.now().year}-{mo:02d}"
    return None

def _oy_label(p):
    y, m = p.split('-'); return f"{_OY_NOMI[int(m)]} {y}"

def xl_parse_sheet(name, cells):
    res = {'sheet': name, 'period': _xl_period(name), 'ok': False, 'why': '', 'rows': [],
           'opening': None, 'sales_cash': None, 'qoldiq': None, 'xarajat': [], 'tavar': None}
    if not cells:
        res['why'] = "bo'sh varaq"; return res
    by_row = defaultdict(dict)
    for (r, c), v in cells.items(): by_row[r][c] = v
    hdr, cols = None, {}
    for r in sorted(by_row):
        found = {}
        for c, v in sorted(by_row[r].items()):
            if isinstance(v, str):
                k = _XL_HDR.get(_hn(v))
                if k and k not in found: found[k] = c
        if {'bosh', 'sold_qty', 'end_qty'} <= set(found):
            hdr, cols = r, found; break
    if hdr is None:
        res['why'] = "sarlavha topilmadi (bosh Qoldi | Sotildi sht | Qoldi sht)"; return res
    name_col, price_col = cols['bosh'] - 1, cols['bosh'] - 2
    span = range(min(cols.values()), max(cols.values()) + 1)
    for r in sorted(x for x in by_row if x > hdr):
        rv = by_row[r]
        nm = rv.get(name_col)
        nm = re.sub(r'\s+', ' ', nm).strip() if isinstance(nm, str) else ''
        if _hn(nm).startswith(('order', 'zakaz', 'jami', 'itogo', 'total')): break
        if not nm:
            if any((_xnum(rv.get(c)) or 0) != 0 for c in span): break     # itog qatori — jadval tugadi
            continue
        g = lambda k: _xnum(rv.get(cols[k])) if k in cols else None
        res['rows'].append({'name': nm, 'price': _xnum(rv.get(price_col)),
                            'bosh': g('bosh'), 'bosh_sebest': g('bosh_sebest'), 'unit': g('unit'),
                            'sold_qty': g('sold_qty'), 'sold_cost': g('sold_cost'), 'sold_rev': g('sold_rev'),
                            'end_qty': g('end_qty'), 'end_cost': g('end_cost')})
    # O'ng tomondagi kassa bloki: naqd (oy boshi), naqd (sotuv), Xarajatlar, Qoldiq
    labels = sorted((r, c, _hn(v)) for (r, c), v in cells.items() if isinstance(v, str))
    right = lambda r, c, k=1: cells.get((r, c + k))
    naqd = [x for x in (_xnum(right(r, c)) for r, c, h in labels if h == 'naqd') if x is not None]
    if naqd: res['opening'] = naqd[0]
    if len(naqd) > 1: res['sales_cash'] = naqd[1]
    for r, c, h in labels:
        if h == 'qoldiq' and _xnum(right(r, c)) is not None:
            res['qoldiq'] = _xnum(right(r, c)); break
    for r, c, h in labels:
        if h == 'tavar' and _xnum(right(r, c)) is not None:
            res['tavar'] = _xnum(right(r, c)); break
    for r, c, h in labels:
        if h in ('xarajatlar', 'xarajat'):
            amt = _xnum(right(r, c))
            if not amt: continue
            note = ' — '.join(re.sub(r'\s+', ' ', x).strip() for x in (right(r, c, 2), right(r, c, 3))
                              if isinstance(x, str) and x.strip())
            res['xarajat'].append({'amount': round(amt, 2), 'note': note})
    if not res['rows']:
        res['why'] = "mahsulot qatorlari topilmadi"; return res
    if not res['period']:
        res['why'] = f"varaq nomidan oy aniqlanmadi ('{name}')"; return res
    res['ok'] = True
    return res

def xl_parse_workbook(raw):
    sheets = xlsx_oqi(raw)
    if not sheets: raise XLError("Excel faylda varaq topilmadi")
    return [xl_parse_sheet(n, c) for n, c in sheets]

def xl_choose(parsed, caption=''):
    """Qaysi oy(lar) import qilinadi → (oylar, eng_oxirgi_oy). Astatka faqat eng oxirgi oydan olinadi."""
    good = [p for p in parsed if p['ok']]
    if not good:
        why = '\n'.join(f"• {p['sheet']}: {p['why']}" for p in parsed[:8])
        raise XLError("Import qilsa bo'ladigan oylik varaq topilmadi.\n" + why +
                      "\n\nKerakli ustunlar: bosh Qoldi | sebestda | bitta sebest | Sotildi sht | "
                      "sotildi sebest | sotildi narx | Qoldi sht | Qoldi sebest")
    by_p = {}
    for p in good: by_p[p['period']] = p
    periods = sorted(by_p)
    latest = periods[-1]
    cap = (caption or '').lower()
    if re.search(r'\b(hammasi|barchasi|hamma|all)\b', cap):
        return [by_p[x] for x in periods], latest
    want = _xl_period(caption) if cap.strip() else None
    if want and want not in by_p:
        raise XLError(f"{_oy_label(want)} uchun varaq yo'q. Bor oylar: " + ', '.join(_oy_label(x) for x in periods))
    return [by_p[want or latest]], latest

# Excel'dagi nom (normallashgan) → botdagi nom
_XL_ALIAS = {
    'airassitpump': 'Air Assist Pump', 'airassistpump': 'Air Assist Pump',
    'cnc3018': 'CNC3018 Pro', 'f1130': 'F1130 (2 in 1)',
    '15in1': '15 in 1 (SB400)', 'sb40015a': '15 in 1 (SB400)',
    'p8100': 'P8100 (11 in 1)', 'p8100b220v11': 'P8100 (11 in 1)',
    'hc12e': "Hc12E qorong'i", 'hc12gb': 'Hc12g-B och', 'st210b110va': 'ST210 kepka',
    '4thaxiscncrotarymodulekit': '4th Axis Rotary', '500wspindleforttc450pro25': '500W Spindle',
    'extensionkit600x600mmforttsprottsseries': 'Extension Kit 600x600',
    'honeycomb500x500mm': 'Honeycomb 500x500', 'honeycomb400x400': 'Honeycomb 400x400',
    'ttc450pro25': 'TTC450 PRO', 'laserhead10w': 'Laser head 10W',
}

def xl_match(xname, prods):
    """Excel nomi → (botdagi mahsulot | None, usul)"""
    nx = _nrm(xname)
    if not nx: return None, ''
    byname = {p['name']: p for p in prods}
    a = _XL_ALIAS.get(nx)
    if a and a in byname: return byname[a], 'alias'
    ex = [p for p in prods if _nrm(p['name']) == nx]
    if ex: return ex[0], 'aniq'
    pre = [p for p in prods if len(_nrm(p['name'])) >= 4 and len(nx) >= 4 and
           (_nrm(p['name']).startswith(nx) or nx.startswith(_nrm(p['name'])))]
    if len(pre) == 1: return pre[0], 'boshi'
    if len(pre) > 1:
        return max(pre, key=lambda p: len(os.path.commonprefix([_nrm(p['name']), nx]))), 'taxminiy'
    xt = set(re.findall(r'[a-z0-9]+', str(xname).lower().replace('*', 'x')))
    sub = []
    for p in prods:
        pt = set(re.findall(r'[a-z0-9]+', p['name'].lower().replace('*', 'x')))
        if len(pt) >= 2 and pt <= xt: sub.append((len(pt), p))
    if sub:
        return sorted(sub, key=lambda x: -x[0])[0][1], "so'zlar"
    best, br = None, 0.0
    for p in prods:
        r = difflib.SequenceMatcher(None, nx, _nrm(p['name'])).ratio()
        if r > br: best, br = p, r
    if best and br >= 0.85: return best, 'taxminiy'
    return None, ''

def _xl_guess_cat(name):
    n = name.lower()
    if re.search(r'tts|laser|lazer|head', n): return 'Lazer', 'Two Trees'
    if re.search(r'cnc|ttc|spindle|honeycomb|rotary|pump|cutter|freza|extension|axis|vacuum', n):
        return 'CNC', 'Two Trees'
    if re.search(r'hc12|qog', n): return "Qog'oz", 'Freesub'
    return 'Press', 'Freesub'

_XL_SUP = [(r"two\s*t?re|twotre|\btrees?\b", 'Two Trees'), (r'free\s*su[bn]', 'Freesub'),
           (r'algo\s*laser', 'AlgoLaser'), (r'\bzavod', '')]
_XL_SHAXSIY = (r"\bo'?zim|shaxsiy|\buy\b|\buyga\b|\buyda\b|ro'?z?g'?or|kvartira|\bonam|\botam|ehson|"
               r"sadaqa|praduxt|produkt|oziq|ovqat|pitaniya|\bdacha|\boila|kiyim|\bbola")

def _xl_sup_of(note):
    n = str(note or '').lower()
    for rx, sup in _XL_SUP:
        if re.search(rx, n): return sup or '?'
    return '?'

def _xl_classify(note):
    n = str(note or '').lower()
    for ch in ('ʻ', '’', '‘', '`', 'ʼ'): n = n.replace(ch, "'")
    for rx, sup in _XL_SUP:
        if re.search(rx, n): return {'kind': 'zavod', 'sup': sup or '?'}
    if re.search(_XL_SHAXSIY, n): return {'kind': 'shaxsiy'}
    if re.search(r'\bbank|alibaba|komissiya|\bfee\b', n): return {'kind': 'xarajat', 'cat': 'bank', 'type': 'cogs_bank'}
    if re.search(r'olx|olex|reklama|instagram|target', n): return {'kind': 'xarajat', 'cat': 'reklama', 'type': 'period'}
    if re.search(r'\bai\b|\bai[ _-]|claude|chatgpt|\bgpt', n): return {'kind': 'xarajat', 'cat': 'ai_xizmat', 'type': 'period'}
    if re.search(r'abusa|kargo|cargo', n): return {'kind': 'xarajat', 'cat': 'kargo', 'type': 'period'}
    if re.search(r"dostavka|yo'?lkira|transport|taksi|taxi|pochta|\bbts\b|yetkaz", n):
        return {'kind': 'xarajat', 'cat': 'transport', 'type': 'period'}
    return {'kind': 'xarajat', 'cat': 'boshqa', 'type': 'period'}

def xl_plan(m, update_stock, prods=None):
    """Bitta oy uchun reja (bazaga hali yozmaydi)"""
    prods = prods if prods is not None else get_products(active_only=False)
    P = m['period']; y, mo = map(int, P.split('-'))
    d0 = P + '-01'
    d_end = f"{P}-{calendar.monthrange(y, mo)[1]:02d}"
    td = today()
    d_ops = td if d0 <= td < d_end else d_end
    if is_closed(d0): raise XLError(f"{_oy_label(P)} yopilgan — avval /och {P}")
    pl = {'period': P, 'sheet': m['sheet'], 'update_stock': update_stock, 'date': d_ops, 'd_end': d_end,
          'stock': [], 'sales': [], 'noaniq': [], 'exps': [], 'zavod': [], 'shaxsiy': [],
          'warn': [], 'opening': m['opening'], 'qoldiq': m['qoldiq'], 'not_in_excel': []}
    seen = {}
    for r in m['rows']:
        p, how = xl_match(r['name'], prods)
        tgt = p['name'] if p else r['name']
        if how == 'taxminiy': pl['warn'].append(f"'{r['name']}' → {tgt} (taxminiy moslik)")
        sq = r['sold_qty'] or 0; sr = r['sold_rev'] or 0; sc = r['sold_cost'] or 0
        unit = r['unit'] or 0
        if unit <= 0:
            if (r['end_qty'] or 0) > 0 and (r['end_cost'] or 0) > 0: unit = r['end_cost'] / r['end_qty']
            elif (r['bosh'] or 0) > 0 and (r['bosh_sebest'] or 0) > 0: unit = r['bosh_sebest'] / r['bosh']
        if sq > 0:
            cu = (sc / sq) if sc > 0 else unit
            pl['sales'].append({'product': tgt, 'qty': int(round(sq)), 'unit_cost': round(cu, 4),
                                'revenue': round(sr, 2)})
            if sr <= 0: pl['warn'].append(f"{tgt}: {int(round(sq))} ta sotilgan, lekin summasi yo'q — $0 deb yozildi")
        elif sr > 0:
            pl['noaniq'].append({'product': tgt, 'amount': round(sr, 2)})
        if not update_stock: continue
        eq = r['end_qty']
        if eq is None and r['bosh'] is not None: eq = max(0.0, r['bosh'] - sq)
        eq = int(round(eq or 0))
        if p is None and eq <= 0: continue
        if tgt in seen:
            seen[tgt]['qty'] += eq
            pl['warn'].append(f"'{r['name']}' qatori {tgt} bilan qo'shildi")
            continue
        st = {'name': tgt, 'excel_name': r['name'], 'new': p is None, 'pid': p['id'] if p else None,
              'old_qty': p['qty'] if p else 0, 'qty': eq,
              'old_cost': p['cost'] if p else 0,
              'cost': round(unit, 2) if unit > 0 else (p['cost'] if p else 0),
              'old_price': p['price'] if p else 0,
              'price': r['price'] if (r['price'] or 0) > 0 else (p['price'] if p else 0)}
        if p is None: st['cat'], st['sup'] = _xl_guess_cat(tgt)
        seen[tgt] = st; pl['stock'].append(st)
    if update_stock:
        conn = db(); c = conn.cursor()
        c.execute("SELECT product, COALESCE(SUM(qty),0) FROM sales WHERE date>? AND reversed=0 GROUP BY product", (d_end,))
        later = {a: int(b) for a, b in c.fetchall()}
        conn.close()
        for st in pl['stock']:
            k = later.get(st['name'], 0)
            if k:
                st['later'] = k; st['qty'] = max(0, st['qty'] - k)
        if later:
            pl['warn'].append("Oydan keyingi sotuvlar astatkadan ayirildi: " +
                              ', '.join(f"{a} {b} ta" for a, b in list(later.items())[:6]))
        names = {st['name'] for st in pl['stock']}
        pl['not_in_excel'] = [p['name'] for p in prods if p['qty'] > 0 and p['name'] not in names]
    for x in m['xarajat']:
        cl = _xl_classify(x['note']); amt = x['amount']
        if amt < 0:
            pl['warn'].append(f"Manfiy xarajat ({x['note']} {fmt(amt)}) — kassaga kirim deb yozildi")
        if cl['kind'] == 'zavod': pl['zavod'].append({'amount': amt, 'sup': cl['sup'], 'note': x['note']})
        elif cl['kind'] == 'shaxsiy': pl['shaxsiy'].append({'amount': amt, 'note': x['note']})
        else: pl['exps'].append({'amount': amt, 'cat': cl['cat'], 'type': cl['type'], 'note': x['note']})
    s_sum = sum(s['revenue'] for s in pl['sales']); n_sum = sum(n['amount'] for n in pl['noaniq'])
    out = sum(e['amount'] for e in pl['exps']) + sum(z['amount'] for z in pl['zavod']) + sum(s['amount'] for s in pl['shaxsiy'])
    pl['sales_sum'], pl['noaniq_sum'], pl['out_sum'] = s_sum, n_sum, out
    pl['adj'] = 0.0
    if pl['opening'] is not None:
        computed = pl['opening'] + s_sum + n_sum - out
        pl['computed_end'] = round(computed, 2)
        if pl['qoldiq'] is not None and abs(pl['qoldiq'] - computed) >= 0.5:
            pl['adj'] = round(pl['qoldiq'] - computed, 2)
    if m['sales_cash'] is not None and abs(m['sales_cash'] - (s_sum + n_sum)) >= 0.5:
        pl['warn'].append(f"Excel'dagi 2-'naqd' ({fmt(m['sales_cash'])}) sotuvlar yig'indisiga ({fmt(s_sum + n_sum)}) teng emas")
    # Zavod qarzi: oldin shu oy uchun yozilgan to'lovlar bilan farqi (qayta importda ikki marta yopilmasin)
    conn = db(); c = conn.cursor()
    c.execute("SELECT note, amount FROM cash_box WHERE date LIKE ? AND type='chiqim' AND category='zavod_qarz'", (P + '%',))
    old = defaultdict(float)
    for note, amt in c.fetchall(): old[_xl_sup_of(note)] += amt or 0
    new = defaultdict(float)
    for z in pl['zavod']: new[z['sup']] += z['amount']
    pl['debt'] = []
    for sup in sorted(set(old) | set(new)):
        # faqat shu oy oxirigacha paydo bo'lgan qarzlar (iyun to'lovi sentyabr qarzini yopmasin)
        if sup == '?':
            c.execute("SELECT COALESCE(SUM(remaining),0) FROM transit WHERE remaining>0 AND date<=?", (d_end,))
        else:
            c.execute("SELECT COALESCE(SUM(remaining),0) FROM transit WHERE remaining>0 AND supplier LIKE ? AND date<=?",
                      (f'%{sup}%', d_end))
        open_debt = c.fetchone()[0] or 0
        delta = round(new.get(sup, 0) - old.get(sup, 0), 2)
        pl['debt'].append({'sup': sup, 'delta': delta, 'open': round(open_debt, 2),
                           'after': round(max(0.0, open_debt - max(0.0, delta)), 2)})
    c.execute("SELECT COUNT(*) FROM sales WHERE date LIKE ?", (P + '%',)); pl['had_sales'] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM expenses WHERE date LIKE ?", (P + '%',)); pl['had_exps'] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM cash_box WHERE date LIKE ?", (P + '%',)); pl['had_cash'] = c.fetchone()[0]
    conn.close()
    return pl

def _xl_cash(c, d, typ, amt, cat, note):
    if abs(amt) < 0.005: return
    if amt < 0: typ = 'kirim' if typ == 'chiqim' else 'chiqim'
    c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
              (d, '12:00', typ, round(abs(amt), 2), cat, note, 'naqd'))

def _xl_pay_debt(c, sup, amount, d_end):
    if sup and sup != '?':
        c.execute("SELECT id, remaining FROM transit WHERE remaining>0 AND supplier LIKE ? AND date<=? ORDER BY date, id",
                  (f'%{sup}%', d_end))
    else:
        c.execute("SELECT id, remaining FROM transit WHERE remaining>0 AND date<=? ORDER BY date, id", (d_end,))
    left = amount
    for tid, rem in c.fetchall():
        if left <= 0.004: break
        part = min(left, rem)
        c.execute("UPDATE transit SET deposit=deposit+?, remaining=MAX(0,remaining-?) WHERE id=?", (part, part, tid))
        c.execute("UPDATE transit SET status='tolangan' WHERE id=? AND remaining<=0.004 AND status='qarz'", (tid,))
        left -= part
    return round(amount - left, 2)

def _xl_reanchor(c):
    """Import qilingan har oy boshida kassa qoldig'i Excel'dagi 'naqd' ga teng bo'lishi uchun"""
    for period, opening in c.execute(
            "SELECT period, opening_cash FROM excel_imports WHERE opening_cash IS NOT NULL ORDER BY period").fetchall():
        d0 = period + '-01'
        c.execute("DELETE FROM cash_box WHERE date=? AND category='boshlangich'", (d0,))
        c.execute("SELECT COALESCE(SUM(CASE WHEN type='kirim' THEN amount ELSE -amount END),0) FROM cash_box WHERE date<?", (d0,))
        diff = round(opening - (c.fetchone()[0] or 0), 2)
        if abs(diff) >= 0.01:
            c.execute("INSERT INTO cash_box (date,time,type,amount,category,note,payment_method) VALUES (?,?,?,?,?,?,?)",
                      (d0, '00:00', 'kirim' if diff > 0 else 'chiqim', abs(diff), 'boshlangich',
                       f"{_oy_label(period)} boshi qoldig'i {fmt(opening)} (Excel)", 'naqd'))

def _xl_apply_one(c, pl):
    P = pl['period']; like = P + '%'; d = pl['date']
    c.execute("SELECT DISTINCT customer_id FROM sales WHERE date LIKE ? AND COALESCE(customer_id,0)>0", (like,))
    cids = [r[0] for r in c.fetchall()]
    # 1) shu oy yozuvlari Excel bilan almashtiriladi
    c.execute("DELETE FROM warranties WHERE sale_id IN (SELECT id FROM sales WHERE date LIKE ?)", (like,))
    c.execute("DELETE FROM sales WHERE date LIKE ?", (like,))
    c.execute("DELETE FROM expenses WHERE date LIKE ?", (like,))
    c.execute("DELETE FROM cash_box WHERE date LIKE ?", (like,))
    c.execute("UPDATE op_log SET reversed=1 WHERE date LIKE ? AND op_type IN ('sale','expense')", (like,))
    # 2) astatka (faqat eng oxirgi oy)
    for st in pl['stock']:
        if st['new']:
            c.execute("SELECT id FROM products WHERE name=?", (st['name'],))
            bor = c.fetchone()
            if bor:
                stock_set(c, bor[0], st['qty'], 'tuzatish', f"Excel {P}", new_cost=st['cost'])
                c.execute("UPDATE products SET price=?, active=1 WHERE id=?", (st['price'], bor[0]))
            else:
                c.execute("INSERT INTO products (name,cat,supplier,qty,cost,price,factory_price,warranty_days,active) "
                          "VALUES (?,?,?,?,?,?,0,90,1)",
                          (st['name'], st['cat'], st['sup'], st['qty'], st['cost'], st['price']))
                if st['qty']: _sm_yoz(c, c.lastrowid, st['name'], int(st['qty']), int(st['qty']), 'yangi_tovar', st['cost'], f"Excel {P}")
        else:
            stock_set(c, st['pid'], st['qty'], 'tuzatish', f"Excel {P}", new_cost=st['cost'])
            c.execute("UPDATE products SET price=? WHERE id=?", (st['price'], st['pid']))
    # 3) sotuvlar + kassa
    for s in pl['sales']:
        c.execute("INSERT INTO sales (date,time,product,qty,unit_cost,revenue,profit,discount,customer,customer_type) "
                  "VALUES (?,?,?,?,?,?,?,0,'','B2C')",
                  (d, '12:00', s['product'], s['qty'], s['unit_cost'], s['revenue'],
                   round(s['revenue'] - s['unit_cost'] * s['qty'], 2)))
        sid = c.lastrowid
        _xl_cash(c, d, 'kirim', s['revenue'], 'sotuv', f"{s['product']} x{s['qty']} (#{sid}) Excel")
    for n in pl['noaniq']:
        _xl_cash(c, d, 'kirim', n['amount'], 'sotuv', f"{n['product']} — soni ko'rsatilmagan tushum (Excel)")
    # 4) xarajatlar (+kassa), zavod to'lovlari, shaxsiy
    for e in pl['exps']:
        if e['amount'] > 0:
            c.execute("INSERT INTO expenses (date,amount,category,expense_type,note) VALUES (?,?,?,?,?)",
                      (d, e['amount'], e['cat'], e['type'], (e['note'] or e['cat']) + ' (Excel)'))
            eid = c.lastrowid
            _xl_cash(c, d, 'chiqim', e['amount'], e['cat'], f"{e['note'] or e['cat']} (#x{eid})")
        else:
            _xl_cash(c, d, 'chiqim', e['amount'], 'boshqa', f"{e['note']} (Excel)")
    for z in pl['zavod']:
        _xl_cash(c, d, 'chiqim', z['amount'], 'zavod_qarz',
                 f"{z['sup'] if z['sup'] != '?' else 'Zavod'} — {z['note'] or 'to`lov'} (Excel)")
    debt_res = []
    for dbt in pl['debt']:
        if dbt['delta'] > 0.004:
            paid = _xl_pay_debt(c, dbt['sup'], dbt['delta'], pl['d_end'])
            debt_res.append({'sup': dbt['sup'], 'paid': paid})
    for s in pl['shaxsiy']:
        _xl_cash(c, d, 'chiqim', s['amount'], 'shaxsiy', f"{s['note'] or 'shaxsiy'} (Excel)")
    if pl['adj']:
        _xl_cash(c, d, 'kirim', pl['adj'], 'tuzatish', "Excel'dagi oy oxiri qoldig'iga tenglashtirish")
    summ = {'sales': len(pl['sales']), 'revenue': pl['sales_sum'], 'noaniq': pl['noaniq_sum'],
            'exps': sum(e['amount'] for e in pl['exps']), 'zavod': sum(z['amount'] for z in pl['zavod']),
            'shaxsiy': sum(s['amount'] for s in pl['shaxsiy']), 'adj': pl['adj']}
    c.execute("INSERT OR REPLACE INTO excel_imports (period,imported_at,sheet,opening_cash,summary) VALUES (?,?,?,?,?)",
              (P, now_t(), pl['sheet'], pl['opening'], json.dumps(summ, ensure_ascii=False)))
    return {'period': P, 'cids': cids, 'debt': debt_res}

def xl_apply(months, latest):
    """Tanlangan oylarni BITTA tranzaksiyada yozadi (xato bo'lsa hech narsa o'zgarmaydi)"""
    prods = get_products(active_only=False)
    plans = [xl_plan(m, m['period'] == latest, prods) for m in sorted(months, key=lambda x: x['period'])]
    conn = db(); c = conn.cursor()
    try:
        res = [_xl_apply_one(c, pl) for pl in plans]
        _xl_reanchor(c)
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
    for r in res:
        for cid in r['cids']:
            try: yangila_jami(cid)
            except Exception: pass
    return plans, res

def _cut(lines, n):
    return lines[:n] + ([f"  … yana {len(lines) - n} ta"] if len(lines) > n else [])

def xl_preview_text(plans):
    L = []
    multi = len(plans) > 1
    if multi:
        L.append(f"📥 EXCEL IMPORT — {len(plans)} oy: " + ', '.join(_oy_label(p['period']) for p in plans))
        L.append("")
        for p in plans:
            L.append(f"• {_oy_label(p['period'])}: sotuv {len(p['sales'])} ta {fmt(p['sales_sum'] + p['noaniq_sum'])}, "
                     f"xarajat {fmt(sum(e['amount'] for e in p['exps']))}, zavodga {fmt(sum(z['amount'] for z in p['zavod']))}, "
                     f"shaxsiy {fmt(sum(s['amount'] for s in p['shaxsiy']))}"
                     + (f", kassa oxiri {fmt(p['qoldiq'])}" if p['qoldiq'] is not None else ""))
        L.append("")
    for p in plans:
        if multi and not p['update_stock']: continue
        if not multi:
            L.append(f"📥 EXCEL IMPORT — {_oy_label(p['period'])} (varaq \"{p['sheet']}\")")
            L.append("")
        if p['update_stock']:
            tq = sum(s['qty'] for s in p['stock']); tc = sum(s['qty'] * s['cost'] for s in p['stock'])
            L.append(f"📦 Astatka ({_oy_label(p['period'])} oxiri): {tq} dona, sebest {fmt(tc)}")
            ch = [f"  • {s['name']}: {s['old_qty']} → {s['qty']}" + (f" (keyin {s['later']} ta sotilgan)" if s.get('later') else "")
                  for s in p['stock'] if not s['new'] and s['old_qty'] != s['qty']]
            pc = [s for s in p['stock'] if not s['new'] and s['old_qty'] == s['qty'] and
                  (abs((s['old_cost'] or 0) - s['cost']) >= 1 or abs((s['old_price'] or 0) - s['price']) >= 1)]
            L += _cut(ch, 14) if ch else ["  • soni o'zgarmaydi"]
            if pc: L.append(f"  (yana {len(pc)} ta mahsulotda faqat sebest/narx yangilanadi)")
            nw = [f"{s['name']} ({s['qty']} ta)" for s in p['stock'] if s['new']]
            if nw: L.append("  🆕 Yangi mahsulot: " + ', '.join(nw))
            if p['not_in_excel']:
                L.append("  ℹ️ Excel'da yo'q (o'zgarmaydi): " + ', '.join(p['not_in_excel'][:8]))
            L.append("")
        if multi: continue
        prof = sum(s['revenue'] - s['unit_cost'] * s['qty'] for s in p['sales'])
        L.append(f"🛒 Sotuvlar: {len(p['sales'])} ta — {fmt(p['sales_sum'])}, foyda {fmt(prof)}")
        L += _cut([f"  • {s['product']} ×{s['qty']} — {fmt(s['revenue'])}" for s in p['sales']], 12)
        for n in p['noaniq']:
            L.append(f"⚠️ {n['product']}: {fmt(n['amount'])} sotuv summasi yozilgan, lekin SONI yo'q → "
                     f"kassaga kirim qilinadi, astatka o'zgarmaydi. Agar sotilgan bo'lsa — Excel'da \"Sotildi sht\" ni to'ldirib qayta yuboring.")
        L.append("")
        if p['exps']:
            L.append(f"💸 Xarajat: {fmt(sum(e['amount'] for e in p['exps']))}")
            L += _cut([f"  • {e['note'] or '—'}: {fmt(e['amount'])} ({e['cat']})" for e in p['exps']], 10)
        for z in p['zavod']:
            L.append(f"🏭 Zavodga to'lov: {z['sup'] if z['sup'] != '?' else 'zavod'} {fmt(z['amount'])} ({z['note']})")
        for dbt in p['debt']:
            if dbt['delta'] > 0.004 and dbt['open'] > 0:
                L.append(f"   {dbt['sup'] if dbt['sup'] != '?' else 'Zavod'} qarzi: {fmt(dbt['open'])} → {fmt(dbt['after'])}")
            elif dbt['delta'] > 0.004:
                L.append("   (ochiq qarz yo'q — oldindan to'lov sifatida kassadan chiqim)")
            elif dbt['delta'] < -0.004:
                L.append(f"   ⚠️ {dbt['sup']}: avvalgi importdan {fmt(-dbt['delta'])} kam — zavod qarzini tekshiring")
        if p['shaxsiy']:
            L.append(f"👤 Shaxsiy (xarajat emas): {fmt(sum(s['amount'] for s in p['shaxsiy']))} — " +
                     ', '.join(f"{s['note']} {fmt(s['amount'])}" for s in p['shaxsiy'][:5]))
        L.append("")
        if p['opening'] is not None:
            end = p.get('computed_end', 0) + p['adj']
            line = f"💵 Kassa: oy boshi {fmt(p['opening'])} → oy oxiri {fmt(end)}"
            if p['qoldiq'] is not None:
                line += " (Excel bilan teng ✅)" if not p['adj'] else f" (Excel: {fmt(p['qoldiq'])})"
            L.append(line)
            if p['adj']:
                L.append(f"⚖️ Excel'dagi Qoldiq bilan farq {fmt(p['adj'])} — 'tuzatish' yozuvi bilan tenglashtiriladi")
        else:
            L.append("💵 Kassa: oy boshi qoldig'i ('naqd') topilmadi — faqat oy harakatlari yoziladi")
        for w in p['warn'][:8]: L.append("⚠️ " + w)
        if p['had_sales'] or p['had_exps'] or p['had_cash']:
            L.append(f"❗ Botdagi {_oy_label(p['period'])} yozuvlari ({p['had_sales']} sotuv, {p['had_exps']} xarajat, "
                     f"{p['had_cash']} kassa) Excel bilan ALMASHTIRILADI.")
    if multi:
        for p in plans:
            for n in p['noaniq']:
                L.append(f"⚠️ {_oy_label(p['period'])}: {n['product']} {fmt(n['amount'])} — soni yozilmagan → kassaga kirim, astatka o'zgarmaydi")
            for w in p['warn'][:3]: L.append(f"⚠️ {_oy_label(p['period'])}: {w}")
        L.append("❗ Shu oylarning botdagi yozuvlari Excel bilan ALMASHTIRILADI. Astatka — eng oxirgi oydan.")
    L.append("")
    L.append("Tasdiqlaysizmi?")
    txt = '\n'.join(L)
    return txt if len(txt) < 3900 else txt[:3850] + "\n…\nTasdiqlaysizmi?"

async def handle_excel(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc = u.message.document
    if doc.file_size and doc.file_size > 15 * 1024 * 1024:
        await u.message.reply_text("❌ Fayl juda katta (15 MB dan oshmasin)."); return
    await ctx.bot.send_chat_action(chat_id=u.effective_chat.id, action='typing')
    try:
        f = await ctx.bot.get_file(doc.file_id)
        raw = bytes(await f.download_as_bytearray())
        parsed = await asyncio.to_thread(xl_parse_workbook, raw)
        months, latest = xl_choose(parsed, u.message.caption or '')
        prods = await asyncio.to_thread(get_products, False)
        plans = await asyncio.to_thread(lambda: [xl_plan(m, m['period'] == latest, prods) for m in months])
    except XLError as e:
        await u.message.reply_text(f"⚠️ {e}"); return
    except Exception as e:
        log.exception("excel o'qish")
        await u.message.reply_text(f"⚠️ Excel'ni o'qib bo'lmadi: {str(e)[:200]}"); return
    token = secrets.token_hex(4)
    ctx.user_data['xl_import'] = {'token': token, 'months': months, 'latest': latest,
                                  'file': doc.file_name, 'ts': time.time()}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Import qilish", callback_data=f"xlimp_ok_{token}"),
                                InlineKeyboardButton("❌ Bekor", callback_data=f"xlimp_no_{token}")]])
    await u.message.reply_text(xl_preview_text(plans), reply_markup=kb)

async def xl_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE, data: str):
    q = u.callback_query
    if not can(u, 'boshqaruv'): return
    try: _, action, token = data.split('_', 2)
    except ValueError: return
    st = ctx.user_data.get('xl_import')
    if not st or st.get('token') != token:
        await q.message.reply_text("⌛ Bu import eskirgan. Excel faylni qaytadan yuboring."); return
    ctx.user_data.pop('xl_import', None)
    try: await q.edit_message_reply_markup(reply_markup=None)
    except Exception: pass
    if action != 'ok':
        await q.message.reply_text("❌ Import bekor qilindi — hech narsa o'zgarmadi."); return
    await q.message.reply_text("⏳ Import qilinmoqda...")
    try:
        plans, res = await asyncio.to_thread(xl_apply, st['months'], st['latest'])
    except XLError as e:
        await q.message.reply_text(f"⚠️ {e}\nHech narsa o'zgarmadi."); return
    except Exception as e:
        log.exception("excel import")
        await q.message.reply_text(f"⚠️ Import xatosi — hech narsa o'zgarmadi: {str(e)[:200]}"); return
    prods = get_products()
    L = ["✅ Excel import tugadi — " + ', '.join(_oy_label(p['period']) for p in plans), ""]
    for p in plans:
        L.append(f"• {_oy_label(p['period'])}: {len(p['sales'])} sotuv {fmt(p['sales_sum'] + p['noaniq_sum'])}, "
                 f"xarajat {fmt(sum(e['amount'] for e in p['exps']))}")
    for r in res:
        for dbt in r['debt']:
            if dbt['paid'] > 0: L.append(f"🏭 {dbt['sup']} qarzidan {fmt(dbt['paid'])} yopildi")
    conn = db(); c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(remaining),0) FROM transit WHERE remaining>0")
    zq = c.fetchone()[0] or 0; conn.close()
    L += ["", f"📦 Astatka: {sum(p['qty'] for p in prods)} dona, sebest {fmt(sum(p['qty'] * p['cost'] for p in prods))}",
          f"💵 Kassa hozir: {fmt(get_cash_balance())}",
          f"🏭 Zavod qarzi: {fmt(zq)}", "",
          "Tekshiring: 📦 Astatka, 💵 Kassa, /oy_tafsil " + plans[-1]['period']]
    await q.message.reply_text('\n'.join(L))
    ok, msg = await asyncio.to_thread(db_backup_to_github, 'excel import')
    await q.message.reply_text(("💾 Zaxira: " if ok else "⚠️ Zaxira: ") + msg)


# ── TELEGRAM KANAL POSTLAR ────────────────────────────────────────
async def post_to_channel(ctx: ContextTypes.DEFAULT_TYPE, text: str):
    """Kanalga post yuborish"""
    ch = get_channel_id()
    if not ch:
        return False
    try:
        await ctx.bot.send_message(
            chat_id=ch,
            text=text,
            parse_mode='Markdown')
        return True
    except BadRequest as e:
        # Mahsulot nomidagi _ yoki * Markdown'ni buzsa — post yo'qolmasin, oddiy matn bilan yuboramiz
        log.warning(f"Kanal post Markdown xato, oddiy matn: {e}")
        try:
            await ctx.bot.send_message(chat_id=ch, text=text.replace('*', '').replace('`', ''))
            return True
        except Exception as e2:
            log.error(f"Kanal post xato: {e2}")
            return False
    except Exception as e:
        log.error(f"Kanal post xato: {e}")
        return False

async def cmd_post_kanal(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Kanalga tovarlar e'lonini yuborish"""
    if not can(u, 'boshqaruv'): return
    ch = get_channel_id()
    if not ch:
        await u.message.reply_text("❌ CHANNEL_ID Railway da sozlanmagan!\n\nVariables ga qo'shing:\nCHANNEL_ID = @ThermoCrafts")
        return

    prods = get_products()
    rate = get_exchange_rate()

    # Two Trees mahsulotlari
    tt = [p for p in prods if p['sup'] == 'Two Trees' and p['qty'] > 0]
    fs = [p for p in prods if p['sup'] == 'Freesub' and p['qty'] > 0]

    text = "🏭 *ThermoCrafts — Mavjud mahsulotlar*\n"
    text += "📍 Yunusobod, Toshkent\n\n"

    if tt:
        text += "🔵 *Lazer va CNC stanoklar:*\n"
        for p in tt:
            text += f"• {p['name']} — *{fmt(p['price'])}*\n"
        text += "\n"

    if fs:
        text += "🟠 *Termopress va sublimatsiya:*\n"
        for p in fs:
            if p['cat'] == 'Press':
                text += f"• {p['name']} — *{fmt(p['price'])}*\n"
        text += "\n"

    text += f"💱 1 USD = {rate:,.0f} so'm\n"
    text += "📞 Buyurtma uchun yozing!\n"
    text += "#ThermoCrafts #lazer #termopress #Toshkent"

    ok = await post_to_channel(ctx, text)
    if ok:
        await u.message.reply_text("✅ Kanal ga post yuborildi!")
    else:
        await u.message.reply_text("❌ Post yuborib bo'lmadi! Bot admin qilinganmi?")

async def cmd_post_maxsus(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Maxsus aksiya yoki e'lon postlash"""
    if not can(u, 'boshqaruv'): return
    if not ctx.args:
        await u.message.reply_text(
            "Format: /post_maxsus <matn>\n\n"
            "Misol: /post_maxsus TTS 20 Pro 10% chegirma bilan!")
        return
    text = "📢 *ThermoCrafts — Maxsus taklif!*\n\n"
    text += ' '.join(ctx.args)
    text += "\n\n📞 Buyurtma uchun yozing!"
    ok = await post_to_channel(ctx, text)
    if ok:
        await u.message.reply_text("✅ Maxsus post yuborildi!")
    else:
        await u.message.reply_text("❌ Post yuborib bo'lmadi!")

async def cmd_post_taklif(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Kunlik set takliflarini postlash"""
    if not can(u, 'boshqaruv'): return
    prods = get_products()
    rate = get_exchange_rate()

    # Top 3 mahsulot
    top = sorted([p for p in prods if p['qty'] > 0],
                 key=lambda x: x['price']-x['cost'], reverse=True)[:4]

    text = "⭐ *ThermoCrafts — Bugungi takliflar!*\n\n"
    for p in top:
        margin = p['price'] - p['cost']
        text += f"✅ {p['name']}\n"
        text += f"   💵 {fmt(p['price'])} ({fmt(margin)} tejaysiz!)\n\n"

    text += f"💱 1 USD = {rate:,.0f} so'm\n"
    text += "📍 Yunusobod, Toshkent\n"
    text += "📞 Buyurtma: @ThermoCrafts\n"
    text += "#lazer #termopress #CNC #Toshkent"

    ok = await post_to_channel(ctx, text)
    if ok:
        await u.message.reply_text("✅ Kunlik taklif post yuborildi!")
    else:
        await u.message.reply_text("❌ Post yuborib bo'lmadi!")


async def cmd_stock_reset(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Astatka ma'lumotlarini Excel dan yangilash"""
    if not can(u, 'system'): return
    if not ctx.args or ctx.args[0].lower() != 'ha':
        await u.message.reply_text(
            "⚠️ Bu buyruq 21 ta mahsulotning soni/sebest/narxini 01.09.2026 holatiga QAYTA YOZADI "
            "(sentyabrdan keyingi sotuv va kelgan tovarlar astatkadan yo'qoladi).\n\n"
            "Rostdan ham kerak bo'lsa: /stock_reset ha")
        return
    conn = db(); c = conn.cursor()
    # Haqiqiy Sept 2026 ma'lumoti
    updates = [
        (2, 117, 250, 1),   # TTS 55 Pro: 2ta
        (4, 154, 290, 2),   # TTS 10 Pro: 4ta
        (3, 296, 490, 3),   # TTS 20 Pro: 3ta
        (2,  87, 120, 4),   # Laser head: 2ta
        (5,  98, 185, 5),   # CNC3018: 5ta
        (1,  91, 180, 6),   # 4th Axis: 1ta
        (1,  91, 180, 7),   # 500W Spindle: 1ta
        (1,  65, 100, 8),   # Milling: 1ta
        (1,  65, 110, 9),   # Extension Kit: 1ta
        (2,  23,  35, 10),  # Honeycomb 400: 2ta
        (1,  23,  70, 11),  # Honeycomb 500: 1ta
        (2,  21,  45, 12),  # Rotary Blue: 2ta
        (2,  41,  45, 13),  # Air Assist: 2ta
        (2, 300, 360, 14),  # 15 in 1: 2ta
        (2, 160, 335, 15),  # P8100: 2ta
        (2, 100, 190, 16),  # F1130: 2ta
        (1,  88, 130, 17),  # PD150: 1ta
        (1,  89, 190, 18),  # ST210: 1ta
        (1,  85, 190, 19),  # F270: 1ta
        (2,  53,  65, 20),  # Hc12E: 2ta
        (1,  15,  18, 21),  # Hc12g-B: 1ta
    ]
    for qty, cost, price, pid in updates:
        stock_set(c, pid, qty, 'tuzatish', '/stock_reset', new_cost=cost)
        c.execute('UPDATE products SET price=? WHERE id=?', (price, pid))
    # Kassa qoldig'i ham yangilansin
    conn.commit(); conn.close()
    await u.message.reply_text(
        "✅ *Astatka yangilandi!*\n\n"
        "📊 Excel (01.09.2026) ma'lumoti asosida:\n"
        "🔵 Two Trees — 23 dona\n"
        "🟠 Freesub — 14 dona\n"
        "💰 Kassa qoldig'i: $1,080\n\n"
        "_Hozirgi holat botda yangilandi!_",
        parse_mode='Markdown')


# ── SUHBATDAN CHIQISH (menyu tugmasi bosilsa) ────────────────────
async def conv_escape_start(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await cmd_start(u, ctx)
    return ConversationHandler.END

async def conv_escape_menu(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await route_menu(u, ctx, u.message.text)
    return ConversationHandler.END

async def on_error(u: object, ctx: ContextTypes.DEFAULT_TYPE):
    log.error("Xato:", exc_info=ctx.error)
    try:
        # Xato matni (ichki tafsilotlar) faqat egasiga ko'rsatiladi — mijozga/kanalga emas.
        # Markdown'siz: xato matnidagi ` yoki _ yangi xatoga sabab bo'lmasin.
        if (isinstance(u, Update) and u.effective_message and u.effective_user
                and u.effective_user.id == OWNER_ID):
            await u.effective_message.reply_text(
                f"\u26a0\ufe0f Xato yuz berdi:\n{str(ctx.error)[:250]}")
        elif isinstance(u, Update) and u.effective_message and user_role(u):
            await u.effective_message.reply_text("\u26a0\ufe0f Xato yuz berdi. Qaytadan urinib ko'ring.")
    except Exception:
        pass


async def _faqat_yangi_xabar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tahrirlangan xabarlar va kanal postlari hech qaysi handlerga bormaydi.
    Aks holda: tahrirlangan "/restore ha" yoki sotuv qayta bajarilardi, u.message None bo'lib
    xato chiqardi, kanal postlariga esa bot xato matni bilan javob yozardi."""
    if u.edited_message or u.channel_post or u.edited_channel_post:
        raise ApplicationHandlerStop


# ── MARKDOWN XATOSIDAN HIMOYA ────────────────────────────────────
def _install_safe_reply():
    """Markdown buzilsa, xabarni oddiy matn sifatida qayta yuboradi"""
    from telegram import Message
    _orig = Message.reply_text
    async def safe_reply_text(self, text, *a, **kw):
        try:
            return await _orig(self, text, *a, **kw)
        except Exception as e:
            if "parse entities" in str(e).lower() or "parse_mode" in str(e).lower():
                kw.pop('parse_mode', None)
                clean = text.replace('*','').replace('_','').replace('`','')
                return await _orig(self, clean, *a, **kw)
            raise
    Message.reply_text = safe_reply_text

# ── MAIN ──────────────────────────────────────────────────────────
class RolFiltr(filters.MessageFilter):
    """Xabar yuboruvchining roli bo'yicha filtr (rol bazadan o'qiladi — o'zgarish darhol ishlaydi).
    perm=None — istalgan faol xodim yoki egasi; perm berilsa — can(uid, perm)."""
    def __init__(self, perm=None):
        super().__init__(name=f"RolFiltr({perm or 'xodim'})")
        self.perm = perm
    def filter(self, message):
        uid = getattr(message.from_user, 'id', None) if message.from_user else None
        if uid is None: return False
        return (user_role(uid) is not None) if self.perm is None else can(uid, self.perm)


def main():
    if not BOT_TOKEN: raise ValueError("BOT_TOKEN yo'q!")
    if not ANTHROPIC_KEY: raise ValueError("ANTHROPIC_KEY yo'q!")
    if OWNER_ID == 0: raise ValueError("OWNER_ID yo'q!")

    _d = os.path.dirname(DB_PATH)
    if _d: os.makedirs(_d, exist_ok=True)
    log.info("Baza: %s (%s)", DB_PATH, "Volume — doimiy disk" if db_on_volume() else "vaqtinchalik disk, GitHub zaxira")
    try:
        db_autorestore()
    except Exception as e:
        log.exception("db_autorestore")
        _BK['blocked'] = f"tiklashda kutilmagan xato: {str(e)[:120]}"
        _BK['restore_msg'] = ("⚠️ Ishga tushishda zaxirani tiklashda xato: " + str(e)[:200] +
                              "\nAvto-zaxira to'xtatildi. /restore ha ni sinab ko'ring.")
    init_db()

    app = (Application.builder().token(BOT_TOKEN)
           .post_init(_post_init).post_shutdown(_post_shutdown).build())

    STAFF = RolFiltr()                    # egasi + faol xodimlar (rol bazadan, har safar)
    BOSHQ = RolFiltr('boshqaruv')         # egasi + admin
    # Tahrirlangan xabar / kanal postlarini eng oldin to'xtatamiz (group=-1)
    app.add_handler(TypeHandler(Update, _faqat_yangi_xabar), group=-1)
    # Suhbat ichida menyu tugmasi bosilsa — u nom/narx sifatida yozilmasin, fallback'ga o'tsin
    MENU_F = filters.Text(list(MENU_MAP.keys()))
    CONV_TEXT = filters.TEXT & ~filters.COMMAND & ~MENU_F

    # Yangi tovar qo'shish (ConversationHandler)
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('yangi_tovar', conv_start, filters=BOSHQ),
            CallbackQueryHandler(conv_start, pattern='^new_product$'),
            # "➕ Yangi tovar" menyu tugmasi: avval suhbatdan tashqarida ochilib, nom yozilganda AI'ga ketardi
            MessageHandler(filters.Text(["➕ Yangi tovar"]) & BOSHQ, conv_start),
        ],
        states={
            S_NAME: [MessageHandler(CONV_TEXT, conv_name)],
            S_CAT: [CallbackQueryHandler(conv_cat_cb, pattern='^cat_')],
            S_SUP: [CallbackQueryHandler(conv_sup_cb, pattern='^sup_')],
            S_COST: [MessageHandler(CONV_TEXT, conv_cost)],
            S_PRICE: [MessageHandler(CONV_TEXT, conv_price)],
            S_QTY: [MessageHandler(CONV_TEXT, conv_qty)],
            S_SPECS: [
                MessageHandler(CONV_TEXT, conv_specs),
                CommandHandler('tayyor', conv_specs_done),
            ],
            S_PHOTOS: [
                CallbackQueryHandler(conv_photos_cb, pattern='^photos_'),
                MessageHandler(filters.PHOTO, conv_photo),
                CommandHandler('tayyor', conv_finish),
            ],
        },
        fallbacks=[
            CommandHandler('bekor', conv_cancel),
            CommandHandler('start', conv_escape_start),
            MessageHandler(MENU_F, conv_escape_menu),
        ],
        allow_reentry=True,
        # 15 daqiqa javob bo'lmasa suhbat yopiladi (JobQueue o'rnatilgan bo'lsa)
        conversation_timeout=(900 if app.job_queue else None),
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('start', cmd_start, filters=STAFF))
    app.add_handler(CommandHandler('start', cmd_start_public, filters=~STAFF))
    app.add_handler(CommandHandler('stop', cmd_stop_public, filters=~STAFF))
    app.add_handler(CommandHandler('sotuv', pos_start))
    app.add_handler(CommandHandler('qoldiq', cmd_qoldiq))
    app.add_handler(CommandHandler('mening', cmd_mening))
    app.add_handler(CommandHandler('id', cmd_id))
    app.add_handler(CommandHandler('xodim_qosh', cmd_xodim_qosh))
    app.add_handler(CommandHandler('xodimlar', cmd_xodimlar))
    app.add_handler(CommandHandler('xodim_ochir', cmd_xodim_ochir))
    app.add_handler(CommandHandler('sotuvchilar', cmd_sotuvchilar))
    app.add_handler(CommandHandler('ombor', cmd_ombor))
    app.add_handler(CommandHandler('kam', cmd_kam))
    app.add_handler(CommandHandler('qarzdorlar', cmd_qarzdorlar))
    app.add_handler(CommandHandler('hisobotlar', cmd_hisobotlar))
    app.add_handler(CommandHandler('zavod', cmd_zavod_ui))
    app.add_handler(CommandHandler('marketing', cmd_marketing))
    app.add_handler(CommandHandler('zaxira', cmd_zaxira))
    app.add_handler(CommandHandler('qaytarish', cmd_qaytarish))
    app.add_handler(CommandHandler('smena', cmd_smena))
    app.add_handler(CommandHandler('serial', cmd_serial))
    app.add_handler(CommandHandler('yorliq', cmd_yorliq))
    app.add_handler(CommandHandler('help', cmd_yordam))
    app.add_handler(CommandHandler('yordam', cmd_yordam))
    app.add_handler(CommandHandler('astatka', cmd_astatka))
    app.add_handler(CommandHandler('narxlar', cmd_narxlar))
    app.add_handler(CommandHandler('bugun', cmd_bugun))
    app.add_handler(CommandHandler('oy', cmd_oy))
    app.add_handler(CommandHandler('yil', cmd_yil))
    app.add_handler(CommandHandler('yolda', cmd_yolda))
    app.add_handler(CommandHandler('zavod_qarz', cmd_zavod_qarz))
    app.add_handler(CommandHandler('analiz', cmd_analiz))
    app.add_handler(CommandHandler('mijozlar', cmd_mijozlar_yangi))
    app.add_handler(CommandHandler('qarzlar', cmd_qarzlar))
    app.add_handler(CommandHandler('qarz_tolov', cmd_qarz_tolov))
    app.add_handler(CommandHandler('zavod_tolov', cmd_zavod_tolov))
    app.add_handler(CommandHandler('xarajatlar', cmd_xarajatlar))
    app.add_handler(CommandHandler('kafolat', cmd_kafolat))
    app.add_handler(CommandHandler('cashflow', cmd_cashflow))
    app.add_handler(CommandHandler('trend', cmd_trend))
    app.add_handler(CommandHandler('rate', cmd_rate))
    app.add_handler(CommandHandler('maqsad', cmd_maqsad))
    app.add_handler(CommandHandler('olx', cmd_olx))
    app.add_handler(CommandHandler('raqobat', cmd_raqobat))
    app.add_handler(CommandHandler('undo', cmd_undo_list))
    app.add_handler(CommandHandler('katalog', cmd_katalog))
    app.add_handler(CommandHandler('tayyor', handle_photo_done))
    app.add_handler(CommandHandler('update', cmd_update))
    app.add_handler(CommandHandler('reset', cmd_ai_reset))
    app.add_handler(CommandHandler('xotira', cmd_xotira))
    app.add_handler(CommandHandler('brief', cmd_brief))
    app.add_handler(CommandHandler('dashboard', cmd_dashboard))
    app.add_handler(CommandHandler('moliya', cmd_moliya))
    app.add_handler(CommandHandler('qarz_yosh', cmd_qarz_yosh))
    app.add_handler(CommandHandler('aylanish', cmd_aylanish))
    app.add_handler(CommandHandler('yop', cmd_yop))
    app.add_handler(CommandHandler('och', cmd_och))
    app.add_handler(CommandHandler('hujjat', cmd_hujjat))
    app.add_handler(CommandHandler('deps', cmd_deps))
    app.add_handler(CommandHandler('mijoz', cmd_mijoz))
    app.add_handler(CommandHandler('bogla', cmd_bogla))
    app.add_handler(CommandHandler('birlashtir', cmd_birlashtir))
    app.add_handler(CommandHandler('kanal', cmd_kanal))
    app.add_handler(CommandHandler('kanallar', cmd_kanallar))
    app.add_handler(CommandHandler('qayta', cmd_qayta))
    app.add_handler(CommandHandler('qayta_ochir', cmd_qayta_ochir))
    app.add_handler(CommandHandler('rasxodnik', cmd_rasxodnik))
    app.add_handler(CommandHandler('dalolatnoma', cmd_dalolatnoma))
    app.add_handler(CommandHandler('ulash', cmd_ulash))
    app.add_handler(CommandHandler('backup', cmd_backup))
    app.add_handler(CommandHandler('restore', cmd_restore))
    app.add_handler(CommandHandler('stock_reset', cmd_stock_reset))
    app.add_handler(CommandHandler('oy_tafsil', cmd_oy_tafsil))
    app.add_handler(CommandHandler('kassa', cmd_kassa))
    app.add_handler(CommandHandler('nelikvid', cmd_nelikvid))
    app.add_handler(CommandHandler('eslatmalar', cmd_eslatmalar))
    app.add_handler(CommandHandler('reklama', cmd_reklama))
    app.add_handler(CommandHandler('reklama_preview', cmd_reklama_preview))
    app.add_handler(CommandHandler('obunachilar', cmd_obunachilar))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.Document.ALL, handle_photo_ai))
    app.add_handler(MessageHandler(filters.VIDEO & ~filters.Document.ALL, handle_video_post))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CommandHandler('post', cmd_post_kanal))
    app.add_handler(CommandHandler('post_maxsus', cmd_post_maxsus))
    app.add_handler(CommandHandler('post_taklif', cmd_post_taklif))
    app.add_handler(CallbackQueryHandler(pos_callback, pattern=r'^pos:'))
    app.add_handler(CallbackQueryHandler(xodim_callback, pattern=r'^xod:'))
    app.add_handler(CallbackQueryHandler(omb_callback, pattern=r'^omb:'))
    app.add_handler(CallbackQueryHandler(mij_callback, pattern=r'^mij:'))
    app.add_handler(CallbackQueryHandler(his_callback, pattern=r'^his:'))
    app.add_handler(CallbackQueryHandler(zav_callback, pattern=r'^zav:'))
    app.add_handler(CallbackQueryHandler(mkt_callback, pattern=r'^mkt:'))
    app.add_handler(CallbackQueryHandler(lead_callback, pattern=r'^lead:'))
    app.add_handler(CallbackQueryHandler(pub_callback, pattern=r'^pub:'))
    app.add_handler(CallbackQueryHandler(zx_callback, pattern=r'^zx:'))
    app.add_handler(CallbackQueryHandler(qr_callback, pattern=r'^qr:'))
    app.add_handler(CallbackQueryHandler(sm_callback, pattern=r'^sm:'))
    app.add_handler(CallbackQueryHandler(sn_callback, pattern=r'^sn:'))
    app.add_handler(CallbackQueryHandler(kod_callback, pattern=r'^kod:'))
    app.add_handler(MessageHandler(filters.CONTACT & ~STAFF, pub_contact))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & STAFF, handle_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~STAFF, handle_text_public))

    _install_safe_reply()
    app.add_error_handler(on_error)
    log.info("ThermoCrafts Bot v3.0 ishga tushdi! ✅")
    log.info(f"21 modul | {len(get_products())} mahsulot")
    # drop_pending_updates=False: qayta ishga tushish paytida yozilgan xabarlar (sotuv) yo'qolmasin
    app.run_polling(drop_pending_updates=False)

if __name__ == '__main__':
    main()
