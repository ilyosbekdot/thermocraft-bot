#!/usr/bin/env python3
"""
ThermoCrafts Telegram Bot
Savdo va astatka boshqaruvi — Claude AI bilan
"""
import os, json, sqlite3, logging
from datetime import datetime
from collections import Counter
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
log = logging.getLogger(__name__)

# ── SOZLAMALAR ────────────────────────────────────────────────────
BOT_TOKEN    = os.getenv('BOT_TOKEN', '')
ANTHROPIC_KEY = os.getenv('ANTHROPIC_KEY', '')
OWNER_ID     = int(os.getenv('OWNER_ID', '0'))
DB_PATH      = 'thermocraft.db'

ai = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# ── BOSHLANG'ICH MAHSULOTLAR ──────────────────────────────────────
INIT_P = [
    (1,  'TTS 55 Pro',          'Lazer',  'Two Trees', 3, 130, 195),
    (2,  'TTS 10 Pro',          'Lazer',  'Two Trees', 2, 170, 260),
    (3,  'TTS 20 Pro',          'Lazer',  'Two Trees', 3, 300, 470),
    (4,  'Laser head 10W',      'Lazer',  'Two Trees', 2,  87, 120),
    (5,  'CNC3018 Pro',         'CNC',    'Two Trees', 5, 115, 182),
    (6,  '4th Axis Rotary',     'CNC',    'Two Trees', 1,  91, 180),
    (7,  '500W Spindle',        'CNC',    'Two Trees', 1,  91, 180),
    (8,  'Milling Cutter',      'CNC',    'Two Trees', 1,  65, 100),
    (9,  'Extension Kit 600x600','CNC',   'Two Trees', 1,  65, 110),
    (10, 'Honeycomb 400x400',   'CNC',    'Two Trees', 2,  23,  35),
    (11, 'Honeycomb 500x500',   'CNC',    'Two Trees', 1,  23,  70),
    (12, 'Rotary Blue',         'CNC',    'Two Trees', 2,  21,  47),
    (13, 'Air Assist Pump',     'CNC',    'Two Trees', 2,  41,  47),
    (14, '15 in 1 (SB400)',     'Press',  'Freesub',   2, 300, 355),
    (15, 'P8100 (11 in 1)',     'Press',  'Freesub',   2, 160, 332),
    (16, 'F1130 (2 in 1)',      'Press',  'Freesub',   2, 100, 187),
    (17, 'PD150',               'Press',  'Freesub',   1,  88, 140),
    (18, 'ST210 kepka',         'Press',  'Freesub',   1,  89, 190),
    (19, 'F270',                'Press',  'Freesub',   1,  85, 190),
    (20, "Hc12E qorong'i",      "Qog'oz", 'Freesub',   2,  53,  65),
    (21, "Hc12g-B och",         "Qog'oz", 'Freesub',   1,  15,  18),
]

# ── DATABASE ──────────────────────────────────────────────────────
def db():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY, name TEXT, cat TEXT,
        supplier TEXT, qty INTEGER, cost REAL, price REAL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, time TEXT, product TEXT,
        qty INTEGER, cost REAL, revenue REAL, profit REAL, note TEXT
    )''')
    c.execute('SELECT COUNT(*) FROM products')
    if c.fetchone()[0] == 0:
        c.executemany('INSERT INTO products VALUES (?,?,?,?,?,?,?)', INIT_P)
        log.info("Boshlang'ich mahsulotlar qo'shildi")
    conn.commit()
    conn.close()

def get_all_products():
    conn = db()
    c = conn.cursor()
    c.execute('SELECT id,name,cat,supplier,qty,cost,price FROM products ORDER BY cat,name')
    rows = c.fetchall()
    conn.close()
    return [{'id':r[0],'name':r[1],'cat':r[2],'sup':r[3],'qty':r[4],'cost':r[5],'price':r[6]} for r in rows]

def find_product(query):
    """Nomga yaqin mahsulotni topish"""
    products = get_all_products()
    q = query.lower().strip()
    # To'liq moslik
    for p in products:
        if p['name'].lower() == q: return p
    # Qisman moslik
    for p in products:
        if q in p['name'].lower() or p['name'].lower() in q: return p
    # So'z bo'yicha moslik
    words = [w for w in q.split() if len(w) > 2]
    for p in products:
        pn = p['name'].lower()
        if any(w in pn for w in words): return p
    return None

def save_sale(product_id, product_name, qty, price, cost):
    profit = (price - cost) * qty
    now = datetime.now()
    conn = db()
    c = conn.cursor()
    c.execute(
        'INSERT INTO sales (date,time,product,qty,cost,revenue,profit) VALUES (?,?,?,?,?,?,?)',
        (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'), product_name, qty, cost, price*qty, profit)
    )
    c.execute('UPDATE products SET qty = qty - ? WHERE id = ? AND qty >= ?', (qty, product_id, qty))
    ok = c.rowcount > 0
    conn.commit()
    conn.close()
    return ok

def add_qty(product_id, delta):
    conn = db()
    c = conn.cursor()
    c.execute('UPDATE products SET qty = MAX(0, qty + ?) WHERE id = ?', (delta, product_id))
    conn.commit()
    conn.close()

def update_product_price(product_id, new_price):
    conn = db()
    c = conn.cursor()
    c.execute('UPDATE products SET price = ? WHERE id = ?', (new_price, product_id))
    conn.commit()
    conn.close()

def get_sales_by_date(date_filter):
    conn = db()
    c = conn.cursor()
    c.execute('SELECT * FROM sales WHERE date LIKE ? ORDER BY id DESC', (date_filter+'%',))
    rows = c.fetchall()
    conn.close()
    return rows

# ── CLAUDE AI ─────────────────────────────────────────────────────
def ai_parse(user_msg, products):
    plist = '\n'.join([
        f"- {p['name']} | astatka:{p['qty']}ta | narx:${p['price']} | sebest:${p['cost']}"
        for p in products
    ])

    system = f"""Siz ThermoCrafts do'konining AI yordamchisisiz (Toshkent, O'zbekiston).
Foydalanuvchi xabarini tahlil qilib, FAQAT JSON qaytaring (boshqa matn yozmang).

MAVJUD MAHSULOTLAR:
{plist}

AMALLAR va FORMAT:

Sotish:
{{"action":"sell","product":"mahsulot nomi","qty":1,"price":260,"note":""}}

Astatka qo'shish (yangi tovar keldi):
{{"action":"add","product":"mahsulot nomi","qty":2}}

Astatka ko'rish:
{{"action":"stock","cat":"Barchasi"}}
(cat = Lazer | CNC | Press | Qog'oz | Barchasi)

Hisobot:
{{"action":"report","period":"today"}}
(period = today | month | week)

Narx ko'rish:
{{"action":"price","product":"mahsulot nomi"}}

Narx o'zgartirish:
{{"action":"set_price","product":"mahsulot nomi","price":280}}

Tushunarsiz:
{{"action":"unknown","reply":"Aniqroq yozing..."}}

QOIDALAR:
1. product maydonida MAVJUD MAHSULOTLAR ro'yxatidagi nomni yozing (eng yaqinini)
2. Narx ko'rsatilmagan bo'lsa price=0 qiling
3. O'zbek va rus tillarini tushuning
4. "sotdim", "ketdi", "oldi", "sotildi" = sell amali
5. "keldi", "qo'shildi", "kirdi", "oldim" = add amali"""

    try:
        resp = ai.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=250,
            system=system,
            messages=[{'role':'user','content':user_msg}]
        )
        raw = resp.content[0].text.strip()
        start, end = raw.find('{'), raw.rfind('}')+1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception as e:
        log.error(f'AI xatosi: {e}')
    return {'action':'unknown','reply':'Xizmat vaqtinchalik ishlamayapti'}

# ── HELPERS ───────────────────────────────────────────────────────
def is_owner(upd):
    return upd.effective_user.id == OWNER_ID

def now_str():
    return datetime.now().strftime('%d.%m.%Y %H:%M')

def fmt_money(n):
    return f"${n:,.0f}"

# ── HANDLERS ──────────────────────────────────────────────────────
async def cmd_start(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(upd): return
    msg = (
        "🏭 *ThermoCrafts Bot* — savdo boshqaruvi\n\n"
        "*Buyruqlar:*\n"
        "/astatka — barcha tovarlar holati\n"
        "/bugun — bugungi savdo\n"
        "/oy — oylik hisobot\n"
        "/yordam — yo'riqnoma\n\n"
        "*Erkin yozish (AI):*\n"
        "`TTS 10 Pro sotdim 260 ga`\n"
        "`2 ta CNC3018 keldi`\n"
        "`Lazer astatka qanday?`\n"
        "`Bugungi savdo`\n"
        "`TTS 20 narxi qancha?`\n\n"
        "Savdo muvaffaqiyatli bo'lsin! 💪"
    )
    await upd.message.reply_text(msg, parse_mode='Markdown')

async def cmd_astatka(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(upd): return
    prods = get_all_products()
    cats = ['Lazer','CNC','Press',"Qog'oz"]
    text = f"📦 *ASTATKA* — {now_str()}\n\n"
    for cat in cats:
        ps = [p for p in prods if p['cat']==cat]
        if ps:
            text += f"*— {cat} —*\n"
            for p in ps:
                e = "🔴" if p['qty']==0 else "🟡" if p['qty']<=1 else "🟢"
                text += f"{e} {p['name']}: *{p['qty']} ta* | ${p['price']}\n"
            text += "\n"
    total_c = sum(p['qty']*p['cost'] for p in prods)
    total_p = sum(p['qty']*p['price'] for p in prods)
    out = [p['name'] for p in prods if p['qty']==0]
    text += f"💰 Sebest: *{fmt_money(total_c)}*\n"
    text += f"💵 Narxda: *{fmt_money(total_p)}*\n"
    if out:
        text += f"\n⚠️ *Tugagan:* {', '.join(out)}"
    await upd.message.reply_text(text, parse_mode='Markdown')

async def cmd_bugun(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(upd): return
    today = datetime.now().strftime('%Y-%m-%d')
    sales = get_sales_by_date(today)
    label = datetime.now().strftime('%d.%m.%Y')
    if not sales:
        await upd.message.reply_text(f"📊 *{label}*\n\nBugun hali sotuv yo'q.", parse_mode='Markdown')
        return
    total_rev  = sum(s[6] for s in sales)
    total_prof = sum(s[7] for s in sales)
    text = f"📊 *Bugungi savdo — {label}*\n\n"
    for s in sales:
        unit = s[6]/s[4] if s[4] else s[6]
        text += f"• {s[3]}: {s[4]}ta × {fmt_money(unit)} = *{fmt_money(s[6])}* (+{fmt_money(s[7])})\n"
    text += f"\n💵 Jami tushum: *{fmt_money(total_rev)}*"
    text += f"\n✅ Foyda: *{fmt_money(total_prof)}*"
    await upd.message.reply_text(text, parse_mode='Markdown')

async def cmd_oy(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(upd): return
    month = datetime.now().strftime('%Y-%m')
    sales = get_sales_by_date(month)
    label = datetime.now().strftime('%B %Y')
    if not sales:
        await upd.message.reply_text(f"📈 *{label}*\n\nBu oy hali sotuv yo'q.", parse_mode='Markdown')
        return
    total_rev  = sum(s[6] for s in sales)
    total_prof = sum(s[7] for s in sales)
    text = f"📈 *Oylik hisobot — {label}*\n\n"
    text += f"🛍 Sotuvlar: {len(sales)} ta\n"
    text += f"💵 Tushum: *{fmt_money(total_rev)}*\n"
    text += f"✅ Foyda: *{fmt_money(total_prof)}*\n"
    text += f"📊 O'rtacha: *{fmt_money(total_rev/len(sales))}* / sotuv\n"
    prod_cnt = Counter(s[3] for s in sales)
    if prod_cnt:
        text += "\n*Top mahsulotlar:*\n"
        for name, cnt in prod_cnt.most_common(3):
            text += f"• {name}: {cnt} ta\n"
    await upd.message.reply_text(text, parse_mode='Markdown')

async def cmd_yordam(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(upd): return
    msg = (
        "📋 *Yo'riqnoma*\n\n"
        "*Buyruqlar:*\n"
        "/astatka — tovarlar holati\n"
        "/bugun — bugungi savdo\n"
        "/oy — oylik hisobot\n\n"
        "*Erkin yozish misollari:*\n\n"
        "🔵 *Sotish:*\n"
        "`TTS 10 Pro sotdim 260 ga`\n"
        "`CNC3018 1 ta $180 dan ketdi`\n"
        "`2 ta SB400 sotildi 350 dollardan`\n\n"
        "📦 *Tovar qo'shish:*\n"
        "`3 ta TTS 20 Pro keldi`\n"
        "`Freesub dan P8100 2 ta kirdi`\n\n"
        "📊 *Ma'lumot:*\n"
        "`Lazer astatka qanday`\n"
        "`TTS 10 narxi qancha`\n"
        "`Bugungi savdo`\n"
        "`Oylik hisobot`\n"
    )
    await upd.message.reply_text(msg, parse_mode='Markdown')

async def handle_text(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(upd): return
    user_msg = upd.message.text
    prods = get_all_products()

    await upd.message.chat.send_action('typing')

    parsed = ai_parse(user_msg, prods)
    action = parsed.get('action','unknown')
    log.info(f"AI parsed: {parsed}")

    # ── SOTISH ────────────────────────────────────────────────────
    if action == 'sell':
        pname  = parsed.get('product','')
        qty    = max(1, int(parsed.get('qty', 1)))
        price  = float(parsed.get('price', 0))
        prod   = find_product(pname)

        if not prod:
            await upd.message.reply_text(
                f"❓ Mahsulot topilmadi: *{pname}*\n\nAstatka ro'yxati: /astatka",
                parse_mode='Markdown'
            )
            return

        if prod['qty'] < qty:
            await upd.message.reply_text(
                f"❌ Yetarli mahsulot yo'q!\n*{prod['name']}*: {prod['qty']} ta mavjud",
                parse_mode='Markdown'
            )
            return

        if price <= 0:
            price = prod['price']

        ok = save_sale(prod['id'], prod['name'], qty, price, prod['cost'])
        if ok:
            profit = (price - prod['cost']) * qty
            text = (
                f"✅ *Sotuv qayd etildi!*\n\n"
                f"📦 {prod['name']}\n"
                f"🔢 Soni: {qty} ta\n"
                f"💵 Narx: {fmt_money(price)} × {qty} = *{fmt_money(price*qty)}*\n"
                f"✅ Foyda: *{fmt_money(profit)}*\n"
                f"📊 Qoldi: {prod['qty']-qty} ta"
            )
            await upd.message.reply_text(text, parse_mode='Markdown')
        else:
            await upd.message.reply_text("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

    # ── QOSHISH ───────────────────────────────────────────────────
    elif action == 'add':
        pname = parsed.get('product','')
        qty   = max(1, int(parsed.get('qty', 1)))
        prod  = find_product(pname)

        if not prod:
            await upd.message.reply_text(
                f"❓ Mahsulot topilmadi: *{pname}*", parse_mode='Markdown'
            )
            return

        add_qty(prod['id'], qty)
        await upd.message.reply_text(
            f"✅ *Astatka yangilandi!*\n\n"
            f"📦 {prod['name']}\n"
            f"➕ Qo'shildi: +{qty} ta\n"
            f"📊 Jami: {prod['qty']+qty} ta",
            parse_mode='Markdown'
        )

    # ── ASTATKA ───────────────────────────────────────────────────
    elif action == 'stock':
        cat = parsed.get('cat','Barchasi')
        prods_f = prods if cat=='Barchasi' else [p for p in prods if p['cat']==cat]
        text = f"📦 *Astatka — {cat}*\n\n"
        for p in prods_f:
            e = "🔴" if p['qty']==0 else "🟡" if p['qty']<=1 else "🟢"
            text += f"{e} {p['name']}: *{p['qty']} ta* | ${p['price']}\n"
        total_c = sum(p['qty']*p['cost'] for p in prods_f)
        text += f"\n💰 Sebest: *{fmt_money(total_c)}*"
        await upd.message.reply_text(text, parse_mode='Markdown')

    # ── HISOBOT ───────────────────────────────────────────────────
    elif action == 'report':
        period = parsed.get('period','today')
        if 'month' in period or 'oy' in period:
            await cmd_oy(upd, ctx)
        else:
            await cmd_bugun(upd, ctx)

    # ── NARX ──────────────────────────────────────────────────────
    elif action == 'price':
        pname = parsed.get('product','')
        prod  = find_product(pname)
        if prod:
            profit = prod['price'] - prod['cost']
            margin = profit/prod['price']*100 if prod['price'] else 0
            text = (
                f"💲 *{prod['name']}*\n\n"
                f"Sebest: {fmt_money(prod['cost'])}\n"
                f"Narx: *{fmt_money(prod['price'])}*\n"
                f"Foyda: {fmt_money(profit)} ({margin:.0f}%)\n"
                f"Astatka: {prod['qty']} ta"
            )
            await upd.message.reply_text(text, parse_mode='Markdown')
        else:
            await upd.message.reply_text(f"❓ Topilmadi: {pname}")

    # ── NARX OZGARTIRISH ──────────────────────────────────────────
    elif action == 'set_price':
        pname    = parsed.get('product','')
        new_price= float(parsed.get('price', 0))
        prod     = find_product(pname)
        if prod and new_price > 0:
            update_product_price(prod['id'], new_price)
            profit = new_price - prod['cost']
            await upd.message.reply_text(
                f"✅ *Narx yangilandi!*\n\n"
                f"📦 {prod['name']}\n"
                f"💵 Yangi narx: *{fmt_money(new_price)}*\n"
                f"✅ Foyda: *{fmt_money(profit)}*",
                parse_mode='Markdown'
            )
        else:
            await upd.message.reply_text("❌ Mahsulot topilmadi yoki narx noto'g'ri")

    # ── TUSHUNARSIZ ───────────────────────────────────────────────
    else:
        reply = parsed.get('reply', "Tushunmadim 🤔\n\n/yordam — yo'riqnoma")
        await upd.message.reply_text(reply)

# ── MAIN ──────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN muhit o'zgaruvchisi o'rnatilmagan!")
    if not ANTHROPIC_KEY:
        raise ValueError("ANTHROPIC_KEY muhit o'zgaruvchisi o'rnatilmagan!")
    if OWNER_ID == 0:
        raise ValueError("OWNER_ID muhit o'zgaruvchisi o'rnatilmagan!")

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start',    cmd_start))
    app.add_handler(CommandHandler('help',     cmd_start))
    app.add_handler(CommandHandler('astatka',  cmd_astatka))
    app.add_handler(CommandHandler('bugun',    cmd_bugun))
    app.add_handler(CommandHandler('oy',       cmd_oy))
    app.add_handler(CommandHandler('yordam',   cmd_yordam))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    log.info("ThermoCrafts Bot ishga tushdi! ✅")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
