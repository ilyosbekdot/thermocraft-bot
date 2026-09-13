#!/usr/bin/env python3
"""
ThermoCrafts Biznes Bot v3.0
21 Modul | IAS 2 | ABC/XYZ CV | Katalog | Kafolat | Marketing
"""
import os, json, sqlite3, logging, math, re, requests, base64
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup,
                       InputMediaPhoto, ReplyKeyboardMarkup, KeyboardButton)
from telegram.ext import (Application, CommandHandler, MessageHandler,
                           CallbackQueryHandler, ConversationHandler,
                           filters, ContextTypes)
import anthropic

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
log = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────
BOT_TOKEN     = os.getenv('BOT_TOKEN', '')
ANTHROPIC_KEY = os.getenv('ANTHROPIC_KEY', '')
OWNER_ID      = int(os.getenv('OWNER_ID', '0'))
CHANNEL_ID    = os.getenv('CHANNEL_ID', '')   # @ThermoCrafts
DB_PATH       = 'thermocraft.db'
ai = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# Conversation states
(S_NAME, S_CAT, S_SUP, S_COST, S_PRICE, S_QTY,
 S_SPECS, S_PHOTOS, S_DONE) = range(9)

# ── INITIAL PRODUCTS ──────────────────────────────────────────────
INIT_P = [
    (1,'TTS 55 Pro','Lazer','Two Trees',3,130,195,110),
    (2,'TTS 10 Pro','Lazer','Two Trees',2,170,260,150),
    (3,'TTS 20 Pro','Lazer','Two Trees',3,300,470,280),
    (4,'Laser head 10W','Lazer','Two Trees',2,87,120,80),
    (5,'CNC3018 Pro','CNC','Two Trees',5,115,182,95),
    (6,'4th Axis Rotary','CNC','Two Trees',1,91,180,70),
    (7,'500W Spindle','CNC','Two Trees',1,91,180,70),
    (8,'Milling Cutter','CNC','Two Trees',1,65,100,50),
    (9,'Extension Kit 600x600','CNC','Two Trees',1,65,110,55),
    (10,'Honeycomb 400x400','CNC','Two Trees',2,23,35,20),
    (11,'Honeycomb 500x500','CNC','Two Trees',1,23,70,18),
    (12,'Rotary Blue','CNC','Two Trees',2,21,47,18),
    (13,'Air Assist Pump','CNC','Two Trees',2,41,47,35),
    (14,'15 in 1 (SB400)','Press','Freesub',2,300,355,198),
    (15,'P8100 (11 in 1)','Press','Freesub',2,160,332,140),
    (16,'F1130 (2 in 1)','Press','Freesub',2,100,187,88),
    (17,'PD150','Press','Freesub',1,88,140,80),
    (18,'ST210 kepka','Press','Freesub',1,89,190,82),
    (19,'F270','Press','Freesub',1,85,190,79),
    (20,"Hc12E qorong'i","Qog'oz",'Freesub',2,53,65,45),
    (21,"Hc12g-B och","Qog'oz",'Freesub',1,15,18,12),
]

# Texnik ma'lumotlar (saytdan olingan)
INIT_SPECS = {
    'TTS 20 Pro': [
        ('Quvvat','20W (22W peak)'),('Lazer turi','Diod 450nm'),
        ('Ishchi maydon','418 × 418 mm'),('Lazer dog\'i','0.13 × 0.145 mm'),
        ('Maks tezlik','30,000 mm/min'),('Aniqlik','0.01 mm'),
        ('Kontroller','32-bit ESP32 Pro V2.1'),
        ('Ulanish','WiFi + USB'),('Dastur','LightBurn, LaserGRBL'),
        ('Materiallar','Yog\'och, akrilik, teri, metall, bambu, tosh'),
        ('Og\'irlik','3.2 kg'),('O\'lcham','695×595×125 mm'),
        ('Kuchlanish','110-240V'),('Kafolat','3 oy'),
    ],
    'TTS 10 Pro': [
        ('Quvvat','10W'),('Lazer turi','Diod 450nm'),
        ('Ishchi maydon','418 × 418 mm'),('Lazer dog\'i','0.15 × 0.16 mm'),
        ('Maks tezlik','30,000 mm/min'),('Aniqlik','0.01 mm'),
        ('Kontroller','32-bit ESP32 Pro V2.1'),
        ('Ulanish','WiFi + USB'),('Dastur','LightBurn, LaserGRBL'),
        ('Materiallar','Yog\'och, akrilik, teri, shisha, metall bo\'yash'),
        ('Og\'irlik','3.0 kg'),('O\'lcham','695×595×125 mm'),
        ('Kuchlanish','110-240V'),('Kafolat','3 oy'),
    ],
    'TTS 55 Pro': [
        ('Quvvat','5.5W'),('Lazer turi','Diod 450nm'),
        ('Ishchi maydon','418 × 418 mm'),('Maks tezlik','30,000 mm/min'),
        ('Aniqlik','0.01 mm'),('Kontroller','32-bit ESP32 Pro V2.1'),
        ('Ulanish','WiFi + USB'),('Dastur','LightBurn, LaserGRBL'),
        ('Materiallar','Yog\'och, qog\'oz, teri, plastik, bambu'),
        ('Og\'irlik','2.8 kg'),('Kuchlanish','110-240V'),('Kafolat','3 oy'),
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
    return sqlite3.connect(DB_PATH)

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

    conn.commit(); conn.close()
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

def find_product(q):
    prods = get_products(); ql = q.lower().strip()
    for p in prods:
        if p['name'].lower() == ql: return p
    for p in prods:
        if ql in p['name'].lower() or p['name'].lower() in ql: return p
    words = [w for w in ql.split() if len(w) > 2]
    for p in prods:
        if any(w in p['name'].lower() for w in words): return p
    return None

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
        conn.commit(); conn.close()
        log_op('add_product', {'name':name,'cat':cat,'qty':qty,'cost':cost,'price':price})
        return pid
    except: conn.close(); return None

def update_product(pid, **kwargs):
    conn = db(); c = conn.cursor()
    for k, v in kwargs.items():
        if k in ('name','cat','supplier','qty','cost','price','factory_price','warranty_days','active'):
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

def save_sale(pid, pname, qty, price, cost, discount=0, customer='', ctype='B2C'):
    profit = (price - cost) * qty
    now = datetime.now()
    conn = db(); c = conn.cursor()
    c.execute('INSERT INTO sales (date,time,product,qty,unit_cost,revenue,profit,discount,customer,customer_type) VALUES (?,?,?,?,?,?,?,?,?,?)',
              (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'),
               pname, qty, cost, price*qty, profit, discount, customer, ctype))
    sale_id = c.lastrowid
    c.execute('UPDATE products SET qty=qty-? WHERE id=? AND qty>=?', (qty, pid, qty))
    ok = c.rowcount > 0
    if ok:
        # Kafolat
        p = get_products()
        prod = next((x for x in p if x['id']==pid), None)
        if prod and prod['warranty'] > 0:
            start = now.strftime('%Y-%m-%d')
            end = (now + timedelta(days=prod['warranty'])).strftime('%Y-%m-%d')
            c.execute('INSERT INTO warranties (sale_id,product,customer,start_date,end_date) VALUES (?,?,?,?,?)',
                      (sale_id, pname, customer, start, end))
        # Mijoz yangilash
        if customer:
            c.execute('SELECT id FROM customers WHERE name LIKE ?', (f'%{customer}%',))
            row = c.fetchone()
            if row:
                c.execute('UPDATE customers SET total_purchases=total_purchases+?, last_purchase=? WHERE id=?',
                          (price*qty, now.strftime('%Y-%m-%d'), row[0]))
    conn.commit(); conn.close()
    if ok: log_op('sale', {'sale_id':sale_id,'product':pname,'qty':qty,'price':price,'profit':profit})
    return ok, sale_id

def reverse_sale(sale_id):
    conn = db(); c = conn.cursor()
    c.execute('SELECT * FROM sales WHERE id=? AND reversed=0', (sale_id,))
    row = c.fetchone()
    if not row: conn.close(); return False
    product, qty, cost = row[3], row[4], row[5]
    c.execute('UPDATE sales SET reversed=1 WHERE id=?', (sale_id,))
    c.execute('UPDATE products SET qty=qty+? WHERE name=?', (qty, product))
    c.execute("UPDATE warranties SET status='cancelled' WHERE sale_id=?", (sale_id,))
    conn.commit(); conn.close()
    return True

def add_expense(amount, category, expense_type='period', note=''):
    now = datetime.now()
    conn = db(); c = conn.cursor()
    c.execute('INSERT INTO expenses (date,amount,category,expense_type,note) VALUES (?,?,?,?,?)',
              (now.strftime('%Y-%m-%d'), amount, category, expense_type, note))
    eid = c.lastrowid
    conn.commit(); conn.close()
    log_op('expense', {'id':eid,'amount':amount,'type':expense_type,'note':note})
    return eid

def add_transit(supplier, product, qty, unit_cost, deposit=0, bank_fee=0, delivery_fee=0, note=''):
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
    conn.commit(); conn.close()
    log_op('transit', {'id':tid,'supplier':supplier,'product':product,'qty':qty,'total':total,'deposit':deposit})
    return tid

def arrive_transit(tid):
    conn = db(); c = conn.cursor()
    c.execute('SELECT * FROM transit WHERE id=? AND status=?', (tid, 'yolda'))
    row = c.fetchone()
    if not row: conn.close(); return None
    product, qty, real_cost = row[3], row[4], row[10]
    now = datetime.now().strftime('%Y-%m-%d')
    c.execute("UPDATE transit SET status='keldi', arrived_date=? WHERE id=?", (now, tid))
    c.execute('SELECT id FROM products WHERE name LIKE ?', (f'%{product}%',))
    pid_row = c.fetchone()
    if pid_row:
        c.execute('UPDATE products SET qty=qty+?, cost=? WHERE id=?',
                  (qty, real_cost, pid_row[0]))
    conn.commit(); conn.close()
    return {'product': product, 'qty': qty, 'real_cost': real_cost}

def pay_transit_deposit(tid, amount):
    conn = db(); c = conn.cursor()
    c.execute('UPDATE transit SET deposit=deposit+?, remaining=MAX(0,remaining-?) WHERE id=?',
              (amount, amount, tid))
    conn.commit(); conn.close()

def add_customer(name, phone='', ctype='B2C', notes=''):
    conn = db(); c = conn.cursor()
    c.execute('SELECT id FROM customers WHERE name LIKE ?', (f'%{name}%',))
    if c.fetchone(): conn.close(); return False
    now = datetime.now().strftime('%Y-%m-%d')
    c.execute('INSERT INTO customers (name,phone,type,notes,created) VALUES (?,?,?,?,?)',
              (name, phone, ctype, notes, now))
    conn.commit(); conn.close()
    return True

def add_debt(person, amount, dtype, note=''):
    now = datetime.now()
    conn = db(); c = conn.cursor()
    c.execute('INSERT INTO debts (date,person,amount,type,note) VALUES (?,?,?,?,?)',
              (now.strftime('%Y-%m-%d'), person, amount, dtype, note))
    conn.commit(); conn.close()

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

def get_exchange_rate():
    conn = db(); c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('SELECT usd_uzs FROM exchange_rates WHERE date=?', (today,))
    row = c.fetchone()
    conn.close()
    if row: return row[0]
    try:
        r = requests.get('https://cbu.uz/uz/arkhiv-kursov-valyut/json/', timeout=5)
        data = r.json()
        for item in data:
            if item.get('Ccy') == 'USD':
                rate = float(item['Rate'])
                conn2 = db(); c2 = conn2.cursor()
                c2.execute('INSERT OR REPLACE INTO exchange_rates (date,usd_uzs) VALUES (?,?)',
                           (today, rate))
                conn2.commit(); conn2.close()
                return rate
    except: pass
    return 12500.0  # fallback

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

def add_qty(pid, delta):
    conn = db(); c = conn.cursor()
    c.execute('UPDATE products SET qty=MAX(0,qty+?) WHERE id=?', (delta, pid))
    conn.commit(); conn.close()


# ── ABC/XYZ TAHLIL (IAS 2 + CV formula) ──────────────────────────
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
    months = [(datetime.now()-timedelta(days=30*i)).strftime('%Y-%m') for i in range(7,-1,-1)]

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
def is_owner(u): return u.effective_user.id == OWNER_ID

def cash_flow_forecast():
    """30 kunlik cash flow prognozi"""
    prods = get_products()
    conn = db(); c = conn.cursor()
    # O'rtacha oylik sotuv (oxirgi 3 oy)
    months = [(datetime.now()-timedelta(days=30*i)).strftime('%Y-%m') for i in range(3)]
    monthly_revs = []
    for m in months:
        c.execute('SELECT COALESCE(SUM(revenue),0) FROM sales WHERE date LIKE ? AND reversed=0', (m+'%',))
        monthly_revs.append(c.fetchone()[0])
    avg_monthly = sum(monthly_revs) / 3 if monthly_revs else 0

    # Yo'ldagi tovar xarajatlari
    c.execute("SELECT SUM(remaining) FROM transit WHERE status='yolda'")
    transit_remaining = c.fetchone()[0] or 0

    # Qarzlar
    c.execute("SELECT SUM(amount) FROM debts WHERE type='berildi' AND paid=0")
    debt_out = c.fetchone()[0] or 0
    c.execute("SELECT SUM(amount) FROM debts WHERE type='olindi' AND paid=0")
    debt_in = c.fetchone()[0] or 0

    conn.close()
    return {
        'avg_monthly_revenue': avg_monthly,
        'expected_30day': avg_monthly,
        'transit_to_pay': transit_remaining,
        'debts_to_receive': debt_in,
        'debts_to_pay': debt_out,
        'net_forecast': avg_monthly + debt_in - transit_remaining - debt_out
    }

def get_sales_trend():
    """Oxirgi 3 oy trendi"""
    months = []
    for i in range(2, -1, -1):
        m = (datetime.now()-timedelta(days=30*i)).strftime('%Y-%m')
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
Sotish: {{"action":"sell","product":"nom","qty":1,"price":260,"discount":0,"customer":"","type":"B2C"}}
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
Qarz berdi: {{"action":"debt","person":"ism","amount":100,"type":"olindi"}}
Qarz oldim: {{"action":"debt","person":"ism","amount":100,"type":"berildi"}}
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
- "sotdim/ketdi/sotildi" = sell
- "keldi/qoshildi/kirdi" = add
- "xarajat/sarf berdim" = expense (type=period)
- "bank tolov" = expense (type=cogs_bank)
- "dostavka/yolkira" = expense (type=cogs_delivery)
- "zakaz berdim/yo'lga tushdi" = transit_add
- "qarz oldi" = debt (type=olindi — biz berdik)
- "qarz berdim" = debt (type=berildi — bizdan oldi)
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
    "💳 Qarzlar": "debts",
    "💸 Xarajatlar": "expenses",
    "🎯 Maqsad": "target",
    "🔧 Kafolat": "warranties",
    "📈 Trend": "trend",
    "💵 Cash Flow": "cashflow",
    "📢 OLX": "olx",
    "➕ Yangi tovar": "new_product",
    "↩️ Qayt etish": "undo_list",
}

async def cmd_start(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
    rate = get_exchange_rate()
    kb = ReplyKeyboardMarkup([
        ["📦 Astatka",    "💰 Bugun"],
        ["📈 Oylik",      "📅 Yillik"],
        ["🚚 Yo'lda",    "💳 Zavod qarzi"],
        ["💵 Narxlar",    "📊 Analiz"],
        ["👥 Mijozlar",   "💳 Qarzlar"],
        ["💸 Xarajatlar", "🎯 Maqsad"],
        ["🔧 Kafolat",    "📈 Trend"],
        ["💵 Cash Flow",  "📢 OLX"],
        ["➕ Yangi tovar","↩️ Qayt etish"],
    ], resize_keyboard=True, is_persistent=True)
    await u.message.reply_text(
        f"🏭 ThermoCrafts Bot v3.0\n💱 1 USD = {rate:,.0f} so'm",
        reply_markup=kb)


async def cmd_astatka(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
    prods = get_products()
    rate = get_exchange_rate()
    text = f"📦 *ASTATKA* — {now_t()}\n\n"
    for cat in ['Lazer', 'CNC', 'Press', "Qog'oz"]:
        ps = [p for p in prods if p['cat'] == cat]
        if ps:
            text += f"*{cat}:*\n"
            for p in ps:
                e = "🔴" if p['qty']==0 else "🟡" if p['qty']<=1 else "🟢"
                uzs = fmtuzs(p['price'], rate)
                text += f"{e} {p['name']}: *{p['qty']} ta* · {fmt(p['price'])} ({uzs})\n"
            text += "\n"
    tc = sum(p['qty']*p['cost'] for p in prods)
    tp = sum(p['qty']*p['price'] for p in prods)
    out = [p['name'] for p in prods if p['qty']==0]
    text += f"💰 Sebest: *{fmt(tc)}* | Narxda: *{fmt(tp)}*"
    if out: text += f"\n⚠️ *Tugagan:* {', '.join(out)}"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_narxlar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
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
    avg_margin = sum((p['price']-p['cost'])/p['price']*100 for p in prods if p['price']>0) / len(prods)
    text += f"📊 O'rtacha marja: *{avg_margin:.0f}%*"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_bugun(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
    sales = get_sales(today())
    exps_cogs = get_expenses(today(), 'cogs_bank') + get_expenses(today(), 'cogs_delivery')
    exps_period = get_expenses(today(), 'period')
    label = datetime.now().strftime('%d.%m.%Y')
    if not sales and not exps_cogs and not exps_period:
        await u.message.reply_text(f"📊 *{label}*\n\nBugun hali hech narsa yo'q.", parse_mode='Markdown')
        return
    tR = sum(s[6] for s in sales)
    tCOGS = sum(s[5]*s[4] for s in sales)  # unit_cost * qty
    tF = sum(s[7] for s in sales)
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
    if not is_owner(u): return
    if not month: month = this_month()
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
        text += f"\n🎯 *Maqsad:*\n"
        text += f"Tushum: {rpct:.0f}% ({fmt(tR)}/{fmt(tgt[0])})\n"
        text += f"Foyda: {ppct:.0f}% ({fmt(sof)}/{fmt(tgt[1])})"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_yil(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
    year = datetime.now().strftime('%Y')
    HIST = [
        ('Yanvar','2026-01',1987,429),('Fevral','2026-02',2680,540),
        ('Mart','2026-03',2185,871),('Aprel','2026-04',3190,820),
        ('May','2026-05',1515,799),('Iyun','2026-06',1500,257),
        ('Iyul','2026-07',525,97),('Avgust','2026-08',1993,637),
    ]
    conn = db(); c = conn.cursor()
    text = f"📅 *YILLIK HISOBOT — {year}*\n\n"
    text += "```\n"
    text += f"{'Oy':<10} {'Tushum':>8} {'Foyda':>8}\n"
    text += "─" * 28 + "\n"
    total_r, total_f = 0, 0
    for name, month, rev, profit in HIST:
        text += f"{name:<10} {fmt(rev):>8} {fmt(profit):>8}\n"
        total_r += rev; total_f += profit
    # Joriy oy
    current_sales = get_sales(this_month())
    cur_r = sum(s[6] for s in current_sales)
    cur_f = sum(s[7] for s in current_sales)
    cur_name = datetime.now().strftime('%B')
    text += f"{cur_name:<10} {fmt(cur_r):>8} {fmt(cur_f):>8}\n"
    total_r += cur_r; total_f += cur_f
    text += "─" * 28 + "\n"
    text += f"{'JAMI':<10} {fmt(total_r):>8} {fmt(total_f):>8}\n"
    text += "```\n"
    text += f"\n📊 O'rtacha oylik: {fmt(total_r//9)} tushum | {fmt(total_f//9)} foyda"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_yolda(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
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
    if not is_owner(u): return
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
        text += f"  ──────────────\n"
        text += f"  💸 Qolgan qarz: *{fmt(r[3])}*\n\n"
        total_remaining += r[3]
    text += f"💸 *JAMI ZAVOD QARZI: {fmt(total_remaining)}*"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_analiz(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
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
    if not is_owner(u): return
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
    if not is_owner(u): return
    conn = db(); c = conn.cursor()
    c.execute("SELECT * FROM debts WHERE paid=0 ORDER BY id DESC")
    rows = c.fetchall(); conn.close()
    if not rows:
        await u.message.reply_text("💳 *Qarzlar*\n\nQarz yo'q ✅", parse_mode='Markdown')
        return
    text = "💳 *QARZLAR*\n\n"
    olindi = [r for r in rows if r[4]=='olindi']
    berildi = [r for r in rows if r[4]=='berildi']
    if olindi:
        text += "*💸 Biz berganimiz (bizda qarz):*\n"
        for r in olindi:
            text += f"• {r[3]}: *{fmt(r[2])}* — {r[1]}\n"
        text += f"Jami: *{fmt(sum(r[2] for r in olindi))}*\n\n"
    if berildi:
        text += "*💰 Bizdan olganlar:*\n"
        for r in berildi:
            text += f"• {r[3]}: *{fmt(r[2])}* — {r[1]}\n"
        text += f"Jami: *{fmt(sum(r[2] for r in berildi))}*\n"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_xarajatlar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
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
    if not is_owner(u): return
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
        else: text += f" (tugagan!)"
        text += "\n\n"
    if expiring:
        text += f"⚠️ {len(expiring)} ta kafolat yaqin tugaydi!"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_cashflow(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
    cf = cash_flow_forecast()
    text = "💵 *CASH FLOW PROGNOZ (30 kun)*\n\n"
    text += f"📈 Kutilayotgan tushum: *{fmt(cf['expected_30day'])}*\n"
    text += f"💳 Yo'ldagi tovar to'lovi: −{fmt(cf['transit_to_pay'])}\n"
    text += f"💰 Qarz qaytishi: +{fmt(cf['debts_to_receive'])}\n"
    text += f"💸 Qarz to'lash: −{fmt(cf['debts_to_pay'])}\n"
    text += f"──────────────────────\n"
    net = cf['net_forecast']
    emoji = "✅" if net > 0 else "❌"
    text += f"{emoji} *Prognoz qoldi: {fmt(net)}*\n\n"
    text += f"_O'rtacha oylik tushum: {fmt(cf['avg_monthly_revenue'])}_"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_trend(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
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
    if not is_owner(u): return
    rate = get_exchange_rate()
    prods = get_products()
    text = f"💱 *VALYUTA KURSI*\n\n"
    text += f"1 USD = *{rate:,.0f} so'm* (CBU)\n\n"
    text += "*Asosiy tovarlar UZS da:*\n"
    for p in prods[:5]:
        text += f"• {p['name']}: *{p['price']*rate:,.0f} so'm*\n"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_maqsad(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
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
        r_bar = "█" * int(rpct/10) + "░" * (10-int(min(rpct,100)/10))
        p_bar = "█" * int(ppct/10) + "░" * (10-int(min(ppct,100)/10))
        text += f"💵 Tushum: {rpct:.0f}%\n`{r_bar}` {fmt(tR)}/{fmt(tgt[3])}\n\n"
        text += f"✅ Foyda: {ppct:.0f}%\n`{p_bar}` {fmt(sof)}/{fmt(tgt[4])}\n\n"
        days = (datetime(now.year, now.month+1 if now.month<12 else 1, 1) - now).days
        need_daily = (tgt[3]-tR)/days if days>0 and tgt[3]>tR else 0
        text += f"⏰ {days} kun qoldi | Kuniga: *{fmt(need_daily)}* kerak"
    else:
        text += f"Hozir:\nTushum: *{fmt(tR)}*\nFoyda: *{fmt(sof)}*\n\n"
        text += "_Maqsad qo'yish: '3000 dollar maqsad' deb yozing_"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_olx(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
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
    if not is_owner(u): return
    conn = db(); c = conn.cursor()
    c.execute("SELECT * FROM competitors ORDER BY date DESC LIMIT 20")
    rows = c.fetchall(); conn.close()
    if not rows:
        await u.message.reply_text("🔍 *Raqobatchilar*\n\nMa'lumot yo'q.", parse_mode='Markdown')
        return
    text = "🔍 *RAQOBATCHI NARXLAR*\n\n"
    by_prod = defaultdict(list)
    for r in rows: by_prod[r[3]].append(r)
    for prod, comps in by_prod.items():
        our = find_product(prod)
        our_p = our['price'] if our else 0
        text += f"*{prod}:*\n"
        for r in comps[:3]:
            diff = our_p - r[4]
            emoji = "✅" if diff >= 0 else "❌"
            text += f"  {emoji} {r[2]}: {fmt(r[4])} (biz: {fmt(our_p)}, farq: {fmt(diff)})\n"
        text += "\n"
    await u.message.reply_text(text, parse_mode='Markdown')

async def cmd_undo_list(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
    ops = get_last_ops(8)
    if not ops:
        await u.message.reply_text("↩️ Qaytarish uchun operatsiya yo'q.", parse_mode='Markdown')
        return
    text = "↩️ *OXIRGI OPERATSIYALAR*\n\n"
    kb = []
    for op in ops:
        data = json.loads(op[4])
        label = f"#{op[0]} {op[2]}: "
        if op[2] == 'sale': label += f"{data.get('product','')} {fmt(data.get('revenue',0))}"
        elif op[2] == 'expense': label += f"{data.get('note','')} {fmt(data.get('amount',0))}"
        elif op[2] == 'transit': label += f"{data.get('product','')} {fmt(data.get('total',0))}"
        else: label += str(data)[:30]
        text += f"{label}\n"
        kb.append([InlineKeyboardButton(f"↩️ #{op[0]} qayt", callback_data=f"undo_{op[0]}")])
    kb.append([InlineKeyboardButton("❌ Yopish", callback_data='close')])
    await u.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def cmd_katalog(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
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
    text += f"💵 Narx: *{fmt(prod['price'])}* | ✅ Marja: {fmt(margin)} ({margin/prod['price']*100:.0f}%)\n"
    text += f"📦 Astatka: {prod['qty']} ta"
    kb = [[InlineKeyboardButton("📸 Rasm qo'sh", callback_data=f"add_photo_{prod['id']}"),
           InlineKeyboardButton("✏️ Specs tahrirlash", callback_data=f"edit_specs_{prod['id']}")]]
    await u.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def cmd_yordam(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
    text = (
        "📋 *Buyruqlar:*\n"
        "/astatka /narxlar /bugun /oy /yil\n"
        "/yolda /zavod_qarz /analiz /xarajatlar\n"
        "/mijozlar /qarzlar /kafolat /cashflow\n"
        "/trend /rate /maqsad /olx /undo\n"
        "/katalog [nom] /yangi_tovar\n\n"
        "*Erkin yozish:*\n\n"
        "💰 *Sotuv:*\n`TTS 20 Pro sotdim 470 ga`\n"
        "`Ahmadga 10% chegirma bilan P8100 ketdi`\n\n"
        "🚚 *Yo'lda:*\n`Two Trees ga TTS 20 Pro 3 ta zakaz berdim 280 dan, 200 deposit`\n"
        "`Zakaz #1 keldi`\n`Two Trees ga 300 dollar to'ladim`\n\n"
        "💸 *Xarajat:*\n`Bank to'lovi 45 dollar`\n"
        "`Abusaxiy dostavka 110 dollar`\n`OLX reklama 33 dollar`\n\n"
        "👥 *Mijoz:*\n`Jahongir B2B mijoz qo'sh 998901234567`\n\n"
        "💳 *Qarz:*\n`Alibek 200 dollar qarz oldi`\n\n"
        "🎯 *Maqsad:*\n`Bu oy 3000 dollar maqsad 800 foyda`\n\n"
        "📊 *Tahlil:*\n`ABC XYZ tahlil` | `Trend` | `Cash flow`\n"
        "`TTS 20 Pro katalog` | `apexmach TTS 20 490 raqobatchi`\n"
        "`OLX TTS 20 yangilandi 2 qongiroq`"
    )
    await u.message.reply_text(text, parse_mode='Markdown')


# ── YANGI TOVAR QOSHISH (ConversationHandler) ─────────────────────
async def conv_start(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return ConversationHandler.END
    ctx.user_data.clear()
    await u.message.reply_text(
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
    except: await u.message.reply_text("Raqam kiriting:"); return S_COST
    await u.message.reply_text("Sotuv narxi ($):")
    return S_PRICE

async def conv_price(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try: ctx.user_data['price'] = float(u.message.text.replace('$','').strip())
    except: await u.message.reply_text("Raqam kiriting:"); return S_PRICE
    ctx.user_data['cost'] = ctx.user_data['factory']
    await u.message.reply_text("Boshlang'ich miqdor (dona):")
    return S_QTY

async def conv_qty(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try: ctx.user_data['qty'] = int(u.message.text.strip())
    except: await u.message.reply_text("Raqam kiriting:"); return S_QTY
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
async def on_callback(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    data = q.data
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
    elif data == 'customers': await fake_cmd(cmd_mijozlar)
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
        op_id = int(data.split('_')[1])
        conn = db(); c = conn.cursor()
        c.execute('SELECT * FROM op_log WHERE id=? AND reversed=0', (op_id,))
        op = c.fetchone()
        if not op: await msg.reply_text("❌ Topilmadi yoki allaqachon qaytarilgan"); conn.close(); return
        op_data = json.loads(op[4])
        ok = False
        if op[3] == 'sale':
            ok = reverse_sale(op_data.get('sale_id', 0))
        elif op[3] == 'expense':
            conn2 = db(); c2 = conn2.cursor()
            c2.execute('UPDATE expenses SET reversed=1 WHERE id=?', (op_data.get('id',0),))
            ok = c2.rowcount > 0
            conn2.commit(); conn2.close()
        if ok:
            c.execute('UPDATE op_log SET reversed=1 WHERE id=?', (op_id,))
            conn.commit()
            await msg.reply_text(f"✅ Operatsiya #{op_id} qaytarildi!")
        else:
            await msg.reply_text("❌ Qaytarib bo'lmadi!")
        conn.close()
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
                f"Haqiqiy sebest: {fmt(result['real_cost'])}/ta\nAstatka yangilandi!",
                parse_mode='Markdown')
        else:
            await msg.reply_text("❌ Topilmadi yoki allaqachon kelgan!")
    elif data.startswith('cat_') or data.startswith('sup_') or data.startswith('photos_'):
        pass  # ConversationHandler handles these

# ── TEXT MESSAGE HANDLER ──────────────────────────────────────────
async def handle_text(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
    msg = u.message.text
    prods = get_products()

    # Foto qo'shish rejimi
    if ctx.user_data.get('photo_product_id'):
        return

    # Menyu tugmalari
    if msg in MENU_MAP:
        action = MENU_MAP[msg]
        class FakeUpd:
            effective_user = u.effective_user
            message = u.message
            callback_query = None
        fake = FakeUpd()
        if action == 'stock': await cmd_astatka(fake, ctx)
        elif action == 'today': await cmd_bugun(fake, ctx)
        elif action == 'month': await cmd_oy(fake, ctx)
        elif action == 'year': await cmd_yil(fake, ctx)
        elif action == 'transit': await cmd_yolda(fake, ctx)
        elif action == 'supplier_debt': await cmd_zavod_qarz(fake, ctx)
        elif action == 'prices': await cmd_narxlar(fake, ctx)
        elif action == 'analiz': await cmd_analiz(fake, ctx)
        elif action == 'customers': await cmd_mijozlar(fake, ctx)
        elif action == 'debts': await cmd_qarzlar(fake, ctx)
        elif action == 'expenses': await cmd_xarajatlar(fake, ctx)
        elif action == 'target': await cmd_maqsad(fake, ctx)
        elif action == 'warranties': await cmd_kafolat(fake, ctx)
        elif action == 'trend': await cmd_trend(fake, ctx)
        elif action == 'cashflow': await cmd_cashflow(fake, ctx)
        elif action == 'olx': await cmd_olx(fake, ctx)
        elif action == 'new_product': await conv_start(fake, ctx)
        elif action == 'undo_list': await cmd_undo_list(fake, ctx)
        return

    # Oy buyrug'i: /oy 2026-07
    if msg.startswith('/oy '):
        month = msg.split(' ')[1].strip()
        await cmd_oy(u, ctx, month=month)
        return

    await u.message.chat.send_action('typing')
    parsed = ai_parse(msg, prods)
    action = parsed.get('action', 'unknown')
    log.info(f"Action: {action} | {parsed}")

    if action == 'sell':
        prod = find_product(parsed.get('product',''))
        qty = max(1, int(parsed.get('qty', 1)))
        price = float(parsed.get('price', 0))
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
            disc_txt = f"\n🏷️ Chegirma: {discount}%" if discount else ""
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
    elif action == 'customers': await cmd_mijozlar(u, ctx)
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
            eid = add_expense(amount, cat, etype, note)
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
        tid = add_transit(supplier, product, qty, unit_cost, deposit, bank_fee, delivery_fee)
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
                    f"📊 Sebest: {fmt(result['real_cost'])}/ta\n✅ Astatka yangilandi!",
                    parse_mode='Markdown')
            else:
                await u.message.reply_text("❌ Topilmadi!")
        else:
            await u.message.reply_text("Zakaz ID ni yozing: 'Zakaz #3 keldi'")

    elif action == 'transit_pay':
        tid = int(parsed.get('id', 0))
        amount = float(parsed.get('amount', 0))
        if tid and amount > 0:
            pay_transit_deposit(tid, amount)
            await u.message.reply_text(
                f"✅ *To'lov qayd!*\nZakaz #{tid}: +{fmt(amount)} to'landi",
                parse_mode='Markdown')
        else:
            await u.message.reply_text("❌ Zakaz ID va summa kiriting")

    elif action == 'transit_list': await cmd_yolda(u, ctx)
    elif action == 'supplier_debt': await cmd_zavod_qarz(u, ctx)

    elif action == 'add_customer':
        name = parsed.get('name', '')
        phone = parsed.get('phone', '')
        ctype = parsed.get('ctype', 'B2C')
        if name:
            ok = add_customer(name, phone, ctype)
            if ok:
                await u.message.reply_text(f"👤 *{name} ({ctype}) qo'shildi!*", parse_mode='Markdown')
            else:
                await u.message.reply_text(f"ℹ️ {name} allaqachon bor")
        else:
            await u.message.reply_text("❌ Ism kiriting")

    elif action == 'debt':
        person = parsed.get('person', '')
        amount = float(parsed.get('amount', 0))
        dtype = parsed.get('type', 'olindi')
        note = parsed.get('note', '')
        if person and amount > 0:
            add_debt(person, amount, dtype, note)
            emoji = "💸" if dtype=='olindi' else "💰"
            txt = "oldi (biz berdik)" if dtype=='olindi' else "berdi (bizda bor)"
            await u.message.reply_text(
                f"{emoji} *Qarz qayd!*\n👤 {person}: {fmt(amount)} {txt}",
                parse_mode='Markdown')

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

    else:
        reply = parsed.get('reply', "Tushunmadim 🤔\n/yordam buyrug'ini ko'ring")
        await u.message.reply_text(reply)

# Foto qabul qilish (astatka qo'shish vaqtida)
async def handle_photo(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
    pid = ctx.user_data.get('photo_product_id')
    if pid and u.message.photo:
        file_id = u.message.photo[-1].file_id
        add_photo(pid, file_id)
        count = len(get_product_photos(pid))
        await u.message.reply_text(f"✅ Rasm {count} qo'shildi. Davom eting yoki /tayyor")

async def handle_photo_done(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(u): return
    pid = ctx.user_data.pop('photo_product_id', None)
    if pid:
        count = len(get_product_photos(pid))
        await u.message.reply_text(f"✅ Jami {count} ta rasm saqlandi!")
    else:
        await conv_finish(u, ctx)



# ── SELF-UPDATE (GitHub API) ──────────────────────────────────────
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
GITHUB_REPO  = 'ilyosbekdot/thermocraft-bot'
BOT_FILENAME = 'bot-3.py'

async def cmd_update(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Bot o'zini yangilaydi — /update <raw_url>"""
    if not is_owner(u): return
    if not GITHUB_TOKEN:
        await u.message.reply_text("❌ GITHUB_TOKEN Railway da sozlanmagan!"); return
    args = ctx.args
    if not args:
        await u.message.reply_text(
            "📌 *Bot yangilash*\n\nFormat:\n`/update <raw_url>`\n\n"
            "Men yangi kod yozganda raw URL beraman!", parse_mode='Markdown'); return

    raw_url = args[0]
    await u.message.reply_text("⏳ Yangilanmoqda...")

    try:
        # 1. Yangi kodni yuklab olish
        r = requests.get(raw_url, timeout=15)
        if r.status_code != 200:
            await u.message.reply_text(f"❌ URL topilmadi: {r.status_code}"); return
        new_code = r.text
        if len(new_code) < 100:
            await u.message.reply_text("❌ Kod juda qisqa, xato URL?"); return

        # 2. Hozirgi fayl SHA ni olish
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{BOT_FILENAME}"
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        r2 = requests.get(api_url, headers=headers, timeout=10)
        if r2.status_code != 200:
            await u.message.reply_text(f"❌ GitHub API xato: {r2.status_code}"); return
        sha = r2.json().get('sha', '')

        # 3. Faylni yangilash (GitHub API PUT)
        content_b64 = base64.b64encode(new_code.encode('utf-8')).decode('utf-8')
        payload = {
            "message": f"Bot auto-update by owner",
            "content": content_b64,
            "sha": sha
        }
        r3 = requests.put(api_url, json=payload, headers=headers, timeout=30)

        if r3.status_code in (200, 201):
            await u.message.reply_text(
                "✅ *Bot yangilandi!*\n\n"
                "📦 GitHub ga commit qilindi\n"
                "🚀 Railway qayta deploy qilmoqda...\n"
                "⏳ 1-2 daqiqada yangi bot ishlaydi!",
                parse_mode='Markdown')
        else:
            err = r3.json().get('message', r3.text[:200])
            await u.message.reply_text(f"❌ GitHub xato: {err}")

    except requests.Timeout:
        await u.message.reply_text("❌ Timeout — internet muammosi?")
    except Exception as e:
        await u.message.reply_text(f"❌ Xato: {str(e)[:200]}")

# ── MAIN ──────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN: raise ValueError("BOT_TOKEN yo'q!")
    if not ANTHROPIC_KEY: raise ValueError("ANTHROPIC_KEY yo'q!")
    if OWNER_ID == 0: raise ValueError("OWNER_ID yo'q!")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Yangi tovar qo'shish (ConversationHandler)
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('yangi_tovar', conv_start),
            CallbackQueryHandler(conv_start, pattern='^new_product$'),
        ],
        states={
            S_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, conv_name)],
            S_CAT: [CallbackQueryHandler(conv_cat_cb, pattern='^cat_')],
            S_SUP: [CallbackQueryHandler(conv_sup_cb, pattern='^sup_')],
            S_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, conv_cost)],
            S_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, conv_price)],
            S_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, conv_qty)],
            S_SPECS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, conv_specs),
                CommandHandler('tayyor', conv_specs_done),
            ],
            S_PHOTOS: [
                CallbackQueryHandler(conv_photos_cb, pattern='^photos_'),
                MessageHandler(filters.PHOTO, conv_photo),
                CommandHandler('tayyor', conv_finish),
            ],
        },
        fallbacks=[CommandHandler('bekor', conv_cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('start', cmd_start))
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
    app.add_handler(CommandHandler('mijozlar', cmd_mijozlar))
    app.add_handler(CommandHandler('qarzlar', cmd_qarzlar))
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
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("ThermoCrafts Bot v3.0 ishga tushdi! ✅")
    log.info(f"21 modul | {len(get_products())} mahsulot")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
