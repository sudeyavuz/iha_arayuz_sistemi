import sys
import random
import os
import serial
import struct
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

# ================= CRSF ALICI THREAD'İ =================
class CRSFReceiver(QThread):
    telemetry_updated = Signal(dict)

    def __init__(self, port='/dev/cu.usbserial-0001', baudrate=420000):
        # macOS için varsayılan port adını "/dev/cu.usbserial-..." formatında bıraktım.
        # Kendi adaptörüne göre port adını güncelleyebilirsin.
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.running = True
        
        self.data = {
            'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0,
            'lat': 39.123456, 'lon': 32.987654, 'alt': 0.0, 'speed': 0.0,
            'batt_v': 0.0, 'batt_a': 0.0, 'cap': 0
        }

    def run(self):
        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"{self.port} portuna bağlanıldı. CRSF verisi bekleniyor...")
            
            while self.running:
                if ser.in_waiting > 0:
                    sync = ser.read(1)
                    if sync == b'\xc8':
                        length_byte = ser.read(1)
                        if length_byte:
                            length = ord(length_byte)
                            if 0 < length <= 64:
                                payload = ser.read(length)
                                self.parse_frame(payload)
                                self.telemetry_updated.emit(self.data)
                                
        except serial.SerialException as e:
            print(f"Seri Port Hatası (Alıcı bağlı olmayabilir): {e}")

    def parse_frame(self, payload):
        if len(payload) < 2: return
        
        frame_type = payload[0]
        data_bytes = payload[1:-1] 
        
        try:
            if frame_type == 0x02 and len(data_bytes) >= 14: # GPS
                lat, lon, speed, heading, alt, sats = struct.unpack('>iiHhHH', data_bytes[:14])
                self.data['lat'] = lat / 10000000.0
                self.data['lon'] = lon / 10000000.0
                self.data['speed'] = speed / 36.0 
                self.data['alt'] = alt - 1000 
                
            elif frame_type == 0x08 and len(data_bytes) >= 7: # Batarya
                v, a, cap = struct.unpack('>HHH', data_bytes[:6])
                self.data['batt_v'] = v / 10.0
                self.data['batt_a'] = a / 10.0
                self.data['cap'] = cap
                
            elif frame_type == 0x1E and len(data_bytes) >= 6: # Tutum (Attitude)
                pitch, roll, yaw = struct.unpack('>hhh', data_bytes[:6])
                self.data['pitch'] = pitch / 10000.0 * 57.2958
                self.data['roll'] = roll / 10000.0 * 57.2958
                self.data['yaw'] = yaw / 10000.0 * 57.2958
                
        except Exception:
            pass 

    def stop(self):
        self.running = False
        self.wait()


# ================= ÖZEL ÇİZİM WIDGET'LARI =================
class CameraView(QWidget):
    def __init__(self):
        super().__init__()
        file_name = "kamera.jpg" 
        if os.path.exists(file_name):
            self.bg_pixmap = QPixmap(file_name)
        else:
            self.bg_pixmap = QPixmap()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if not self.bg_pixmap.isNull():
            scaled_pixmap = self.bg_pixmap.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(0, 0, scaled_pixmap)
        else:
            painter.fillRect(0, 0, w, h, QColor("#090c10"))
            painter.setPen(Qt.white)
            painter.drawText(self.rect(), Qt.AlignCenter, "Resim Bulunamadı")

class TacticalMap(QWidget):
    def __init__(self, state_dict):
        super().__init__()
        self.state = state_dict 

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        
        painter.fillRect(0, 0, w, h, QColor("#ffffff"))
        painter.setPen(QPen(QColor("#f0f0f0"), 1))
        for i in range(0, w, 40): painter.drawLine(i, 0, i, h)
        for i in range(0, h, 40): painter.drawLine(0, i, w, i)

        cx, cy = w // 2, h // 2
        scale = 150 

        avci_x, avci_y = cx - 50, cy + 50
        target_dist_px = self.state['dist'] * scale
        target_x = avci_x + target_dist_px
        target_y = avci_y - target_dist_px

        pen = QPen(QColor("#8b949e"), 2, Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(avci_x, avci_y, target_x, target_y)

        mid_x, mid_y = int((avci_x + target_x) / 2), int((avci_y + target_y) / 2)
        painter.setPen(QColor("#21262d"))
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(mid_x + 10, mid_y, f"{self.state['dist']:.2f} km")

        painter.setBrush(QColor("#1f6feb"))
        painter.setPen(QPen(Qt.white, 1))
        avci_poly = QPolygon([
            QPoint(avci_x, avci_y - 12),
            QPoint(avci_x - 8, avci_y + 8),
            QPoint(avci_x + 8, avci_y + 8)
        ])
        t = QTransform()
        t.translate(avci_x, avci_y)
        t.rotate(self.state['yaw'])
        t.translate(-avci_x, -avci_y)
        painter.setTransform(t)
        painter.drawPolygon(avci_poly)
        painter.resetTransform()
        
        painter.setPen(QColor("#1f6feb"))
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        painter.drawText(avci_x - 15, avci_y + 22, "AVCI")

        painter.setBrush(QColor("#f85149"))
        painter.setPen(QPen(Qt.white, 1))
        target_rect = QRect(int(target_x - 8), int(target_y - 8), 16, 16)
        painter.drawRect(target_rect)
        painter.setPen(QColor("#f85149"))
        painter.drawText(int(target_x - 25), int(target_y - 12), "HEDEF")

class ArtificialHorizon(QWidget):
    def __init__(self):
        super().__init__()
        self.roll = 0
        self.pitch = 0

    def update_attitude(self, roll, pitch):
        self.roll, self.pitch = roll, pitch
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        radius = min(w, h) // 2 + 5
        path = QPainterPath()
        path.moveTo(cx - radius, cy)
        path.arcTo(cx - radius, cy - radius, radius * 2, radius * 2, 180, -180)
        path.lineTo(cx + radius, cy + radius)
        path.lineTo(cx - radius, cy + radius)
        painter.setClipPath(path)

        painter.translate(cx, cy)
        painter.rotate(-self.roll)
        painter.translate(0, self.pitch * 2)

        painter.fillRect(-w, -h*2, w*2, h*2, QColor("#1f6feb"))
        painter.fillRect(-w, 0, w*2, h*2, QColor("#8c564b"))
        painter.setPen(QPen(Qt.white, 2))
        painter.drawLine(-w, 0, w, 0)

        painter.resetTransform()
        painter.setClipping(False)
        
        painter.setPen(QPen(QColor("#8b949e"), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(cx - radius, cy - radius, radius * 2, radius * 2, 0 * 16, 180 * 16)
        
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        painter.drawText(cx - radius - 25, cy + 5, "-60°")
        painter.drawText(cx - 5, cy - radius - 5, "0°")
        painter.drawText(cx + radius + 5, cy + 5, "+60°")

        painter.setPen(QPen(QColor("#11161d"), 3))
        painter.drawLine(cx - 20, cy, cx + 20, cy)
        painter.setPen(QPen(QColor("#3fb950"), 2))
        painter.drawLine(cx - 20, cy, cx + 20, cy)
        painter.drawLine(cx, cy - 8, cx, cy + 4)

class MissionStages(QWidget):
    def __init__(self):
        super().__init__()
        self.stages = ["KALKIŞ", "ARAMA", "TAKİP", "GÜDÜM", "ANGAJMAN"]
        self.current_stage = 2

    def update_stage(self, stage):
        self.current_stage = stage
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        margin = 35
        y = h // 2 - 5
        step = (w - 2 * margin) / max(1, len(self.stages) - 1)

        painter.setPen(QPen(QColor("#30363d"), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(margin, y, w - margin, y)

        active_x = margin + self.current_stage * step
        painter.setPen(QPen(QColor("#3fb950"), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(margin, y, int(active_x), y)

        for i, stage in enumerate(self.stages):
            cx = margin + i * step
            
            if i < self.current_stage:
                color = QColor("#3fb950")
                bg = QColor("#12331b")
            elif i == self.current_stage:
                color = QColor("#58a6ff")
                bg = QColor("#0d2b4f")
            else:
                color = QColor("#8b949e")
                bg = QColor("#090c10")

            painter.setBrush(bg)
            painter.setPen(QPen(color, 2))
            painter.drawEllipse(int(cx) - 8, y - 8, 16, 16)

            if i == self.current_stage:
                painter.setBrush(color)
                painter.drawEllipse(int(cx) - 4, y - 4, 8, 8)

            painter.setFont(QFont("Arial", 8, QFont.Bold))
            painter.setPen(color)
            fm = QFontMetrics(painter.font())
            tw = fm.horizontalAdvance(stage)
            painter.drawText(int(cx - tw/2), int(y + 22), stage)

# ================= ANA ARAYÜZ =================
class GCS(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AVCI DRONE YKİ - CRSF")
        self.resize(1600, 900)
        self.setStyleSheet("background-color: #010409; color: #c9d1d9; font-family: Arial;")
        
        # Arayüz state verileri (Uçuş verileri CRSF'ten gelecek, diğerleri GCS tarafından yönetilir)
        self.state = {
            'speed': 0.0, 'alt': 0.0, 'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0,
            'lat': 39.123456, 'lon': 32.987654, 'batt_v': 22.4, 'temp': 54,
            'dist': 1.25, 'target_speed': 15.0, 'impact_timer': 24.10,
            'yolo_delay': 38, 'auto_delay': 76, 'total_delay': 114,
            'gcs_cpu': 32, 'gcs_gpu': 45, 'gcs_ram': 58, 'mission_stage': 2
        }

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 5, 10, 10)
        
        main_layout.addWidget(self.create_top_bar())

        # ---- ÜST YERLEŞİM (TOP ROW) ----
        top_row = QHBoxLayout()
        self.cam_card = self.create_cam_card()
        self.map_card = self.create_map_card()
        
        top_right_panel = QVBoxLayout()
        self.status_card = self.create_status_card()
        self.gcs_card = self.create_gcs_card()
        self.mission_card = self.create_mission_card()
        
        # Sıralama güncellendi: Sistem Durumu, Yer İstasyonu Bilgileri, Görev Aşamaları
        top_right_panel.addWidget(self.status_card, 2)
        top_right_panel.addWidget(self.gcs_card, 3)
        top_right_panel.addWidget(self.mission_card, 3)

        top_row.addWidget(self.cam_card, 7)
        top_row.addWidget(self.map_card, 9)   
        top_row.addLayout(top_right_panel, 4)

        # ---- ALT YERLEŞİM (BOTTOM ROW) ----
        bottom_row = QHBoxLayout()
        
        bottom_left_panel = QVBoxLayout()
        self.drone_sys_card = self.create_drone_sys_card()
        self.delay_card = self.create_delay_card()
        bottom_left_panel.addWidget(self.drone_sys_card, 2)
        bottom_left_panel.addWidget(self.delay_card, 3)

        self.horizon_card = self.create_horizon_card()

        bottom_right_panel = QHBoxLayout()
        self.telemetry_card = self.create_telemetry_card()
        
        br_far_right = QVBoxLayout()
        self.mode_card = self.create_mode_card()
        self.guidance_card = self.create_guidance_card()
        br_far_right.addWidget(self.mode_card, 1)
        br_far_right.addWidget(self.guidance_card, 3)
        
        bottom_right_panel.addWidget(self.telemetry_card, 4)
        bottom_right_panel.addLayout(br_far_right, 2)

        bottom_row.addLayout(bottom_left_panel, 5)
        bottom_row.addWidget(self.horizon_card, 5)
        bottom_row.addLayout(bottom_right_panel, 9)

        main_layout.addLayout(top_row, 7)
        main_layout.addLayout(bottom_row, 3)
        main_layout.addWidget(self.create_bottom_bar(), 1)

        # CRSF Thread Başlatma
        self.crsf_thread = CRSFReceiver()
        self.crsf_thread.telemetry_updated.connect(self.on_telemetry_received)
        self.crsf_thread.start()

        # Sensör dışı (YOLO, GCS yükü vb.) arayüz verilerini güncellemek için yavaş zamanlayıcı
        self.slow_timer = QTimer()
        self.slow_timer.timeout.connect(self.update_mock_system_data)
        self.slow_timer.start(400)  

    def base_card(self, title):
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; }")
        l = QVBoxLayout(frame)
        l.setContentsMargins(8, 8, 8, 8)
        t = QLabel(title)
        t.setStyleSheet("border: none; color: #8b949e; font-weight: bold; font-size: 11px;")
        l.addWidget(t)
        return frame, l

    def create_top_bar(self):
        w = QWidget()
        w.setFixedHeight(30)
        l = QHBoxLayout(w)
        l.setContentsMargins(5, 0, 5, 0)
        title = QLabel("🚁 AVCI DRONE YKİ")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #c9d1d9;")
        status = QLabel("📶 Bağlantı: İyi   🛰️ GPS: 3D Fix")
        status.setStyleSheet("color:#3fb950; font-weight:bold;")
        self.clock = QLabel("Saat: 00:00:00")
        l.addWidget(title); l.addStretch(); l.addWidget(status); l.addSpacing(20); l.addWidget(self.clock)
        return w

    def create_cam_card(self):
        frame, l = self.base_card("📷 KAMERA & TESPİT")
        l.addWidget(CameraView(), 1)
        info = QLabel("YOLO: Kilitli 🔒")
        info.setStyleSheet("color:#3fb950; border:none; font-size: 11px;")
        l.addWidget(info)
        return frame

    def create_map_card(self):
        frame, l = self.base_card("🗺️ TAKTİK HARİTA")
        self.map_view = TacticalMap(self.state) 
        l.addWidget(self.map_view, 1)
        btn_layout = QHBoxLayout()
        btn_start = QPushButton("▶ Görev Başlat")
        btn_start.setStyleSheet("background: #12331b; color: #3fb950; border: 1px solid #238636; border-radius: 4px; padding: 4px; font-weight:bold;")
        btn_expand = QPushButton("⛶ Haritayı Büyüt")
        btn_expand.setStyleSheet("background: #0d2b4f; color: #58a6ff; border: 1px solid #1f6feb; border-radius: 4px; padding: 4px; font-weight:bold;")
        btn_expand.clicked.connect(self.toggle_map)
        btn_layout.addWidget(btn_start); btn_layout.addWidget(btn_expand)
        l.addLayout(btn_layout)
        return frame

    def create_telemetry_card(self):
        frame, l = self.base_card("📊 TELEMETRİ & DURUM")
        self.tel_lbl = QLabel()
        self.tel_lbl.setStyleSheet("border: none;")
        l.addWidget(self.tel_lbl)
        
        bottom_w = QWidget()
        bottom_l = QVBoxLayout(bottom_w)
        bottom_l.setContentsMargins(0,0,0,0)
        bottom_l.setSpacing(2)
        self.distance_lbl = QLabel("HEDEFE MESAFE: 1.25 km")
        self.distance_lbl.setStyleSheet("color:#d29922; font-size:12px; font-weight:bold; border:none;")
        bottom_l.addWidget(self.distance_lbl)
        self.time_bar = QProgressBar()
        self.time_bar.setMaximum(100); self.time_bar.setValue(70); self.time_bar.setTextVisible(False); self.time_bar.setFixedHeight(6)
        self.time_bar.setStyleSheet("QProgressBar { background:#21262d; border:none; border-radius:3px;} QProgressBar::chunk { background:#3fb950; border-radius:3px;}")
        bottom_l.addWidget(self.time_bar)
        self.time_lbl = QLabel("Kalan Uçuş Süresi: 24 sn"); self.time_lbl.setStyleSheet("color:#8b949e; border:none; font-size:10px;")
        bottom_l.addWidget(self.time_lbl)
        l.addWidget(bottom_w)
        return frame

    def create_mode_card(self):
        frame, l = self.base_card("✈️ UÇUŞ MODU")
        mode = QLabel("✈️\nANGLE MOD\n(Açı Modu)")
        mode.setAlignment(Qt.AlignCenter)
        mode.setStyleSheet("border: 1px solid #1f6feb; background: #0d2b4f; color: #58a6ff; font-weight: bold; font-size:11px; border-radius:4px; padding:2px;")
        l.addWidget(mode)
        return frame

    def create_guidance_card(self):
        frame, l = self.base_card("🎯 GÜDÜM KARARI")
        self.guide_lbl = QLabel()
        self.guide_lbl.setStyleSheet("border: none;")
        l.addWidget(self.guide_lbl)
        l.addStretch()
        self.last_decision = QLabel("TAKİP")
        self.last_decision.setAlignment(Qt.AlignCenter)
        self.last_decision.setFixedHeight(30)
        self.last_decision.setStyleSheet("background:#12331b; color:#3fb950; font-size:13px; font-weight:bold; border:1px solid #238636; border-radius:4px;")
        l.addWidget(self.last_decision)
        return frame

    def create_drone_sys_card(self):
        frame, l = self.base_card("⚙️ İHA SİSTEM")
        self.drone_bars = {}
        def add_row(lbl_text, color):
            row = QHBoxLayout()
            lbl = QLabel(lbl_text); lbl.setStyleSheet("border:none; color:#8b949e; font-size:11px;"); lbl.setFixedWidth(50)
            pb = QProgressBar(); pb.setFixedHeight(8); pb.setTextVisible(False)
            pb.setStyleSheet(f"QProgressBar {{ border:none; background:#21262d; border-radius:4px; }} QProgressBar::chunk {{ background-color:{color}; border-radius:4px; }}")
            val = QLabel("0"); val.setStyleSheet("border:none; color:#c9d1d9; font-size:11px; font-weight:bold;"); val.setFixedWidth(35)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(lbl); row.addWidget(pb); row.addWidget(val)
            l.addLayout(row)
            return pb, val

        self.drone_bars['batt'] = add_row("Batarya:", "#3fb950")
        self.drone_bars['temp'] = add_row("Sıcaklık:", "#d29922")
        return frame

    def create_delay_card(self):
        frame, l = self.base_card("⏱️ GECİKME DEĞERLERİ")
        hl = QHBoxLayout()
        hl.setSpacing(5)
        def create_val(title, color):
            w = QWidget()
            w.setStyleSheet(f"background: #090c10; border: 1px solid #21262d; border-radius: 4px;")
            vl = QVBoxLayout(w); vl.setAlignment(Qt.AlignCenter); vl.setContentsMargins(4,4,4,4)
            t = QLabel(title); t.setStyleSheet("color: #8b949e; font-size: 10px; font-weight: bold; border: none;"); t.setAlignment(Qt.AlignCenter)
            val = QLabel("0 ms"); val.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold; border: none;"); val.setAlignment(Qt.AlignCenter)
            vl.addWidget(t); vl.addWidget(val)
            return w, val
        w1, self.val_yolo = create_val("YOLO", "#3fb950")
        w2, self.val_auto = create_val("OTONOM", "#d29922")
        w3, self.val_total = create_val("TOPLAM", "#f85149")
        hl.addWidget(w1); hl.addWidget(w2); hl.addWidget(w3)
        l.addLayout(hl)
        return frame

    def create_horizon_card(self):
        frame, l = self.base_card("✈️ AÇI DURUM GÖSTERGESİ")
        self.horizon = ArtificialHorizon()
        self.att_lbl = QLabel("ROLL: 0°   PITCH: 0°   YAW: 0°")
        self.att_lbl.setAlignment(Qt.AlignCenter)
        self.att_lbl.setStyleSheet("border: none; color: #8b949e; font-size: 11px;")
        l.addWidget(self.horizon); l.addWidget(self.att_lbl)
        return frame

    def create_mission_card(self):
        frame, l = self.base_card("🚀 GÖREV AŞAMALARI")
        self.mission_view = MissionStages()
        l.addWidget(self.mission_view)
        return frame

    def create_gcs_card(self):
        frame, l = self.base_card("💻 YER İSTASYONU BİLGİLERİ")
        hl = QHBoxLayout()
        hl.setSpacing(8)
        
        def create_val(title, color):
            w = QWidget()
            w.setStyleSheet(f"background: #090c10; border: 1px solid #21262d; border-radius: 4px;")
            vl = QVBoxLayout(w); vl.setAlignment(Qt.AlignCenter); vl.setContentsMargins(4,8,4,8)
            t = QLabel(title); t.setStyleSheet("color: #8b949e; font-size: 10px; font-weight: bold; border: none;"); t.setAlignment(Qt.AlignCenter)
            val = QLabel("0%"); val.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold; border: none;"); val.setAlignment(Qt.AlignCenter)
            vl.addWidget(t); vl.addWidget(val)
            return w, val

        w1, self.gcs_cpu_val = create_val("CPU", "#58a6ff")
        w2, self.gcs_gpu_val = create_val("GPU", "#bc8cff")
        w3, self.gcs_ram_val = create_val("BELLEK", "#3fb950")
        
        hl.addWidget(w1); hl.addWidget(w2); hl.addWidget(w3)
        l.addLayout(hl)
        return frame

    def create_status_card(self):
        frame, l = self.base_card("SİSTEM DURUMU")
        stat = QLabel("✅ TÜM SİSTEMLER NORMAL")
        stat.setAlignment(Qt.AlignCenter)
        stat.setStyleSheet("border: 2px solid #238636; background: #12331b; color: #3fb950; font-weight: bold; font-size:13px; border-radius:4px; padding:4px;")
        l.addWidget(stat)
        return frame

    def create_bottom_bar(self):
        w = QWidget(); w.setFixedHeight(50)
        l = QHBoxLayout(w); l.setContentsMargins(0, 5, 0, 0); l.setSpacing(8)
        def uniform_btn(text, bg_col, border_col, text_col):
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            b.setStyleSheet(f"QPushButton {{ background-color: {bg_col}; border: 1px solid {border_col}; color: {text_col}; border-radius: 4px; font-weight: bold; font-size: 12px; padding: 6px;}} QPushButton:hover {{ background-color: {border_col}; }}")
            return b
        l.addWidget(uniform_btn("⬆ KALKIŞ", "#12331b", "#238636", "#3fb950"))
        l.addWidget(uniform_btn("⬇ İNİŞ", "#0d2b4f", "#1f6feb", "#58a6ff"))
        l.addWidget(uniform_btn("🛑 ACİL DURDUR", "#490202", "#da3633", "#ff7b72"))
        l.addWidget(uniform_btn("🏠 RTL EVE DÖN", "#452303", "#9e4c05", "#ffa657"))
        l.addWidget(uniform_btn("⏱ LOITER BEKLE", "#3d3202", "#877207", "#e3b341"))
        l.addWidget(uniform_btn("🔗 BAĞLANTI KOPARSA\nRTL", "#2d1645", "#5c2f8f", "#d2a8ff"))
        l.addWidget(uniform_btn("⚙ AYARLAR", "#21262d", "#30363d", "#c9d1d9"))
        return w

    def toggle_map(self):
        if self.map_card.isFullScreen():
            self.map_card.showNormal()
        else:
            self.map_card.showFullScreen()

    # --- CRSF THREAD'DEN GELEN VERİYİ ARAYÜZE İŞLEME ---
    @Slot(dict)
    def on_telemetry_received(self, data):
        # State'i güncelle
        for key, val in data.items():
            self.state[key] = val

        # Açıları güncelle
        self.horizon.update_attitude(self.state['roll'], self.state['pitch'])
        self.att_lbl.setText(f"ROLL: {self.state['roll']:.1f}°   PITCH: {self.state['pitch']:.1f}°   YAW: {self.state['yaw']:.1f}°")
        
        # Haritayı yeniden çizdir
        self.map_view.update()

        # Batarya güncellemesi
        self.drone_bars['batt'][0].setValue(int(self.state['batt_v'] * 4)) 
        self.drone_bars['batt'][1].setText(f"{self.state['batt_v']:.1f} V")
        self.drone_bars['temp'][0].setValue(int(self.state['temp']))
        self.drone_bars['temp'][1].setText(f"{int(self.state['temp'])} °C")

    # --- SENSÖR DIŞI (EKSTRA) VERİLERİN GÜNCELLENMESİ ---
    def update_mock_system_data(self):
        self.clock.setText(f"Saat: {QTime.currentTime().toString('HH:mm:ss')}")
        
        # Arayüzün boş kalmaması için hedef mesafe, gecikme ve işlemci değerlerini simüle etmeye devam ediyoruz
        if self.state['dist'] > 0.05:
            self.state['dist'] -= 0.005 
        
        if self.state['dist'] > 1.0: self.mission_view.update_stage(1)
        elif self.state['dist'] > 0.7: self.mission_view.update_stage(2)
        elif self.state['dist'] > 0.3: self.mission_view.update_stage(3)
        else: self.mission_view.update_stage(4)

        self.state['impact_timer'] -= 0.05 if self.state['impact_timer'] > 0 else 0
        self.state['yolo_delay'] = random.randint(30, 45)
        self.state['auto_delay'] = random.randint(60, 85)
        self.state['total_delay'] = random.randint(100, 120)
        self.state['gcs_cpu'] = max(10, min(100, self.state['gcs_cpu'] + random.randint(-3, 3)))
        self.state['gcs_gpu'] = max(10, min(100, self.state['gcs_gpu'] + random.randint(-4, 4)))
        self.state['gcs_ram'] = max(10, min(100, self.state['gcs_ram'] + random.randint(-1, 1)))

        self.distance_lbl.setText(f"HEDEFE MESAFE: {self.state['dist']:.2f} km")
        remaining = max(0, int(self.state['impact_timer']))
        self.time_bar.setValue(int((remaining / 45.0) * 100)) 
        self.time_lbl.setText(f"Kalan Uçuş Süresi: {remaining} sn")

        self.val_yolo.setText(f"{self.state['yolo_delay']} ms")
        self.val_auto.setText(f"{self.state['auto_delay']} ms")
        self.val_total.setText(f"{self.state['total_delay']} ms")

        color_cpu = "#f85149" if self.state['gcs_cpu'] > 70 else "#58a6ff"
        self.gcs_cpu_val.setStyleSheet(f"color: {color_cpu}; font-size: 16px; font-weight: bold; border: none;")
        self.gcs_cpu_val.setText(f"{self.state['gcs_cpu']}%")
        self.gcs_gpu_val.setText(f"{self.state['gcs_gpu']}%")
        self.gcs_ram_val.setText(f"{self.state['gcs_ram']}%")

        tel_html = f"""
        <style> td {{ padding: 1px; font-size: 11px; color: #8b949e; }} .val {{ text-align: right; font-weight: bold; }} </style>
        <table width="100%">
            <tr><td colspan="2" style="color:#58a6ff; font-weight:bold;">🔵 AVCI DRONE (CRSF VERİSİ)</td></tr>
            <tr><td>Çizgisel Hız:</td><td class="val" style="color:#58a6ff;">{self.state['speed']:.1f} m/s</td></tr>
            <tr><td>Yatış (Roll):</td><td class="val" style="color:#58a6ff;">{self.state['roll']:.1f}°</td></tr>
            <tr><td>Dikilme (Pitch):</td><td class="val" style="color:#58a6ff;">{self.state['pitch']:.1f}°</td></tr>
            <tr><td>Sapma (Yaw):</td><td class="val" style="color:#58a6ff;">{self.state['yaw']:.1f}°</td></tr>
            <tr><td>Enlem (Lat):</td><td class="val" style="color:#58a6ff;">{self.state['lat']:.6f}° N</td></tr>
            <tr><td>Boylam (Lon):</td><td class="val" style="color:#58a6ff;">{self.state['lon']:.6f}° E</td></tr>
            <tr><td>İrtifa:</td><td class="val" style="color:#58a6ff;">{self.state['alt']:.1f} m</td></tr>
            <tr><td colspan="2"><hr style="border:0.5px solid #30363d; margin: 2px 0;"></td></tr>
            <tr><td colspan="2" style="color:#f85149; font-weight:bold;">🔴 HEDEF İHA</td></tr>
            <tr><td>Enlem (Lat):</td><td class="val" style="color:#f85149;">39.120123° N</td></tr>
            <tr><td>Boylam (Lon):</td><td class="val" style="color:#f85149;">32.991234° E</td></tr>
            <tr><td>İrtifa:</td><td class="val" style="color:#f85149;">150.0 m</td></tr>
            <tr><td>Hız:</td><td class="val" style="color:#f85149;">{self.state['target_speed']:.1f} m/s</td></tr>
        </table>
        """
        self.tel_lbl.setText(tel_html)

        guide_html = f"""
        <style> td {{ padding: 2px; font-size: 10px; color: #8b949e; }} .v {{ text-align: right; }} </style>
        <table width="100%">
            <tr><td>Toplam Karar</td><td class="v" style="color:#58a6ff;">327</td></tr>
            <tr><td>Takip Kararı</td><td class="v" style="color:#3fb950;">152</td></tr>
            <tr><td>Yakalama Kararı</td><td class="v" style="color:#d29922;">98</td></tr>
            <tr><td>Atlatma Kararı</td><td class="v" style="color:#d29922;">43</td></tr>
            <tr><td>Rota Düzeltme</td><td class="v" style="color:#bc8cff;">34</td></tr>
        </table>
        """
        self.guide_lbl.setText(guide_html)
        
        decision_text = "İMHA / YAKALAMA" if self.state['dist'] < 0.5 else "TAKİP"
        self.last_decision.setText(decision_text)

    def closeEvent(self, event):
        self.crsf_thread.stop()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = GCS()
    w.show()
    sys.exit(app.exec())