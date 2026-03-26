#!/usr/bin/env python3

import sys, os, re, threading, json, math, base64
from datetime import datetime
from pathlib import Path
from io import BytesIO
from functools import partial
from urllib.parse import urlparse, parse_qs
import subprocess

softname="Prism"

def pip_install(pkg):
    subprocess.run([sys.executable, '-m', 'pip', 'install', pkg,
                    '--break-system-packages', '-q'], check=False)

for pkg, imp in [('yt-dlp', 'yt_dlp'), ('Pillow', 'PIL'), ('requests', 'requests')]:
    try:    __import__(imp)
    except ImportError: pip_install(pkg)

import yt_dlp, requests
from PIL import Image as PILImage
from PyQt6.QtWidgets import *
from PyQt6.QtCore    import *
from PyQt6.QtGui     import *

DATA_FILE = Path(__file__).parent / 'data.json'

# ─────────────────────────── Console redirection ────────────────────────────

class ConsoleStream(QObject):
    text_written = pyqtSignal(str)
    def __init__(self, orig=None):
        super().__init__(); self._orig = orig
    def write(self, t):
        if t:
            self.text_written.emit(str(t))
            if self._orig:
                try: self._orig.write(t)
                except: pass
    def flush(self):
        if self._orig:
            try: self._orig.flush()
            except: pass
    def fileno(self):
        if self._orig:
            try: return self._orig.fileno()
            except: pass
        return -1

_ORIG_OUT = sys.stdout
_ORIG_ERR = sys.stderr
_S_OUT    = ConsoleStream(_ORIG_OUT)
_S_ERR    = ConsoleStream(_ORIG_ERR)
sys.stdout = _S_OUT
sys.stderr = _S_ERR

# ─────────────────────────── Persistence ────────────────────────────────────

def load_data():
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
                defaults = {
                    'nav_position':       'top',
                    'history':            [],
                    'bg_animate':         True,
                    'cursor_color':       '#3b82f6',
                    'top_glow_color':     '#3b82f6',
                    'corner_glow_color':  '#7c3aed',
                }
                for k, v in defaults.items():
                    d.setdefault(k, v)
                return d
        except:
            pass
    return {
        'nav_position':       'top',
        'history':            [],
        'bg_animate':         True,
        'cursor_color':       '#3b82f6',
        'top_glow_color':     '#3b82f6',
        'corner_glow_color':  '#7c3aed',
    }

def save_data(d):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception as e:
        _ORIG_OUT.write(f'[{softname}] save_data error: {e}\n')

# ─────────────────────────── URL helpers ────────────────────────────────────

def normalize_video_url(url: str) -> str:
    url = url.strip()
    try:
        parsed = urlparse(url)
        if 'youtu.be' in parsed.netloc:
            vid_id = parsed.path.strip('/')
            if not vid_id:
                return url
            params = parse_qs(parsed.query)
            t = params.get('t', [None])[0]
            clean = f"https://www.youtube.com/watch?v={vid_id}"
            if t:
                clean += f"&t={t}"
            return clean
        if 'youtube.com' in parsed.netloc and '/watch' in parsed.path:
            params = parse_qs(parsed.query)
            vid_id = params.get('v', [None])[0]
            if vid_id:
                t = params.get('t', [None])[0]
                clean = f"https://www.youtube.com/watch?v={vid_id}"
                if t:
                    clean += f"&t={t}"
                return clean
    except Exception:
        pass
    return url

# ─────────────────────────── Theme ──────────────────────────────────────────

C = {
    'bg'      : '#09090b',
    'bg2'     : '#111115',
    'bg3'     : '#18181f',
    'bg4'     : '#1e1e28',
    'border'  : '#1a1a22',
    'border2' : '#2a2a38',
    'accent'  : '#3b82f6',
    'accent2' : '#60a5fa',
    'accent_d': '#1d4ed8',
    'txt'     : '#f0f0f5',
    'txt2'    : '#6b6b80',
    'txt3'    : '#3a3a4a',
    'red'     : '#ff4d6d',
    'green'   : '#4ade80',
    'purple'  : '#7c3aed',
    'panel_bg': '#0c0c10',
}

STYLESHEET = f"""
* {{ font-family:'Outfit','Segoe UI','Ubuntu',sans-serif; outline:none; }}
QMainWindow, QWidget {{ background:{C['bg']}; color:{C['txt']}; }}
QScrollArea                     {{ background:transparent; border:none; }}
QScrollArea > QWidget > QWidget {{ background:transparent; }}
#topNav {{
    background:rgba(9,9,11,0.97);
    border-bottom:1px solid {C['border']};
    min-height:58px; max-height:58px;
}}
#bottomNav {{
    background:rgba(9,9,11,0.97);
    border-top:1px solid {C['border']};
    min-height:58px; max-height:58px;
}}
#logoBar {{
    background:rgba(9,9,11,0.97);
    border-bottom:1px solid {C['border']};
    min-height:46px; max-height:46px;
}}
#tabsContainer {{
    background:{C['bg3']};
    border:1px solid {C['border']};
    border-radius:10px; padding:4px;
}}
QPushButton#navTab {{
    background:transparent; border:none;
    border-radius:7px; color:{C['txt2']};
    font-size:13px; font-weight:500;
    padding:7px 16px; min-width:76px;
}}
QPushButton#navTab:hover {{
    color:{C['txt']}; background:rgba(59,130,246,0.08);
}}
QPushButton#navTab[active=true] {{
    background:rgba(59,130,246,0.15);
    color:{C['accent2']};
    border:1px solid rgba(59,130,246,0.3);
}}
QPushButton#utilBtn {{
    background:transparent;
    border:1px solid {C['border']};
    border-radius:7px; color:{C['txt2']};
    font-size:12px; font-weight:500;
    padding:5px 13px; min-height:30px;
}}
QPushButton#utilBtn:hover {{
    color:{C['txt']}; border-color:{C['border2']};
    background:rgba(255,255,255,0.04);
}}
QPushButton#utilBtn[active=true] {{
    background:rgba(59,130,246,0.12);
    border-color:rgba(59,130,246,0.40);
    color:{C['accent2']};
}}
#logoLabel   {{ color:{C['txt']};  font-size:17px; font-weight:700; letter-spacing:-0.3px; }}
#versionLabel{{ color:{C['txt3']}; font-size:12px;
               font-family:'JetBrains Mono','Courier New',monospace; letter-spacing:1px; }}
#searchBox {{
    background:{C['bg3']}; border:1.5px solid {C['border2']};
    border-radius:20px; min-height:62px;
}}
#searchBoxFocused {{
    background:{C['bg3']}; border:1.5px solid {C['accent']};
    border-radius:20px; min-height:62px;
}}
QLineEdit#searchInput {{
    background:transparent; border:none;
    color:{C['txt']}; font-size:15px; padding:0 8px;
    selection-background-color:{C['accent_d']};
}}
QLineEdit#searchInput::placeholder {{ color:{C['txt3']}; }}
QPushButton#fetchBtn {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #2563eb,stop:1 #1d4ed8);
    border:none; border-radius:12px; color:white;
    font-size:13px; font-weight:700; padding:0 22px; min-height:44px;
}}
QPushButton#fetchBtn:hover {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #3b82f6,stop:1 #2563eb);
}}
QPushButton#fetchBtn:pressed  {{ background:{C['accent_d']}; }}
QPushButton#fetchBtn:disabled {{
    background:{C['bg3']}; color:{C['txt2']};
    border:1px solid {C['border']};
}}
QPushButton#fmtPill {{
    background:{C['bg3']}; border:1px solid {C['border']};
    border-radius:8px; color:{C['txt2']};
    font-size:12px; font-weight:500; padding:6px 14px;
}}
QPushButton#fmtPill:hover {{
    color:{C['txt']}; border-color:rgba(59,130,246,0.4);
    background:rgba(59,130,246,0.07);
}}
QPushButton#fmtPill[active=true] {{
    background:rgba(59,130,246,0.15);
    border-color:rgba(59,130,246,0.45);
    color:{C['accent2']};
}}
QComboBox {{
    background:{C['bg3']}; border:1px solid {C['border']};
    border-radius:10px; color:{C['txt']};
    font-size:13px; padding:8px 32px 8px 13px; min-height:40px;
}}
QComboBox:focus {{ border-color:{C['accent']}; }}
QComboBox:hover {{ border-color:{C['border2']}; }}
QComboBox::drop-down {{ border:none; width:24px; }}
QComboBox::down-arrow {{
    image:none;
    border-left:4px solid transparent; border-right:4px solid transparent;
    border-top:5px solid {C['txt3']}; width:0; height:0;
}}
QComboBox QAbstractItemView {{
    background:{C['bg3']}; border:1px solid {C['border2']};
    color:{C['txt']}; selection-background-color:rgba(59,130,246,0.2);
    selection-color:{C['accent2']}; padding:4px; outline:none;
}}
QComboBox#smallSelect {{
    min-height:32px; padding:4px 28px 4px 10px;
    font-size:12px; border-radius:8px; min-width:110px;
}}
QPushButton#dlMainBtn {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #2563eb,stop:1 #1d4ed8);
    border:none; border-radius:10px; color:white;
    font-size:13px; font-weight:700; padding:0 22px; min-height:40px;
}}
QPushButton#dlMainBtn:hover {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #3b82f6,stop:1 #2563eb);
}}
QPushButton#dlMainBtn:disabled {{
    background:{C['bg3']}; color:{C['txt2']};
    border:1px solid {C['border']};
}}
QPushButton#dlAllBtn {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #2563eb,stop:1 #1d4ed8);
    border:none; border-radius:10px; color:white;
    font-size:13px; font-weight:700; padding:0 20px; min-height:40px;
}}
QPushButton#dlAllBtn:hover {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #3b82f6,stop:1 #2563eb);
}}
QPushButton#stopBtn {{
    background:rgba(255,77,109,0.10);
    border:1px solid rgba(255,77,109,0.30);
    border-radius:10px; color:{C['red']};
    font-size:13px; font-weight:700; padding:0 18px; min-height:40px;
}}
QPushButton#stopBtn:hover {{
    background:rgba(255,77,109,0.22); border-color:{C['red']};
}}
QPushButton#plDlBtn {{
    background:rgba(59,130,246,0.10);
    border:1px solid rgba(59,130,246,0.25);
    border-radius:8px; color:{C['accent2']};
    font-size:12px; font-weight:600; padding:0 14px; min-height:32px;
}}
QPushButton#plDlBtn:hover {{
    background:rgba(59,130,246,0.20); border-color:{C['accent']};
}}
QPushButton#plDlBtn[done=true] {{
    background:rgba(74,222,128,0.08);
    border-color:rgba(74,222,128,0.25); color:{C['green']};
}}
QPushButton#tbJpgBtn {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #2563eb,stop:1 #1d4ed8);
    border:none; border-radius:9px; color:white;
    font-size:13px; font-weight:600; padding:0 18px; min-height:38px;
}}
QPushButton#tbJpgBtn:hover {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #3b82f6,stop:1 #2563eb);
}}
QPushButton#tbPngBtn {{
    background:transparent; border:1px solid {C['border2']};
    border-radius:9px; color:{C['txt2']};
    font-size:13px; font-weight:600; padding:0 18px; min-height:38px;
}}
QPushButton#tbPngBtn:hover {{
    color:{C['txt']}; border-color:rgba(255,255,255,0.2);
    background:rgba(255,255,255,0.04);
}}
#slidePanel {{
    background:{C['panel_bg']};
    border-left:1px solid {C['border2']};
}}
#panelHeader {{
    background:{C['panel_bg']};
    border-bottom:1px solid {C['border']};
    min-height:52px; max-height:52px;
}}
QPushButton#panelCloseBtn {{
    background:transparent; border:none;
    color:{C['txt2']}; font-size:18px; padding:4px 8px; border-radius:6px;
}}
QPushButton#panelCloseBtn:hover {{
    color:{C['txt']}; background:rgba(255,255,255,0.07);
}}
QPushButton#posBtnTop, QPushButton#posBtnBottom {{
    background:{C['bg3']}; border:1px solid {C['border']};
    border-radius:12px; color:{C['txt2']};
    font-size:13px; font-weight:500;
    padding:18px 0; min-width:150px;
}}
QPushButton#posBtnTop:hover, QPushButton#posBtnBottom:hover {{
    border-color:{C['border2']}; color:{C['txt']};
    background:rgba(255,255,255,0.03);
}}
QPushButton#posBtnTop[active=true], QPushButton#posBtnBottom[active=true] {{
    background:rgba(59,130,246,0.12);
    border-color:rgba(59,130,246,0.40);
    color:{C['accent2']};
}}
QPushButton#saveSettingsBtn {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #2563eb,stop:1 #1d4ed8);
    border:none; border-radius:10px; color:white;
    font-size:13px; font-weight:700; padding:0 28px; min-height:42px;
}}
QPushButton#saveSettingsBtn:hover {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #3b82f6,stop:1 #2563eb);
}}
QPushButton#toggleBtn {{
    border-radius:14px; font-size:12px; font-weight:600;
    padding:6px 18px; min-height:28px; min-width:90px;
}}
QPushButton#toggleBtn[on=true] {{
    background:rgba(59,130,246,0.15);
    border:1px solid rgba(59,130,246,0.45);
    color:{C['accent2']};
}}
QPushButton#toggleBtn[on=false] {{
    background:{C['bg3']};
    border:1px solid {C['border']};
    color:{C['txt2']};
}}
QFrame#histCard {{
    background:{C['bg2']}; border:1px solid {C['border']}; border-radius:14px;
}}
QFrame#histCard:hover {{
    border-color:rgba(59,130,246,0.30); background:{C['bg3']};
}}
QPushButton#clearHistBtn {{
    background:rgba(255,77,109,0.09); border:1px solid rgba(255,77,109,0.25);
    border-radius:8px; color:{C['red']};
    font-size:12px; font-weight:600; padding:6px 16px;
}}
QPushButton#clearHistBtn:hover {{
    background:rgba(255,77,109,0.16); border-color:{C['red']};
}}
QLabel#heroTitle    {{ color:{C['txt']};    font-size:52px; font-weight:700; letter-spacing:-2px; }}
QLabel#heroSub      {{ color:{C['txt2']};   font-size:16px; }}
QLabel#sectionTitle {{ color:{C['txt']};    font-size:36px; font-weight:700; letter-spacing:-1.5px; }}
QLabel#sectionSub   {{ color:{C['txt2']};   font-size:15px; }}
QLabel#vcChannel    {{ color:{C['accent2']}; font-size:11px; font-weight:500; letter-spacing:2px; }}
QLabel#vcTitle      {{ color:{C['txt']};    font-size:20px; font-weight:600; letter-spacing:-0.3px; }}
QLabel#dlLabel      {{ color:{C['txt3']};   font-size:10px; font-weight:600; letter-spacing:1.5px; }}
QLabel#tagLabel     {{
    color:{C['txt2']}; font-size:12px; font-weight:500;
    background:rgba(255,255,255,0.04); border:1px solid {C['border']};
    border-radius:20px; padding:4px 12px;
}}
QLabel#tagLabelHi   {{
    color:{C['accent2']}; font-size:12px; font-weight:500;
    background:rgba(59,130,246,0.08); border:1px solid rgba(59,130,246,0.25);
    border-radius:20px; padding:4px 12px;
}}
QLabel#monoSmall    {{
    color:{C['txt2']}; font-size:11px;
    font-family:'JetBrains Mono','Courier New',monospace;
}}
QLabel#statusOk     {{ color:{C['green']}; font-size:13px; }}
QLabel#statusErr    {{ color:{C['red']};   font-size:13px; }}
QLabel#statusInfo   {{ color:{C['txt2']}; font-size:13px; }}
QLabel#plStatN      {{
    color:{C['txt']};    font-size:26px; font-weight:700; letter-spacing:-1px;
    font-family:'JetBrains Mono','Courier New',monospace;
}}
QLabel#plStatNA     {{
    color:{C['accent2']}; font-size:26px; font-weight:700; letter-spacing:-1px;
    font-family:'JetBrains Mono','Courier New',monospace;
}}
QLabel#plStatNG     {{
    color:{C['green']}; font-size:26px; font-weight:700; letter-spacing:-1px;
    font-family:'JetBrains Mono','Courier New',monospace;
}}
QLabel#plStatL      {{ color:{C['txt3']};  font-size:11px; letter-spacing:1px; }}
QLabel#plRowTitle   {{ color:{C['txt']};   font-size:14px; font-weight:500; }}
QLabel#plRowMeta    {{
    color:{C['txt3']}; font-size:11px;
    font-family:'JetBrains Mono','Courier New',monospace;
}}
QLabel#durBadge     {{
    color:{C['txt']}; font-size:12px;
    font-family:'JetBrains Mono','Courier New',monospace;
    background:rgba(0,0,0,0.75); border:1px solid {C['border']};
    border-radius:6px; padding:3px 9px;
}}
QLabel#resBadge     {{
    color:{C['txt2']}; font-size:11px;
    font-family:'JetBrains Mono','Courier New',monospace;
    background:rgba(0,0,0,0.75); border:1px solid {C['border']};
    border-radius:6px; padding:4px 10px;
}}
QLabel#tbTitleLabel {{ color:{C['txt']};   font-size:16px; font-weight:500; }}
QLabel#panelTitle   {{ color:{C['txt']};   font-size:15px; font-weight:600; }}
QLabel#panelSub     {{ color:{C['txt3']};  font-size:11px; letter-spacing:1px; }}
QLabel#histCardTitle{{ color:{C['txt']};   font-size:14px; font-weight:500; }}
QLabel#histCardMeta {{ color:{C['txt3']};  font-size:11px; font-family:'JetBrains Mono','Courier New',monospace; }}
QLabel#histCardDate {{ color:{C['accent2']}; font-size:11px; font-family:'JetBrains Mono','Courier New',monospace; }}
QFrame#videoCard {{ background:{C['bg2']}; border:1px solid {C['border']}; border-radius:20px; }}
QFrame#statCard  {{ background:{C['bg2']}; border:1px solid {C['border']}; border-radius:14px; }}
QFrame#plRow     {{ background:{C['bg2']}; border:1px solid {C['border']}; border-radius:14px; }}
QFrame#plRow:hover {{ border-color:rgba(59,130,246,0.35); background:{C['bg3']}; }}
QFrame#tbCard    {{ background:{C['bg2']}; border:1px solid {C['border']}; border-radius:20px; }}
QFrame[frameShape="4"] {{ background:{C['border']}; border:none; max-height:1px; }}
QTextEdit#consoleEdit {{
    background:#060608; border:none;
    color:#4ade80; font-size:11px;
    font-family:'JetBrains Mono','Courier New',monospace;
    padding:10px;
}}
QTextEdit {{
    background:{C['bg3']}; border:1px solid {C['border']};
    border-radius:10px; color:{C['txt2']};
    font-size:12px; padding:8px;
}}
QScrollBar:vertical   {{ background:transparent; width:5px; margin:0; }}
QScrollBar::handle:vertical {{ background:{C['bg3']}; border-radius:2px; min-height:40px; }}
QScrollBar::handle:vertical:hover {{ background:{C['border2']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar:horizontal {{ height:5px; background:transparent; }}
QScrollBar::handle:horizontal {{ background:{C['bg3']}; border-radius:2px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}

QCheckBox {{
    spacing: 0px;
    color: {C['txt']};
}}
QCheckBox::indicator {{
    width: 24px;
    height: 24px;
    border: 2px solid {C['border2']};
    border-radius: 7px;
    background: {C['bg3']};
}}
QCheckBox::indicator:hover {{
    border-color: {C['accent']};
    background: rgba(59,130,246,0.10);
}}
QCheckBox::indicator:checked {{
    background: {C['accent']};
    border-color: {C['accent']};
}}
QCheckBox::indicator:checked:hover {{
    background: {C['accent2']};
    border-color: {C['accent2']};
}}
"""

# ────────────────────── Animated background ─────────────────────────────────

class AnimatedSquaresBg(QWidget):
    def __init__(self, parent=None,
                 top_glow_color: str = '#3b82f6',
                 corner_glow_color: str = '#7c3aed'):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._enabled       = True
        self._offset_x      = 0.0
        self._offset_y      = 0.0
        self._speed_x       = 0.22
        self._speed_y       = 0.13
        self._top_color     = QColor(top_glow_color)
        self._corner_color  = QColor(corner_glow_color)
        self._timer         = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_enabled(self, val: bool):
        self._enabled = val
        self.update()

    def set_top_glow_color(self, hex_color: str):
        self._top_color = QColor(hex_color)
        self.update()

    def set_corner_glow_color(self, hex_color: str):
        self._corner_color = QColor(hex_color)
        self.update()

    def _tick(self):
        if not self._enabled:
            return
        self._offset_x = (self._offset_x + self._speed_x) % 48
        self._offset_y = (self._offset_y + self._speed_y) % 48
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(C['bg']))
        grid_alpha = 9 if self._enabled else 5
        p.setPen(QPen(QColor(255, 255, 255, grid_alpha), 1))
        ox = -self._offset_x if self._enabled else 0
        oy = -self._offset_y if self._enabled else 0
        x = ox
        while x <= self.width() + 48:
            p.drawLine(int(x), 0, int(x), self.height())
            x += 48
        y = oy
        while y <= self.height() + 48:
            p.drawLine(0, int(y), self.width(), int(y))
            y += 48

        tc = QColor(self._top_color)
        g1 = QRadialGradient(self.width() // 2, -40, 440)
        g1.setColorAt(0, QColor(tc.red(), tc.green(), tc.blue(), 22))
        g1.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(g1)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(self.width() // 2 - 440, -200, 880, 500)

        cc = QColor(self._corner_color)
        g2 = QRadialGradient(self.width(), self.height(), 300)
        g2.setColorAt(0, QColor(cc.red(), cc.green(), cc.blue(), 22))
        g2.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(g2)
        p.drawEllipse(self.width() - 320, self.height() - 320, 640, 640)
        p.end()


# ────────────────────── Cursor glow ─────────────────────────────────────────

class CursorGlow(QWidget):
    def __init__(self, parent=None, color: str = '#3b82f6'):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._pos      = QPointF(-500, -500)
        self._alpha    = 0.0
        self._target   = 0.0
        self._radius   = 130.0
        self._r_target = 130.0
        self._color    = QColor(color)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(16)

    def set_color(self, hex_color: str):
        self._color = QColor(hex_color)
        self.update()

    def move_to(self, pos: QPoint):
        self._pos    = QPointF(pos.x(), pos.y())
        self._target = 35.0
        self.update()

    def fade_out(self):
        self._target = 0.0

    def click_flash(self):
        self._target   = 90.0
        self._r_target = 180.0
        QTimer.singleShot(500, self._restore_glow)

    def _restore_glow(self):
        self._target   = 35.0
        self._r_target = 130.0

    def _tick(self):
        diff = self._target - self._alpha
        if abs(diff) > 0.3:
            self._alpha += diff * 0.12
        else:
            self._alpha = self._target
        rdiff = self._r_target - self._radius
        if abs(rdiff) > 0.5:
            self._radius += rdiff * 0.10
        else:
            self._radius = self._r_target
        self.update()

    def paintEvent(self, _):
        if self._alpha < 0.5:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self._pos.x(), self._pos.y()
        r  = self._radius
        c  = self._color
        g  = QRadialGradient(cx, cy, r)
        g.setColorAt(0,    QColor(c.red(), c.green(), c.blue(), int(self._alpha)))
        g.setColorAt(0.45, QColor(c.red(), c.green(), c.blue(), int(self._alpha * 0.35)))
        g.setColorAt(1,    QColor(0, 0, 0, 0))
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.end()


# ────────────────────── Colour picker button ────────────────────────────────

class ColorPickerBtn(QPushButton):
    color_changed = pyqtSignal(str)

    def __init__(self, color: str = '#3b82f6', parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(44, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._refresh()

    def _refresh(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background: {self._color};
                border: 2px solid rgba(255,255,255,0.18);
                border-radius: 8px;
            }}
            QPushButton:hover {{
                border: 2px solid rgba(255,255,255,0.55);
            }}
        """)

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, 'Choose Colour',
                                   QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self._color = c.name()
            self._refresh()
            self.color_changed.emit(self._color)

    def color(self) -> str:
        return self._color

    def set_color(self, hex_color: str):
        self._color = hex_color
        self._refresh()

# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
#  NEXUS  –  Premium Splash Screen
#
#  Concept: A luminous ring draws itself around the centre. On completion it
#  pulses outward, sparks fly off the leading tip, and "Nexus" materialises
#  from inside the ring with a chromatic gradient and layered glow. A thin
#  gradient line sweeps beneath it. The entire scene breathes once, then
#  dissolves to black.
#
#  Timeline (ticks × 16 ms ≈ seconds):
#   [ 0 →  12]  Background grid + glows breathe in
#   [12 →  84]  Ring draws clockwise, tip emits sparks every 3 ticks
#   [86 → 116]  Ring-close expansion pulse
#   [90 → 130]  "Nexus" rises + fades in, ring dims to 30 %
#   [118→ 142]  Separator line sweeps out, end-cap dots pop
#   [136→ 158]  Subtitle + version fade in
#   [158→ 370]  Hold
#   [370→ 416]  Full scene fades to black
#   [426+]      finished() signal emitted
#
# ─────────────────────────────────────────────────────────────────────────────

import math, random
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore    import Qt, QTimer, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui     import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QFontInfo,
    QLinearGradient, QRadialGradient, QPainterPath, QConicalGradient,
)


class HelloSplash(QWidget):

    finished = pyqtSignal()

    # ── Ring geometry ─────────────────────────────────────────────────────────
    _RING_DUR    = 72      # ticks to complete ring draw
    _RING_START  = 12
    _PULSE_START = 86      # ring-close pulse
    _NEXUS_START = 90      # text materialises
    _LINE_START  = 118     # separator line
    _SUB_START   = 136     # subtitle / version
    _FADE_START  = 370     # fade to black
    _FADE_DUR    = 46

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background:#000008;')
        self._t = 0

        # Ring
        self._ring_arc   = 0.0   # 0 → 1
        self._ring_alpha = 0.0
        self._ring_fade  = 1.0   # dims as nexus appears
        self._pulse      = 0.0   # 0 → 1 expansion pulse

        # Sparks
        self._sparks: list[dict] = []

        # Nexus text
        self._nex_alpha = 0.0
        self._nex_glow  = 0.0
        self._nex_y     = 22.0   # slides to 0

        # Separator
        self._line_w    = 0.0
        self._line_a    = 0.0
        self._dot_a     = 0.0

        # Sub
        self._sub_a     = 0.0
        self._ver_a     = 0.0

        # Background
        self._bg_a      = 0.0
        self._ox        = 0.0
        self._oy        = 0.0

        # Master
        self._master    = 1.0

        # Precompute Nexus path
        self._npath    = None
        self._nw       = 0.0
        self._nh       = 0.0
        self._precompute_nexus()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # ── Easing ────────────────────────────────────────────────────────────────

    @staticmethod
    def _eo3(t):
        t = max(0.0, min(1.0, t))
        return 1.0 - (1.0 - t) ** 3

    @staticmethod
    def _eo5(t):
        t = max(0.0, min(1.0, t))
        return 1.0 - (1.0 - t) ** 5

    @staticmethod
    def _eio(t):
        t = max(0.0, min(1.0, t))
        return t * t * (3.0 - 2.0 * t)

    # ── Precompute ────────────────────────────────────────────────────────────

    def _nexus_font(self) -> QFont:
        f = QFont()
        for fam in ('Outfit', 'Segoe UI', 'Ubuntu', 'Arial'):
            f.setFamily(fam)
            if QFontInfo(f).family().lower() == fam.lower():
                break
        f.setWeight(QFont.Weight.Bold)
        f.setPixelSize(self._nexus_px())
        return f

    def _nexus_px(self) -> int:
        side = min(self.width() or 900, self.height() or 600)
        return max(72, int(side * 0.175))

    def _precompute_nexus(self):
        fn  = self._nexus_font()
        raw = QPainterPath()
        raw.addText(0, 0, fn, 'PRISM')
        br  = raw.boundingRect()
        pp  = QPainterPath()
        pp.addText(-br.x(), -br.y(), fn, 'PRISM')
        nb  = pp.boundingRect()
        self._npath = pp
        self._nw    = nb.width()
        self._nh    = nb.height()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._precompute_nexus()

    # ── Ring radius ───────────────────────────────────────────────────────────

    def _ring_r(self) -> float:
        return min(self.width(), self.height()) * 0.21

    # ── Spark helpers ─────────────────────────────────────────────────────────

    def _spawn_spark(self):
        angle = self._ring_arc * math.pi * 2 - math.pi / 2
        R  = self._ring_r()
        CX = self.width()  / 2
        CY = self.height() / 2
        tx = CX + math.cos(angle) * R
        ty = CY + math.sin(angle) * R
        spread = (random.random() - 0.5) * 0.9
        speed  = 0.5 + random.random() * 1.0
        tang   = angle + math.pi / 2 + spread
        sign   = 1 if random.random() > 0.5 else -1
        self._sparks.append({
            'x':     tx,  'y': ty,
            'vx':    math.cos(tang) * speed * sign + (random.random()-0.5)*0.35,
            'vy':    math.sin(tang) * speed - 0.4,
            'life':  1.0,
            'decay': 0.020 + random.random() * 0.022,
            'size':  0.9  + random.random() * 1.3,
            'hue':   220 if random.random() > 0.5 else 270,
            'sat':   70  + random.random() * 30,
        })

    def _update_sparks(self):
        for s in self._sparks:
            s['x']  += s['vx']
            s['y']  += s['vy']
            s['vy'] += 0.014
            s['life'] -= s['decay']
        self._sparks = [s for s in self._sparks if s['life'] > 0]

    # ── Tick ──────────────────────────────────────────────────────────────────

    def _tick(self):
        self._t += 1
        t = self._t
        eo3 = self._eo3
        eo5 = self._eo5
        eio = self._eio

        RS = self._RING_START
        RD = self._RING_DUR
        PS = self._PULSE_START
        NS = self._NEXUS_START
        LS = self._LINE_START
        SS = self._SUB_START
        FS = self._FADE_START
        FD = self._FADE_DUR

        # Background
        self._bg_a = min(1.0, eo3(t / 14.0))
        if self._bg_a > 0:
            self._ox = (self._ox + 0.22) % 52
            self._oy = (self._oy + 0.13) % 52

        # Ring
        if t >= RS:
            rf = (t - RS) / RD
            self._ring_alpha = min(1.0, eo3(min(rf, 1.0) * 2.0))
            self._ring_arc   = min(1.0, eo3(rf))
            if rf < 1.0 and rf > 0.05 and t % 3 == 0:
                self._spawn_spark()

        # Pulse
        if t >= PS:
            self._pulse = min(1.0, eo3((t - PS) / 30.0))

        # prism
        if t >= NS:
            nf = (t - NS) / 40.0
            self._nex_alpha = min(1.0, eo5(nf))
            self._nex_glow  = min(1.0, eo3(nf))
            self._nex_y     = 22.0 * (1.0 - min(1.0, eo3(nf)))
            self._ring_fade = max(0.15, 1.0 - eo3(min(1.0, (t - NS) / 60.0)) * 0.85)

        # Line
        if t >= LS:
            lf = eo3(min(1.0, (t - LS) / 22.0))
            side = min(self.width(), self.height())
            self._line_w  = lf * self._nw * self._master
            self._line_a  = min(1.0, lf * 3.0)
        if t >= LS + 18:
            self._dot_a = eo3(min(1.0, (t - LS - 18) / 14.0))

        # Subtitle
        if t >= SS:
            self._sub_a = eo3(min(1.0, (t - SS) / 20.0))
        if t >= SS + 14:
            self._ver_a = eo3(min(1.0, (t - SS - 14) / 16.0))

        # Sparks
        self._update_sparks()

        # Master fade
        if t >= FS:
            self._master = max(0.0, 1.0 - eio(min(1.0, (t - FS) / FD)))

        self.update()

        if t >= FS + FD + 10:
            self._timer.stop()
            self.finished.emit()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        W  = self.width()
        H  = self.height()
        CX = W / 2.0
        CY = H / 2.0
        GA = self._master
        BG = self._bg_a

        # ── Base ──────────────────────────────────────────────────────────────
        p.fillRect(self.rect(), QColor('#000008'))

        # ── Grid ──────────────────────────────────────────────────────────────
        if BG > 0.01:
            p.setPen(QPen(QColor(255, 255, 255, int(BG * 11)), 0.5))
            x = -self._ox
            while x <= W + 52:
                p.drawLine(int(x), 0, int(x), H); x += 52
            y = -self._oy
            while y <= H + 52:
                p.drawLine(0, int(y), W, int(y)); y += 52

        # ── Ambient radial glows ──────────────────────────────────────────────
        g1 = QRadialGradient(CX, CY * 0.3, W * 0.55)
        g1.setColorAt(0, QColor(20, 60, 180, int(BG * 30)))
        g1.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(g1); p.setPen(Qt.PenStyle.NoPen); p.drawRect(self.rect())

        g2 = QRadialGradient(W * 0.85, H * 0.85, W * 0.45)
        g2.setColorAt(0, QColor(80, 20, 200, int(BG * 26)))
        g2.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(g2); p.drawRect(self.rect())

        # ── Corner brackets ───────────────────────────────────────────────────
        if BG > 0.01:
            p.setOpacity(BG * GA * 0.28)
            p.setPen(QPen(QColor(96, 165, 250), 0.8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            M, L = 32, 22
            for bx, by, sx, sy in (
                (M,     M,     +1, +1),
                (W - M, M,     -1, +1),
                (M,     H - M, +1, -1),
                (W - M, H - M, -1, -1),
            ):
                p.drawLine(bx + sx*L, by, bx, by)
                p.drawLine(bx, by, bx, by + sy*L)
            p.setOpacity(1.0)

        # ── Ring ──────────────────────────────────────────────────────────────
        R  = self._ring_r()
        ra = self._ring_alpha * self._ring_fade * GA

        if ra > 0.005 and self._ring_arc > 0.005:
            start_deg = -90.0
            span_deg  = self._ring_arc * 360.0

            # Outer halo
            p.setOpacity(ra * 0.09)
            p.setPen(QPen(QColor(96, 165, 250), 24))
            p.drawArc(QRectF(CX-R-12, CY-R-12, (R+12)*2, (R+12)*2),
                      int(start_deg*16), int(span_deg*16))

            # Mid halo
            p.setOpacity(ra * 0.16)
            p.setPen(QPen(QColor(130, 120, 255), 8))
            p.drawArc(QRectF(CX-R-3, CY-R-3, (R+3)*2, (R+3)*2),
                      int(start_deg*16), int(span_deg*16))

            # Core arc — rendered in ~90 segments for colour variation
            SEGS = 90
            for i in range(SEGS):
                t0 = i / SEGS
                t1 = (i + 1) / SEGS
                if t1 > self._ring_arc: break
                a0_deg = start_deg + t0 * 360.0
                a1_deg = start_deg + t1 * 360.0

                frac = t0
                # Hue 220 (blue) → 270 (violet) → 220
                hue  = int(220 + math.sin(frac * math.pi) * 55)
                lite = int(58  + math.sin(frac * math.pi) * 18)
                col  = QColor.fromHsl(hue, 210, lite)
                p.setOpacity(ra)
                p.setPen(QPen(col, 1.5))
                p.drawArc(QRectF(CX-R, CY-R, R*2, R*2),
                          int(a0_deg*16), int((a1_deg-a0_deg)*16))

            # Bright leading tip
            if self._ring_arc < 1.0:
                tip_rad = (start_deg + span_deg) * math.pi / 180.0
                tx = CX + math.cos(tip_rad) * R
                ty = CY + math.sin(tip_rad) * R
                tg = QRadialGradient(tx, ty, 14)
                tg.setColorAt(0,   QColor(210, 230, 255, int(ra * 240)))
                tg.setColorAt(0.3, QColor(150, 180, 255, int(ra * 130)))
                tg.setColorAt(1,   QColor(96, 165, 250, 0))
                p.setOpacity(1.0)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(tg)
                p.drawEllipse(QPointF(tx, ty), 14, 14)
                p.setBrush(QColor(255, 255, 255, int(ra * 255)))
                p.drawEllipse(QPointF(tx, ty), 2.8, 2.8)

        # Pulse ring after close
        if self._pulse > 0 and self._pulse < 1.0:
            pR = R + self._pulse * 85.0
            pA = (1.0 - self._pulse) * 0.38 * GA
            p.setOpacity(pA)
            p.setPen(QPen(QColor(160, 180, 255), 1.1 * (1-self._pulse)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(CX, CY), pR, pR)
            p2R = R + self._pulse * 32.0
            p2A = (1.0 - self._pulse) * 0.22 * GA
            p.setOpacity(p2A)
            p.setPen(QPen(QColor(200, 180, 255), 0.8))
            p.drawEllipse(QPointF(CX, CY), p2R, p2R)
            p.setOpacity(1.0)

        # Subtle ring interior fill once prism appears
        if self._ring_arc >= 1.0 and self._nex_alpha > 0:
            fg = QRadialGradient(CX, CY, R * 0.88)
            fg.setColorAt(0,   QColor(59, 130, 246, int(self._nex_alpha * GA * 10)))
            fg.setColorAt(0.6, QColor(139, 92, 246, int(self._nex_alpha * GA * 8)))
            fg.setColorAt(1,   QColor(0, 0, 0, 0))
            p.setBrush(fg); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(CX, CY), R * 0.88, R * 0.88)

        # ── Sparks ────────────────────────────────────────────────────────────
        p.setPen(Qt.PenStyle.NoPen)
        for s in self._sparks:
            a = s['life'] * self._ring_fade * self._ring_alpha * GA
            if a < 0.01: continue
            col = QColor.fromHsl(int(s['hue']), int(s['sat']/100*255), 200)
            col.setAlphaF(a)
            p.setBrush(col)
            r_s = s['size'] * s['life']
            p.drawEllipse(QPointF(s['x'], s['y']), r_s, r_s)

        # ── Prism ─────────────────────────────────────────────────────────────
        if self._nex_alpha > 0.003 and self._npath:
            nw, nh = self._nw, self._nh
            nx_off = CX
            ny_off = CY - nh * 0.06 + self._nex_y

            p.save()
            p.translate(nx_off, ny_off)
            p.translate(-nw / 2.0, -nh / 2.0)

            # Glow passes (back-to-front, widest first)
            if self._nex_glow > 0.01:
                specs = [
                    (0.085, 0.08, QColor(59, 130, 246)),
                    (0.052, 0.16, QColor(124, 58, 237)),
                    (0.026, 0.28, QColor(147, 197, 253)),
                ]
                for sd, af, col in specs:
                    p.save()
                    p.translate(nw/2, nh/2)
                    p.scale(1.0+sd, 1.0+sd)
                    p.translate(-nw/2, -nh/2)
                    gc = QColor(col)
                    gc.setAlpha(int(self._nex_glow * af * GA * 255))
                    p.setBrush(gc); p.setPen(Qt.PenStyle.NoPen)
                    p.drawPath(self._npath)
                    p.restore()

            # Main fill gradient
            gf = QLinearGradient(0, 0, nw, 0)
            gf.setColorAt(0.00, QColor(147, 197, 253))   # blue-300
            gf.setColorAt(0.25, QColor( 59, 130, 246))   # blue-500
            gf.setColorAt(0.60, QColor(139,  92, 246))   # violet-500
            gf.setColorAt(1.00, QColor(221, 214, 254))   # violet-200
            p.setOpacity(self._nex_alpha * GA)
            p.setBrush(gf); p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(self._npath)

            # Sheen
            if self._nex_glow > 0.05:
                sh = QLinearGradient(0, 0, 0, nh * 0.32)
                sh.setColorAt(0, QColor(255, 255, 255, int(self._nex_glow * GA * 48)))
                sh.setColorAt(1, QColor(255, 255, 255, 0))
                p.setBrush(sh)
                p.drawPath(self._npath)

            p.restore()

        # ── Separator line ────────────────────────────────────────────────────
        if self._line_a > 0.005:
            ny_off = CY + self._nh * 0.5 + 28.0
            half   = self._line_w / 2.0

            if half > 2:
                lg = QLinearGradient(CX - half, 0, CX + half, 0)
                lg.setColorAt(0.00, QColor(59, 130, 246,   0))
                lg.setColorAt(0.18, QColor(96, 165, 250, 140))
                lg.setColorAt(0.50, QColor(196,181, 253, 220))
                lg.setColorAt(0.82, QColor(96, 165, 250, 140))
                lg.setColorAt(1.00, QColor(59, 130, 246,   0))
                p.setOpacity(self._line_a * GA)
                p.setPen(QPen(QBrush(lg), 0.85))
                p.drawLine(QPointF(CX-half, ny_off), QPointF(CX+half, ny_off))

                # End-cap dots
                if self._dot_a > 0.01:
                    p.setOpacity(self._dot_a * GA)
                    p.setPen(Qt.PenStyle.NoPen)
                    for dx in (CX - half, CX + half):
                        dg = QRadialGradient(dx, ny_off, 7)
                        dg.setColorAt(0, QColor(196, 181, 253, 230))
                        dg.setColorAt(1, QColor(139,  92, 246, 0))
                        p.setBrush(dg)
                        p.drawEllipse(QPointF(dx, ny_off), 7, 7)
                        p.setBrush(QColor(220, 210, 255, 240))
                        p.drawEllipse(QPointF(dx, ny_off), 1.8, 1.8)

        # ── Subtitle ──────────────────────────────────────────────────────────
        if self._sub_a > 0.005:
            ny_off = CY + self._nh * 0.5 + 60.0
            p.setOpacity(self._sub_a * GA * 0.60)
            fsub = QFont()
            for fam in ('Outfit', 'Segoe UI', 'Ubuntu'):
                fsub.setFamily(fam)
                if QFontInfo(fsub).family().lower() == fam.lower(): break
            fsub.setWeight(QFont.Weight.Medium)
            fsub.setPixelSize(11)
            fsub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4.0)
            p.setFont(fsub)
            sub_txt = 'YOUTUBE  ·  MEDIA SUITE'
            fm_sub  = QFontMetrics(fsub)
            sw      = fm_sub.horizontalAdvance(sub_txt)

            sg = QLinearGradient(CX - sw/2, 0, CX + sw/2, 0)
            sg.setColorAt(0.0, QColor( 80, 110, 170))
            sg.setColorAt(0.5, QColor(140, 160, 210))
            sg.setColorAt(1.0, QColor( 80, 110, 170))
            p.setPen(QPen(QBrush(sg), 1))
            p.drawText(int(CX - sw/2), int(ny_off), sub_txt)

        # ── Version ───────────────────────────────────────────────────────────
        if self._ver_a > 0.005:
            ny_off = CY + self._nh * 0.5 + 84.0
            p.setOpacity(self._ver_a * GA * 0.38)
            fver = QFont(); fver.setFamily('JetBrains Mono')
            fver.setPixelSize(10)
            p.setFont(fver)
            p.setPen(QColor(40, 40, 60))
            vw = QFontMetrics(fver).horizontalAdvance('v7.3')
            p.drawText(int(CX - vw/2), int(ny_off), 'v7.3')

        # ── Vignette edges ────────────────────────────────────────────────────
        vr = min(W, H) * 0.75
        ve = QRadialGradient(CX, CY, vr * 0.38, CX, CY, vr)
        ve.setColorAt(0, QColor(0, 0, 0, 0))
        ve.setColorAt(1, QColor(0, 0, 8,  int(BG * GA * 150)))
        p.setOpacity(1.0)
        p.setBrush(ve); p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(self.rect())

        # ── Final fade overlay ────────────────────────────────────────────────
        if GA < 0.999:
            ov = QColor(0, 0, 8, int((1.0 - GA) * 255))
            p.fillRect(self.rect(), ov)

        p.end()
# ────────────────────── Workers ─────────────────────────────────────────────

class VideoInfoWorker(QThread):
    info_ready = pyqtSignal(dict)
    error      = pyqtSignal(str)
    def __init__(self, url): super().__init__(); self.url = url
    def run(self):
        try:
            opts = {'quiet': True, 'no_warnings': True,
                    'extract_flat': False, 'skip_download': True}
            with yt_dlp.YoutubeDL(opts) as y:
                info = y.extract_info(self.url, download=False)
            print(f'[Prism] Fetched: {info.get("title", "?")}')
            self.info_ready.emit(info)
        except Exception as e:
            print(f'[Prism] Fetch error: {e}')
            self.error.emit(str(e))


class DownloadWorker(QThread):
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, url, fmt, out_dir):
        super().__init__()
        self.url        = url
        self.fmt        = fmt
        self.out_dir    = out_dir
        self._abort     = False
        self._file_idx  = 0
        self._n_files   = 2
        self._seen_fids = set()

    def abort(self): self._abort = True

    def run(self):
        def hook(d):
            if self._abort:
                raise Exception('Download aborted')
            fname  = d.get('filename') or d.get('tmpfilename') or ''
            status = d['status']
            if fname and fname not in self._seen_fids:
                self._seen_fids.add(fname)
                self._n_files = max(self._n_files, len(self._seen_fids))
            if status == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                dl    = d.get('downloaded_bytes', 0)
                spd   = d.get('speed', 0) or 0
                if total and total > 0:
                    slice_size = 96.0 / self._n_files
                    base       = self._file_idx * slice_size
                    file_pct   = min(dl / total * 100.0, 99.9)
                    overall    = min(base + file_pct / 100.0 * slice_size, 96.0)
                    spd_s = (f"{spd/1048576:.1f} MB/s" if spd >= 1048576
                             else f"{spd/1024:.0f} KB/s" if spd else "—")
                    label = 'Downloading…'
                    if self._file_idx == 1:   label = 'Downloading audio…'
                    elif self._file_idx >= 2: label = 'Processing…'
                    self.progress.emit(overall, f"{spd_s}  ·  {label}")
            elif status == 'finished':
                self._file_idx += 1
                slice_size = 96.0 / self._n_files
                done_pct   = min(self._file_idx * slice_size, 96.0)
                if self._file_idx < self._n_files:
                    self.progress.emit(done_pct, 'Downloading next stream…')
                else:
                    self.progress.emit(97.0, 'Merging & encoding…')

        try:
            os.makedirs(self.out_dir, exist_ok=True)
            opts = {
                'format': self.fmt,
                'outtmpl': os.path.join(self.out_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [hook],
                'quiet': True, 'no_warnings': True,
                'merge_output_format': 'mp4',
                'postprocessors': [
                    {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}
                ],
            }
            with yt_dlp.YoutubeDL(opts) as y:
                info  = y.extract_info(self.url)
                fname = yt_dlp.YoutubeDL(opts).prepare_filename(info)
            print(f'[Prism] Done: {os.path.basename(fname)}')
            self.finished.emit(fname)
        except Exception as e:
            print(f'[Prism] DL error: {e}')
            self.error.emit(str(e))


class PlaylistInfoWorker(QThread):
    video_ready = pyqtSignal(int, dict)
    total_found = pyqtSignal(int)
    error       = pyqtSignal(str)
    def __init__(self, url): super().__init__(); self.url = url; self._stop = False
    def stop(self): self._stop = True
    def run(self):
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True,
                                    'extract_flat': True, 'skip_download': True}) as y:
                pl = y.extract_info(self.url, download=False)
            entries = pl.get('entries', [])
            print(f'[Prism] Playlist: {len(entries)} entries')
            self.total_found.emit(len(entries))
            for i, e in enumerate(entries):
                if self._stop: return
                if not e: continue
                try:
                    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True,
                                           'skip_download': True}) as y2:
                        vid = y2.extract_info(
                            e.get('url') or e.get('webpage_url', ''), download=False)
                    self.video_ready.emit(i, vid)
                except:
                    self.video_ready.emit(i, e)
        except Exception as e:
            print(f'[Prism] Playlist error: {e}')
            self.error.emit(str(e))


class ThumbnailFetcher(QThread):
    ready = pyqtSignal(QPixmap)
    def __init__(self, url, w=400, h=225):
        super().__init__(); self.url = url; self.w = w; self.h = h
    def run(self):
        try:
            r   = requests.get(self.url, timeout=10)
            img = PILImage.open(BytesIO(r.content)).convert('RGB')
            img.thumbnail((self.w, self.h), PILImage.LANCZOS)
            d   = BytesIO(); img.save(d, 'PNG')
            pm  = QPixmap(); pm.loadFromData(d.getvalue())
            self.ready.emit(pm)
        except: pass


# ────────────────────── Utility functions ───────────────────────────────────

def fmt_size(b):
    if not b: return 'N/A'
    for u in ('B', 'KB', 'MB', 'GB'):
        if b < 1024: return f"~{b:.0f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def fmt_dur(s):
    if not s: return '—'
    s = int(s); h = s // 3600; m = (s % 3600) // 60; sec = s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

def fmt_views(n):
    if not n: return '—'
    if n >= 1_000_000_000: return f"{n/1_000_000_000:.2f}B views"
    if n >= 1_000_000:     return f"{n/1_000_000:.1f}M views"
    if n >= 1_000:         return f"{n/1_000:.1f}K views"
    return f"{n} views"

def fmt_likes(n):
    if not n: return '—'
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M likes"
    if n >= 1_000:     return f"{n/1_000:.1f}K likes"
    return f"{n} likes"

def best_thumbnail(info):
    thumbs = info.get('thumbnails', [])
    if thumbs:
        return max(thumbs, key=lambda t: (t.get('width', 0) or 0)).get('url', '')
    return info.get('thumbnail', '')

def parse_formats(info):
    fmts = info.get('formats', []); vf = []; af = []; sv = set(); sa = set()
    for f in reversed(fmts):
        vc  = f.get('vcodec', 'none'); ac = f.get('acodec', 'none')
        fid = f.get('format_id', ''); ext = f.get('ext', '?')
        h   = f.get('height'); fps = f.get('fps')
        abr = f.get('abr'); tbr = f.get('tbr')
        sz  = f.get('filesize') or f.get('filesize_approx')
        if vc and vc != 'none' and h:
            k = f"{h}_{fps}"
            if k not in sv:
                sv.add(k)
                fps_s = f" {int(fps)}fps" if fps and fps > 30 else ""
                vf.append((f"{h}p{fps_s}  [{ext.upper()}]  {fmt_size(sz)}", fid))
        if ac and ac != 'none' and vc in (None, 'none', ''):
            k = round(abr or tbr or 0)
            if k not in sa and k > 0:
                sa.add(k)
                lang = f.get('language', '')
                ls   = f"  [{lang.upper()}]" if lang else ""
                af.append((f"{k} kbps  [{ext.upper()}]{ls}  {fmt_size(sz)}", fid))
    return ([('Best (auto)', 'bestvideo')] + vf, [('Best (auto)', 'bestaudio')] + af)

def mk_lbl(text, obj='statusInfo', wrap=False):
    l = QLabel(text); l.setObjectName(obj)
    if wrap: l.setWordWrap(True)
    return l

def sep_h():
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"background:{C['border']};max-height:1px;border:none;")
    return f


# ────────────────────── Small UI widgets ────────────────────────────────────

class BreatheDot(QWidget):
    def __init__(self, color='#3b82f6', size=8, parent=None):
        super().__init__(parent)
        self._c = QColor(color); self._sz = size; self._scale = 1.0; self._grow = True
        self.setFixedSize(size + 10, size + 10)
        t = QTimer(self); t.timeout.connect(self._tick); t.start(30)
    def _tick(self):
        spd = 0.018
        self._scale = min(1.5, self._scale + spd) if self._grow else max(1.0, self._scale - spd)
        if self._scale >= 1.5: self._grow = False
        elif self._scale <= 1.0: self._grow = True
        self.update()
    def set_color(self, h): self._c = QColor(h); self.update()
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() // 2; cy = self.height() // 2; r = int(self._sz / 2 * self._scale)
        gl = QRadialGradient(cx, cy, r + 5); gc = QColor(self._c); gc.setAlpha(70)
        gl.setColorAt(0, gc); gl.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(gl); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - r - 5, cy - r - 5, (r + 5) * 2, (r + 5) * 2)
        p.setBrush(self._c); p.drawEllipse(cx - r // 2, cy - r // 2, r, r); p.end()


class SpinWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.setFixedSize(16, 16); self._angle = 0
        t = QTimer(self); t.timeout.connect(self._tick); t.start(18)
    def _tick(self): self._angle = (self._angle + 6) % 360; self.update()
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(); pen.setWidth(2); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setColor(QColor(C['border2'])); p.setPen(pen); p.drawArc(2, 2, 12, 12, 0, 360 * 16)
        pen.setColor(QColor(C['accent'])); p.setPen(pen)
        p.drawArc(2, 2, 12, 12, self._angle * 16, 100 * 16); p.end()


class SlimProgress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._target = 0.0; self._visual = 0.0; self.setFixedHeight(4)
        t = QTimer(self); t.timeout.connect(self._step); t.start(16)

    def setValue(self, v):
        self._target = min(100.0, max(0.0, float(v)))

    def value(self): return self._target

    def reset(self): self._target = 0.0; self._visual = 0.0; self.update()

    def _step(self):
        diff = self._target - self._visual
        if abs(diff) > 0.05: self._visual += diff * 0.12; self.update()
        elif self._visual != self._target: self._visual = self._target; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setBrush(QColor(C['bg3'])); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, w, h, 2, 2)
        if self._visual > 0:
            fw = max(0, int(w * self._visual / 100))
            if fw > 0:
                g = QLinearGradient(0, 0, fw, 0)
                g.setColorAt(0, QColor(C['accent_d'])); g.setColorAt(1, QColor(C['accent']))
                p.setBrush(g); p.drawRoundedRect(0, 0, fw, h, 2, 2)
                if fw > 6:
                    dr = h + 2
                    gd = QRadialGradient(fw, h // 2, dr + 3)
                    gd.setColorAt(0, QColor(59, 130, 246, 160))
                    gd.setColorAt(1, QColor(0, 0, 0, 0))
                    p.setBrush(gd)
                    p.drawEllipse(fw - dr - 3, h // 2 - dr - 3, (dr + 3) * 2, (dr + 3) * 2)
                    p.setBrush(QColor(C['accent2']))
                    p.drawEllipse(fw - dr, h // 2 - dr, dr * 2, dr * 2)
        p.end()


class ThumbWidget(QLabel):
    def __init__(self, w, h, parent=None):
        super().__init__(parent); self._w = w; self._h = h
        self.setFixedSize(w, h); self._draw_placeholder()
    def _draw_placeholder(self):
        pm = QPixmap(self._w, self._h); pm.fill(Qt.GlobalColor.transparent)
        p  = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QLinearGradient(0, 0, self._w, self._h)
        bg.setColorAt(0, QColor(13, 13, 20)); bg.setColorAt(1, QColor(17, 17, 28))
        p.setBrush(bg); p.setPen(Qt.PenStyle.NoPen); p.drawRect(0, 0, self._w, self._h)
        p.setPen(QPen(QColor(255, 255, 255, 12), 1))
        for x in range(0, self._w, 24): p.drawLine(x, 0, x, self._h)
        for y in range(0, self._h, 24): p.drawLine(0, y, self._w, y)
        p.setPen(QColor(60, 80, 120))
        f = QFont(); f.setPointSize(max(12, self._h // 5)); p.setFont(f)
        p.drawText(QRect(0, 0, self._w, self._h), Qt.AlignmentFlag.AlignCenter, "▶")
        p.end(); self.setPixmap(pm)
    def set_pixmap(self, pm):
        scaled = pm.scaled(self._w, self._h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation)
        final = QPixmap(self._w, self._h); p = QPainter(final)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(0, 0, self._w, self._h, QColor(C['bg2']))
        x = (self._w - scaled.width()) // 2; y = (self._h - scaled.height()) // 2
        p.drawPixmap(x, y, scaled); p.end(); self.setPixmap(final)


class HeroBadge(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self); lay.setContentsMargins(14, 5, 14, 5); lay.setSpacing(7)
        dot = BreatheDot(C['accent'], 6)
        lb  = QLabel(text)
        lb.setStyleSheet(f"color:{C['accent2']};font-size:12px;font-weight:500;"
                         f"background:transparent;border:none;")
        lay.addWidget(dot); lay.addWidget(lb)
        self.setStyleSheet(f"background:rgba(59,130,246,0.08);"
                           f"border:1px solid rgba(59,130,246,0.25);border-radius:20px;")


class StatusRow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 6, 0, 0); lay.setSpacing(8)
        self.dot  = BreatheDot(C['txt3'], 6)
        self.spin = SpinWidget(); self.spin.setVisible(False)
        self.lbl  = QLabel(''); self.lbl.setObjectName('statusInfo')
        lay.addWidget(self.dot); lay.addWidget(self.spin)
        lay.addWidget(self.lbl); lay.addStretch()
        self.setVisible(False)
    def _rs(self, obj):
        self.lbl.setObjectName(obj)
        self.lbl.style().unpolish(self.lbl); self.lbl.style().polish(self.lbl)
    def show_loading(self, t):
        self.setVisible(True); self.dot.setVisible(False); self.spin.setVisible(True)
        self.lbl.setText(t); self._rs('statusInfo')
    def show_ok(self, t):
        self.setVisible(True); self.dot.setVisible(True); self.spin.setVisible(False)
        self.dot.set_color(C['green']); self.lbl.setText(t); self._rs('statusOk')
    def show_err(self, t):
        self.setVisible(True); self.dot.setVisible(True); self.spin.setVisible(False)
        self.dot.set_color(C['red']); self.lbl.setText(t); self._rs('statusErr')
    def show_info(self, t):
        self.setVisible(True); self.dot.setVisible(True); self.spin.setVisible(False)
        self.dot.set_color(C['accent']); self.lbl.setText(t); self._rs('statusInfo')


class SearchBar(QWidget):
    submitted = pyqtSignal(str)
    def __init__(self, icon='🔗', placeholder='Paste a YouTube link…', parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(6)
        self.box = QFrame(); self.box.setObjectName('searchBox'); self.box.setMinimumHeight(62)
        bl = QHBoxLayout(self.box); bl.setContentsMargins(20, 8, 8, 8); bl.setSpacing(10)
        ico = QLabel(icon)
        ico.setStyleSheet(f"font-size:16px;color:{C['txt3']};background:transparent;border:none;")
        self.inp = QLineEdit(); self.inp.setObjectName('searchInput')
        self.inp.setPlaceholderText(placeholder); self.inp.returnPressed.connect(self._go)
        self.inp.focusInEvent  = self._fi
        self.inp.focusOutEvent = self._fo
        self.btn = QPushButton('Fetch  ↗'); self.btn.setObjectName('fetchBtn')
        self.btn.setFixedWidth(120); self.btn.clicked.connect(self._go)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        bl.addWidget(ico); bl.addWidget(self.inp, 1); bl.addWidget(self.btn)
        outer.addWidget(self.box)
        self.status = StatusRow(); outer.addWidget(self.status)
    def _fi(self, e):
        self.box.setObjectName('searchBoxFocused')
        self.box.style().unpolish(self.box); self.box.style().polish(self.box)
        QLineEdit.focusInEvent(self.inp, e)
    def _fo(self, e):
        self.box.setObjectName('searchBox')
        self.box.style().unpolish(self.box); self.box.style().polish(self.box)
        QLineEdit.focusOutEvent(self.inp, e)
    def _go(self):
        u = self.inp.text().strip()
        if u: self.submitted.emit(u)
    def url(self): return self.inp.text().strip()
    def set_loading(self, t): self.btn.setEnabled(False); self.btn.setText('Fetching…'); self.status.show_loading(t)
    def set_done(self, t):    self.btn.setEnabled(True);  self.btn.setText('Fetch  ↗'); self.status.show_ok(t)
    def set_error(self, t):   self.btn.setEnabled(True);  self.btn.setText('Fetch  ↗'); self.status.show_err(t)
    def set_info(self, t):    self.status.show_info(t)


# ────────────────────── Video result card (single reusable widget) ───────────

class VideoResultCard(QFrame):
    """
    A self-contained card that shows all video metadata + download controls.
    Created once per fetched video; multiple cards stack vertically.
    """
    download_saved = pyqtSignal(dict)

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self._info      = info
        self._workers   = {}
        self._vid_ids   = []
        self._aud_ids   = []
        self._active_fmt = 'va'
        self.setObjectName('videoCard')
        self._build()
        self._populate(info)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        cl = QHBoxLayout(self); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)

        # Left thumbnail column
        left = QWidget(); left.setFixedWidth(320)
        left.setStyleSheet("background:#0a0a0e;border-radius:20px 0 0 20px;")
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(0)
        self.thumb = ThumbWidget(320, 215); ll.addWidget(self.thumb)
        dr = QHBoxLayout(); dr.setContentsMargins(10, 4, 10, 10)
        self.dur_badge = mk_lbl('—', 'durBadge')
        dr.addStretch(); dr.addWidget(self.dur_badge)
        ll.addLayout(dr); ll.addStretch()
        cl.addWidget(left)

        # Right detail column
        right = QWidget()
        rl = QVBoxLayout(right); rl.setContentsMargins(20, 18, 20, 14); rl.setSpacing(0)

        self.vc_channel = mk_lbl('—', 'vcChannel'); rl.addWidget(self.vc_channel)
        self.vc_title   = mk_lbl('—', 'vcTitle');   self.vc_title.setWordWrap(True)
        tw = QWidget(); tl_l = QHBoxLayout(tw); tl_l.setContentsMargins(0, 4, 0, 10)
        tl_l.addWidget(self.vc_title); rl.addWidget(tw)

        tags1 = QWidget(); t1l = QHBoxLayout(tags1)
        t1l.setContentsMargins(0, 0, 0, 8); t1l.setSpacing(6)
        self.tag_views = mk_lbl('—', 'tagLabelHi')
        self.tag_likes = mk_lbl('—', 'tagLabel')
        self.tag_date  = mk_lbl('—', 'tagLabel')
        self.tag_size  = mk_lbl('—', 'tagLabel')
        for w in (self.tag_views, self.tag_likes, self.tag_date, self.tag_size):
            t1l.addWidget(w)
        t1l.addStretch(); rl.addWidget(tags1)

        # Format pills
        pr = QHBoxLayout(); pr.setContentsMargins(0, 4, 0, 10); pr.setSpacing(6)
        self._pills = {}
        for key, txt in [('va', 'Video + Audio'), ('ao', 'Audio Only'), ('vo', 'Video Only')]:
            b = QPushButton(txt); b.setObjectName('fmtPill')
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty('active', key == 'va')
            b.clicked.connect(partial(self._set_fmt, key, b))
            pr.addWidget(b); self._pills[key] = b
        pr.addStretch(); rl.addLayout(pr)
        rl.addWidget(sep_h())

        # Download row
        dl_w = QWidget(); dl_l = QVBoxLayout(dl_w)
        dl_l.setContentsMargins(0, 12, 0, 12); dl_l.setSpacing(12)
        row1 = QHBoxLayout(); row1.setSpacing(10)
        for ts, attr in [('QUALITY', 'vid_cb'), ('AUDIO', 'aud_cb'), ('LANGUAGE', 'lang_cb')]:
            col = QVBoxLayout(); col.setSpacing(4)
            col.addWidget(mk_lbl(ts, 'dlLabel'))
            cb = QComboBox(); cb.setMinimumWidth(140); setattr(self, attr, cb)
            col.addWidget(cb); row1.addLayout(col)
        row1.addStretch()
        bc = QVBoxLayout(); bc.setSpacing(4); bc.addWidget(mk_lbl(' ', 'dlLabel'))
        self.dl_btn = QPushButton('↓  Download'); self.dl_btn.setObjectName('dlMainBtn')
        self.dl_btn.setMinimumWidth(120); self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(self._start_dl)
        bc.addWidget(self.dl_btn); row1.addLayout(bc); dl_l.addLayout(row1)

        self.prog_w = QWidget(); self.prog_w.setVisible(False)
        pw_l = QVBoxLayout(self.prog_w); pw_l.setContentsMargins(0, 0, 0, 0); pw_l.setSpacing(6)
        ir = QHBoxLayout()
        self.prog_pct = mk_lbl('0%', 'monoSmall'); self.prog_spd = mk_lbl('—', 'monoSmall')
        ir.addWidget(self.prog_pct); ir.addStretch(); ir.addWidget(self.prog_spd)
        pw_l.addLayout(ir)
        self.prog = SlimProgress(); pw_l.addWidget(self.prog)
        self.prog_status = StatusRow(); pw_l.addWidget(self.prog_status)
        dl_l.addWidget(self.prog_w)
        rl.addWidget(dl_w); rl.addStretch()
        cl.addWidget(right, 1)

    # ── Populate ──────────────────────────────────────────────────────────────

    def _populate(self, info: dict):
        size    = info.get('filesize') or info.get('filesize_approx')
        channel = info.get('uploader') or info.get('channel', '')
        self.vc_channel.setText(channel.upper())
        self.vc_title.setText(info.get('title', ''))
        views = info.get('view_count')
        likes = info.get('like_count')
        ud    = info.get('upload_date', '') or ''
        if len(ud) == 8: ud = f"{ud[6:8]}/{ud[4:6]}/{ud[:4]}"
        self.tag_views.setText(fmt_views(views))
        self.tag_likes.setText(fmt_likes(likes))
        self.tag_date.setText(f"📅 {ud}" if ud else '—')
        self.tag_size.setText(fmt_size(size))
        self.dur_badge.setText(fmt_dur(info.get('duration')))

        turl = best_thumbnail(info)
        if turl:
            tw = ThumbnailFetcher(turl, 320, 215)
            tw.ready.connect(self.thumb.set_pixmap)
            tw.start(); self._workers['thumb'] = tw

        vf, af = parse_formats(info)
        self._vid_ids = []; self._aud_ids = []
        self.vid_cb.clear(); self.aud_cb.clear()
        for t, fid in vf: self.vid_cb.addItem(t); self._vid_ids.append(fid)
        for t, fid in af: self.aud_cb.addItem(t); self._aud_ids.append(fid)
        self.lang_cb.clear(); langs = set()
        for f in info.get('formats', []):
            lang = f.get('language', '')
            if lang and lang not in langs:
                langs.add(lang); self.lang_cb.addItem(lang.capitalize())
        if not langs: self.lang_cb.addItem('Original')
        self.prog_w.setVisible(False); self.prog.reset()
        self.dl_btn.setEnabled(True); self.dl_btn.setText('↓  Download')
        self.dl_btn.setStyleSheet('')

    # ── Interaction ───────────────────────────────────────────────────────────

    def _set_fmt(self, key, _):
        self._active_fmt = key
        for k, b in self._pills.items():
            b.setProperty('active', k == key); b.style().unpolish(b); b.style().polish(b)

    def _start_dl(self):
        out = QFileDialog.getExistingDirectory(self, 'Select Folder', str(Path.home() / 'Downloads'))
        if not out: return
        vi = self.vid_cb.currentIndex(); ai = self.aud_cb.currentIndex()
        vf = self._vid_ids[vi] if vi < len(self._vid_ids) else 'bestvideo'
        af = self._aud_ids[ai] if ai < len(self._aud_ids) else 'bestaudio'
        if   self._active_fmt == 'va': fmt = f"{vf}+{af}/best"
        elif self._active_fmt == 'ao': fmt = af
        else:                           fmt = vf
        url = self._info.get('webpage_url', '')
        self.prog.reset(); self.prog_w.setVisible(True)
        self.dl_btn.setEnabled(False); self.dl_btn.setText('Downloading…')
        self.prog_status.show_loading('Starting…')
        w = DownloadWorker(url, fmt, out)
        w.progress.connect(self._on_prog); w.finished.connect(self._on_done)
        w.error.connect(self._on_err); w.start(); self._workers['dl'] = w

    def _on_prog(self, pct, label):
        self.prog.setValue(pct)
        self.prog_pct.setText(f"{pct:.1f}%")
        self.prog_spd.setText(label)
        self.prog_status.show_info(f"{pct:.1f}%  ·  {label}")

    def _on_done(self, fname):
        self.prog.setValue(100); self.prog_pct.setText('100%'); self.prog_spd.setText('')
        self.dl_btn.setEnabled(True); self.dl_btn.setText('✓  Saved')
        self.dl_btn.setStyleSheet(
            f"background:rgba(74,222,128,0.12);color:{C['green']};"
            f"border:1px solid rgba(74,222,128,0.3);border-radius:10px;"
            f"font-weight:700;padding:0 22px;min-height:40px;")
        self.prog_status.show_ok(f"Saved: {os.path.basename(fname)}")
        self.download_saved.emit({
            'title':         self._info.get('title', ''),
            'url':           self._info.get('webpage_url', ''),
            'duration':      fmt_dur(self._info.get('duration')),
            'downloaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'save_path':     fname,
            'thumbnail':     best_thumbnail(self._info),
        })

    def _on_err(self, msg):
        self.prog_status.show_err(msg[:140])
        self.dl_btn.setEnabled(True); self.dl_btn.setText('↓  Retry')
        self.dl_btn.setStyleSheet('')


# ────────────────────── Single video page ───────────────────────────────────
#
#  Key change: the search bar STAYS at the top always.
#  Each new fetch APPENDS a VideoResultCard below.
#  A "Clear all" button lets the user remove all fetched cards.
#

class SingleVideoPage(QWidget):
    download_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = {}
        self._cards: list[VideoResultCard] = []
        self._build()

    def _build(self):
        # Outer scroll area
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._container = QWidget(); scroll.setWidget(self._container)
        self._root = QVBoxLayout(self._container)
        self._root.setContentsMargins(0, 0, 0, 0); self._root.setSpacing(0)

        # ── Persistent hero / search area (always visible) ────────────────────
        hero = QWidget()
        hl = QVBoxLayout(hero); hl.setContentsMargins(24, 60, 24, 36); hl.setSpacing(0)
        hl.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        badge = HeroBadge('YouTube Media Suite'); badge.setFixedWidth(210)
        bw = QWidget(); bwl = QHBoxLayout(bw)
        bwl.setContentsMargins(0, 0, 0, 22)
        bwl.addStretch(); bwl.addWidget(badge); bwl.addStretch()
        hl.addWidget(bw)

        title = QLabel('Download anything.\nInstantly.')
        title.setObjectName('heroTitle')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter); title.setWordWrap(True)
        hl.addWidget(title)

        sub = QLabel('Paste any YouTube URL below — stack multiple videos!')
        sub.setObjectName('heroSub'); sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sw = QWidget(); swl = QHBoxLayout(sw); swl.setContentsMargins(0, 10, 0, 32)
        swl.addStretch(); swl.addWidget(sub); swl.addStretch(); hl.addWidget(sw)

        # Search bar row
        sbw = QWidget(); sbl = QHBoxLayout(sbw); sbl.setContentsMargins(0, 0, 0, 0)
        self.search = SearchBar('🔗', 'Paste a YouTube link…')
        self.search.setMaximumWidth(700)
        self.search.submitted.connect(self._fetch)
        sbl.addStretch(); sbl.addWidget(self.search, 0); sbl.addStretch()
        hl.addWidget(sbw)

        self._root.addWidget(hero)

        # ── Toolbar row (Clear all button) ────────────────────────────────────
        self._toolbar = QWidget(); self._toolbar.setVisible(False)
        tb_l = QHBoxLayout(self._toolbar)
        tb_l.setContentsMargins(24, 0, 24, 12); tb_l.setSpacing(8)
        self._count_lbl = mk_lbl('', 'monoSmall')
        tb_l.addWidget(self._count_lbl); tb_l.addStretch()
        clr_btn = QPushButton('✕  Clear all'); clr_btn.setObjectName('clearHistBtn')
        clr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clr_btn.clicked.connect(self._clear_cards)
        tb_l.addWidget(clr_btn)
        self._root.addWidget(self._toolbar)

        # ── Cards container ───────────────────────────────────────────────────
        self._cards_w = QWidget()
        self._cards_l = QVBoxLayout(self._cards_w)
        self._cards_l.setContentsMargins(24, 0, 24, 60); self._cards_l.setSpacing(20)
        self._root.addWidget(self._cards_w)
        self._root.addStretch()

    # ── Fetch ─────────────────────────────────────────────────────────────────

    def _fetch(self, url: str):
        clean = normalize_video_url(url)
        if clean != url:
            print(f'[Prism] URL normalised → {clean}')
        self.search.set_loading('Connecting to YouTube…')
        print(f'[Prism] Fetching: {clean}')
        w = VideoInfoWorker(clean)
        w.info_ready.connect(self._on_info)
        w.error.connect(lambda e: self.search.set_error(e[:140]))
        w.start()
        # keep a reference
        self._workers[f'info_{id(w)}'] = w

    def _on_info(self, info: dict):
        self.search.set_done(f'Ready — {len(self._cards) + 1} video(s) loaded')
        card = VideoResultCard(info)
        card.download_saved.connect(self.download_saved)
        self._cards.append(card)
        self._cards_l.addWidget(card)
        self._toolbar.setVisible(True)
        n = len(self._cards)
        self._count_lbl.setText(f"{n} video{'s' if n != 1 else ''} fetched")

        # Smooth reveal animation
        anim = QPropertyAnimation(card, QByteArray(b'maximumHeight'))
        anim.setDuration(350)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(0)
        anim.setEndValue(500)
        anim.start()
        # keep reference so GC doesn't kill it
        self._workers[f'anim_{id(card)}'] = anim

    def _clear_cards(self):
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()
        self._toolbar.setVisible(False)
        self.search.set_info('')
        self.search.status.setVisible(False)


# ────────────────────── Playlist page ───────────────────────────────────────

class ClickableRow(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('plRow')
        self._chk: QCheckBox | None = None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._chk is not None:
            child = self.childAt(event.pos())
            interactive = (QPushButton, QComboBox, QCheckBox, QScrollBar, QAbstractSlider)
            if child is None or not isinstance(child, interactive):
                self._chk.toggle()
        super().mousePressEvent(event)


class PlaylistPage(QWidget):
    download_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items          = []
        self._workers        = {}
        self._done           = 0
        self._loaded         = 0
        self._queue          = []
        self._current_worker = None
        self._is_downloading = False
        self._overall_total  = 0
        self._overall_done   = 0
        self._build()

    def _build(self):
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(scroll)
        container = QWidget(); scroll.setWidget(container)
        root = QVBoxLayout(container); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        hero = QWidget(); hl = QVBoxLayout(hero)
        hl.setContentsMargins(24, 50, 24, 32); hl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        t = mk_lbl('Playlist Downloader', 'sectionTitle'); t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s = mk_lbl('Batch download a YouTube playlist — select videos, track progress', 'sectionSub')
        s.setAlignment(Qt.AlignmentFlag.AlignCenter); hl.addWidget(t)
        sw = QWidget(); sl = QHBoxLayout(sw); sl.setContentsMargins(0, 10, 0, 0)
        sl.addStretch(); sl.addWidget(s); sl.addStretch(); hl.addWidget(sw)
        bw = QWidget(); bl = QHBoxLayout(bw); bl.setContentsMargins(0, 28, 0, 0)
        self.search = SearchBar('📋', 'Paste playlist URL…'); self.search.setMaximumWidth(560)
        self.search.submitted.connect(self._fetch)
        bl.addStretch(); bl.addWidget(self.search, 0); bl.addStretch(); hl.addWidget(bw)
        root.addWidget(hero)

        self.stats_bar = QWidget(); self.stats_bar.setVisible(False)
        sb_l = QHBoxLayout(self.stats_bar)
        sb_l.setContentsMargins(24, 0, 24, 14); sb_l.setSpacing(10)
        self.st_total  = self._mk_stat('0', 'Total',    'plStatNA')
        self.st_loaded = self._mk_stat('0', 'Loaded',   'plStatN')
        self.st_sel    = self._mk_stat('0', 'Selected', 'plStatN')
        self.st_done   = self._mk_stat('0', 'Done',     'plStatNG')
        for sc in (self.st_total, self.st_loaded, self.st_sel, self.st_done):
            sb_l.addWidget(sc)
        sb_l.addStretch()
        qc = QVBoxLayout(); qc.setSpacing(4)
        qc.addWidget(mk_lbl('QUALITY', 'dlLabel'))
        self.batch_q = QComboBox(); self.batch_q.setMinimumWidth(144)
        self.batch_q.addItems(['Best (auto)', '1080p', '720p', '480p', '360p'])
        qc.addWidget(self.batch_q)
        qcw = QWidget(); qcwl = QVBoxLayout(qcw); qcwl.setContentsMargins(0,0,0,0)
        qcwl.addLayout(qc); sb_l.addWidget(qcw)
        btn_col = QVBoxLayout(); btn_col.setSpacing(6)
        btn_col.addWidget(mk_lbl(' ', 'dlLabel'))
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self.sel_all_btn = QPushButton('Select All'); self.sel_all_btn.setObjectName('utilBtn')
        self.sel_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sel_all_btn.clicked.connect(self._select_all)
        btn_row.addWidget(self.sel_all_btn)
        self.dl_sel_btn = QPushButton('↓  Download Selected'); self.dl_sel_btn.setObjectName('dlAllBtn')
        self.dl_sel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_sel_btn.clicked.connect(self._dl_selected)
        btn_row.addWidget(self.dl_sel_btn)
        self.stop_btn = QPushButton('■  Stop'); self.stop_btn.setObjectName('stopBtn')
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.clicked.connect(self._stop_all); self.stop_btn.setVisible(False)
        btn_row.addWidget(self.stop_btn)
        btn_col.addLayout(btn_row)
        btn_col_w = QWidget(); btn_col_wl = QVBoxLayout(btn_col_w); btn_col_wl.setContentsMargins(0,0,0,0)
        btn_col_wl.addLayout(btn_col); sb_l.addWidget(btn_col_w)
        root.addWidget(self.stats_bar)

        self.prog_panel = QWidget(); self.prog_panel.setVisible(False)
        pp_l = QVBoxLayout(self.prog_panel)
        pp_l.setContentsMargins(24, 0, 24, 16); pp_l.setSpacing(10)
        cur_frame = QFrame(); cur_frame.setObjectName('infoSection')
        cur_lay = QVBoxLayout(cur_frame); cur_lay.setContentsMargins(16, 12, 16, 12); cur_lay.setSpacing(6)
        row_c = QHBoxLayout()
        row_c.addWidget(mk_lbl('CURRENT VIDEO', 'plStatL'))
        row_c.addStretch()
        self.curr_pct = mk_lbl('0%', 'monoSmall')
        self.curr_spd = mk_lbl('—',  'monoSmall')
        row_c.addWidget(self.curr_pct); row_c.addSpacing(10); row_c.addWidget(self.curr_spd)
        cur_lay.addLayout(row_c)
        self.curr_prog = SlimProgress(); cur_lay.addWidget(self.curr_prog)
        self.curr_title = mk_lbl('—', 'plRowMeta'); self.curr_title.setWordWrap(True)
        cur_lay.addWidget(self.curr_title)
        pp_l.addWidget(cur_frame)
        ovr_frame = QFrame(); ovr_frame.setObjectName('infoSection')
        ovr_lay = QVBoxLayout(ovr_frame); ovr_lay.setContentsMargins(16, 12, 16, 12); ovr_lay.setSpacing(6)
        row_o = QHBoxLayout()
        row_o.addWidget(mk_lbl('OVERALL PROGRESS', 'plStatL'))
        row_o.addStretch()
        self.ovr_pct = mk_lbl('0 / 0', 'monoSmall')
        row_o.addWidget(self.ovr_pct)
        ovr_lay.addLayout(row_o)
        self.ovr_prog = SlimProgress(); ovr_lay.addWidget(self.ovr_prog)
        pp_l.addWidget(ovr_frame)
        root.addWidget(self.prog_panel)

        self.grid_w = QWidget(); self.grid_l = QVBoxLayout(self.grid_w)
        self.grid_l.setContentsMargins(24, 0, 24, 60); self.grid_l.setSpacing(8)
        self.grid_l.addStretch()
        root.addWidget(self.grid_w); root.addStretch()

    def _mk_stat(self, n, label, obj):
        card = QFrame(); card.setObjectName('statCard')
        l = QVBoxLayout(card); l.setContentsMargins(14, 10, 14, 10); l.setSpacing(2)
        nl = mk_lbl(n, obj); ll = mk_lbl(label.upper(), 'plStatL')
        l.addWidget(nl); l.addWidget(ll); card._n = nl; return card

    def _fetch(self, url):
        if 'pl' in self._workers: self._workers['pl'].stop()
        for i in reversed(range(self.grid_l.count())):
            w = self.grid_l.itemAt(i).widget()
            if w: w.deleteLater()
        self.grid_l.addStretch(); self._items.clear()
        self._done = 0; self._loaded = 0
        self.stats_bar.setVisible(False); self.prog_panel.setVisible(False)
        self.search.set_loading('Loading playlist…')
        w = PlaylistInfoWorker(url)
        w.total_found.connect(self._on_total)
        w.video_ready.connect(self._on_video)
        w.error.connect(lambda e: self.search.set_error(e[:140]))
        w.start(); self._workers['pl'] = w

    def _on_total(self, n):
        self.st_total._n.setText(str(n))
        self.st_loaded._n.setText('0'); self.st_done._n.setText('0'); self.st_sel._n.setText('0')
        self.stats_bar.setVisible(True)

    def _on_video(self, idx, info):
        row = self._make_row(idx, info)
        pos = self.grid_l.count() - 1
        self.grid_l.insertWidget(pos, row); self._items.append(row)
        self._loaded += 1; self.st_loaded._n.setText(str(self._loaded))
        sel = sum(1 for r in self._items if r._chk.isChecked())
        self.st_sel._n.setText(str(sel))
        self.search.set_done(f'{self._loaded} videos loaded')

    def _make_row(self, idx, info):
        row = ClickableRow()
        rl  = QHBoxLayout(row); rl.setContentsMargins(12, 12, 12, 12); rl.setSpacing(12)
        chk = QCheckBox(); chk.setChecked(True)
        chk.setFixedSize(32, 32)
        chk.stateChanged.connect(self._update_sel_count)
        row._chk = chk
        rl.addWidget(chk, 0, Qt.AlignmentFlag.AlignVCenter)
        il = mk_lbl(f"{idx+1:02d}", 'monoSmall')
        il.setFixedWidth(22); il.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(il, 0, Qt.AlignmentFlag.AlignVCenter)
        th = ThumbWidget(144, 81)
        turl = best_thumbnail(info)
        if turl:
            tw = ThumbnailFetcher(turl, 144, 81); tw.ready.connect(th.set_pixmap)
            tw.start(); row._tw = tw
        rl.addWidget(th)
        ic = QVBoxLayout(); ic.setSpacing(4)
        title   = info.get('title', 'Unknown')
        channel = info.get('uploader') or info.get('channel', '') or '—'
        dur     = fmt_dur(info.get('duration'))
        views   = fmt_views(info.get('view_count'))
        likes   = fmt_likes(info.get('like_count'))
        sz      = fmt_size(info.get('filesize') or info.get('filesize_approx'))
        ud      = info.get('upload_date', '') or ''
        if len(ud) == 8: ud = f"{ud[6:8]}/{ud[4:6]}/{ud[:4]}"
        tl   = mk_lbl(title[:85] + ('…' if len(title) > 85 else ''), 'plRowTitle')
        meta = mk_lbl(
            f"📺 {channel}  ·  ⏱ {dur}  ·  👁 {views}  ·  👍 {likes}  ·  💾 {sz}  ·  📅 {ud}",
            'plRowMeta')
        meta.setWordWrap(True)
        row._status_lbl = mk_lbl('', 'monoSmall')
        row._prog = SlimProgress()
        ic.addWidget(tl); ic.addWidget(meta)
        ic.addWidget(row._status_lbl); ic.addWidget(row._prog)
        rl.addLayout(ic, 1)
        act = QVBoxLayout(); act.setSpacing(6)
        act.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        vf, af = parse_formats(info)
        row._vids = [fid for _, fid in vf]
        row._auds = [fid for _, fid in af]
        vc = QComboBox(); vc.setObjectName('smallSelect')
        for t, _ in vf: vc.addItem(t)
        ac = QComboBox(); ac.setObjectName('smallSelect')
        for t, _ in af: ac.addItem(t)
        act.addWidget(vc); act.addWidget(ac)
        row._vc = vc; row._ac = ac
        db = QPushButton('↓  Download'); db.setObjectName('plDlBtn')
        db.setCursor(Qt.CursorShape.PointingHandCursor)
        db.clicked.connect(partial(self._dl_one_now, row))
        row._btn = db; act.addWidget(db)
        rl.addLayout(act)
        row._info = info; return row

    def _update_sel_count(self):
        sel = sum(1 for r in self._items if r._chk.isChecked())
        self.st_sel._n.setText(str(sel))

    def _select_all(self):
        all_checked = all(r._chk.isChecked() for r in self._items)
        for r in self._items:
            r._chk.setChecked(not all_checked)
        self.sel_all_btn.setText('Deselect All' if not all_checked else 'Select All')

    def _dl_one_now(self, row):
        out = QFileDialog.getExistingDirectory(self, 'Select Folder', str(Path.home() / 'Downloads'))
        if not out: return
        vi  = row._vc.currentIndex(); ai = row._ac.currentIndex()
        vf  = row._vids[vi] if vi < len(row._vids) else 'bestvideo'
        af  = row._auds[ai] if ai < len(row._auds) else 'bestaudio'
        fmt = f"{vf}+{af}/best"; url = row._info.get('webpage_url', '')
        row._btn.setEnabled(False); row._btn.setText('Downloading…'); row._prog.reset()
        row._status_lbl.setText('')
        w = DownloadWorker(url, fmt, out)
        w.progress.connect(lambda pct, lbl, r=row: (
            r._prog.setValue(pct),
            r._status_lbl.setText(f"{pct:.1f}%  ·  {lbl}")
        ))
        w.finished.connect(lambda f, r=row, i=row._info: self._mark_done_single(r, f, i))
        w.error.connect(lambda e, r=row: self._mark_err(r, e))
        w.start(); self._workers[url] = w

    def _mark_done_single(self, row, fname, info):
        row._prog.setValue(100); row._btn.setText('✓  Done')
        row._btn.setProperty('done', True)
        row._btn.style().unpolish(row._btn); row._btn.style().polish(row._btn)
        row._status_lbl.setText('✓ Done')
        self._done += 1; self.st_done._n.setText(str(self._done))
        self.download_saved.emit({
            'title': info.get('title', ''), 'url': info.get('webpage_url', ''),
            'duration': fmt_dur(info.get('duration')),
            'downloaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'save_path': fname, 'thumbnail': best_thumbnail(info),
        })

    def _mark_err(self, row, msg):
        row._btn.setEnabled(True); row._btn.setText('↓  Retry')
        row._status_lbl.setText(f"✗ {msg[:50]}")
        self.search.set_error(msg[:80])

    def _dl_selected(self):
        out = QFileDialog.getExistingDirectory(self, 'Select Folder', str(Path.home() / 'Downloads'))
        if not out: return
        qi   = self.batch_q.currentIndex()
        vmap = {0: 'bestvideo', 1: 'bestvideo[height<=1080]', 2: 'bestvideo[height<=720]',
                3: 'bestvideo[height<=480]', 4: 'bestvideo[height<=360]'}
        fmt  = f"{vmap.get(qi, 'bestvideo')}+bestaudio/best"
        queue = []
        for row in self._items:
            if not row._chk.isChecked(): continue
            url = row._info.get('webpage_url', '')
            if not url or row._btn.property('done'): continue
            queue.append((row, url, fmt, out))
        if not queue: return
        self._queue          = queue
        self._is_downloading = True
        self._overall_total  = len(queue)
        self._overall_done   = 0
        self.ovr_pct.setText(f"0 / {self._overall_total}")
        self.ovr_prog.reset(); self.curr_prog.reset()
        self.prog_panel.setVisible(True)
        self.stop_btn.setVisible(True)
        self.dl_sel_btn.setEnabled(False)
        self.search.set_info(f'Downloading {len(queue)} selected videos…')
        self._next_in_queue()

    def _next_in_queue(self):
        if not self._queue or not self._is_downloading:
            self._finish_batch(); return
        row, url, fmt, out = self._queue.pop(0)
        row._btn.setEnabled(False); row._btn.setText('Downloading…')
        row._prog.reset(); row._status_lbl.setText('')
        self.curr_prog.reset()
        self.curr_pct.setText('0%'); self.curr_spd.setText('—')
        self.curr_title.setText(row._info.get('title', '')[:80])
        w = DownloadWorker(url, fmt, out)
        w.progress.connect(lambda pct, lbl, r=row: self._on_curr_prog(pct, lbl, r))
        w.finished.connect(lambda f, r=row, i=row._info: self._on_curr_done(r, f, i))
        w.error.connect(lambda e, r=row: self._on_curr_err(r, e))
        w.start(); self._current_worker = w

    def _on_curr_prog(self, pct, lbl, row):
        self.curr_prog.setValue(pct); self.curr_pct.setText(f"{pct:.1f}%")
        self.curr_spd.setText(lbl); row._prog.setValue(pct)
        row._status_lbl.setText(f"{pct:.1f}%  ·  {lbl}")

    def _on_curr_done(self, row, fname, info):
        row._prog.setValue(100); row._btn.setText('✓  Done')
        row._btn.setProperty('done', True)
        row._btn.style().unpolish(row._btn); row._btn.style().polish(row._btn)
        row._status_lbl.setText('✓ Done')
        self._overall_done += 1; self._done += 1
        self.st_done._n.setText(str(self._done))
        self.ovr_pct.setText(f"{self._overall_done} / {self._overall_total}")
        if self._overall_total > 0:
            self.ovr_prog.setValue(self._overall_done / self._overall_total * 100)
        self.download_saved.emit({
            'title': info.get('title', ''), 'url': info.get('webpage_url', ''),
            'duration': fmt_dur(info.get('duration')),
            'downloaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'save_path': fname, 'thumbnail': best_thumbnail(info),
        })
        self._next_in_queue()

    def _on_curr_err(self, row, msg):
        row._btn.setEnabled(True); row._btn.setText('↓  Retry')
        row._status_lbl.setText(f"✗ {msg[:50]}")
        self._overall_done += 1
        self.ovr_pct.setText(f"{self._overall_done} / {self._overall_total}")
        if self._overall_total > 0:
            self.ovr_prog.setValue(self._overall_done / self._overall_total * 100)
        self._next_in_queue()

    def _stop_all(self):
        self._is_downloading = False; self._queue.clear()
        if self._current_worker:
            try: self._current_worker.abort()
            except: pass
        self._finish_batch(); self.search.set_info('Download stopped.')

    def _finish_batch(self):
        self._is_downloading = False; self.stop_btn.setVisible(False)
        self.dl_sel_btn.setEnabled(True)
        if self._overall_total > 0 and self._overall_done == self._overall_total:
            self.search.set_done(f'All {self._overall_total} videos downloaded.')


# ────────────────────── Thumbnail page ──────────────────────────────────────

class ThumbnailPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self._info = None; self._workers = {}; self._build()
    def _build(self):
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(scroll)
        container = QWidget(); scroll.setWidget(container)
        root = QVBoxLayout(container); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        hero = QWidget(); hl = QVBoxLayout(hero)
        hl.setContentsMargins(24, 50, 24, 40); hl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        t = mk_lbl('Thumbnail Extractor', 'sectionTitle'); t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s = mk_lbl('Download the highest-quality thumbnail from any video', 'sectionSub')
        s.setAlignment(Qt.AlignmentFlag.AlignCenter); hl.addWidget(t)
        sw = QWidget(); sl = QHBoxLayout(sw); sl.setContentsMargins(0, 10, 0, 0)
        sl.addStretch(); sl.addWidget(s); sl.addStretch(); hl.addWidget(sw)
        bw = QWidget(); bl = QHBoxLayout(bw); bl.setContentsMargins(0, 32, 0, 0)
        self.search = SearchBar('🖼', 'Paste video URL…'); self.search.setMaximumWidth(560)
        self.search.submitted.connect(self._fetch)
        bl.addStretch(); bl.addWidget(self.search, 0); bl.addStretch(); hl.addWidget(bw)
        root.addWidget(hero)
        rw = QWidget(); rwl = QHBoxLayout(rw); rwl.setContentsMargins(24, 0, 24, 60)
        self.tb_card = QFrame(); self.tb_card.setObjectName('tbCard')
        self.tb_card.setVisible(False); self.tb_card.setMaximumWidth(820)
        tc = QVBoxLayout(self.tb_card); tc.setContentsMargins(0, 0, 0, 0); tc.setSpacing(0)
        img_f = QWidget()
        img_f.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                            "stop:0 #0d0d14,stop:1 #111120);border-radius:20px 20px 0 0;")
        ifl = QVBoxLayout(img_f); ifl.setContentsMargins(0, 0, 0, 0)
        self.thumb = ThumbWidget(820, 462); self.thumb.setMinimumWidth(400)
        ifl.addWidget(self.thumb); tc.addWidget(img_f)
        ir = QWidget(); irl = QHBoxLayout(ir); irl.setContentsMargins(24, 20, 24, 22); irl.setSpacing(16)
        self.tb_title = mk_lbl('—', 'tbTitleLabel'); self.tb_title.setWordWrap(False)
        self.res_badge = mk_lbl('—', 'resBadge')
        irl.addWidget(self.tb_title, 1); irl.addWidget(self.res_badge)
        btns = QHBoxLayout(); btns.setSpacing(8)
        jpg = QPushButton('↓  JPG'); jpg.setObjectName('tbJpgBtn')
        jpg.setCursor(Qt.CursorShape.PointingHandCursor); jpg.clicked.connect(lambda: self._dl('jpg'))
        png = QPushButton('↓  PNG'); png.setObjectName('tbPngBtn')
        png.setCursor(Qt.CursorShape.PointingHandCursor); png.clicked.connect(lambda: self._dl('png'))
        btns.addWidget(jpg); btns.addWidget(png); irl.addLayout(btns)
        tc.addWidget(ir); rwl.addStretch(); rwl.addWidget(self.tb_card, 0); rwl.addStretch()
        root.addWidget(rw); root.addStretch()
    def _fetch(self, url):
        clean_url = normalize_video_url(url)
        self.search.set_loading('Fetching thumbnail…'); self.tb_card.setVisible(False)
        w = VideoInfoWorker(clean_url); w.info_ready.connect(self._on_info)
        w.error.connect(lambda e: self.search.set_error(e[:140])); w.start(); self._workers['info'] = w
    def _on_info(self, info):
        self._info = info; self.search.set_done('Thumbnail ready')
        self.tb_title.setText(info.get('title', ''))
        turl = best_thumbnail(info)
        if turl:
            tw = ThumbnailFetcher(turl, 820, 462); tw.ready.connect(self._on_thumb)
            tw.start(); self._workers['th'] = tw
        self.tb_card.setVisible(True)
    def _on_thumb(self, pm):
        self.thumb.set_pixmap(pm); self.res_badge.setText(f"{pm.width()} × {pm.height()}  ·  JPEG")
    def _dl(self, ext):
        if not self._info: return
        turl = best_thumbnail(self._info)
        if not turl: return
        title = re.sub(r'[^\w\s-]', '', self._info.get('title', 'thumbnail'))[:60].strip()
        fname, _ = QFileDialog.getSaveFileName(self, 'Save Thumbnail',
            str(Path.home() / 'Downloads' / f"{title}.{ext}"), f"Image (*.{ext})")
        if not fname: return
        def _save():
            try:
                r   = requests.get(turl, timeout=15)
                img = PILImage.open(BytesIO(r.content)).convert('RGB')
                img.save(fname, ext.upper() if ext != 'jpg' else 'JPEG')
                self.search.set_done(f'Saved: {os.path.basename(fname)}')
            except Exception as e:
                self.search.set_error(str(e)[:100])
        threading.Thread(target=_save, daemon=True).start()


# ────────────────────── History page ────────────────────────────────────────

class HistoryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self._fetchers = []; self._build()
    def _build(self):
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(scroll)
        self._container = QWidget(); scroll.setWidget(self._container)
        self._root = QVBoxLayout(self._container)
        self._root.setContentsMargins(0, 0, 0, 0); self._root.setSpacing(0)
        hdr = QWidget(); hl = QHBoxLayout(hdr); hl.setContentsMargins(32, 40, 32, 10); hl.setSpacing(16)
        t = mk_lbl('Download History', 'sectionTitle'); hl.addWidget(t); hl.addStretch()
        self._count_lbl = mk_lbl('0 downloads', 'monoSmall'); hl.addWidget(self._count_lbl)
        self._clear_btn = QPushButton('🗑  Clear All'); self._clear_btn.setObjectName('clearHistBtn')
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._clear_all); hl.addWidget(self._clear_btn)
        self._root.addWidget(hdr)
        self._list_w = QWidget(); self._list_l = QVBoxLayout(self._list_w)
        self._list_l.setContentsMargins(32, 10, 32, 60); self._list_l.setSpacing(10)
        self._empty = mk_lbl('No downloads yet — start downloading!', 'sectionSub')
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_l.addWidget(self._empty); self._list_l.addStretch()
        self._root.addWidget(self._list_w); self.refresh()
    def refresh(self):
        while self._list_l.count() > 2:
            item = self._list_l.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._fetchers.clear()
        data = load_data(); history = data.get('history', [])
        self._count_lbl.setText(f"{len(history)} download{'s' if len(history) != 1 else ''}")
        self._empty.setVisible(len(history) == 0)
        for entry in history:
            card = self._make_card(entry)
            self._list_l.insertWidget(self._list_l.count() - 2, card)
    def _make_card(self, entry):
        card = QFrame(); card.setObjectName('histCard')
        cl = QHBoxLayout(card); cl.setContentsMargins(18, 14, 18, 14); cl.setSpacing(16)
        th_w = QLabel(); th_w.setFixedSize(96, 54)
        th_w.setAlignment(Qt.AlignmentFlag.AlignCenter); th_w.setText('▶')
        th_w.setStyleSheet(f"background:{C['bg3']};border-radius:8px;"
                           f"color:{C['txt3']};font-size:18px;")
        turl = entry.get('thumbnail', '')
        if turl:
            def _set(pm, lw=th_w):
                sc  = pm.scaled(96, 54, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
                fin = QPixmap(96, 54); p = QPainter(fin)
                p.fillRect(0, 0, 96, 54, QColor(C['bg3']))
                p.drawPixmap((96 - sc.width()) // 2, (54 - sc.height()) // 2, sc); p.end()
                lw.setPixmap(fin); lw.setStyleSheet("border-radius:8px;")
            tf = ThumbnailFetcher(turl, 96, 54); tf.ready.connect(_set); tf.start()
            self._fetchers.append(tf)
        cl.addWidget(th_w)
        ic = QVBoxLayout(); ic.setSpacing(4)
        title = entry.get('title', 'Unknown')
        tl = mk_lbl(title[:80] + ('…' if len(title) > 80 else ''), 'histCardTitle')
        path = entry.get('save_path', '')
        ps   = os.path.basename(path)[:50] if path else '—'
        meta = mk_lbl(f"⏱ {entry.get('duration', '—')}  ·  📁 {ps}", 'histCardMeta')
        date = mk_lbl(f"📅 {entry.get('downloaded_at', '?')}", 'histCardDate')
        ic.addWidget(tl); ic.addWidget(meta); ic.addWidget(date)
        cl.addLayout(ic, 1); return card
    def _clear_all(self):
        r = QMessageBox.question(self, 'Clear History', 'Clear all download history?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            d = load_data(); d['history'] = []; save_data(d); self.refresh()
            print('[Prism] History cleared')


# ────────────────────── Console panel ───────────────────────────────────────

class ConsolePanel(QWidget):
    close_clicked = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('slidePanel')
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        hdr = QWidget(); hdr.setObjectName('panelHeader')
        hl  = QHBoxLayout(hdr); hl.setContentsMargins(20, 0, 12, 0); hl.setSpacing(8)
        dot = BreatheDot(C['green'], 6); title = mk_lbl('CONSOLE', 'panelSub')
        hl.addWidget(dot); hl.addWidget(title); hl.addStretch()
        x = QPushButton('✕'); x.setObjectName('panelCloseBtn')
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.clicked.connect(self.close_clicked.emit); hl.addWidget(x)
        lay.addWidget(hdr)
        self.te = QTextEdit(); self.te.setObjectName('consoleEdit'); self.te.setReadOnly(True)
        lay.addWidget(self.te, 1)
        bot = QWidget(); bl = QHBoxLayout(bot); bl.setContentsMargins(12, 8, 12, 8)
        clr = QPushButton('Clear'); clr.setObjectName('utilBtn')
        clr.setCursor(Qt.CursorShape.PointingHandCursor)
        clr.clicked.connect(self.te.clear)
        bl.addStretch(); bl.addWidget(clr); lay.addWidget(bot)
        _S_OUT.text_written.connect(self._append, Qt.ConnectionType.QueuedConnection)
        _S_ERR.text_written.connect(self._append_err, Qt.ConnectionType.QueuedConnection)
        print('[Prism] Console connected.')
    def _append(self, t):
        c = self.te.textCursor(); c.movePosition(QTextCursor.MoveOperation.End)
        self.te.setTextCursor(c); self.te.insertPlainText(t)
        self.te.ensureCursorVisible()
    def _append_err(self, t):
        c = self.te.textCursor(); c.movePosition(QTextCursor.MoveOperation.End)
        self.te.setTextCursor(c)
        fmt = QTextCharFormat(); fmt.setForeground(QColor(C['red']))
        c.insertText(t, fmt); self.te.ensureCursorVisible()


# ────────────────────── Settings panel ──────────────────────────────────────

class SettingsPanel(QWidget):
    close_clicked    = pyqtSignal()
    nav_pos_changed  = pyqtSignal(str)
    bg_anim_changed  = pyqtSignal(bool)
    cursor_color_changed     = pyqtSignal(str)
    top_glow_color_changed   = pyqtSignal(str)
    corner_glow_color_changed= pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('slidePanel')
        d = load_data()
        self._pending          = d.get('nav_position', 'top')
        self._bg_enabled       = d.get('bg_animate', True)
        self._cursor_color     = d.get('cursor_color', '#3b82f6')
        self._top_glow_color   = d.get('top_glow_color', '#3b82f6')
        self._corner_glow_color= d.get('corner_glow_color', '#7c3aed')

        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        hdr = QWidget(); hdr.setObjectName('panelHeader')
        hl  = QHBoxLayout(hdr); hl.setContentsMargins(20, 0, 12, 0); hl.setSpacing(8)
        dot = BreatheDot(C['accent'], 6); title = mk_lbl('SETTINGS', 'panelSub')
        hl.addWidget(dot); hl.addWidget(title); hl.addStretch()
        x = QPushButton('✕'); x.setObjectName('panelCloseBtn')
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.clicked.connect(self.close_clicked.emit); hl.addWidget(x)
        lay.addWidget(hdr)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 28, 24, 28); bl.setSpacing(22)
        scroll.setWidget(body)

        bl.addWidget(mk_lbl('NAV BAR POSITION', 'panelSub'))
        br = QHBoxLayout(); br.setSpacing(12)
        self.btn_top = QPushButton('⬆  Top'); self.btn_top.setObjectName('posBtnTop')
        self.btn_top.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_top.clicked.connect(lambda: self._pick('top'))
        self.btn_bot = QPushButton('⬇  Bottom'); self.btn_bot.setObjectName('posBtnBottom')
        self.btn_bot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bot.clicked.connect(lambda: self._pick('bottom'))
        br.addWidget(self.btn_top); br.addWidget(self.btn_bot); bl.addLayout(br)
        bl.addWidget(mk_lbl('Tab bar moves to top or bottom of the window.', 'monoSmall', wrap=True))
        bl.addWidget(self._div())

        bl.addWidget(mk_lbl('BACKGROUND ANIMATION', 'panelSub'))
        bg_row = QHBoxLayout(); bg_row.setSpacing(12)
        bg_desc = mk_lbl('Moving squares in background', 'statusInfo')
        bg_row.addWidget(bg_desc, 1)
        self.bg_toggle = QPushButton('Enabled' if self._bg_enabled else 'Disabled')
        self.bg_toggle.setObjectName('toggleBtn')
        self.bg_toggle.setProperty('on', self._bg_enabled)
        self.bg_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bg_toggle.clicked.connect(self._toggle_bg)
        bg_row.addWidget(self.bg_toggle); bl.addLayout(bg_row)
        bl.addWidget(mk_lbl('Disable for better performance on slower systems.', 'monoSmall', wrap=True))
        bl.addWidget(self._div())

        bl.addWidget(mk_lbl('CURSOR & CLICK GLOW', 'panelSub'))
        cg_row = QHBoxLayout(); cg_row.setSpacing(10)
        cg_row.addWidget(mk_lbl('Glow colour', 'statusInfo'), 1)
        self.cursor_btn = ColorPickerBtn(self._cursor_color)
        self.cursor_btn.color_changed.connect(self._on_cursor_color)
        cg_row.addWidget(self.cursor_btn); bl.addLayout(cg_row)
        bl.addWidget(mk_lbl(
            'Sets the colour of the radial glow that follows your cursor\nand flashes when you click.',
            'monoSmall', wrap=True))
        bl.addWidget(self._div())

        bl.addWidget(mk_lbl('BACKGROUND GLOW', 'panelSub'))
        tg_row = QHBoxLayout(); tg_row.setSpacing(10)
        tg_row.addWidget(mk_lbl('Top glow colour', 'statusInfo'), 1)
        self.top_glow_btn = ColorPickerBtn(self._top_glow_color)
        self.top_glow_btn.color_changed.connect(self._on_top_glow)
        tg_row.addWidget(self.top_glow_btn); bl.addLayout(tg_row)
        cng_row = QHBoxLayout(); cng_row.setSpacing(10)
        cng_row.addWidget(mk_lbl('Corner glow colour', 'statusInfo'), 1)
        self.corner_glow_btn = ColorPickerBtn(self._corner_glow_color)
        self.corner_glow_btn.color_changed.connect(self._on_corner_glow)
        cng_row.addWidget(self.corner_glow_btn); bl.addLayout(cng_row)
        bl.addWidget(mk_lbl(
            'Top glow radiates from the top-centre of the window.\nCorner glow radiates from the bottom-right corner.',
            'monoSmall', wrap=True))
        bl.addWidget(self._div())

        self.save_btn = QPushButton('  Save Settings  ↓')
        self.save_btn.setObjectName('saveSettingsBtn')
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._save)
        sr = QHBoxLayout(); sr.addStretch(); sr.addWidget(self.save_btn); sr.addStretch()
        bl.addLayout(sr); bl.addStretch()
        lay.addWidget(scroll, 1)
        self._refresh_nav()

    def _div(self):
        f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(f"background:{C['border']};max-height:1px;border:none;")
        return f

    def _pick(self, pos):
        self._pending = pos; self._refresh_nav()

    def _toggle_bg(self):
        self._bg_enabled = not self._bg_enabled
        self.bg_toggle.setText('Enabled' if self._bg_enabled else 'Disabled')
        self.bg_toggle.setProperty('on', self._bg_enabled)
        self.bg_toggle.style().unpolish(self.bg_toggle)
        self.bg_toggle.style().polish(self.bg_toggle)
        self.bg_anim_changed.emit(self._bg_enabled)

    def _on_cursor_color(self, color: str):
        self._cursor_color = color; self.cursor_color_changed.emit(color)

    def _on_top_glow(self, color: str):
        self._top_glow_color = color; self.top_glow_color_changed.emit(color)

    def _on_corner_glow(self, color: str):
        self._corner_glow_color = color; self.corner_glow_color_changed.emit(color)

    def _refresh_nav(self):
        self.btn_top.setProperty('active', self._pending == 'top')
        self.btn_top.style().unpolish(self.btn_top); self.btn_top.style().polish(self.btn_top)
        self.btn_bot.setProperty('active', self._pending == 'bottom')
        self.btn_bot.style().unpolish(self.btn_bot); self.btn_bot.style().polish(self.btn_bot)

    def _save(self):
        d = load_data()
        d['nav_position']       = self._pending
        d['bg_animate']         = self._bg_enabled
        d['cursor_color']       = self._cursor_color
        d['top_glow_color']     = self._top_glow_color
        d['corner_glow_color']  = self._corner_glow_color
        save_data(d)
        print(f'[Prism] Settings saved → nav={self._pending}')
        self.nav_pos_changed.emit(self._pending)
        self.save_btn.setText('✓  Saved!')
        QTimer.singleShot(1600, lambda: self.save_btn.setText('  Save Settings  ↓'))

    def sync_pos(self, pos):
        self._pending = pos; self._refresh_nav()

    def sync_bg(self, val: bool):
        self._bg_enabled = val
        self.bg_toggle.setText('Enabled' if val else 'Disabled')
        self.bg_toggle.setProperty('on', val)
        self.bg_toggle.style().unpolish(self.bg_toggle)
        self.bg_toggle.style().polish(self.bg_toggle)

    def sync_cursor_color(self, color: str):
        self._cursor_color = color; self.cursor_btn.set_color(color)

    def sync_top_glow(self, color: str):
        self._top_glow_color = color; self.top_glow_btn.set_color(color)

    def sync_corner_glow(self, color: str):
        self._corner_glow_color = color; self.corner_glow_btn.set_color(color)


# ────────────────────── Logo bar ────────────────────────────────────────────

class LogoBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('logoBar')
        lay = QHBoxLayout(self); lay.setContentsMargins(24, 0, 24, 0); lay.setSpacing(0)
        dot  = BreatheDot(C['accent'], 8)
        logo = QLabel('Prism'); logo.setObjectName('logoLabel')
        lay.addWidget(dot); lay.addSpacing(8); lay.addWidget(logo); lay.addStretch()
        ver = QLabel('v7.3'); ver.setObjectName('versionLabel'); lay.addWidget(ver)


# ────────────────────── Tab navigation ──────────────────────────────────────

class TabNav(QWidget):
    tab_changed     = pyqtSignal(int)
    console_toggle  = pyqtSignal(bool)
    settings_toggle = pyqtSignal(bool)
    history_clicked = pyqtSignal()

    TABS = [('Download', 0), ('Playlist', 1), ('Thumbnail', 2)]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('topNav')
        self._btns       = []
        self._con_active = False
        self._set_active = False
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 0, 16, 0); root.setSpacing(0)
        self._sbtn = QPushButton('⚙  Settings'); self._sbtn.setObjectName('utilBtn')
        self._sbtn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sbtn.clicked.connect(self._tog_set)
        self._cbtn = QPushButton('>_  Console'); self._cbtn.setObjectName('utilBtn')
        self._cbtn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cbtn.clicked.connect(self._tog_con)
        left_w = QWidget(); left_l = QHBoxLayout(left_w)
        left_l.setContentsMargins(0, 0, 0, 0); left_l.setSpacing(8)
        left_l.addWidget(self._sbtn); left_l.addWidget(self._cbtn)
        root.addWidget(left_w); root.addStretch(1)
        tc = QWidget(); tc.setObjectName('tabsContainer')
        tbl = QHBoxLayout(tc); tbl.setContentsMargins(4, 4, 4, 4); tbl.setSpacing(2)
        for name, idx in self.TABS:
            b = QPushButton(name); b.setObjectName('navTab')
            b.setProperty('active', idx == 0); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(partial(self._sel, idx)); tbl.addWidget(b); self._btns.append(b)
        hb = QPushButton('History'); hb.setObjectName('navTab')
        hb.setProperty('active', False); hb.setCursor(Qt.CursorShape.PointingHandCursor)
        hb.clicked.connect(self._on_hist); tbl.addWidget(hb)
        self._btns.append(hb); self._hbtn = hb
        root.addWidget(tc); root.addStretch(1)
        self._right_spacer = QWidget(); root.addWidget(self._right_spacer)

    def _sync_spacer(self):
        left_w = self._sbtn.parentWidget()
        if left_w:
            self._right_spacer.setFixedWidth(left_w.sizeHint().width())

    def showEvent(self, e):
        super().showEvent(e); self._sync_spacer()

    def _sel(self, idx):
        for i, b in enumerate(self._btns):
            b.setProperty('active', i == idx); b.style().unpolish(b); b.style().polish(b)
        self.tab_changed.emit(idx)

    def _on_hist(self):
        for i, b in enumerate(self._btns):
            b.setProperty('active', i == 3); b.style().unpolish(b); b.style().polish(b)
        self.history_clicked.emit()

    def _tog_con(self):
        self._con_active = not self._con_active
        self._cbtn.setProperty('active', self._con_active)
        self._cbtn.style().unpolish(self._cbtn); self._cbtn.style().polish(self._cbtn)
        if self._con_active and self._set_active:
            self._set_active = False
            self._sbtn.setProperty('active', False)
            self._sbtn.style().unpolish(self._sbtn); self._sbtn.style().polish(self._sbtn)
            self.settings_toggle.emit(False)
        self.console_toggle.emit(self._con_active)

    def _tog_set(self):
        self._set_active = not self._set_active
        self._sbtn.setProperty('active', self._set_active)
        self._sbtn.style().unpolish(self._sbtn); self._sbtn.style().polish(self._sbtn)
        if self._set_active and self._con_active:
            self._con_active = False
            self._cbtn.setProperty('active', False)
            self._cbtn.style().unpolish(self._cbtn); self._cbtn.style().polish(self._cbtn)
            self.console_toggle.emit(False)
        self.settings_toggle.emit(self._set_active)

    def force_close_panels(self):
        self._con_active = False; self._set_active = False
        for b in (self._cbtn, self._sbtn):
            b.setProperty('active', False); b.style().unpolish(b); b.style().polish(b)

    def set_bottom_style(self, bottom: bool):
        self.setObjectName('bottomNav' if bottom else 'topNav')
        self.style().unpolish(self); self.style().polish(self)


# ────────────────────── Main window ─────────────────────────────────────────

class NexusApp(QMainWindow):
    LOGO_H  = 46
    NAV_H   = 58
    PANEL_W = 420

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Prism — YouTube Media Suite v7.3')
        self.setMinimumSize(1080, 700); self.resize(1300, 840)
        self._nav_pos  = 'top'
        self._con_open = False
        self._set_open = False
        self._con_anim = None
        self._set_anim = None
        self._nav_anim = None
        self._stk_anim = None
        self._build()
        self._load_prefs()
        QApplication.instance().installEventFilter(self)

    def _build(self):
        central = QWidget(); self.setCentralWidget(central)
        central.setMouseTracking(True)
        d = load_data()
        self.bg_canvas = AnimatedSquaresBg(
            central,
            top_glow_color    = d.get('top_glow_color',    '#3b82f6'),
            corner_glow_color = d.get('corner_glow_color', '#7c3aed'),
        )
        self.stack = QStackedWidget(central); self.stack.setStyleSheet('background:transparent;')
        self.p_video    = SingleVideoPage()
        self.p_playlist = PlaylistPage()
        self.p_thumb    = ThumbnailPage()
        self.p_history  = HistoryPage()
        for p in (self.p_video, self.p_playlist, self.p_thumb, self.p_history):
            self.stack.addWidget(p)
        self.logo_bar = LogoBar(central)
        self.tab_nav = TabNav(central)
        self.tab_nav.tab_changed.connect(self.stack.setCurrentIndex)
        self.tab_nav.history_clicked.connect(lambda: self.stack.setCurrentIndex(3))
        self.tab_nav.console_toggle.connect(self._on_con_toggle)
        self.tab_nav.settings_toggle.connect(self._on_set_toggle)
        self.con_panel = ConsolePanel(central)
        self.set_panel = SettingsPanel(central)
        self.con_panel.close_clicked.connect(self._close_con)
        self.set_panel.close_clicked.connect(self._close_set)
        self.set_panel.nav_pos_changed.connect(self._animate_nav)
        self.set_panel.bg_anim_changed.connect(self.bg_canvas.set_enabled)
        self.set_panel.cursor_color_changed.connect(self._on_cursor_color)
        self.set_panel.top_glow_color_changed.connect(self.bg_canvas.set_top_glow_color)
        self.set_panel.corner_glow_color_changed.connect(self.bg_canvas.set_corner_glow_color)
        self.p_video.download_saved.connect(self._save_hist)
        self.p_playlist.download_saved.connect(self._save_hist)
        self.glow = CursorGlow(central, color=d.get('cursor_color', '#3b82f6'))
        self._place_all()

    def _on_cursor_color(self, color: str):
        self.glow.set_color(color)

    def _place_all(self):
        c = self.centralWidget()
        W = c.width()  or self.width()
        H = c.height() or self.height()
        lh = self.LOGO_H; nh = self.NAV_H; pw = self.PANEL_W
        self.bg_canvas.setGeometry(0, 0, W, H)
        self.glow.setGeometry(0, 0, W, H); self.glow.raise_()
        self.logo_bar.setGeometry(0, 0, W, lh)
        if self._nav_pos == 'top':
            self.tab_nav.setGeometry(0, lh, W, nh)
            self.stack.setGeometry(0, lh + nh, W, H - lh - nh)
        else:
            self.tab_nav.setGeometry(0, H - nh, W, nh)
            self.stack.setGeometry(0, lh, W, H - lh - nh)
        cx = W - pw if self._con_open else W
        sx = W - pw if self._set_open else W
        if self._con_anim is None or self._con_anim.state() != QAbstractAnimation.State.Running:
            self.con_panel.setGeometry(cx, 0, pw, H)
        if self._set_anim is None or self._set_anim.state() != QAbstractAnimation.State.Running:
            self.set_panel.setGeometry(sx, 0, pw, H)
        self.logo_bar.raise_(); self.tab_nav.raise_()
        self.con_panel.raise_(); self.set_panel.raise_(); self.glow.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e); self._place_all()

    def _load_prefs(self):
        d = load_data()
        pos          = d.get('nav_position',      'top')
        bg           = d.get('bg_animate',        True)
        cursor_color = d.get('cursor_color',      '#3b82f6')
        top_glow     = d.get('top_glow_color',    '#3b82f6')
        corner_glow  = d.get('corner_glow_color', '#7c3aed')
        self._nav_pos = pos
        self.tab_nav.set_bottom_style(pos == 'bottom')
        self.set_panel.sync_pos(pos)
        self.bg_canvas.set_enabled(bg)
        self.bg_canvas.set_top_glow_color(top_glow)
        self.bg_canvas.set_corner_glow_color(corner_glow)
        self.glow.set_color(cursor_color)
        self.set_panel.sync_bg(bg)
        self.set_panel.sync_cursor_color(cursor_color)
        self.set_panel.sync_top_glow(top_glow)
        self.set_panel.sync_corner_glow(corner_glow)
        self._place_all()
        print(f'[Prism] Prefs loaded: nav={pos}')

    def _save_hist(self, entry):
        d = load_data(); d['history'].insert(0, entry); d['history'] = d['history'][:500]
        save_data(d); self.p_history.refresh()
        print(f'[Prism] Saved to history: {entry.get("title", "?")}')

    def _slide(self, panel: QWidget, open_it: bool, anim_attr: str, open_attr: str):
        c = self.centralWidget(); W = c.width(); H = c.height(); pw = self.PANEL_W
        old = getattr(self, anim_attr, None)
        if old is not None:
            try:
                if old.state() == QAbstractAnimation.State.Running: old.stop()
            except RuntimeError: pass
        start_x = panel.x()
        end_x   = W - pw if open_it else W
        if open_it:
            panel.setVisible(True); panel.raise_(); self.glow.raise_()
        anim = QPropertyAnimation(panel, QByteArray(b'geometry'))
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic if open_it else QEasingCurve.Type.InCubic)
        anim.setStartValue(QRect(start_x, 0, pw, H))
        anim.setEndValue(QRect(end_x, 0, pw, H))
        setattr(self, anim_attr, anim); setattr(self, open_attr, open_it)
        if not open_it:
            anim.finished.connect(lambda: panel.setVisible(False))
        anim.start()

    def _on_con_toggle(self, open_it: bool):
        self._slide(self.con_panel, open_it, '_con_anim', '_con_open')

    def _on_set_toggle(self, open_it: bool):
        self._slide(self.set_panel, open_it, '_set_anim', '_set_open')

    def _close_con(self):
        self.tab_nav.force_close_panels()
        self._slide(self.con_panel, False, '_con_anim', '_con_open')

    def _close_set(self):
        self.tab_nav.force_close_panels()
        self._slide(self.set_panel, False, '_set_anim', '_set_open')

    def _animate_nav(self, new_pos: str):
        if new_pos == self._nav_pos: return
        c = self.centralWidget(); W = c.width(); H = c.height()
        lh = self.LOGO_H; nh = self.NAV_H
        for a in ('_nav_anim', '_stk_anim'):
            old = getattr(self, a, None)
            if old:
                try:
                    if old.state() == QAbstractAnimation.State.Running: old.stop()
                except RuntimeError: pass
        if new_pos == 'bottom':
            ns = QRect(0, lh, W, nh);          ne = QRect(0, H - nh, W, nh)
            ss = QRect(0, lh + nh, W, H-lh-nh); se = QRect(0, lh, W, H-lh-nh)
        else:
            ns = QRect(0, H - nh, W, nh);      ne = QRect(0, lh, W, nh)
            ss = QRect(0, lh, W, H-lh-nh);     se = QRect(0, lh+nh, W, H-lh-nh)
        self.tab_nav.set_bottom_style(new_pos == 'bottom')
        self._nav_anim = QPropertyAnimation(self.tab_nav, QByteArray(b'geometry'))
        self._nav_anim.setDuration(400)
        self._nav_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._nav_anim.setStartValue(ns); self._nav_anim.setEndValue(ne)
        self._stk_anim = QPropertyAnimation(self.stack, QByteArray(b'geometry'))
        self._stk_anim.setDuration(400)
        self._stk_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._stk_anim.setStartValue(ss); self._stk_anim.setEndValue(se)
        def _done():
            self._nav_pos = new_pos
            self.set_panel.sync_pos(new_pos); self._place_all()
        self._stk_anim.finished.connect(_done)
        self._nav_anim.start(); self._stk_anim.start()
        print(f'[Prism] Nav → {new_pos}')

    def mousePressEvent(self, event):
        self.glow.click_flash(); super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseMove:
            gpos = QCursor.pos(); lpos = self.centralWidget().mapFromGlobal(gpos)
            if self.centralWidget().rect().contains(lpos): self.glow.move_to(lpos)
            else: self.glow.fade_out()
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            gpos = QCursor.pos(); lpos = self.centralWidget().mapFromGlobal(gpos)
            if self.centralWidget().rect().contains(lpos):
                if event.type() == QEvent.Type.MouseButtonPress:
                    self.glow.click_flash()
        return super().eventFilter(obj, event)


# ────────────────────── Entry point ─────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Prism'); app.setStyle('Fusion')
    app.setStyleSheet(STYLESHEET)

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,          QColor(C['bg']))
    pal.setColor(QPalette.ColorRole.WindowText,      QColor(C['txt']))
    pal.setColor(QPalette.ColorRole.Base,            QColor(C['bg2']))
    pal.setColor(QPalette.ColorRole.AlternateBase,   QColor(C['bg3']))
    pal.setColor(QPalette.ColorRole.Text,            QColor(C['txt']))
    pal.setColor(QPalette.ColorRole.Button,          QColor(C['bg2']))
    pal.setColor(QPalette.ColorRole.ButtonText,      QColor(C['txt']))
    pal.setColor(QPalette.ColorRole.Highlight,       QColor(C['accent']))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor('#ffffff'))
    pal.setColor(QPalette.ColorRole.Link,            QColor(C['accent2']))
    app.setPalette(pal)

    print('[Prism] v7.3 starting…')

    data_exists = DATA_FILE.exists()

    if not data_exists:
        splash_container = QWidget()
        splash_container.setWindowTitle('Prism')
        splash_container.resize(1300, 840)
        splash_container.setStyleSheet(f"background:{C['bg']};")
        splash = HelloSplash(splash_container)
        splash.resize(splash_container.size())
        splash_container.show()
        win = None
        def _launch():
            nonlocal win
            splash_container.close()
            win = NexusApp()
            win.show()
        splash.finished.connect(_launch)
        splash_container.resizeEvent = lambda e: splash.resize(splash_container.size())
    else:
        win = NexusApp()
        win.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
