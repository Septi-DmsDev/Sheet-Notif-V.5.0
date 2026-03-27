import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import requests
import time
import threading

# ===== CONFIG SHEET 2 =====
BOT_TOKEN = "8220544772:AAHFvIz13Go9k-DXgoOEuduG9WwwERlulAY"
CHAT_ID = "-1003756930613"
SPREADSHEET_NAME = "SGR TEKNOS IDN (STOK GUDANG REALTIME) 2025"

# Range mapping
CATEGORY_RANGES = {
    "ALL": ["A7:C22", "E7:G38", "I7:K18", "M7:O23", "Q7:S17", "U7:W14", "Y7:AA17", "AC7:AE12", "AG7:AI25", "AK7:AM31", "AO7:AQ21", 
            "AS7:AU22", "AW7:AY30", "BA7:BC32", "BE7:BG30", "BI7:BK12", "BM7:BO15", "BQ7:BS14", "BU7:BW19", "BY7:CA22", "CG7:CI18", "CK7:CM8", 
            "CO7:CQ11", "CS7:CU12", "CW7:CY41", "DB7:DD10", "DG7:DI10", "DL7:DN18", "DQ7:DS12", "DU7:DW20", "DY7:EA18", "EC7:EE10", "EG7:EI14", "EK7:EM21", 
            "EO7:EQ51", "ES7:EU12", "EW7:EY12", "FA7:FC51", "FE7:FG11"],
    "CINTA": ["A7:C22"],
    "RINDU": ["E7:G38"],
    "AVIS": ["I7:K18"],
    "SALMA": ["M7:O23"],
    "RIZKI": ["Q7:S17"],
    "CANTIK": ["U7:W14"],
    "HEPI": ["Y7:AA17"],
    "HC": ["AC7:AE12"],
    "FADHIL": ["AG7:AI25"],
    "GRIYA": ["AK7:AM31"],
    "ZIGNA": ["AO7:AQ21"],
    "SAYANG": ["AS7:AU22"],
    "KASIH": ["AW7:AY30"],
    "KASIH SERI 2": ["BA7:BC32"],
    "KANGEN": ["BE7:BG30"],
    "KHITAN": ["BI7:BK12"],
    "BUKU OLSHOP": ["BM7:BO15"],
    "BUKU TAMU": ["BQ7:BS14"],
    "NOTA OLSHOP": ["BU7:BW19"],
    "BUKU EDUKASI": ["BY7:CA22"],
    ##"STIKER PENGIRIMAN": ["XX:021"],##
    "BAHAN": ["CG7:CI18"],
    "STIKER QC PASS HOLOGRAM": ["CK7:CM8"],
    "PARFUM": ["CO7:CQ11"],
    "AMPLOP": ["CS7:CU12"],
    "PAPERBAG": ["CW7:CY41"],
    "GBC": ["DB7:DD10"],
    "PBM": ["DG7:DI10"],
    "BRIDESMAID BBR": ["DL7:DN18"],
    "KALENDER": ["DQ7:DS12"],
    "PRODUK AKRILIK": ["DU7:DW20"],
    "REPLIKA MAHAR AKRILIK": ["DY7:EA18"],
    "TOPPER CAKE AKRILIK": ["EC7:EE10"],
    "GANCI AKRILIK": ["EG7:EI14"],
    "WORKSHEET": ["EK7:EM21"],
    "STIKER OTOMOTIF": ["EO7:EQ51"],
    "PLASTIK POLYMAILER": ["ES7:EU12"],
    "PLASTIK ZIPLOK": ["EW7:EY12"],
    "PLASTIK HD PLONG": ["FA7:FC51"],
    "KATALOG": ["FE7:FG11"],
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
                [{"text": "⛔ ZERO STOCK", "callback_data": "FILTER_ZERO"}],
                [{"text": "🟥 DANGER", "callback_data": "FILTER_DANGER"}, {"text": "🟨 EMERGENCY", "callback_data": "FILTER_EMERGENCY"}],
                [{"text": "🟩 SAFE STOCK", "callback_data": "FILTER_SAFE"}, {"text": "🟦 OVERSTOCK", "callback_data": "FILTER_OVER"}],
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
            if it['persen'] >= 130: icon = "🟦"
            elif it['persen'] >= 60: icon = "🟩"
            elif it['persen'] >= 40: icon = "🟨"
            elif it['stock'] == 0: icon = "⛔"
            else: icon = "🟥"
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
                icon = {"ZERO":"⛔","DANGER":"🟥","EMERGENCY":"🟨","SAFE":"🟩","OVER":"🟦"}[mode]
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
                        
                        if stock == 0: status_msg = "⛔ *STOCK HABIS!*"
                        elif persen < 40: status_msg = "🟥 *STOCK DANGER!*"
                        elif persen < 60: status_msg = "🟨 *STOCK EMERGENCY!*"
                        elif persen >= 130: status_msg = "🟦 *STOCK OVERSTOCK!*"
                        else: status_msg = "🟩 *STOCK UPDATE*"
                        
                        msg = f"{status_msg}\n------------------------------------------\n◾ {name}\n◾ Perubahan: {prev_stock} -> {stock} ({diff:+})"
                        self.send_telegram(msg)
                    
                    self.stock_cache[name] = stock
            except Exception as e:
                print(f"❌ Error di Thread Stok: {e}")
            
            # Cek setiap 30 detik agar tidak kena limit Google API
            time.sleep(30)

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
                            if text == "/teknos":
                                self.send_telegram("Silahkan pilih menu:", reply_markup=self.get_main_keyboard())
                        elif "callback_query" in update:
                            self.process_callback(update["callback_query"])
            except Exception as e:
                print(f"? Error di Polling Telegram: {e}")
                time.sleep(2) # Hanya jeda kalau ada error koneksi

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
