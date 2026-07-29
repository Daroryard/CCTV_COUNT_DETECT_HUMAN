import cv2
import customtkinter as ctk
from tkinter import filedialog, colorchooser
from PIL import Image, ImageTk
from ultralytics import YOLO
from shapely.geometry import Point, Polygon
import threading
import time
import json
import os
import datetime
import numpy as np
import pystray
from pystray import MenuItem as item
from tkinter import messagebox

# ตั้งค่าธีมการออกแบบควบคุมห้อง Control Room
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "multi_config.json"
LOG_FILE = "log.json"
MAX_CHANNELS = 4
DEFAULT_AREA_COLOR = "#3498DB"
AREA_COLOR_PRESETS = {
    "Blue / น้ำเงิน": "#3498DB",
    "Green / เขียว": "#2ECC71",
    "Yellow / เหลือง": "#F1C40F",
    "Red / แดง": "#E74C3C",
    "Cyan / ฟ้า": "#00D7FF",
    "Orange / ส้ม": "#E67E22",
    "Purple / ม่วง": "#9B59B6",
    "White / ขาว": "#FFFFFF",
}

class CTkToast(ctk.CTkToplevel):
    def __init__(self, master, message, bg_color="#2ECC71", fg_color="#FFFFFF", duration=2500):
        super().__init__(master)
        
        # โครงสร้างหน้าต่างไร้ขอบ ลอยอยู่ด้านบนสุด
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=bg_color)
        
        if os.name == 'nt':
            self.attributes("-alpha", 0.95) # เพิ่มมิติความโปร่งแสงนิด ๆ ให้ดูโมเดิร์น
            
        # จัด Layout และตัวหนังสือภายใน
        label = ctk.CTkLabel(
            self, 
            text=message, 
            font=("Arial", 13, "bold"), 
            text_color=fg_color, 
            padx=25, 
            pady=12
        )
        label.pack()
        
        # 📌 อัปเดตพิกัดเพื่อให้ดึงตำแหน่งปัจจุบันของตัวโปรแกรมหลักมาคำนวณ
        master.update_idletasks()
        self.update_idletasks()
        
      # ดึงพิกัดมุมซ้ายบน และขนาดของตัวโปรแกรมหลัก
        main_x = master.winfo_x()
        main_y = master.winfo_y()
        main_w = master.winfo_width()
        main_h = master.winfo_height()
        
        # ดึงขนาดของตัวกล่อง Toast เอง
        toast_w = self.winfo_reqwidth()
        toast_h = self.winfo_reqheight()
        
        # 📐 [ปรับปรุงใหม่] เพิ่มระยะหักลบเพื่อดึง Toast กลับเข้ามาไม่ให้ทะลุขอบโปรแกรม
        # เปลี่ยนจาก - 20 เป็น - 50 (ขยับเข้าซ้าย) และ - 45 (ขยับขึ้นบนเพื่อหลบขอบล่าง)
        x = main_x + main_w - toast_w - 200
        y = main_y + main_h - toast_h - 45
        
        # สั่งกำหนดพิกัดให้แสดงผล
        self.geometry(f"{toast_w}x{toast_h}+{x}+{y}")
        
        # สั่งทำลายตัวเองทิ้งเมื่อครบเวลา
        self.after(duration, self.destroy)



class CCTVApp(ctk.CTk):
    def __init__(self):
        super().__init__()
   
        self.title("🎬 Enterprise Multi-CCTV AI Analytics (Fixed System V3)")
        self.geometry("1480x860")
        self.resizable(False, False)
        
        self.lock = threading.Lock()
        self.stream_versions = [0] * MAX_CHANNELS
        self.is_running_channels = [False] * MAX_CHANNELS
        self.caps = [None] * MAX_CHANNELS
        
        self.people_counts = [0] * MAX_CHANNELS
        self.inside_ids_pool = [set() for _ in range(MAX_CHANNELS)]
        self.id_maps_pool = [{} for _ in range(MAX_CHANNELS)]
        
        self.current_setting_ch = 0 
        
        # 1. โหลด Config ดึงข้อมูลขึ้นมาก่อน (จะทำการโหลดค่า global_model_name มาให้ด้วย)
        self.load_multi_config()
        self.load_daily_logs()
        
        # 🚀 2. ดึงชื่อ Master Model จากตัวแปรกลางของระบบมาโหลด
        default_model_name = getattr(self, 'global_model_name', "yolov8s")
            
        self.model = YOLO(f"{default_model_name}.pt")
        
        # ย้ายมาใส่ Device ให้เรียบร้อยตั้งแต่เริ่มต้น
        import torch
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(dev)
        
        self.protocol('WM_DELETE_WINDOW', self.withdraw_to_background)
        self.setup_tray()
        
        # --- UI LAYOUT MAIN ---
        self.tabview = ctk.CTkTabview(self, segmented_button_selected_color="#1F6AA5", segmented_button_selected_hover_color="#144870", command=self.on_tab_changed)
        self.tabview.pack(padx=15, pady=15, fill="both", expand=True)
        
        self.tab_monitor = self.tabview.add("📺 Live Monitor Panel (1024x768 Grid)")
        self.tab_setting = self.tabview.add("⚙️ Multi-Channel Settings")
        
        # สร้าง Control Variables สำหรับผูกมัดสถานะ Checkbox ให้เสถียร
        self.chk_enabled_var = ctk.BooleanVar(value=True)
        
        self.setup_monitor_page()
        self.setup_setting_page()
        
        # 🚀 3. อัปเดตช่อง ComboBox ของ Master Model ในหน้า Setting ให้ตรงกับค่าที่โหลดมา
        if hasattr(self, 'combo_model'):
            self.combo_model.set(default_model_name)
            
        self.refresh_log_table()

    def on_tab_changed(self):
        current_tab = self.tabview.get()
        
        # เช็คชื่อแท็บให้ตรงกับ Live Monitor ของคุณ Kiangsak นะครับ
        if "Live Monitor Panel" in current_tab:
            try:
                # 1. จัดผัง Grid Layout หน้าจอใหม่ตามค่าคอนฟิกปัจจุบัน (ช่องที่ปิดจะหลุดออก)
                self.rebuild_monitor_grid()
                
                # 2. บังคับเคลียร์ให้ภาพนิ่งและขึ้นข้อความ Stream Stopped รอไว้ (ยังไม่เล่นวิดีโอ)
                self.stop_all_channels()
                
                print("🔄 [Tab Sync] จัดการล้างและเรียง Grid Layout ล่าสุดแบบนิ่ง ๆ เรียบร้อยแล้ว")
            except Exception as e:
                print(f"Error updating grid on tab change: {e}")

    def load_multi_config(self):
        self.global_model_name = "yolov8s"  # ค่าเริ่มต้น
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                # รองรับโครงสร้างใหม่ที่มี global_model แยกออกมา
                if isinstance(data, dict):
                    self.global_model_name = data.get("global_model", "yolov8s")
                    self.channels_data = data.get("channels", [])
                elif isinstance(data, list):
                    # รองรับไฟล์ config แบบเก่าที่เป็น list ของช่อง
                    self.channels_data = data
                    self.global_model_name = "yolov8s"
                    
                # เผื่อช่องข้อมูลไม่ครบ MAX_CHANNELS
                if len(self.channels_data) < MAX_CHANNELS:
                    self.generate_default_channels()
                    
            except Exception:
                self.generate_default_channels()
                self.save_multi_config()
        else:
            self.generate_default_channels()
            self.save_multi_config()

    def save_multi_config(self):
        try:
            data = {
                "global_model": getattr(self, 'global_model_name', "yolov8s"),
                "channels": self.channels_data
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def generate_default_channels(self):
        self.channels_data = []
        for i in range(MAX_CHANNELS):
            self.channels_data.append({
                "ch_index": i,
                "enabled": True if i < 4 else False, 
                "source_type": "video",
                "video_path": "test.mp4",
                "dvr_rtsp": f"rtsp://admin:password@192.168.1.{100+i}:554/stream1",
                "area_polygon": [[100, 100], [700, 100], [700, 450], [100, 450]],
                "area_color": DEFAULT_AREA_COLOR
            })

    def save_multi_config(self):
        try:
            data = {
                "global_model": getattr(self, 'global_model_name', "yolov8s"),
                "channels": self.channels_data
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def load_daily_logs(self):
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    self.daily_logs = json.load(f)
            except Exception:
                self.daily_logs = {}
        else:
            self.daily_logs = {}

    def save_daily_log(self, ch_idx):
        today_str = datetime.date.today().strftime("%d/%m/%Y")
        
        # 🛡️ แก้ไขบั๊กโครงสร้างข้อมูลทับซ้อน (Data Type Conflict Fix)
        if today_str not in self.daily_logs or not isinstance(self.daily_logs[today_str], dict):
            self.daily_logs[today_str] = {}
            
        self.daily_logs[today_str][f"CH_{ch_idx + 1}"] = self.people_counts[ch_idx]
        
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.daily_logs, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving log file: {e}")

    # ==================== MONITOR PANEL ====================
    def setup_monitor_page(self):
        self.monitor_container = ctk.CTkFrame(self.tab_monitor, width=1024, height=768, fg_color="#0A0A0A")
        self.monitor_container.pack(side="left", padx=10, pady=5)
        self.monitor_container.pack_propagate(False)
        
        self.video_labels = []
        self.rebuild_monitor_grid()
        
        frame_control_right = ctk.CTkFrame(self.tab_monitor)
        frame_control_right.pack(side="right", padx=10, pady=5, fill="both", expand=True)
        
        lbl_control_title = ctk.CTkLabel(frame_control_right, text="🕹️ MULTI CONTROLLER", font=("Arial", 16, "bold"), text_color="#3498DB")
        lbl_control_title.pack(pady=10)
        
        self.btn_master_start = ctk.CTkButton(frame_control_right, text="🚀 Start All Enabled Cameras", command=self.start_all_channels, fg_color="#2980B9", hover_color="#2471A3", font=("Arial", 13, "bold"), height=38)
        self.btn_master_start.pack(pady=6, padx=20, fill="x")
        
        self.btn_master_stop = ctk.CTkButton(frame_control_right, text="🛑 Stop All Monitor Streams", command=self.stop_all_channels, fg_color="#C0392B", hover_color="#962D22", font=("Arial", 13, "bold"), height=38)
        self.btn_master_stop.pack(pady=6, padx=20, fill="x")
        
        self.btn_master_reload = ctk.CTkButton(frame_control_right, text="🔄 Safe Sync & Reload All Streams", command=self.reload_all_channels, fg_color="#E67E22", hover_color="#D35400", font=("Arial", 13, "bold"), height=38)
        self.btn_master_reload.pack(pady=6, padx=20, fill="x")
        
        self.btn_master_hide = ctk.CTkButton(frame_control_right, text="📥 Run Background (Hide Window)", command=self.withdraw_to_background, fg_color="#27AE60", hover_color="#1E8449", font=("Arial", 13, "bold"), height=38)
        self.btn_master_hide.pack(pady=6, padx=20, fill="x")
        
        lbl_history_title = ctk.CTkLabel(frame_control_right, text="📊 History Log Database Table", font=("Arial", 14, "bold"), text_color="#ECF0F1")
        lbl_history_title.pack(pady=15)
        
        th = ctk.CTkFrame(frame_control_right, height=28, fg_color="#2C3E50")
        th.pack(fill="x", padx=15)
        ctk.CTkLabel(th, text="Date / วันที่", font=("Arial", 11, "bold"), text_color="#BDC3C7").pack(side="left", padx=15)
        ctk.CTkLabel(th, text="Counts / จำนวนแยกช่อง", font=("Arial", 11, "bold"), text_color="#BDC3C7").pack(side="right", padx=15)
        
        self.table_scroll = ctk.CTkScrollableFrame(frame_control_right, height=360, fg_color="#1A252F")
        self.table_scroll.pack(fill="both", expand=True, padx=15, pady=5)

    def rebuild_monitor_grid(self):
        # 📌 เคลียร์ทำลายออบเจกต์เดิมในลิสต์
        for lbl in self.video_labels:
            try:
                lbl.destroy()
            except Exception:
                pass
        self.video_labels.clear()
        
        # 📌 สั่งเคลียร์สิ่งตกค้างทั้งหมดภายใน container ป้องกันเคส pack/grid ซ้อนทับกัน
        for child in self.monitor_container.winfo_children():
            child.destroy()
            
        # 📌 เคลียร์ค่า Grid Configuration เก่าทั้งหมด ป้องกันปัญหากรณีสลับจำนวนจอไปมาแล้ว Grid ค้าง
        for r in range(10): 
            self.monitor_container.grid_rowconfigure(r, weight=0, minsize=0)
            self.monitor_container.grid_columnconfigure(r, weight=0, minsize=0)
        
        enabled_chans = [ch for ch in self.channels_data if ch["enabled"]]
        total_enabled = len(enabled_chans)
        
        # ==========================================================
        # ❌ เคสไม่มีกล้องเปิดใช้งานเลย
        # ==========================================================
        if total_enabled == 0:
            lbl_empty = ctk.CTkLabel(
                self.monitor_container, 
                text="No cameras enabled.\nPlease configure and check Enable in Setting Page.", 
                font=("Arial", 18), 
                text_color="gray"
            )
            lbl_empty.pack(expand=True)
            self.video_labels.append(lbl_empty)
            return
            
        # ==========================================================
        # 🟢 เคสเปิดจอเดียว -> ใช้ .pack() บังคับให้ขยายเต็มขอบดำ 100%
        # ==========================================================
        if total_enabled == 1:
            ch_info = enabled_chans[0]
            real_ch_idx = ch_info["ch_index"]
            
            lbl_vid = ctk.CTkLabel(
                self.monitor_container, 
                text=f"CH {real_ch_idx + 1} - Offline", 
                bg_color="#151515", 
                font=("Arial", 18, "bold"),
                text_color="#95A5A6"
            )
            lbl_vid.pack(expand=True, fill="both", padx=3, pady=3)
            
            # 🔥 [แก้ไขจุดนี้] ดึงขนาดกว้างยาวของ container จริง 
            # ถ้าโปรแกรมเพิ่งเปิดแล้วค่าเป็น 0 หรือน้อยเกินไป จะ fallback ไปใช้ขนาดเริ่มต้น เพื่อไม่ให้ OpenCV บั๊ก
            container_w = self.monitor_container.winfo_width()
            container_h = self.monitor_container.winfo_height()
            
            if container_w < 100 or container_h < 100:
                # ใช้ค่า Default ปลอดภัยไว้ก่อนในเฟรมแรกๆ เดี๋ยวระบบสตรีมจะมาปรับขนาดตามจริงให้เองตอนหลัง
                lbl_vid.target_w = 1024 - 6
                lbl_vid.target_h = 768 - 6
            else:
                lbl_vid.target_w = container_w - 6
                lbl_vid.target_h = container_h - 6
                
            lbl_vid.real_ch_idx = real_ch_idx
            self.video_labels.append(lbl_vid)
            return
            
        # ==========================================================
        # 🔵 เคสปกติ: ตั้งแต่ 2 จอขึ้นไป -> ใช้ .grid() แบ่งช่องตามสัดส่วน
        # ==========================================================
        if total_enabled <= 4:
            cols, rows = 2, 2
        else:
            cols, rows = 3, 3
            
        cell_w = int(1024 / cols)
        cell_height = int(768 / rows)
        
        for r in range(rows):
            self.monitor_container.grid_rowconfigure(r, weight=1, minsize=cell_height)
        for c in range(cols):
            self.monitor_container.grid_columnconfigure(c, weight=1, minsize=cell_w)
            
        idx = 0
        for r in range(rows):
            for c in range(cols):
                if idx < total_enabled:
                    ch_info = enabled_chans[idx]
                    real_ch_idx = ch_info["ch_index"]
                    
                    lbl_vid = ctk.CTkLabel(
                        self.monitor_container, 
                        text=f"CH {real_ch_idx + 1} - Offline", 
                        bg_color="#151515", 
                        font=("Arial", 14, "bold"),
                        text_color="#95A5A6"
                    )
                    lbl_vid.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
                    
                    lbl_vid.target_w = cell_w - 6
                    lbl_vid.target_h = cell_height - 6
                    lbl_vid.real_ch_idx = real_ch_idx
                    
                    self.video_labels.append(lbl_vid)
                    idx += 1

    def refresh_log_table(self):
        for child in self.table_scroll.winfo_children():
            child.destroy()
        try:
            sorted_dates = sorted(self.daily_logs.keys(), key=lambda d: datetime.datetime.strptime(d, "%d/%m/%Y"), reverse=True)
        except Exception:
            sorted_dates = sorted(self.daily_logs.keys(), reverse=True)
            
        for i, date_str in enumerate(sorted_dates):
            ch_data_dict = self.daily_logs[date_str]
            row_bg = "#243342" if i % 2 == 0 else "#2C3E50"
            row_frame = ctk.CTkFrame(self.table_scroll, fg_color=row_bg)
            row_frame.pack(fill="x", pady=3, padx=5)
            
            lbl_date = ctk.CTkLabel(row_frame, text=date_str, font=("Arial", 12, "bold"), text_color="#E67E22")
            lbl_date.pack(side="left", padx=12, pady=6)
            
            if isinstance(ch_data_dict, dict):
                sorted_ch_keys = sorted(ch_data_dict.keys())
                pairs = [f"{k}: {ch_data_dict[k]}P" for k in sorted_ch_keys]
                log_details_str = " | ".join(pairs)
            else:
                log_details_str = f"Total: {ch_data_dict} P"
                
            lbl_details = ctk.CTkLabel(row_frame, text=log_details_str, font=("Arial", 11), text_color="#2ECC71")
            lbl_details.pack(side="right", padx=15, pady=6)

    def start_all_channels(self):
        with self.lock:
            today_str = datetime.date.today().strftime("%d/%m/%Y")
            day_logs = self.daily_logs.get(today_str, {})
            
            for lbl in self.video_labels:
                ch_idx = lbl.real_ch_idx
                if not self.is_running_channels[ch_idx]:
                    self.is_running_channels[ch_idx] = True
                    self.stream_versions[ch_idx] += 1
                    
                    init_val = day_logs.get(f"CH_{ch_idx+1}", 0) if isinstance(day_logs, dict) else 0
                    self.people_counts[ch_idx] = init_val
                    self.inside_ids_pool[ch_idx].clear()
                    self.id_maps_pool[ch_idx].clear()
                    
                    t = threading.Thread(
                        target=self.process_single_channel_stream, 
                        args=(ch_idx, self.stream_versions[ch_idx], lbl), 
                        daemon=True
                    )
                    t.start()
            self.btn_master_start.configure(text="⚡ System Online Running...", fg_color="#27AE60")

    def stop_all_channels(self):
        with self.lock:
            # 1. ปิด Flags การทำงานของทุกกล้อง
            for i in range(MAX_CHANNELS):
                self.is_running_channels[i] = False
            
            # 2. รีเซ็ตหน้าจอ UI ทุกช่องโดยใช้เลขช่องที่ฝังไว้จริง (แก้ไขบั๊กสลับชื่อช่อง)
            for lbl in self.video_labels:
                try:
                    # ป้องกันเคสหน้าจอว่างเปล่า (No cameras enabled) ไม่มีค่า real_ch_idx
                    if hasattr(lbl, 'real_ch_idx'):
                        # ล้างภาพเก่าที่ค้างใน Cache ของ CustomTkinter ออกให้หมดจด
                        lbl.configure(image="")
                        if hasattr(lbl, "_image_cache"):
                            lbl._image_cache = None
                        
                        # 💡 ดึงเลขช่องที่ฝังไว้จริงจากตอน rebuild_monitor_grid ขึ้นมาแสดงผล (+1 เพื่อให้คนอ่านเข้าใจ)
                        real_num = lbl.real_ch_idx + 1
                        lbl.configure(text=f"CH {real_num} - Stream Stopped")
                except Exception as e:
                    print(f"Error resetting label: {e}")
            
            # 3. เปลี่ยนข้อความบนปุ่มหลักกลับเป็นสถานะพร้อมเริ่มทำงาน
            self.btn_master_start.configure(text="🚀 Start All Enabled Cameras", fg_color="#2980B9")

    def reload_all_channels(self):
        self.stop_all_channels()
        time.sleep(0.4)
        self.rebuild_monitor_grid()
        self.start_all_channels()

    # ==================== STREAM PROCESSING (DYNAMIC RE-SCALING AREA) ====================
    def process_single_channel_stream(self, ch_idx, current_v, target_label):
            ch_conf = self.channels_data[ch_idx]
            source = ch_conf["video_path"] if ch_conf["source_type"] == "video" else ch_conf["dvr_rtsp"]
            
            cap = cv2.VideoCapture(source)
            # ปรับ Buffer ให้ต่ำที่สุด เพื่อลดดีเลย์ภาพสด
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) 
            self.caps[ch_idx] = cap
            
            w_box = target_label.target_w
            h_box = target_label.target_h
            
            orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if orig_w == 0 or orig_h == 0:
                orig_w, orig_h = 1280, 720
                
            scale_orig_x = orig_w / 850.0
            scale_orig_y = orig_h / 550.0
            
            raw_poly_points = ch_conf.get("area_polygon", [])
            native_poly_points = [[int(pt[0] * scale_orig_x), int(pt[1] * scale_orig_y)] for pt in raw_poly_points]
            
            if len(native_poly_points) >= 3:
                poly_zone = Polygon(native_poly_points)
            else:
                poly_zone = None
                
            # ⚡ ตรวจสอบ Device และเตรียมค่าคงที่ไว้ล่วงหน้า (เช็คครั้งเดียวจบ ไม่ต้องเช็คใน Loop)
            import torch
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            use_half = True if dev == "cuda" else False  # ใช้ FP16 เฉพาะตอนรัน GPU เพื่อความเร็วสูงสุด
                
            frame_counter = 0
            last_boxes = []
            last_ids = []
            
            while cap.isOpened():
                if not self.is_running_channels[ch_idx] or current_v != self.stream_versions[ch_idx]:
                    break
                    
                # เคลียร์เฟรมตกค้างใน Buffer (สำหรับ RTSP เพื่อป้องกันภาพดีเลย์สะสม)
                if frame_counter % 2 == 0 and ch_conf["source_type"] != "video":
                    cap.grab()
                    
                ret, frame = cap.read()
                if not ret or frame is None:
                    if ch_conf["source_type"] == "video":
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        time.sleep(0.03)
                        continue
                    else:
                        time.sleep(1.0)
                        break
                
                frame_counter += 1
                
                # 🚀 ข้ามเฟรม (Frame Skipping) ทุกๆ 3 เฟรม เพื่อลดโหลดการประมวลผล AI
                if frame_counter % 3 == 0:
                    try:
                        # รัน Tracking พร้อมเปิด half=True (ถ้าใช้ CUDA) เพื่อเร่งความเร็วบน GPU
                        results = self.model.track(
                            frame, 
                            persist=True, 
                            classes=[0], 
                            verbose=False, 
                            imgsz=640,       # ขนาดกำลังดี (ถ้ายังกระตุก ลองลดเหลือ 512 หรือ 416)
                            conf=0.25,       
                            device=dev    
                        )
                        
                        if results and results[0].boxes is not None and results[0].boxes.id is not None:
                            # ดึงข้อมูลแปลงเป็น Numpy ทีเดียวเพื่อความเร็ว
                            last_boxes = results[0].boxes.xyxy.cpu().numpy()
                            last_ids = results[0].boxes.id.cpu().numpy().astype(int)
                        else:
                            last_boxes = []
                            last_ids = []
                    except Exception as e:
                        # ป้องกันเคส GPU Error หรือ CUDA Out of Memory ฉุกเฉิน
                        last_boxes = []
                        last_ids = []
                
                # วาดกรอบและคำนวณการตรวจนับ
                if poly_zone is not None and len(last_boxes) > 0:
                    for box, track_id in zip(last_boxes, last_ids):
                        x1, y1, x2, y2 = box
                        foot_x = int((x1 + x2) / 2)
                        foot_y = int(y2)
                        foot_point = Point(foot_x, foot_y)
                        
                        is_inside = poly_zone.contains(foot_point)
                        
                        if is_inside and track_id not in self.inside_ids_pool[ch_idx]:
                            self.inside_ids_pool[ch_idx].add(track_id)
                            self.people_counts[ch_idx] += 1
                            self.id_maps_pool[ch_idx][track_id] = self.people_counts[ch_idx]
                            
                            threading.Thread(target=self.save_daily_log, args=(ch_idx,), daemon=True).start()
                            self.after(0, self.refresh_log_table)
                            
                        if track_id in self.id_maps_pool[ch_idx]:
                            lbl_txt = f"CH{ch_idx+1} No.{self.id_maps_pool[ch_idx][track_id]}"
                        else:
                            lbl_txt = f"Detecting"
                            
                        color = (46, 204, 113) if is_inside else (231, 76, 60)
                        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                        cv2.putText(frame, lbl_txt, (int(x1), int(y1) - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                
                # วาดเส้นเขตแดน
                if len(native_poly_points) >= 3:
                    area_bgr = self.hex_to_bgr(ch_conf.get("area_color", DEFAULT_AREA_COLOR))
                    pts = np.array(native_poly_points, np.int32).reshape((-1, 1, 2))
                    cv2.polylines(frame, [pts], isClosed=True, color=area_bgr, thickness=3)

                # ย่อภาพลงมาแสดงผลในตาราง Grid
                frame = cv2.resize(frame, (w_box, h_box))
                
                # Banner
                cv2.rectangle(frame, (0, 0), (w_box, 25), (44, 62, 80), -1)
                cv2.putText(frame, f"CAM {ch_idx+1} | COUNTS: {self.people_counts[ch_idx]} P", 
                            (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (241, 196, 15), 1, cv2.LINE_AA)
                
                # ส่งภาพขึ้น Tkinter UI (แปลงช่องทางสีครั้งเดียวจบ)
                cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(cv2image)
                imgtk = ImageTk.PhotoImage(image=img)
                
                if self.is_running_channels[ch_idx] and current_v == self.stream_versions[ch_idx]:
                    target_label.configure(image=imgtk, text="")
                    target_label._image_cache = imgtk
                    
                # พัก Thread สั้นๆ เพื่อแบ่งทรัพยากรให้ GUI ทำงานได้ราบรื่น
                time.sleep(0.01)
                
            cap.release()

    # ==================== SETTING PANEL (UI RE-ARRANGED) ====================
    def setup_setting_page(self):
        # แผงอินพุตควบคุมด้านซ้าย
        frame_inputs = ctk.CTkFrame(self.tab_setting, width=440)
        frame_inputs.pack(side="left", fill="both", padx=10, pady=10)
        
        # แผงจอวิดีโอร่างพิกเซลด้านขวา
        frame_preview = ctk.CTkFrame(self.tab_setting)
        frame_preview.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        # 🚀 1. ส่วนเลือก Master AI Model (ย้ายมาไว้บนสุด เพื่อคุมภาพรวมทั้งระบบ)
        lbl_model_title = ctk.CTkLabel(frame_inputs, text="🎯 Master AI Model (Apply All Channels):", font=("Arial", 14, "bold"), text_color="#3498DB")
        lbl_model_title.pack(anchor="w", padx=20, pady=(10, 5))
        
        model_options = ["yolov8m", "yolov8s"]
        self.combo_model = ctk.CTkComboBox(
            frame_inputs, 
            values=model_options, 
            command=self.on_master_model_changed, 
            width=320, 
            font=("Arial", 13)
        )
        self.combo_model.pack(anchor="w", padx=30, pady=5)
        # เซ็ตค่าตามค่ากลางที่โหลดมาจาก config (fallback เป็น yolov8s)
        self.combo_model.set(getattr(self, 'global_model_name', "yolov8s"))
        
        # เส้นคั่นแบ่งสัดส่วนระหว่าง Global Settings กับ Channel Settings
        sep = ctk.CTkFrame(frame_inputs, height=2, fg_color="#34495E")
        sep.pack(fill="x", padx=20, pady=15)
        
        # 2. ส่วนเลือก Channel สำหรับตั้งค่ากล้องแต่ละตัว
        lbl_selector = ctk.CTkLabel(frame_inputs, text="Select Channel to Configure:", font=("Arial", 15, "bold"), text_color="#F1C40F")
        lbl_selector.pack(anchor="w", padx=20, pady=5)
        
        ch_options = [f"Channel {i+1}" for i in range(MAX_CHANNELS)]
        self.combo_ch = ctk.CTkComboBox(frame_inputs, values=ch_options, command=self.on_setting_channel_changed, width=320, font=("Arial", 13))
        self.combo_ch.pack(anchor="w", padx=30, pady=5)
        self.combo_ch.set("Channel 1")
        
        # ผูกตัวแปร Checkbox เข้ากับระบบ BooleanVar
        self.chk_enabled = ctk.CTkCheckBox(frame_inputs, text="Enable this Camera Channel in Grid Layout", variable=self.chk_enabled_var, font=("Arial", 12, "bold"), text_color="#2ECC71")
        self.chk_enabled.pack(anchor="w", padx=30, pady=10)
        
        lbl_src_title = ctk.CTkLabel(frame_inputs, text="Configure Video Source Info:", font=("Arial", 14, "bold"))
        lbl_src_title.pack(anchor="w", padx=20, pady=(15, 10))
        
        self.setting_radio_var = ctk.StringVar(value="video")
        self.rdo_v = ctk.CTkRadioButton(frame_inputs, text="Test with MP4 Video File", variable=self.setting_radio_var, value="video")
        self.rdo_v.pack(anchor="w", padx=40, pady=5)
        
        # โซนช่องกรอก Path วิดีโอพร้อมปุ่ม Browse เคียงข้างกันแบบสมดุล
        frame_browse = ctk.CTkFrame(frame_inputs, fg_color="transparent")
        frame_browse.pack(anchor="w", padx=55, pady=5, fill="x")
        
        self.txt_v_path = ctk.CTkEntry(frame_browse, width=230, font=("Arial", 12))
        self.txt_v_path.pack(side="left", padx=5)
        
        btn_browse = ctk.CTkButton(frame_browse, text="📁 Browse Video", command=self.browse_video_file, width=100, fg_color="#34495E", hover_color="#2C3E50")
        btn_browse.pack(side="left", padx=5)
        
        self.rdo_d = ctk.CTkRadioButton(frame_inputs, text="Enterprise DVR/NVR Line (RTSP)", variable=self.setting_radio_var, value="dvr")
        self.rdo_d.pack(anchor="w", padx=40, pady=5)
        
        self.txt_d_url = ctk.CTkEntry(frame_inputs, width=340, font=("Arial", 12))
        self.txt_d_url.pack(anchor="w", padx=60, pady=5)
        
        lbl_area_color_title = ctk.CTkLabel(frame_inputs, text="Area Zone Color / สีเขตพื้นที่:", font=("Arial", 14, "bold"))
        lbl_area_color_title.pack(anchor="w", padx=20, pady=(15, 5))
        
        frame_area_color = ctk.CTkFrame(frame_inputs, fg_color="transparent")
        frame_area_color.pack(anchor="w", padx=30, pady=5, fill="x")
        
        preset_labels = list(AREA_COLOR_PRESETS.keys()) + ["Custom / กำหนดเอง"]
        self.combo_area_color = ctk.CTkComboBox(
            frame_area_color,
            values=preset_labels,
            command=self.on_area_color_preset_changed,
            width=220,
            font=("Arial", 12)
        )
        self.combo_area_color.pack(side="left", padx=(0, 8))
        
        self.area_color_swatch = ctk.CTkFrame(frame_area_color, width=36, height=28, fg_color=DEFAULT_AREA_COLOR, corner_radius=6)
        self.area_color_swatch.pack(side="left", padx=4)
        self.area_color_swatch.pack_propagate(False)
        
        btn_pick_area_color = ctk.CTkButton(
            frame_area_color,
            text="🎨 Custom",
            command=self.pick_custom_area_color,
            width=90,
            fg_color="#34495E",
            hover_color="#2C3E50",
            font=("Arial", 11)
        )
        btn_pick_area_color.pack(side="left", padx=4)
        
        self.lbl_area_color_hex = ctk.CTkLabel(frame_inputs, text=DEFAULT_AREA_COLOR, font=("Arial", 11), text_color="#95A5A6")
        self.lbl_area_color_hex.pack(anchor="w", padx=30, pady=(0, 5))
        
        btn_save_config = ctk.CTkButton(frame_inputs, text="💾 Save Current Channel Settings", command=self.save_current_channel_settings, fg_color="#27AE60", hover_color="#1E8449", font=("Arial", 14, "bold"), height=42)
        btn_save_config.pack(anchor="w", padx=20, pady=25, fill="x")
        
        # 📌 จัดโครงสร้างฝั่งขวา: คู่มือ ปุ่ม Reset และหน้าจอวาดเรียงดิ่งลงข้างล่าง
        self.lbl_preview_title = ctk.CTkLabel(frame_preview, text="📌 Area Boundary Map Drawer View (CH 1)", font=("Arial", 14, "bold"), text_color="#3498DB")
        self.lbl_preview_title.pack(pady=5)
        
        self.preview_label = ctk.CTkLabel(frame_preview, text="", bg_color="#000000", width=850, height=550)
        self.preview_label.pack(padx=10, pady=5, expand=True)
        self.preview_label.bind("<Button-1>", self.on_preview_canvas_click)
        
        frame_under_layout = ctk.CTkFrame(frame_preview, fg_color="transparent")
        frame_under_layout.pack(fill="x", padx=15, pady=10)
        
        lbl_guide_txt = ctk.CTkLabel(frame_under_layout, text="💡 Guide: Click inside the Black Panel above to deploy point markers. 3+ points form a closed zone.", justify="left", font=("Arial", 11), text_color="#95A5A6")
        lbl_guide_txt.pack(side="left", padx=10)
        
        btn_clear_pt = ctk.CTkButton(frame_under_layout, text="🔄 Reset Zone / Clear Points", command=self.clear_current_channel_points, fg_color="#E74C3C", hover_color="#C0392B", font=("Arial", 12, "bold"), width=220)
        btn_clear_pt.pack(side="right", padx=10)
        
        self.update_channel_fields_in_gui(0)


    def on_master_model_changed(self, choice):
        print(f"Switching Master AI Model to: {choice}.pt")
        try:
            # 1. บันทึกค่าลงตัวแปรกลาง
            self.global_model_name = choice
            
            # 2. โหลดโมเดลใหม่เข้าสู่ระบบ
            from ultralytics import YOLO
            self.model = YOLO(f"{choice}.pt")
            
            # 3. ส่งเข้า Device (GPU/CPU)
            import torch
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            self.model.to(dev)
            
            # 4. บันทึกลงไฟล์ config.json ทันที
            self.save_multi_config()
            print(f"Master Model successfully changed and saved to {choice}.pt")
            
        except Exception as e:
            print(f"Error switching master model {choice}: {e}")

    def normalize_hex_color(self, hex_color, default=DEFAULT_AREA_COLOR):
        if not hex_color or not isinstance(hex_color, str):
            return default
        hex_color = hex_color.strip()
        if not hex_color.startswith("#"):
            hex_color = "#" + hex_color
        if len(hex_color) == 7:
            return hex_color.upper()
        return default

    def hex_to_bgr(self, hex_color):
        hex_color = self.normalize_hex_color(hex_color).lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (b, g, r)

    def preset_label_for_color(self, hex_color):
        normalized = self.normalize_hex_color(hex_color)
        for label, preset_hex in AREA_COLOR_PRESETS.items():
            if preset_hex.upper() == normalized:
                return label
        return None

    def set_area_color_ui(self, hex_color):
        hex_color = self.normalize_hex_color(hex_color)
        preset_label = self.preset_label_for_color(hex_color)
        if preset_label:
            self.combo_area_color.set(preset_label)
        else:
            self.combo_area_color.set("Custom / กำหนดเอง")
        self.area_color_swatch.configure(fg_color=hex_color)
        self.lbl_area_color_hex.configure(text=hex_color)

    def apply_area_color_to_channel(self, hex_color):
        hex_color = self.normalize_hex_color(hex_color)
        self.channels_data[self.current_setting_ch]["area_color"] = hex_color
        self.set_area_color_ui(hex_color)
        self.draw_channel_preview_canvas()

    def on_area_color_preset_changed(self, selected_label):
        if selected_label == "Custom / กำหนดเอง":
            return
        hex_color = AREA_COLOR_PRESETS.get(selected_label, DEFAULT_AREA_COLOR)
        self.apply_area_color_to_channel(hex_color)

    def pick_custom_area_color(self):
        current_hex = self.normalize_hex_color(
            self.channels_data[self.current_setting_ch].get("area_color", DEFAULT_AREA_COLOR)
        )
        rgb_tuple, hex_color = colorchooser.askcolor(color=current_hex, title="Select Area Zone Color")
        if hex_color:
            self.apply_area_color_to_channel(hex_color)

    def browse_video_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video Files", "*.mp4 *.avi *.mkv *.mov"), ("All Files", "*.*")]
        )
        if file_path:
            self.txt_v_path.delete(0, "end")
            self.txt_v_path.insert(0, file_path)

    def on_setting_channel_changed(self, selected_text):
        ch_idx = int(selected_text.split(" ")[1]) - 1
        self.current_setting_ch = ch_idx
        self.lbl_preview_title.configure(text=f"📌 Area Boundary Map Drawer View (CH {ch_idx + 1})")
        self.update_channel_fields_in_gui(ch_idx)

    def update_channel_fields_in_gui(self, ch_idx):
        ch_data = self.channels_data[ch_idx]
        
        # ดึงและอัปเดตค่าเข้าตัวแปร Checkbox State
        self.chk_enabled_var.set(ch_data.get("enabled", False))
        self.setting_radio_var.set(ch_data["source_type"])
        self.txt_v_path.delete(0, "end")
        self.txt_v_path.insert(0, ch_data["video_path"])
        self.txt_d_url.delete(0, "end")
        self.txt_d_url.insert(0, ch_data["dvr_rtsp"])
        
        if "area_color" not in ch_data:
            ch_data["area_color"] = DEFAULT_AREA_COLOR
        self.set_area_color_ui(ch_data["area_color"])
        
        self.draw_channel_preview_canvas()

    def on_preview_canvas_click(self, event):
        x = event.x
        y = event.y
        self.channels_data[self.current_setting_ch]["area_polygon"].append([x, y])
        self.draw_channel_preview_canvas()

    def clear_current_channel_points(self):
        self.channels_data[self.current_setting_ch]["area_polygon"] = []
        self.draw_channel_preview_canvas()

    def draw_channel_preview_canvas(self):
        preview_img = np.zeros((550, 850, 3), dtype=np.uint8) + 30
        for i in range(0, 850, 100):
            cv2.line(preview_img, (i, 0), (i, 550), (45, 45, 45), 1)
        for j in range(0, 550, 100):
            cv2.line(preview_img, (0, j), (850, j), (45, 45, 45), 1)
            
        poly_pts = self.channels_data[self.current_setting_ch].get("area_polygon", [])
        area_bgr = self.hex_to_bgr(
            self.channels_data[self.current_setting_ch].get("area_color", DEFAULT_AREA_COLOR)
        )
        
        if len(poly_pts) > 0:
            for idx, pt in enumerate(poly_pts):
                cv2.circle(preview_img, (pt[0], pt[1]), 6, (231, 76, 60), -1)
                cv2.putText(preview_img, f"P{idx+1}", (pt[0]+7, pt[1]-4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            
            if len(poly_pts) >= 2:
                pts = np.array(poly_pts, np.int32).reshape((-1, 1, 2))
                is_closed = True if len(poly_pts) >= 3 else False
                cv2.polylines(preview_img, [pts], isClosed=is_closed, color=area_bgr, thickness=3)
                if is_closed:
                    overlay = preview_img.copy()
                    cv2.fillPoly(overlay, [pts], color=area_bgr)
                    cv2.addWeighted(overlay, 0.25, preview_img, 0.75, 0, preview_img)
        else:
            cv2.putText(preview_img, f"Click inside grid to draw Boundary points for CH {self.current_setting_ch + 1}", 
                        (140, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (130, 130, 130), 2)

        img = Image.fromarray(cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB))
        imgtk = ImageTk.PhotoImage(image=img)
        self.preview_label.configure(image=imgtk)
        self.preview_label._image_cache = imgtk

    def save_current_channel_settings(self):
        ch_idx = self.current_setting_ch
        
        # 1. ดึงค่าบันทึกลงคอนฟิก
        self.channels_data[ch_idx]["enabled"] = self.chk_enabled_var.get()
        self.channels_data[ch_idx]["source_type"] = self.setting_radio_var.get()
        self.channels_data[ch_idx]["video_path"] = self.txt_v_path.get()
        self.channels_data[ch_idx]["dvr_rtsp"] = self.txt_d_url.get()
        self.channels_data[ch_idx]["area_color"] = self.normalize_hex_color(
            self.channels_data[ch_idx].get("area_color", DEFAULT_AREA_COLOR)
        )
        
        if len(self.channels_data[ch_idx]["area_polygon"]) < 3:
            self.channels_data[ch_idx]["area_polygon"] = [[100, 100], [700, 100], [700, 450], [100, 450]]
            
        self.save_multi_config()
        
        # 2. บังคับเคลียร์ Thread เก่า และสั่งขึ้นข้อความ Stream Stopped รอไว้
        self.stop_all_channels()
        time.sleep(0.2)
        
        # 3. เรียกใช้งาน CTkToast แจ้งเตือนสวย ๆ (ผู้ใช้จะยังอยู่ที่หน้าตั้งค่าเดิม)
        CTkToast(self, message="💾 บันทึกตั้งค่ากล้องสำเร็จเรียบร้อยแล้ว!")
    # ==================== BACKGROUND OPERATIONS ====================
    def setup_tray(self):
        icon_image = Image.new('RGB', (64, 64), color=(41, 128, 185))
        menu = (
            item('Open App GUI Panel (แสดงหน้าโปรแกรม)', self.show_from_background),
            item('Exit Entire Program (ปิดโปรแกรมถาวร)', self.quit_program)
        )
        self.tray_icon = pystray.Icon("cctv_multi_monitor", icon_image, "CCTV Multi-Channel AI System", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def withdraw_to_background(self):
        self.withdraw()

    def show_from_background(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def quit_program(self):
        with self.lock:
            for i in range(MAX_CHANNELS):
                self.is_running_channels[i] = False
        self.tray_icon.stop()
        self.destroy()
        os._exit(0)

if __name__ == "__main__":
    app = CCTVApp()
    app.mainloop()