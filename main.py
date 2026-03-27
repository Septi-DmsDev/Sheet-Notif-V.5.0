import json
import gspread
import requests
import time
import threading
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

class StockBot:
    def __init__(self, bot_name, config, client):
        self.bot_name = bot_name.upper()
        self.config = config
        self.client = client
        self.last_update_id = 0
        self.stock_cache = {}
        self.change_logs = []
        self.is_running = True
        self.emojis = self.config["emojis"]
        
        try:
            self.sheet = self.client.open(self.config["spreadsheet_name"]).sheet1
            print(f"✅ [{self.bot_name}] Auth Sheet '{self.config['spreadsheet_name']}' Berhasil")
        except Exception as e:
            print(f"❌ [{self.bot_name}] Auth Error: {e}")

    def send_telegram(self, msg, reply_markup=None):
        url = f"https://api.telegram.org/bot{self.config['bot_token']}/sendMessage"
        data = {"chat_id": self.config['chat_id'], "text": msg, "parse_mode": "Markdown"}
        if reply_markup: data["reply_markup"] = reply_markup
        try:
            requests.post(url, json=data, timeout=10)
        except Exception as e:
            print(f"❌ [{self.bot_name}] Gagal kirim Telegram: {e}")

    def get_main_keyboard(self):
        em = self.emojis
        return {
            "inline_keyboard": [
                [{"text": "📋 CHECK", "callback_data": "CHECK"}, {"text": "📢 REPORT", "callback_data": "REPORT"}],
                [{"text": f"{em['zero']} ZERO STOCK", "callback_data": "FILTER_ZERO"}],
                [{"text": f"{em['danger']} DANGER", "callback_data": "FILTER_DANGER"}, {"text": f"{em['emergency']} EMERGENCY", "callback_data": "FILTER_EMERGENCY"}],
                [{"text": f"{em['safe']} SAFE STOCK", "callback_data": "FILTER_SAFE"}, {"text": f"{em['over']} OVERSTOCK", "callback_data": "FILTER_OVER"}],
                [{"text": "🔍 FILTER BY PRODUCT", "callback_data": "LIST_CATS"}]
            ]
        }

    def get_category_keyboard(self):
        cats = [k for k in self.config["categories"].keys() if k != "ALL"]
        buttons = [[{"text": cat, "callback_data": f"CAT_{cat}"}] for cat in cats]
        # Restructure to 2 columns
        formatted_buttons = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        # Flatten the inner lists of dicts appropriately
        final_buttons = []
        for row in formatted_buttons:
            new_row = [item[0] for item in row]
            final_buttons.append(new_row)
            
        final_buttons.append([{"text": "⬅️ BACK", "callback_data": "BACK"}])
        return {"inline_keyboard": final_buttons}

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
            except Exception as e: 
                continue
        return data_list

    def get_status_data(self, persen, stock):
        em = self.emojis
        if persen >= 130: return em['over'], "OVERSTOCK!"
        elif persen >= 60: return em['safe'], "SAFE STOCK"
        elif persen >= 40: return em['emergency'], "EMERGENCY!"
        elif stock == 0: return em['zero'], "HABIS!"
        else: return em['danger'], "DANGER!"

    def build_report(self, ranges, title="STOCK REPORT"):
        items = self.get_stock_data(ranges)
        lines = [f"📊 *{title}*", "-"*50]
        for it in items:
            icon, _ = self.get_status_data(it['persen'], it['stock'])
            lines.append(f"{icon} {it['item']} -> {it['stock']} ({it['persen']:.0f}%)")
        return "\n".join(lines) if len(lines) > 2 else "Tidak ada data."

    def filter_by_status(self, mode):
        items = self.get_stock_data(self.config["categories"]["ALL"])
        lines = [f"🔍 *FILTER STOCK: {mode}*", "-"*50]
        for it in items:
            p, s = it['persen'], it['stock']
            match = False
            if mode == "ZERO" and s == 0: match = True
            elif mode == "DANGER" and p < 40 and s > 0: match = True
            elif mode == "EMERGENCY" and 40 <= p < 60: match = True
            elif mode == "SAFE" and 60 <= p < 130: match = True
            elif mode == "OVER" and p >= 130: match = True
            
            if match:
                icon, _ = self.get_status_data(p, s)
                lines.append(f"{icon} {it['item']} -> {s} ({p:.0f}%)")
        return "\n".join(lines) if len(lines) > 2 else "Tidak ada data."

    def stock_check_loop(self):
        print(f"🚀 [{self.bot_name}] Thread Cek Stok Dimulai...")
        while self.is_running:
            try:
                items = self.get_stock_data(self.config["categories"]["ALL"])
                for it in items:
                    name, stock, persen = it['item'], it['stock'], it['persen']
                    prev_stock = self.stock_cache.get(name)
                    
                    if prev_stock is not None and prev_stock != stock:
                        diff = stock - prev_stock
                        sign = "➕" if diff > 0 else "➖"
                        log_entry = f"{sign} {name}: {prev_stock} -> {stock} ({diff:+}) [{datetime.now().strftime('%H:%M')}]"
                        self.change_logs.append(log_entry)
                        
                        icon, status_text = self.get_status_data(persen, stock)
                        msg = f"{icon} *STOCK {status_text}*\n------------------------------------------\n◾ {name}\n◾ Perubahan: {prev_stock} -> {stock} ({diff:+})"
                        self.send_telegram(msg)
                    
                    self.stock_cache[name] = stock
            except Exception as e:
                print(f"❌ [{self.bot_name}] Error di Thread Stok: {e}")
            
            time.sleep(self.config["check_interval"])

    def telegram_polling_loop(self):
        print(f"💬 [{self.bot_name}] Thread Telegram Dimulai...")
        while self.is_running:
            url = f"https://api.telegram.org/bot{self.config['bot_token']}/getUpdates?offset={self.last_update_id + 1}&timeout=1"
            try:
                response = requests.get(url, timeout=5)
                data = response.json()
                if data.get("ok"):
                    for update in data["result"]:
                        self.last_update_id = update["update_id"]
                        if "message" in update:
                            text = update["message"].get("text", "").lower()
                            if text == f"/{self.bot_name.lower()}":
                                self.send_telegram("Silahkan pilih menu:", reply_markup=self.get_main_keyboard())
                        elif "callback_query" in update:
                            self.process_callback(update["callback_query"])
            except Exception as e:
                time.sleep(2)

    def process_callback(self, cb):
        data = cb["data"]
        if data == "CHECK": self.send_telegram(self.build_report(self.config["categories"]["ALL"]))
        elif data == "REPORT":
            res = "📢 *STOCK CHANGE REPORT*\n" + "\n".join(self.change_logs[-10:]) if self.change_logs else "Tidak ada perubahan."
            self.send_telegram(res)
        elif data.startswith("FILTER_"): self.send_telegram(self.filter_by_status(data.split("_")[1]))
        elif data == "LIST_CATS": self.send_telegram("Pilih kategori produk:", reply_markup=self.get_category_keyboard())
        elif data == "BACK": self.send_telegram("🤖 Silahkan pilih menu:", reply_markup=self.get_main_keyboard())
        elif data.startswith("CAT_"):
            cat_name = data.split("_")[1]
            self.send_telegram(self.build_report(self.config["categories"].get(cat_name, []), title=f"CAT: {cat_name}"))

    def start_threads(self):
        t1 = threading.Thread(target=self.stock_check_loop, daemon=True)
        t2 = threading.Thread(target=self.telegram_polling_loop, daemon=True)
        t1.start()
        t2.start()

def main():
    # 1. Global Auth GSpread
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        # KEMBALI MENGGUNAKAN METHOD LAMA YANG LEBIH AMAN
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        print("✅ Global Auth Google API Berhasil")
    except Exception as e:
        print(f"❌ Global Auth Error: {e}")
        return

    # 2. Load Config
    with open("bots-config.json", "r", encoding="utf-8") as f:
        config_data = json.load(f)

    # 3. Instantiate and run all bots
    active_bots = []
    for bot_name, config in config_data.items():
        bot = StockBot(bot_name, config, client)
        bot.start_threads()
        active_bots.append(bot)
        # Kasih jeda 5 detik antar inisialisasi bot agar Google API tidak kaget
        time.sleep(5)

    print("🚀 Semua bot telah berjalan. Menunggu input...")
    
    # Biarkan main thread tetap hidup
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Mematikan semua bot...")

if __name__ == "__main__":
    main()