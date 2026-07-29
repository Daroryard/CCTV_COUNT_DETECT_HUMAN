# CCTV Multi-Channel AI Analytics

ระบบตรวจนับคนด้วย YOLOv8 รองรับหลายช่องกล้อง (สูงสุด 4 ช่อง) พร้อม GUI สำหรับ Live Monitor, ตั้งค่าเขตพื้นที่ (Polygon Zone), และบันทึก Log รายวัน

---

## ความสามารถหลัก

- รองรับ **4 ช่องกล้อง** พร้อมกัน (Grid 1024×768)
- แหล่งวิดีโอ: **ไฟล์ MP4** หรือ **RTSP (DVR/NVR)**
- ตรวจจับและนับคนด้วย **YOLOv8 + Object Tracking**
- วาด **เขตพื้นที่ (Area Zone)** บนหน้า Settings ด้วยการคลิกจุด
- เลือก **สีเขตพื้นที่** ได้ (Preset + Custom Color Picker)
- บันทึกจำนวนคนรายวันต่อช่องใน `log.json`
- ย่อหน้าต่างไป **System Tray** ทำงานเบื้องหลังได้

---

## ความต้องการของระบบ

| รายการ | รายละเอียด |
|--------|------------|
| OS | Windows 10/11 (แนะนำ) |
| Python | 3.10 – 3.12 |
| RAM | 8 GB ขึ้นไป (16 GB แนะนำเมื่อเปิดหลายช่อง) |
| GPU | ไม่บังคับ — มี NVIDIA + CUDA จะเร็วขึ้น (Ultralytics ใช้ CUDA อัตโนมัติถ้ามี) |
| ไฟล์ Model | `yolov8n.pt` (ดาวน์โหลดอัตโนมัติครั้งแรก หรือวางไว้ในโฟลเดอร์รัน) |

---

## โครงสร้างโปรเจกต์

```
cctv-yolo-project/
├── README.md
├── requirements.txt
├── command_build.bat          # สคริปต์ build เป็น .exe
├── source_code/
│   ├── cctv_app.py            # โปรแกรมหลัก
│   ├── multi_config.json      # ค่าตั้งค่าทุกช่องกล้อง
│   ├── log.json               # Log จำนวนคนรายวัน
│   ├── yolov8n.pt             # โมเดล YOLO (ต้องมีตอนรัน/build)
│   ├── test.mp4               # วิดีโอทดสอบ (ถ้ามี)
│   ├── test1.mp4
│   └── cctv-camera.ico        # ไอคอนสำหรับ build (ถ้ามี)
├── build/                     # ไฟล์ชั่วคราวจาก PyInstaller
└── dist/                      # ไฟล์ .exe หลัง build สำเร็จ
```

---

## ติดตั้ง (Development)

### 1. ติดตั้ง Python

ดาวน์โหลดจาก [python.org](https://www.python.org/downloads/) แล้วติ๊ก **Add Python to PATH** ตอนติดตั้ง

ตรวจสอบ:

```powershell
py --version
```

### 2. สร้าง Virtual Environment (แนะนำ)

```powershell
cd c:\project\Python\cctv-yolo-project
py -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. ติดตั้ง Library

```powershell
pip install -r requirements.txt
```

หรือติดตั้ง:

```powershell
pip install opencv-python customtkinter Pillow ultralytics shapely numpy pystray 
python -m pip install opencv-python customtkinter Pillow ultralytics shapely numpy pystray pyinstaller
```
### 4. Library ที่ใช้ในโปรเจกต์

| Library | ใช้ทำอะไร |
|---------|-----------|
| `opencv-python` | อ่านวิดีโอ/กล้อง, วาดกรอบและ Polygon |
| `customtkinter` | UI หลัก (Dark Theme) |
| `Pillow` | แปลงภาพสำหรับแสดงบน Tkinter |
| `ultralytics` | YOLOv8 ตรวจจับและ Track คน |
| `shapely` | ตรวจว่าจุดเท้าอยู่ในเขต Polygon หรือไม่ |
| `numpy` | ประมวลผลพิกัดภาพ |
| `pystray` | ไอคอน System Tray |
| `torch` | ติดตั้งมากับ `ultralytics` อัตโนมัติ |
| `pyinstaller` | ใช้เฉพาะตอน build เป็น `.exe` |

> **GPU (CUDA):** ถ้าต้องการใช้ NVIDIA GPU ให้ติดตั้ง [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads) และติดตั้ง PyTorch รุ่น CUDA ตาม [pytorch.org](https://pytorch.org/) ก่อนหรือหลัง `pip install ultralytics`

---

## วิธีรันโปรแกรม

```powershell
cd c:\project\Python\cctv-yolo-project\source_code
py cctv_app.py
```

ไฟล์ที่ต้องอยู่ในโฟลเดอร์ `source_code` ตอนรัน:

- `cctv_app.py`
- `multi_config.json`
- `yolov8s.pt` (ถ้ายังไม่มี Ultralytics จะพยายามดาวน์โหลดให้)
- ไฟล์วิดีโอที่อ้างใน config เช่น `test.mp4`

---

## วิธีใช้งาน

### แท็บ Live Monitor

1. กด **Start All Enabled Cameras** เพื่อเริ่ม stream ทุกช่องที่เปิดใช้งาน
2. กด **Stop All Monitor Streams** เพื่อหยุด
3. กด **Safe Sync & Reload All Streams** เพื่อโหลด config ใหม่
4. กด **Run Background** เพื่อซ่อนหน้าต่างไป System Tray

### แท็บ Multi-Channel Settings

1. เลือก **Channel** ที่ต้องการตั้งค่า
2. ติ๊ก **Enable** ถ้าต้องการให้แสดงใน Grid
3. เลือกแหล่งวิดีโอ: **MP4** หรือ **RTSP URL**
4. คลิกบน panel ดำเพื่อวางจุดเขตพื้นที่ (อย่างน้อย 3 จุด)
5. เลือก **สีเขตพื้นที่** จาก dropdown หรือปุ่ม **Custom**
6. กด **Save Current Channel Settings**

---

## ไฟล์ Config

### `multi_config.json`

เก็บค่าต่อช่อง เช่น:

```json
{
  "ch_index": 0,
  "enabled": true,
  "source_type": "video",
  "video_path": "test.mp4",
  "dvr_rtsp": "rtsp://admin:password@192.168.1.100:554/stream1",
  "area_polygon": [[100, 100], [700, 100], [700, 450], [100, 450]],
  "area_color": "#3498DB"
}
```

| Field | ความหมาย |
|-------|----------|
| `enabled` | เปิด/ปิดช่องใน Grid |
| `source_type` | `"video"` หรือ `"dvr"` |
| `video_path` | path ไฟล์วิดีโอ |
| `dvr_rtsp` | URL RTSP |
| `area_polygon` | จุด polygon บน canvas 850×550 |
| `area_color` | สีเขต (Hex เช่น `#3498DB`) |

### `log.json`

บันทึกจำนวนคนที่นับได้แยกตามวันและช่อง เช่น `"CH_1": 42`

---

## Build เป็นไฟล์ .exe (Windows)

1. ติดตั้ง PyInstaller:

```powershell
pip install pyinstaller
```

2. เตรียมไฟล์ใน `source_code/`:

   - `yolov8s.pt`
   - `yolov8m.pt`
   - `multi_config.json`
   - `test.mp4`, `test1.mp4` (ถ้าใช้ทดสอบ)
   - `cctv-camera.ico` (ไอคอน)

3. รัน build:

```powershell
command_build.bat
```

หรือ build ด้วยมือ:

```powershell
cd source_code
py -m PyInstaller --onefile --windowed --icon=cctv-camera.ico --distpath=..\dist --name=CCTV_AI_Analytics cctv_app.py
```

> **หมายเหตุ:** `command_build.bat` อ้าง `main.py` — ถ้าไม่มีไฟล์นั้น ให้เปลี่ยนเป็น `cctv_app.py` ตามคำสั่งด้านบน

4. หลัง build สำเร็จ ไฟล์จะอยู่ใน `dist/` พร้อม resource ที่ copy ไว้

---

## แก้ปัญหาเบื้องต้น

| อาการ | วิธีแก้ |
|-------|--------|
| `python` / `py` ไม่รู้จัก | ติดตั้ง Python ใหม่และติ๊ก Add to PATH |
| เปิดวิดีโอไม่ได้ | ตรวจ path ใน Settings และว่าไฟล์อยู่จริง |
| RTSP ไม่ขึ้น | ตรวจ URL, user/password, และ network/firewall |
| ช้ามาก / CPU 100% | ลดจำนวนช่องที่เปิด หรือใช้ GPU + CUDA |
| ไม่มี `yolov8s.pt` | รันโปรแกรมครั้งแรกให้ดาวน์โหลด หรือ copy ไฟล์ model มาวาง |
| CustomTkinter ไม่ขึ้น UI | `pip install --upgrade customtkinter` |

---

## License / Model

- โค้ดโปรเจกต์: ใช้งานภายในตามที่ทีมกำหนด
- โมเดล **YOLOv8** จาก [Ultralytics](https://github.com/ultralytics/ultralytics) — อ่าน license ของ Ultralytics ก่อนใช้งานเชิงพาณิชย์

---

## ผู้พัฒนา

Enterprise Multi-CCTV AI Analytics — Fixed System V3
