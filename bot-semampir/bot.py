import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import requests
import time
import threading

# ===== CONFIG SHEET 3 =====
BOT_TOKEN = "8301381220:AAEEaHNh68RgwC-R_vNIl9X7JuMEw2l146M"
CHAT_ID = "-1003756930613"
SPREADSHEET_NAME = "SGR UTAMA SEMAMPIR 2026"

# Range mapping
CATEGORY_RANGES = {
    "ALL": ["A8:C32", "E8:G53", "I8:K24", "M8:O21", "Q8:S12", "U8:W13", "Y8:AA52", "AC8:AE34", "AG8:AI22", "AK8:AM93", 
            "AO8:AQ23", "AS8:AU28", "AW8:AY43", "BA8:BC18", "BF8:BH51", "BJ8:BL20", "BN8:BP75", "BR8:BT18", "BV8:BX36", "BZ8:CB15", 
            "CE8:CG16", "CI8:CK23", "CM8:CO13", "CQ8:CS17"],
    "ADD ON": ["A8:C32"],
    "KUT BLANGKO": ["E8:G53"],
    "PLASTIK OPP X 22": ["I8:K24"],
    "PLASTIK OPP X 20": ["M8:O21"],
    "PLASTIK POLYMAILER DAN STANDING PAUCH": ["Q8:S12"],
    "PLASTIK ZIPLOCK": ["U8:W13"],
    "PLASTIK HD PLONG": ["Y8:AA52"],
    "NOTA,TC DAN NCR": ["AC8:AE34"],
    "STIKER OLSHOP": ["AG8:AI22"],
    "STIKER OTOMOTIF": ["AK8:AM93"],
    "STIKER KEMERDEKAAN": ["AO8:AQ23"],
    "KERTAS": ["AS8:AU28"],
    "CONSUMABLE GUDANG & FINISHING": ["AW8:AY43"],
    "PITA SATIN": ["BA8:BC18"],
    "CONSUMABLE PRINTING": ["BF8:BH51"],
    "STIKER BRAND, CASE, ANIME": ["BJ8:BL20"],
    "STM": ["BN8:BP75"],
    # "AKRILIK": ["BR8:BT18"],
    "BONEKA": ["BV8:BX36"],
    "BTR": ["BZ8:CB15"],    
    "B. OLSHOP": ["CE8:CG16"],
    "B.EDUKASI": ["CI8:CK23"],
    "BBR": ["CM8:CO13"],
    "POSTER": ["CQ8:CS17"],

}

class StockBot:
    def __init__(self):
        self.last_update_id = 0
        self.stock_cache = {}
        self.change_logs = []
        self.is_running = True
        
        # Google Auth
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        try:
            self.creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
            self.client = gspread.authorize(self.creds)
            self.sheet = self.client.open(SPREADSHEET_NAME).sheet1
            print("✅ Auth Google Sheets Berhasil")
        except Exception as e:
            print(f"❌ Auth Error: {e}")

    def send_telegram(self, msg, reply_markup=None):
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        if reply_markup: data["reply_markup"] = reply_markup
        try:
            requests.post(url, json=data, timeout=10)
        except Exception as e:
            print(f"❌ Gagal kirim Telegram: {e}")

    def get_main_keyboard(self):
        return {
            "inline_keyboard": [
                [{"text": "📋 CHECK", "callback_data": "CHECK"}, {"text": "📢 REPORT", "callback_data": "REPORT"}],
                [{"text": "❌ ZERO STOCK", "callback_data": "FILTER_ZERO"}],
                [{"text": "📕 DANGER", "callback_data": "FILTER_DANGER"}, {"text": "📙 EMERGENCY", "callback_data": "FILTER_EMERGENCY"}],
                [{"text": "📗 SAFE STOCK", "callback_data": "FILTER_SAFE"}, {"text": "📘 OVERSTOCK", "callback_data": "FILTER_OVER"}],
                [{"text": "🔍 FILTER BY PRODUCT", "callback_data": "LIST_CATS"}]
            ]
        }

    def get_category_keyboard(self):
        cats = [k for k in CATEGORY_RANGES.keys() if k != "ALL"]
        buttons = []
        row = []
        for cat in cats:
            row.append({"text": f"{cat}", "callback_data": f"CAT_{cat}"})
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row: buttons.append(row)
        buttons.append([{"text": "⬅️ BACK", "callback_data": "BACK"}])
        return {"inline_keyboard": buttons}

    def get_stock_data(self, ranges):
        data_list = []
        for r in ranges:
            try:
                rows = self.sheet.get(r)
                for row in rows:
                    if len(row) < 3: continue
                    item, b_raw, s_raw = row[0].strip(), row[1].strip(), row[2].strip()
                    if not item or s_raw.upper() == "OFF": continue
                    try:
                        batas = int(b_raw.replace(".", "").replace(",", ""))
                        stock = int(s_raw.replace(".", "").replace(",", ""))
                        persen = (stock / batas * 100) if batas > 0 else 0
                        data_list.append({"item": item, "batas": batas, "stock": stock, "persen": persen})
                    except: continue
            except: continue
        return data_list

    def build_report(self, ranges, title="STOCK REPORT"):
        items = self.get_stock_data(ranges)
        lines = [f"📊 *{title}*", "-"*50]
        for it in items:
            if it['persen'] >= 130: icon = "📘"
            elif it['persen'] >= 60: icon = "📗"
            elif it['persen'] >= 40: icon = "📙"
            elif it['stock'] == 0: icon = "❌"
            else: icon = "📕"
            lines.append(f"{icon} {it['item']} -> {it['stock']} ({it['persen']:.0f}%)")
        return "\n".join(lines) if len(lines) > 2 else "Tidak ada data."

    def filter_by_status(self, mode):
        items = self.get_stock_data(CATEGORY_RANGES["ALL"])
        lines = [f"🔍 *FILTER STOCK: {mode}*", "-"*50]
        for it in items:
            match = False
            if mode == "ZERO" and it['stock'] == 0: match = True
            elif mode == "DANGER" and it['persen'] < 40 and it['stock'] > 0: match = True
            elif mode == "EMERGENCY" and 40 <= it['persen'] < 60: match = True
            elif mode == "SAFE" and 60 <= it['persen'] < 130: match = True
            elif mode == "OVER" and it['persen'] >= 130: match = True
            
            if match:
                icon = {"ZERO":"❌","DANGER":"📕","EMERGENCY":"📙","SAFE":"📗","OVER":"📘"}[mode]
                lines.append(f"{icon} {it['item']} -> {it['stock']} ({it['persen']:.0f}%)")
        return "\n".join(lines) if len(lines) > 2 else "Tidak ada data."

    # TUGAS 1: CEK STOK (Berjalan di Thread Terpisah)
    def stock_check_loop(self):
        print("🚀 Thread Cek Stok Dimulai...")
        while self.is_running:
            try:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Memeriksa perubahan stok di Google Sheets...")
                items = self.get_stock_data(CATEGORY_RANGES["ALL"])
                for it in items:
                    name = it['item']
                    stock = it['stock']
                    persen = it['persen']
                    
                    prev_stock = self.stock_cache.get(name)
                    if prev_stock is not None and prev_stock != stock:
                        diff = stock - prev_stock
                        sign = "➕" if diff > 0 else "➖"
                        log_entry = f"{sign} {name}: {prev_stock} -> {stock} ({diff:+}) [{datetime.now().strftime('%H:%M')}]"
                        self.change_logs.append(log_entry)
                        
                        if stock == 0: status_msg = "❌ *STOCK HABIS!*"
                        elif persen < 40: status_msg = "📕 *STOCK DANGER!*"
                        elif persen < 60: status_msg = "📙 *STOCK EMERGENCY!*"
                        elif persen >= 130: status_msg = "📘 *STOCK OVERSTOCK!*"
                        else: status_msg = "📗 *STOCK UPDATE*"
                        
                        msg = f"{status_msg}\n------------------------------------------\n◾ {name}\n◾ Perubahan: {prev_stock} -> {stock} ({diff:+})"
                        self.send_telegram(msg)
                    
                    self.stock_cache[name] = stock
            except Exception as e:
                print(f"❌ Error di Thread Stok: {e}")
            
            # Cek setiap 40 detik agar tidak kena limit Google API
            time.sleep(40)

        # TUGAS 2: RESPON TELEGRAM (Thread Utama)
    def telegram_polling_loop(self):
        print("?? Thread Telegram Dimulai (Respon Cepat)...")
        while self.is_running:
            # Kecilkan timeout ke 1 detik agar bot langsung ngecek lagi
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={self.last_update_id + 1}&timeout=1"
            try:
                response = requests.get(url, timeout=5 ) # Timeout koneksi pendek saja
                data = response.json()
                if data.get("ok"):
                    for update in data["result"]:
                        self.last_update_id = update["update_id"]
                        if "message" in update:
                            text = update["message"].get("text", "").lower()
                            if text == "/semampir":
                                self.send_telegram("Silahkan pilih menu:", reply_markup=self.get_main_keyboard())
                        elif "callback_query" in update:
                            self.process_callback(update["callback_query"])
            except Exception as e:
                print(f"? Error di Polling Telegram: {e}")
                time.sleep(5) # Hanya jeda kalau ada error koneksi

    def process_callback(self, cb):
        data = cb["data"]
        if data == "CHECK": self.send_telegram(self.build_report(CATEGORY_RANGES["ALL"]))
        elif data == "REPORT":
            res = "📢 *STOCK CHANGE REPORT*\n" + "\n".join(self.change_logs[-10:]) if self.change_logs else "Tidak ada perubahan."
            self.send_telegram(res)
        elif data.startswith("FILTER_"): self.send_telegram(self.filter_by_status(data.split("_")[1]))
        elif data == "LIST_CATS": self.send_telegram("Pilih kategori produk:", reply_markup=self.get_category_keyboard())
        elif data == "BACK": self.send_telegram("🤖 Silahkan pilih menu:", reply_markup=self.get_main_keyboard())
        elif data.startswith("CAT_"):
            cat_name = data.split("_")[1]
            self.send_telegram(self.build_report(CATEGORY_RANGES.get(cat_name, []), title=f"CAT: {cat_name}"))

    def run(self):
        # Jalankan Thread Cek Stok secara background
        t = threading.Thread(target=self.stock_check_loop, daemon=True)
        t.start()
        
        # Jalankan Polling Telegram di thread utama
        self.telegram_polling_loop()

if __name__ == "__main__":
    bot = StockBot()
    bot.run()
