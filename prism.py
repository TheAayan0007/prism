#!/usr/bin/env python3
"""
Prism — YouTube Media Suite  (PyQt6 + yt-dlp)

    python index.py            run  (missing packages are installed automatically)
    python index.py --update   upgrade yt-dlp first — do this whenever downloads stop working

Needs Python 3.10+.  For full YouTube support yt-dlp also wants a JavaScript runtime
(Deno, Node.js 22+ or QuickJS) on PATH.  ffmpeg is bundled automatically if missing.
"""
from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    sys.exit('Prism needs Python 3.10 or newer.')

import hashlib
import importlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote_plus

softname = "Prism"


def _bootstrap() -> None:
    """Install whatever is missing (and upgrade yt-dlp on --update) before the heavy imports."""
    update   = '--update' in sys.argv
    sys.argv = [a for a in sys.argv if a != '--update']
    find     = importlib.util.find_spec
    need     = []
    if find('PyQt6') is None:
        need.append('PyQt6')
    if find('requests') is None:
        need.append('requests')
    # Qt WebEngine is best installed from the OS package manager on Debian/Kali.
    # pip cannot install into an externally-managed system Python (PEP 668).
    try:
        webengine_missing = find('PyQt6.QtWebEngineWidgets') is None
    except (ModuleNotFoundError, ValueError):
        webengine_missing = True
    if webengine_missing and sys.stdout:
        print(f'[{softname}] Qt WebEngine is missing. On Kali/Debian run:', flush=True)
        print('    sudo apt update && sudo apt install python3-pyqt6.qtwebengine', flush=True)
        print('    (Do not install this system package with pip.)', flush=True)
    if find('yt_dlp') is None or find('yt_dlp_ejs') is None or update:
        need.append('yt-dlp[default]')      # [default] pulls in yt-dlp-ejs, the YouTube JS solver
    if find('imageio_ffmpeg') is None and shutil.which('ffmpeg') is None:
        need.append('imageio-ffmpeg')       # portable ffmpeg when none is installed
    if not need:
        return
    if sys.stdout:
        print(f'[{softname}] Installing / updating: {", ".join(need)} …', flush=True)
    cmd = [sys.executable, '-m', 'pip', 'install', '-q', '-U', '--retries', '1', '--timeout', '15', *need]
    # pip on "externally managed" Pythons (Debian/Ubuntu/Homebrew) needs this extra flag
    if subprocess.run(cmd, check=False).returncode != 0:
        subprocess.run(cmd + ['--break-system-packages'], check=False)
    importlib.invalidate_caches()


_bootstrap()

try:
    import requests
    import yt_dlp
    import yt_dlp.utils
    from yt_dlp.version import __version__ as YTDLP_VERSION
    from PyQt6.QtCore import (
        QAbstractAnimation, QByteArray, QEasingCurve, QEvent, QObject, QUrl,
        QParallelAnimationGroup, QPoint, QPointF, QPropertyAnimation, QRect, QRectF,
        QRunnable, QThread, QThreadPool, QTimer, Qt, pyqtSignal,
    )
    from PyQt6.QtGui import (
        QBrush, QColor, QCursor, QDesktopServices, QFont, QFontInfo, QFontMetrics, QImage,
        QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPalette, QPen, QPixmap,
        QRadialGradient, QTextCharFormat, QTextCursor,
    )
    from PyQt6.QtWidgets import (
        QAbstractSlider, QApplication, QCheckBox, QColorDialog, QComboBox, QFileDialog,
        QFontComboBox, QFrame, QGraphicsBlurEffect, QGraphicsOpacityEffect, QHBoxLayout,
        QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QScrollBar,
        QSlider, QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QSizePolicy,
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings
except ImportError as _err:
    if 'QtWebEngine' in str(_err) or 'QtWebEngineWidgets' in str(_err):
        sys.exit(f'[{softname}] Qt WebEngine is required for in-app video playback.\n'
                 'On Kali/Debian install it with: sudo apt install python3-pyqt6.qtwebengine')
    sys.exit(f'[{softname}] Missing dependency ({_err}).\n'
             f'Install the missing package in your Python environment, then run Prism again.')

# ─── Fixed storage: always C:\\Prism\\Main.json ───────────────────────────────
PRISM_DIR = Path('C:/Prism')
DATA_FILE = PRISM_DIR / 'Main.json'

def _ensure_prism_dir():
    """Create C:\\Prism if it doesn't exist yet. Falls back to script dir on non-Windows."""
    global DATA_FILE
    try:
        PRISM_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        fallback = Path(__file__).parent / 'Main.json'
        DATA_FILE = fallback
        import sys as _sys
        _sys.stderr.write(f'[Prism] WARNING: cannot create C:/Prism ({e}), '
                          f'falling back to {fallback}\n')

_ensure_prism_dir()

# ─────────────────────────── Console redirection ────────────────────────────

class ConsoleStream(QObject):
    text_written = pyqtSignal(str)
    encoding = 'utf-8'
    errors   = 'replace'
    def isatty(self): return False
    def __init__(self, orig=None):
        super().__init__(); self._orig = orig
    def write(self, t):
        if t:
            self.text_written.emit(str(t))
            if self._orig:
                try: self._orig.write(t)
                except Exception: pass
    def flush(self):
        if self._orig:
            try: self._orig.flush()
            except Exception: pass
    def fileno(self):
        if self._orig:
            try: return self._orig.fileno()
            except Exception: pass
        return -1

_ORIG_OUT = sys.stdout
_ORIG_ERR = sys.stderr
_S_OUT    = ConsoleStream(_ORIG_OUT)
_S_ERR    = ConsoleStream(_ORIG_ERR)
sys.stdout = _S_OUT
sys.stderr = _S_ERR

# ─────────────────────────── Persistence ────────────────────────────────────

_DATA_DEFAULTS = {
    'nav_position':       'top',
    'history':            [],
    'bg_animate':         True,
    'cursor_color':       '#3b82f6',
    'top_glow_color':     '#3b82f6',
    'corner_glow_color':  '#7c3aed',
    'font_family':        'Outfit',
    'splash_font':        'Outfit',
    'splash_enabled':     True,
    'settings_blur':      18,
    'settings_history':   [],
    'download_folder':    '',
    'ask_download_folder': True,
}

def load_data():
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
            for k, v in _DATA_DEFAULTS.items():
                d.setdefault(k, v)
            return d
        except Exception:
            pass
    return dict(_DATA_DEFAULTS)

def save_data(d):
    _ensure_prism_dir()
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f'[{softname}] save_data error: {e}', file=sys.stderr)

# ─────────────────────── Download folder helper ─────────────────────────────

def get_download_dir(parent_widget=None) -> str:
    """Return the configured download folder, or ask the user if not set.
    Returns empty string if user cancels the picker."""
    d = load_data()
    folder = d.get('download_folder', '').strip()
    if folder and Path(folder).is_dir():
        return folder
    # Ask every time (or folder not set / no longer valid)
    chosen = QFileDialog.getExistingDirectory(
        parent_widget, 'Select Download Folder',
        str(Path.home() / 'Downloads')
    )
    return chosen   # may be '' if cancelled

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
    background: transparent;
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
    background:rgba(10,10,16,0.82);
    border-left:1px solid {C['border2']};
}}

/* ═══════════════════ SETTINGS MODAL — PREMIUM ═══════════════════ */
#settingsModal {{ background: transparent; }}

#settingsCard {{
    background: rgba(10,10,18,0.82);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 18px;
}}

/* Header */
#sHdr {{
    background: #0a0a11;
    border-bottom: 1px solid rgba(255,255,255,0.055);
    border-radius: 18px 18px 0 0;
    min-height: 66px; max-height: 66px;
}}
QLabel#sHdrTitle {{
    color: {C['txt']};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.3px;
}}
QLabel#sHdrSub {{
    color: {C['txt3']};
    font-size: 11px;
    font-weight: 400;
    letter-spacing: 0.5px;
}}
QPushButton#sCloseBtn {{
    background: rgba(255,255,255,0.0);
    border: 1px solid transparent;
    border-radius: 8px;
    color: {C['txt3']};
    font-size: 16px;
    min-width: 32px; max-width: 32px;
    min-height: 32px; max-height: 32px;
}}
QPushButton#sCloseBtn:hover {{
    background: rgba(255,255,255,0.06);
    border-color: rgba(255,255,255,0.08);
    color: {C['txt']};
}}

/* Section label */
QLabel#sSecLabel {{
    color: {C['txt3']};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.4px;
}}

/* Row card */
#sRow {{
    background: rgba(255,255,255,0.022);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 12px;
}}

/* Row title */
QLabel#sRowTitle {{
    color: {C['txt']};
    font-size: 13px;
    font-weight: 600;
}}

/* Row description */
QLabel#sRowDesc {{
    color: {C['txt2']};
    font-size: 11px;
    font-weight: 400;
    letter-spacing: 0.1px;
}}

/* Path label */
QLabel#sPathLbl {{
    color: {C['txt3']};
    font-size: 10px;
    font-weight: 400;
    font-family: 'Consolas', 'Courier New', monospace;
}}

/* Nav position pills */
QPushButton#sPosBtn {{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 9px;
    color: {C['txt2']};
    font-size: 12px;
    font-weight: 600;
    min-height: 38px;
    letter-spacing: 0.2px;
}}
QPushButton#sPosBtn:hover {{
    background: rgba(255,255,255,0.055);
    border-color: rgba(255,255,255,0.10);
    color: {C['txt']};
}}
QPushButton#sPosBtn[active=true] {{
    background: rgba(59,130,246,0.12);
    border: 1px solid rgba(59,130,246,0.35);
    color: {C['accent2']};
}}

/* Toggle pill */
QPushButton#sToggleBtn {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 20px;
    color: {C['txt2']};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    min-height: 28px;
    max-height: 28px;
    padding: 0 16px;
}}
QPushButton#sToggleBtn[on=true] {{
    background: rgba(59,130,246,0.15);
    border-color: rgba(59,130,246,0.40);
    color: {C['accent2']};
}}
QPushButton#sToggleBtn:hover {{
    border-color: rgba(255,255,255,0.14);
    color: {C['txt']};
}}
QPushButton#sToggleBtn[on=true]:hover {{
    background: rgba(59,130,246,0.22);
}}

/* Ghost action buttons (Reset, Choose Folder) */
QPushButton#sGhostBtn {{
    background: transparent;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    color: {C['txt2']};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.3px;
    min-height: 30px;
    padding: 0 14px;
}}
QPushButton#sGhostBtn:hover {{
    background: rgba(255,255,255,0.05);
    border-color: rgba(255,255,255,0.14);
    color: {C['txt']};
}}
QPushButton#sGhostBtn[danger=true]:hover {{
    background: rgba(239,68,68,0.08);
    border-color: rgba(239,68,68,0.30);
    color: #f87171;
}}

/* Font combo */
QFontComboBox#sFontCombo {{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 9px;
    color: {C['txt']};
    font-size: 12px;
    font-weight: 500;
    min-height: 32px;
    padding: 0 10px;
    selection-background-color: rgba(59,130,246,0.25);
}}
QFontComboBox#sFontCombo:focus {{
    border-color: rgba(59,130,246,0.35);
}}

/* Footer */
#sFooter {{
    background: rgba(0,0,0,0.25);
    border-top: 1px solid rgba(255,255,255,0.045);
    border-radius: 0 0 18px 18px;
    min-height: 68px; max-height: 68px;
}}
QPushButton#sSaveBtn {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #2563eb, stop:1 #1d4ed8);
    border: none;
    border-radius: 10px;
    color: white;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.2px;
    min-height: 42px;
    min-width: 148px;
    padding: 0 28px;
}}
QPushButton#sSaveBtn:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #3b82f6, stop:1 #2563eb);
}}
QPushButton#sSaveBtn:pressed {{
    background: #1d4ed8;
}}
QPushButton#sCancelBtn {{
    background: transparent;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    color: {C['txt2']};
    font-size: 13px;
    font-weight: 600;
    min-height: 42px;
    min-width: 96px;
    padding: 0 22px;
}}
QPushButton#sCancelBtn:hover {{
    background: rgba(255,255,255,0.04);
    border-color: rgba(255,255,255,0.14);
    color: {C['txt']};
}}
#panelHeader {{
    background:rgba(8,8,14,0.88);
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

QFontComboBox {{
    background:{C['bg3']}; border:1px solid {C['border']};
    border-radius:10px; color:{C['txt']};
    font-size:13px; padding:8px 32px 8px 13px; min-height:40px;
}}
QFontComboBox:focus {{ border-color:{C['accent']}; }}
QFontComboBox:hover {{ border-color:{C['border2']}; }}
QFontComboBox::drop-down {{ border:none; width:24px; }}
QFontComboBox::down-arrow {{
    image:none;
    border-left:4px solid transparent; border-right:4px solid transparent;
    border-top:5px solid {C['txt3']}; width:0; height:0;
}}
QFontComboBox QAbstractItemView {{
    background:{C['bg3']}; border:1px solid {C['border2']};
    color:{C['txt']}; selection-background-color:rgba(59,130,246,0.2);
    selection-color:{C['accent2']}; padding:4px; outline:none;
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
#  SPLASH SCREEN
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

    _RING_DUR    = 72
    _RING_START  = 12
    _PULSE_START = 86
    _NEXUS_START = 90
    _LINE_START  = 118
    _SUB_START   = 136
    _FADE_START  = 370
    _FADE_DUR    = 46

    def __init__(self, parent=None, font_family: str = ''):
        super().__init__(parent)
        self.setStyleSheet('background:#000008;')
        self._splash_font = font_family or 'Outfit'
        self._t = 0
        self._ring_arc   = 0.0
        self._ring_alpha = 0.0
        self._ring_fade  = 1.0
        self._pulse      = 0.0
        self._sparks: list[dict] = []
        self._nex_alpha = 0.0
        self._nex_glow  = 0.0
        self._nex_y     = 22.0
        self._line_w    = 0.0
        self._line_a    = 0.0
        self._dot_a     = 0.0
        self._sub_a     = 0.0
        self._ver_a     = 0.0
        self._bg_a      = 0.0
        self._ox        = 0.0
        self._oy        = 0.0
        self._master    = 1.0
        self._npath    = None
        self._nw       = 0.0
        self._nh       = 0.0
        self._precompute_nexus()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

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

    def _nexus_font(self) -> QFont:
        f = QFont()
        # Try the user-chosen splash font first, then fall back gracefully
        for fam in (self._splash_font, 'Outfit', 'Segoe UI', 'Ubuntu', 'Arial'):
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

    def _ring_r(self) -> float:
        return min(self.width(), self.height()) * 0.21

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

        self._bg_a = min(1.0, eo3(t / 14.0))
        if self._bg_a > 0:
            self._ox = (self._ox + 0.22) % 52
            self._oy = (self._oy + 0.13) % 52

        if t >= RS:
            rf = (t - RS) / RD
            self._ring_alpha = min(1.0, eo3(min(rf, 1.0) * 2.0))
            self._ring_arc   = min(1.0, eo3(rf))
            if rf < 1.0 and rf > 0.05 and t % 3 == 0:
                self._spawn_spark()

        if t >= PS:
            self._pulse = min(1.0, eo3((t - PS) / 30.0))

        if t >= NS:
            nf = (t - NS) / 40.0
            self._nex_alpha = min(1.0, eo5(nf))
            self._nex_glow  = min(1.0, eo3(nf))
            self._nex_y     = 22.0 * (1.0 - min(1.0, eo3(nf)))
            self._ring_fade = max(0.15, 1.0 - eo3(min(1.0, (t - NS) / 60.0)) * 0.85)

        if t >= LS:
            lf = eo3(min(1.0, (t - LS) / 22.0))
            self._line_w  = lf * self._nw * self._master
            self._line_a  = min(1.0, lf * 3.0)
        if t >= LS + 18:
            self._dot_a = eo3(min(1.0, (t - LS - 18) / 14.0))

        if t >= SS:
            self._sub_a = eo3(min(1.0, (t - SS) / 20.0))
        if t >= SS + 14:
            self._ver_a = eo3(min(1.0, (t - SS - 14) / 16.0))

        self._update_sparks()

        if t >= FS:
            self._master = max(0.0, 1.0 - eio(min(1.0, (t - FS) / FD)))

        self.update()

        if t >= FS + FD + 10:
            self._timer.stop()
            self.finished.emit()

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

        p.fillRect(self.rect(), QColor('#000008'))

        if BG > 0.01:
            p.setPen(QPen(QColor(255, 255, 255, int(BG * 11)), 0.5))
            x = -self._ox
            while x <= W + 52:
                p.drawLine(int(x), 0, int(x), H); x += 52
            y = -self._oy
            while y <= H + 52:
                p.drawLine(0, int(y), W, int(y)); y += 52

        g1 = QRadialGradient(CX, CY * 0.3, W * 0.55)
        g1.setColorAt(0, QColor(20, 60, 180, int(BG * 30)))
        g1.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(g1); p.setPen(Qt.PenStyle.NoPen); p.drawRect(self.rect())

        g2 = QRadialGradient(W * 0.85, H * 0.85, W * 0.45)
        g2.setColorAt(0, QColor(80, 20, 200, int(BG * 26)))
        g2.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(g2); p.drawRect(self.rect())

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

        R  = self._ring_r()
        ra = self._ring_alpha * self._ring_fade * GA

        if ra > 0.005 and self._ring_arc > 0.005:
            start_deg = -90.0
            span_deg  = self._ring_arc * 360.0

            p.setOpacity(ra * 0.09)
            p.setPen(QPen(QColor(96, 165, 250), 24))
            p.drawArc(QRectF(CX-R-12, CY-R-12, (R+12)*2, (R+12)*2),
                      int(start_deg*16), int(span_deg*16))

            p.setOpacity(ra * 0.16)
            p.setPen(QPen(QColor(130, 120, 255), 8))
            p.drawArc(QRectF(CX-R-3, CY-R-3, (R+3)*2, (R+3)*2),
                      int(start_deg*16), int(span_deg*16))

            SEGS = 90
            for i in range(SEGS):
                t0 = i / SEGS
                t1 = (i + 1) / SEGS
                if t1 > self._ring_arc: break
                a0_deg = start_deg + t0 * 360.0
                a1_deg = start_deg + t1 * 360.0

                frac = t0
                hue  = int(220 + math.sin(frac * math.pi) * 55)
                lite = int(58  + math.sin(frac * math.pi) * 18)
                col  = QColor.fromHsl(hue, 210, lite)
                p.setOpacity(ra)
                p.setPen(QPen(col, 1.5))
                p.drawArc(QRectF(CX-R, CY-R, R*2, R*2),
                          int(a0_deg*16), int((a1_deg-a0_deg)*16))

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

        if self._ring_arc >= 1.0 and self._nex_alpha > 0:
            fg = QRadialGradient(CX, CY, R * 0.88)
            fg.setColorAt(0,   QColor(59, 130, 246, int(self._nex_alpha * GA * 10)))
            fg.setColorAt(0.6, QColor(139, 92, 246, int(self._nex_alpha * GA * 8)))
            fg.setColorAt(1,   QColor(0, 0, 0, 0))
            p.setBrush(fg); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(CX, CY), R * 0.88, R * 0.88)

        p.setPen(Qt.PenStyle.NoPen)
        for s in self._sparks:
            a = s['life'] * self._ring_fade * self._ring_alpha * GA
            if a < 0.01: continue
            col = QColor.fromHsl(int(s['hue']), int(s['sat']/100*255), 200)
            col.setAlphaF(a)
            p.setBrush(col)
            r_s = s['size'] * s['life']
            p.drawEllipse(QPointF(s['x'], s['y']), r_s, r_s)

        if self._nex_alpha > 0.003 and self._npath:
            nw, nh = self._nw, self._nh
            nx_off = CX
            ny_off = CY - nh * 0.06 + self._nex_y

            p.save()
            p.translate(nx_off, ny_off)
            p.translate(-nw / 2.0, -nh / 2.0)

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

            gf = QLinearGradient(0, 0, nw, 0)
            gf.setColorAt(0.00, QColor(147, 197, 253))
            gf.setColorAt(0.25, QColor( 59, 130, 246))
            gf.setColorAt(0.60, QColor(139,  92, 246))
            gf.setColorAt(1.00, QColor(221, 214, 254))
            p.setOpacity(self._nex_alpha * GA)
            p.setBrush(gf); p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(self._npath)

            if self._nex_glow > 0.05:
                sh = QLinearGradient(0, 0, 0, nh * 0.32)
                sh.setColorAt(0, QColor(255, 255, 255, int(self._nex_glow * GA * 48)))
                sh.setColorAt(1, QColor(255, 255, 255, 0))
                p.setBrush(sh)
                p.drawPath(self._npath)

            p.restore()

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

        if self._ver_a > 0.005:
            ny_off = CY + self._nh * 0.5 + 84.0
            p.setOpacity(self._ver_a * GA * 0.38)
            fver = QFont(); fver.setFamily('JetBrains Mono')
            fver.setPixelSize(10)
            p.setFont(fver)
            p.setPen(QColor(40, 40, 60))
            vw = QFontMetrics(fver).horizontalAdvance('v8.0')
            p.drawText(int(CX - vw/2), int(ny_off), 'v8.0')

        vr = min(W, H) * 0.75
        ve = QRadialGradient(CX, CY, vr * 0.38, CX, CY, vr)
        ve.setColorAt(0, QColor(0, 0, 0, 0))
        ve.setColorAt(1, QColor(0, 0, 8,  int(BG * GA * 150)))
        p.setOpacity(1.0)
        p.setBrush(ve); p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(self.rect())

        if GA < 0.999:
            ov = QColor(0, 0, 8, int((1.0 - GA) * 255))
            p.fillRect(self.rect(), ov)

        p.end()

# ────────────────────── yt-dlp / network helpers ────────────────────────────

class _YDLLogger:
    """Sends yt-dlp warnings to the in-app console (each distinct warning only once)."""
    def __init__(self): self._seen = set()
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg):
        if msg not in self._seen:
            self._seen.add(msg)
            print(f'[Prism] ⚠ {msg}', file=sys.stderr)
    def error(self, msg): pass          # the raised DownloadError already carries this text

_YDL_LOGGER = _YDLLogger()


def _detect_js_runtimes() -> dict:
    """JavaScript runtimes yt-dlp may use to solve YouTube's signature challenges.
    yt-dlp enables only Deno by default, so Node / QuickJS must be switched on explicitly."""
    found = {}
    if shutil.which('deno'): found['deno'] = {}
    if shutil.which('node'): found['node'] = {}
    qjs = shutil.which('qjs') or shutil.which('quickjs')
    if qjs: found['quickjs'] = {'path': qjs}
    return found


def _detect_ffmpeg() -> str | None:
    """System ffmpeg if there is one, otherwise the binary bundled by imageio-ffmpeg."""
    system = shutil.which('ffmpeg')
    if system:
        return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


_JS_RUNTIMES = _detect_js_runtimes()
_FFMPEG      = _detect_ffmpeg()
_Cancelled   = getattr(yt_dlp.utils, 'DownloadCancelled', Exception)


def ydl_opts(**extra) -> dict:
    """Shared yt-dlp options: quiet, console logging, JS runtime and ffmpeg wired up."""
    o = {'quiet': True, 'noprogress': True, 'logger': _YDL_LOGGER, 'socket_timeout': 30,
         'retries': 3, 'fragment_retries': 3, 'extractor_retries': 2}
    if _JS_RUNTIMES:
        o['js_runtimes'] = {k: dict(v) for k, v in _JS_RUNTIMES.items()}
    if _FFMPEG and not shutil.which('ffmpeg'):
        o['ffmpeg_location'] = _FFMPEG

    # Optional browser cookies help with age/region/login checks and YouTube bot challenges.
    # Set PRISM_BROWSER=chrome|firefox|chromium|brave|edge|vivaldi|opera|safari.
    browser = os.environ.get('PRISM_BROWSER', '').strip().lower()
    if browser:
        o['cookiesfrombrowser'] = (browser,)

    # Keep yt-dlp's default YouTube client selection: hard-coding old clients can
    # make current PO-token enforcement worse and remove available formats.
    o.update(extra)
    return o


def startup_report() -> None:
    """Environment diagnostics for the in-app console (warnings show up red)."""
    print(f'[Prism] yt-dlp {YTDLP_VERSION}  ·  ffmpeg: {"ok" if _FFMPEG else "MISSING"}'
          f'  ·  JS runtime: {", ".join(_JS_RUNTIMES) or "none"}')
    if not _JS_RUNTIMES:
        print('[Prism] ⚠ No JavaScript runtime found — YouTube may return fewer formats or fail. '
              'Install Deno or Node.js 22+ and restart Prism.', file=sys.stderr)
    if not _FFMPEG:
        print('[Prism] ⚠ ffmpeg not found — merging video + audio will fail. '
              'Install ffmpeg, or run: pip install imageio-ffmpeg', file=sys.stderr)
    try:
        y, m, d = (int(p) for p in YTDLP_VERSION.split('.')[:3])
        age = (datetime.now() - datetime(y, m, d)).days
        if age > 60:
            print(f'[Prism] ⚠ yt-dlp is {age} days old — if downloads fail, run: '
                  f'python index.py --update', file=sys.stderr)
    except Exception:
        pass


_UA  = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/131.0 Safari/537.36')
_tls = threading.local()

def http_get(url: str, timeout: float = 10) -> bytes:
    """GET through a per-thread keep-alive session (fast for many small thumbnails)."""
    s = getattr(_tls, 'session', None)
    if s is None:
        s = _tls.session = requests.Session()
        s.headers['User-Agent'] = _UA
    r = s.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


# ────────────────────── Thumbnail pipeline ──────────────────────────────────
# Shared pool (max 6 threads) + in-memory LRU + on-disk cache for small thumbnails.
# Decoding/scaling is done with QImage (thread-safe); QPixmap is only built on the GUI thread.

_THUMB_MEM : OrderedDict = OrderedDict()        # (url, w, h) -> QImage
_THUMB_LOCK = threading.Lock()
_THUMB_POOL : QThreadPool | None = None

def _thumb_pool() -> QThreadPool:
    global _THUMB_POOL
    if _THUMB_POOL is None:
        _THUMB_POOL = QThreadPool()
        _THUMB_POOL.setMaxThreadCount(6)
    return _THUMB_POOL

def _mem_get(key):
    with _THUMB_LOCK:
        img = _THUMB_MEM.get(key)
        if img is not None:
            _THUMB_MEM.move_to_end(key)
        return img

def _mem_put(key, img):
    if key[1] > 400:                            # don't hold big previews in memory
        return
    with _THUMB_LOCK:
        _THUMB_MEM[key] = img
        _THUMB_MEM.move_to_end(key)
        while len(_THUMB_MEM) > 400:
            _THUMB_MEM.popitem(last=False)

def _thumb_cache_file(url: str, w: int, h: int) -> Path:
    d = DATA_FILE.parent / 'thumb_cache'
    d.mkdir(parents=True, exist_ok=True)
    return d / (hashlib.sha1(f'{url}|{w}x{h}'.encode()).hexdigest() + '.jpg')


class _ThumbJob(QRunnable):
    def __init__(self, owner: 'ThumbnailFetcher'):
        super().__init__()
        self.owner = owner

    def run(self):
        o = self.owner
        try:
            img, disk = None, None
            if o.w <= 200:                      # small thumbnails persist across launches
                try:
                    disk = _thumb_cache_file(o.url, o.w, o.h)
                    if disk.exists():
                        img = QImage(str(disk))
                        if img.isNull():
                            img = None
                except Exception:
                    disk = None
            if img is None:
                img = QImage.fromData(http_get(o.url, timeout=10))
                if img.isNull():
                    return
                img = img.convertToFormat(QImage.Format.Format_RGB32)
                if img.width() > o.w or img.height() > o.h:      # shrink only, never upscale
                    img = img.scaled(o.w, o.h, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                if disk is not None:
                    try: img.save(str(disk), 'JPG', 88)
                    except Exception: pass
            _mem_put((o.url, o.w, o.h), img)
            o._img_ready.emit(img)
        except Exception:
            pass


class ThumbnailFetcher(QObject):
    """Fetch a thumbnail fitted into w×h.  Same use as before: connect `ready`, call start()."""
    ready      = pyqtSignal(QPixmap)
    _img_ready = pyqtSignal(QImage)             # worker thread -> GUI thread hand-off

    def __init__(self, url, w=400, h=225):
        super().__init__()
        self.url, self.w, self.h = url, w, h
        self._img_ready.connect(self._deliver)

    def start(self):
        img = _mem_get((self.url, self.w, self.h))
        if img is not None:
            QTimer.singleShot(0, lambda: self._deliver(img))
        else:
            _thumb_pool().start(_ThumbJob(self))

    def _deliver(self, img):
        pm = QPixmap.fromImage(img)
        if not pm.isNull():
            self.ready.emit(pm)


# ────────────────────── Workers ─────────────────────────────────────────────

_LIVE_THREADS: set = set()

class Worker(QThread):
    """QThread that stays referenced until it has really finished.
    Prevents 'QThread: Destroyed while thread is still running' crashes when a page drops
    its reference early (e.g. starting a new search while the previous one is loading)."""
    def __init__(self):
        super().__init__()
        self.finished.connect(self._release)
    def start(self, *args):
        _LIVE_THREADS.add(self)
        super().start(*args)
    def _release(self):
        _LIVE_THREADS.discard(self)


class DownloadHub(QObject):
    """Thread-safe registry of active downloads shared by every Prism page."""
    changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._lock = threading.RLock()
        self._jobs = {}

    def register(self, worker):
        with self._lock:
            self._jobs[worker.job_id] = worker
        self.publish()

    def update(self, worker, **values):
        with self._lock:
            for key, value in values.items():
                setattr(worker, key, value)
        self.publish()

    def unregister(self, worker):
        with self._lock:
            self._jobs.pop(worker.job_id, None)
        self.publish()

    def get(self, job_id):
        with self._lock:
            return self._jobs.get(job_id)

    def snapshot(self):
        with self._lock:
            workers = list(self._jobs.values())
        return [{
            'id': w.job_id,
            'title': w.title or w.url,
            'url': w.url,
            'progress': getattr(w, 'progress_pct', 0.0),
            'label': getattr(w, 'progress_label', 'Starting…'),
            'status': getattr(w, 'status', 'Starting'),
            'paused': getattr(w, '_paused', False),
            'worker': w,
        } for w in workers]

    def publish(self):
        self.changed.emit(self.snapshot())


DOWNLOAD_HUB = DownloadHub()


class VideoInfoWorker(Worker):
    info_ready = pyqtSignal(object)             # object: dict passes by reference, no QVariant copy
    error      = pyqtSignal(str)
    def __init__(self, url): super().__init__(); self.url = url
    def run(self):
        try:
            with yt_dlp.YoutubeDL(ydl_opts(skip_download=True, noplaylist=True)) as y:
                info = y.extract_info(self.url, download=False)
            print(f'[Prism] Fetched: {info.get("title", "?")}')
            self.info_ready.emit(info)
        except Exception as e:
            print(f'[Prism] Fetch error: {e}')
            self.error.emit(str(e))


class DownloadWorker(Worker):
    progress = pyqtSignal(float, str)
    done     = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, url, fmt, out_dir, audio_only=False, title=''):
        super().__init__()
        self.url        = url
        self.fmt        = fmt
        self.out_dir    = out_dir
        self.audio_only = audio_only
        self.title      = str(title or '').strip()
        self.job_id     = f'dl-{id(self):x}'
        self._abort     = False
        self._paused    = False
        self._pause_event = threading.Event()
        self._pause_event.set()
        self.progress_pct = 0.0
        self.progress_label = 'Starting…'
        self.status = 'Starting'
        self._file_idx  = 0
        self._n_files   = 2 if ('+' in fmt and not audio_only) else 1
        self._seen_fids = set()

    def start(self, *args):
        DOWNLOAD_HUB.register(self)
        super().start(*args)

    def pause(self):
        if self.isRunning() and not self._abort and not self._paused:
            self._paused = True
            self._pause_event.clear()
            DOWNLOAD_HUB.update(self, status='Paused', progress_label='Paused')

    def resume(self):
        if self.isRunning() and not self._abort and self._paused:
            self._paused = False
            self._pause_event.set()
            DOWNLOAD_HUB.update(self, status='Downloading', progress_label='Resuming…')

    def abort(self):
        self._abort = True
        self._pause_event.set()
        DOWNLOAD_HUB.update(self, status='Stopping…', progress_label='Stopping…')

    @staticmethod
    def _final_path(y, info) -> str:
        for rd in info.get('requested_downloads') or []:
            if rd.get('filepath'):
                return rd['filepath']
        return y.prepare_filename(info)

    def run(self):
        DOWNLOAD_HUB.update(self, status='Starting', progress_label='Preparing download…')

        def hook(d):
            while not self._pause_event.wait(0.15):
                if self._abort:
                    raise _Cancelled('Download aborted')
            if self._abort:
                raise _Cancelled('Download aborted')
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
                    self.progress_pct = overall
                    self.progress_label = f'{spd_s}  ·  {label}'
                    self.status = 'Downloading'
                    self.progress.emit(overall, self.progress_label)
                    DOWNLOAD_HUB.publish()
            elif status == 'finished':
                self._file_idx += 1
                slice_size = 96.0 / self._n_files
                done_pct   = min(self._file_idx * slice_size, 96.0)
                self.progress_pct = done_pct
                if self._file_idx < self._n_files:
                    self.progress_label = 'Downloading next stream…'
                else:
                    self.progress_label = 'Merging…' if self._n_files > 1 else 'Finalizing…'
                self.status = 'Processing'
                self.progress.emit(done_pct, self.progress_label)
                DOWNLOAD_HUB.publish()

        try:
            os.makedirs(self.out_dir, exist_ok=True)
            opts = ydl_opts(
                format=self.fmt,
                outtmpl=os.path.join(self.out_dir, '%(title)s.%(ext)s'),
                progress_hooks=[hook],
                noplaylist=True,
                concurrent_fragment_downloads=4,
            )
            if not self.audio_only:
                opts['merge_output_format'] = 'mp4'
            with yt_dlp.YoutubeDL(opts) as y:
                info  = y.extract_info(self.url, download=True)
                fname = self._final_path(y, info)
            print(f'[Prism] Done: {os.path.basename(fname)}')
            self.progress_pct = 100.0
            self.status = 'Completed'
            self.progress_label = 'Completed'
            self.done.emit(fname)
        except Exception as e:
            print(f'[Prism] DL error: {e}')
            self.status = 'Failed'
            self.progress_label = str(e)[:160]
            self.error.emit(str(e))
        finally:
            DOWNLOAD_HUB.unregister(self)


class PlaylistInfoWorker(Worker):
    video_ready = pyqtSignal(int, object)
    total_found = pyqtSignal(int)
    error       = pyqtSignal(str)
    WORKERS     = 4                             # concurrent per-video lookups

    def __init__(self, url): super().__init__(); self.url = url; self._stop = False
    def stop(self): self._stop = True

    def run(self):
        pool = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts(extract_flat='in_playlist', skip_download=True)) as y:
                pl = y.extract_info(self.url, download=False)
            entries = list((pl or {}).get('entries') or [])
            print(f'[Prism] Playlist: {len(entries)} entries')
            self.total_found.emit(len(entries))

            local = threading.local()           # one YoutubeDL per pool thread (not thread-safe to share)
            def full_info(entry):
                if self._stop:
                    return entry
                y2 = getattr(local, 'ydl', None)
                if y2 is None:
                    y2 = local.ydl = yt_dlp.YoutubeDL(ydl_opts(skip_download=True, noplaylist=True))
                try:
                    return y2.extract_info(
                        entry.get('url') or entry.get('webpage_url', ''), download=False)
                except Exception:
                    return entry                # fall back to the flat entry, like before

            pool    = ThreadPoolExecutor(max_workers=self.WORKERS, thread_name_prefix='prism-pl')
            futures = [pool.submit(full_info, e) if e else None for e in entries]
            for i, fut in enumerate(futures):   # consume in order -> rows still appear 1, 2, 3…
                if self._stop:
                    return
                if fut is None:
                    continue
                self.video_ready.emit(i, fut.result())
        except Exception as e:
            print(f'[Prism] Playlist error: {e}')
            self.error.emit(str(e))
        finally:
            if pool is not None:
                pool.shutdown(wait=False, cancel_futures=True)


class BrowseSearchWorker(Worker):
    """Search YouTube videos with yt-dlp and playlists via YouTube's playlist filter."""
    results_ready = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, query, kind='video'):
        super().__init__(); self.query = query.strip(); self.kind = kind

    @staticmethod
    def _extract_initial_data(html):
        # Locate ytInitialData then read its JSON object with brace/string awareness.
        import json as _json
        import re as _re
        m = _re.search(r'ytInitialData\s*=\s*', html)
        if not m:
            m = _re.search(r'"ytInitialData"\s*:\s*', html)
        if not m:
            raise RuntimeError('YouTube did not return searchable results. Try again or update yt-dlp.')
        start = html.find('{', m.end())
        if start < 0: raise RuntimeError('Could not read YouTube search response.')
        depth = 0; in_string = False; escaped = False
        for i in range(start, len(html)):
            ch = html[i]
            if in_string:
                if escaped: escaped = False
                elif ch == '\\': escaped = True
                elif ch == '"': in_string = False
            else:
                if ch == '"': in_string = True
                elif ch == '{': depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return _json.loads(html[start:i+1])
        raise RuntimeError('YouTube search response was incomplete.')

    @staticmethod
    def _walk(obj, key):
        if isinstance(obj, dict):
            if key in obj and isinstance(obj[key], dict):
                yield obj[key]
            for value in obj.values():
                yield from BrowseSearchWorker._walk(value, key)
        elif isinstance(obj, list):
            for value in obj:
                yield from BrowseSearchWorker._walk(value, key)

    def run(self):
        try:
            if self.kind == 'video':
                entries = []
                if not self.query:
                    # Start with YouTube's homepage recommendations, then shuffle them so
                    # Browse feels like a discovery feed even before the user searches.
                    try:
                        response = requests.get('https://www.youtube.com/', headers={
                            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36',
                            'Accept-Language': 'en-US,en;q=0.9',
                        }, timeout=25)
                        response.raise_for_status()
                        data = self._extract_initial_data(response.text)
                        seen = set()
                        for item in self._walk(data, 'videoRenderer'):
                            vid = item.get('videoId')
                            if not vid or vid in seen: continue
                            seen.add(vid)
                            title_obj = item.get('title') or {}
                            title = title_obj.get('simpleText') or ''.join(r.get('text', '') for r in title_obj.get('runs', []))
                            owner_obj = item.get('ownerText') or item.get('shortBylineText') or {}
                            channel = owner_obj.get('simpleText') or ''.join(r.get('text', '') for r in owner_obj.get('runs', []))
                            thumbs = (item.get('thumbnail') or {}).get('thumbnails') or []
                            length = (item.get('lengthText') or {}).get('simpleText', '')
                            views = (item.get('viewCountText') or {}).get('simpleText', '')
                            entries.append({
                                'kind': 'video', 'title': title or 'Untitled video',
                                'url': f'https://www.youtube.com/watch?v={vid}',
                                'thumbnail': thumbs[-1].get('url', '') if thumbs else '',
                                'channel': channel or 'YouTube', 'duration': length, 'views': views,
                            })
                    except Exception as feed_error:
                        print(f'[Prism] Homepage feed unavailable, using fallback recommendations: {feed_error}')
                    if not entries:
                        # Fallback for networks/regions where YouTube blocks homepage HTML.
                        with yt_dlp.YoutubeDL(ydl_opts(
                            extract_flat=True, skip_download=True, quiet=True,
                            playlistend=24, ignoreerrors=True
                        )) as ydl:
                            data = ydl.extract_info('ytsearch24:popular videos', download=False)
                        for item in (data or {}).get('entries') or []:
                            if not item: continue
                            vid = item.get('id')
                            url = item.get('webpage_url') or (f'https://www.youtube.com/watch?v={vid}' if vid else item.get('url', ''))
                            entries.append({
                                'kind': 'video', 'title': item.get('title') or 'Untitled video',
                                'url': url, 'thumbnail': item.get('thumbnail') or best_thumbnail(item, 480),
                                'channel': item.get('uploader') or item.get('channel') or 'YouTube',
                                'duration': fmt_dur(item.get('duration')),
                                'views': fmt_views(item.get('view_count')),
                            })
                    if not entries:
                        raise RuntimeError('YouTube did not provide any recommended videos.')
                    import random
                    random.shuffle(entries)
                    entries = entries[:24]
                else:
                    with yt_dlp.YoutubeDL(ydl_opts(
                        extract_flat=True, skip_download=True, quiet=True,
                        playlistend=24, ignoreerrors=True
                    )) as ydl:
                        data = ydl.extract_info(f'ytsearch24:{self.query}', download=False)
                    for item in (data or {}).get('entries') or []:
                        if not item: continue
                        vid = item.get('id')
                        url = item.get('webpage_url') or (f'https://www.youtube.com/watch?v={vid}' if vid else item.get('url', ''))
                        entries.append({
                            'kind': 'video', 'title': item.get('title') or 'Untitled video',
                            'url': url, 'thumbnail': item.get('thumbnail') or best_thumbnail(item, 480),
                            'channel': item.get('uploader') or item.get('channel') or 'YouTube',
                            'duration': fmt_dur(item.get('duration')),
                            'views': fmt_views(item.get('view_count')),
                        })
            else:
                search_url = 'https://www.youtube.com/results?search_query=' + quote_plus(self.query) + '&sp=EgIQAw%3D%3D'
                response = requests.get(search_url, headers={
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36',
                    'Accept-Language': 'en-US,en;q=0.9',
                }, timeout=25)
                response.raise_for_status()
                data = self._extract_initial_data(response.text)
                entries = []
                for item in self._walk(data, 'playlistRenderer'):
                    pid = item.get('playlistId')
                    if not pid: continue
                    thumbs = (item.get('thumbnail') or {}).get('thumbnails') or []
                    title = ''.join(r.get('text', '') for r in (item.get('title') or {}).get('runs', [])) or 'Untitled playlist'
                    owner = ''.join(r.get('text', '') for r in (item.get('shortBylineText') or {}).get('runs', [])) or 'YouTube'
                    count = (item.get('videoCount') or {}).get('simpleText', '')
                    entries.append({
                        'kind': 'playlist', 'title': title,
                        'url': f'https://www.youtube.com/playlist?list={pid}',
                        'thumbnail': thumbs[-1].get('url') if thumbs else '',
                        'channel': owner, 'duration': count or 'Playlist', 'views': '',
                    })
                if not entries:
                    raise RuntimeError('No playlists found. YouTube may be limiting playlist search right now.')
            self.results_ready.emit(entries)
        except Exception as exc:
            self.error.emit(str(exc))


class EmbeddedPlayerPage(QWidget):
    """Embedded YouTube player with metadata and download controls."""
    download_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._url = ''
        self._info = None
        self._info_worker = None
        self._download_worker = None
        self._build()

    def _build(self):
        # Put the complete player page in one vertical scroll area. This prevents
        # the metadata/download panel from being clipped on short displays.
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setObjectName('playerScrollArea')
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        page.addWidget(scroll)

        content = QWidget()
        content.setObjectName('playerScrollContent')
        root = QVBoxLayout(content)
        root.setContentsMargins(24, 18, 24, 28)
        root.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.back_btn = QPushButton('←  Back to Browse')
        self.back_btn.setObjectName('plDlBtn')
        self.back_btn.setMinimumHeight(40)
        self.back_btn.setMinimumWidth(150)
        self.title_label = QLabel('Now playing')
        self.title_label.setObjectName('sectionTitle')
        self.title_label.setWordWrap(True)
        self.title_label.setMinimumWidth(0)
        top.addWidget(self.back_btn, 0, Qt.AlignmentFlag.AlignTop)
        top.addWidget(self.title_label, 1)
        root.addLayout(top)

        self.web = QWebEngineView(content)
        self.web.setObjectName('embeddedVideoView')
        self.web.setMinimumHeight(260)
        self.web.setMaximumHeight(520)
        self.web.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        settings = self.web.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        root.addWidget(self.web, 0)

        self.details = QFrame()
        self.details.setObjectName('videoCard')
        details_l = QVBoxLayout(self.details)
        details_l.setContentsMargins(18, 16, 18, 18)
        details_l.setSpacing(11)

        self.meta_title = QLabel('Loading video details…')
        self.meta_title.setObjectName('vcTitle')
        self.meta_title.setWordWrap(True)
        self.meta_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_l.addWidget(self.meta_title)

        self.channel_label = QLabel('Channel: —')
        self.channel_label.setObjectName('vcChannel')
        self.channel_label.setWordWrap(True)
        details_l.addWidget(self.channel_label)

        self.stats_label = QLabel('Views: —   ·   Likes: —   ·   Subscribers: —   ·   Uploaded: —   ·   Duration: —')
        self.stats_label.setObjectName('plRowMeta')
        self.stats_label.setWordWrap(True)
        details_l.addWidget(self.stats_label)

        self.links_label = QLabel('')
        self.links_label.setObjectName('statusInfo')
        self.links_label.setWordWrap(True)
        self.links_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.links_label.setOpenExternalLinks(True)
        details_l.addWidget(self.links_label)

        details_l.addWidget(sep_h())
        dl_label = QLabel('DOWNLOAD QUALITY')
        dl_label.setObjectName('dlLabel')
        details_l.addWidget(dl_label)

        # Keep the selector and action in a responsive row; at narrow widths
        # the selector can shrink instead of pushing the button off-screen.
        dl_row = QHBoxLayout()
        dl_row.setSpacing(10)
        self.format_combo = QComboBox()
        self.format_combo.setMinimumHeight(42)
        self.format_combo.setMinimumWidth(0)
        self.format_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.format_combo.setMinimumContentsLength(18)
        dl_row.addWidget(self.format_combo, 1)
        self.download_btn = QPushButton('↓  Download')
        self.download_btn.setObjectName('dlMainBtn')
        self.download_btn.setMinimumHeight(42)
        self.download_btn.setMinimumWidth(132)
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._start_download)
        dl_row.addWidget(self.download_btn, 0)
        self.pause_download_btn = QPushButton('Pause')
        self.pause_download_btn.setObjectName('plDlBtn')
        self.pause_download_btn.setMinimumHeight(42)
        self.pause_download_btn.setVisible(False)
        self.pause_download_btn.clicked.connect(self._toggle_download_pause)
        dl_row.addWidget(self.pause_download_btn, 0)
        details_l.addLayout(dl_row)

        self.download_status = QLabel('Fetching video information and available download sizes…')
        self.download_status.setObjectName('statusInfo')
        self.download_status.setWordWrap(True)
        details_l.addWidget(self.download_status)

        details_l.addWidget(sep_h())
        desc_heading = QLabel('ABOUT THIS VIDEO')
        desc_heading.setObjectName('dlLabel')
        details_l.addWidget(desc_heading)
        self.description = QLabel('')
        self.description.setObjectName('statusInfo')
        self.description.setWordWrap(True)
        self.description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.description.setMinimumHeight(24)
        details_l.addWidget(self.description)
        root.addWidget(self.details)
        root.addStretch(1)
        scroll.setWidget(content)
        self._player_scroll = scroll
        self._player_content = content

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Maintain a 16:9 player without letting it consume the entire screen.
        if hasattr(self, 'web') and hasattr(self, '_player_scroll'):
            available = max(320, self._player_scroll.viewport().width() - 48)
            target_h = max(260, min(520, int(available * 9 / 16)))
            if self.web.height() != target_h:
                self.web.setFixedHeight(target_h)

    @staticmethod
    def _video_id(url):
        raw = str(url or '').strip()
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', raw):
            return raw
        try:
            parsed = urlparse(raw)
            host = (parsed.hostname or '').lower()
            if host in ('youtu.be', 'www.youtu.be'):
                return parsed.path.strip('/').split('/')[0]
            if host.endswith('youtube.com'):
                if parsed.path == '/watch':
                    return parse_qs(parsed.query).get('v', [''])[0]
                if parsed.path.startswith(('/shorts/', '/embed/')):
                    return parsed.path.strip('/').split('/')[1]
        except Exception:
            pass
        return ''

    def play(self, url, title='Now playing'):
        """Start embedded playback and fetch the full video metadata in background."""
        self._url = str(url or '').strip()
        video_id = self._video_id(self._url)
        self._info = None
        self.title_label.setText(str(title or 'Now playing'))
        self.meta_title.setText('Loading video details…')
        self.channel_label.setText('Channel: —')
        self.stats_label.setText('Views: —   ·   Likes: —   ·   Subscribers: —   ·   Uploaded: —   ·   Duration: —')
        self.links_label.setText('')
        self.description.setText('')
        self.format_combo.clear()
        self.format_combo.addItem('Best available · size determined by YouTube', 'bestvideo+bestaudio/best')
        self.download_btn.setEnabled(False)
        self.download_status.setText('Fetching available formats and file sizes…')
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id or ''):
            self.title_label.setText('Unable to play this video')
            self.web.setHtml('<html><body style="background:#101018;color:white;font:16px sans-serif">Invalid YouTube video link.</body></html>')
            self.download_status.setText('Invalid YouTube video URL.')
            return

        embed_url = f'https://www.youtube-nocookie.com/embed/{video_id}?autoplay=1&rel=0&playsinline=1'
        html = (
            '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<style>html,body{margin:0;width:100%;height:100%;background:#08080d;overflow:hidden}'
            '.player{width:100%;height:100%;display:flex;align-items:center;justify-content:center}'
            'iframe{width:100%;height:100%;border:0}</style></head><body><div class="player">'
            f'<iframe src="{embed_url}" title="YouTube video player" '
            'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen" '
            'allowfullscreen></iframe></div></body></html>'
        )
        self.web.setHtml(html, QUrl('https://www.youtube-nocookie.com/'))

        worker = VideoInfoWorker(self._url)
        worker.info_ready.connect(self._show_video_info)
        worker.error.connect(self._video_info_error)
        worker.start()
        self._info_worker = worker

    def _show_video_info(self, info):
        self._info = info or {}
        title = self._info.get('title') or 'Untitled video'
        channel = self._info.get('uploader') or self._info.get('channel') or 'Unknown channel'
        subs = self._info.get('channel_follower_count') or self._info.get('subscriber_count')
        upload = self._info.get('upload_date') or ''
        if len(upload) == 8:
            upload = f'{upload[6:8]}/{upload[4:6]}/{upload[:4]}'
        stats = (
            f"Views: {fmt_views(self._info.get('view_count'))}   ·   "
            f"Likes: {fmt_likes(self._info.get('like_count'))}   ·   "
            f"Subscribers: {fmt_views(subs) if subs else 'Not provided'}   ·   "
            f"Uploaded: {upload or '—'}   ·   Duration: {fmt_dur(self._info.get('duration'))}"
        )
        self.title_label.setText(title)
        self.meta_title.setText(title)
        self.channel_label.setText(f'CHANNEL  ·  {channel}')
        self.stats_label.setText(stats)
        video_url = self._info.get('webpage_url') or self._url
        channel_url = self._info.get('channel_url') or self._info.get('uploader_url') or ''
        links = f'<a href="{video_url}">Video link ↗</a>'
        if channel_url:
            links += f'　·　<a href="{channel_url}">Channel link ↗</a>'
        self.links_label.setText(links)

        desc = (self._info.get('description') or '').strip()
        if len(desc) > 1200:
            desc = desc[:1200].rstrip() + '…'
        self.description.setText(desc or 'No description provided.')

        self.format_combo.clear()
        self.format_combo.addItem('Best available · automatic quality · size varies', 'bestvideo+bestaudio/best')
        formats = self._info.get('formats') or []
        audio_sizes = [f.get('filesize') or f.get('filesize_approx') for f in formats
                       if f.get('vcodec') == 'none' and f.get('acodec') not in (None, 'none')]
        audio_size = max((x for x in audio_sizes if isinstance(x, (int, float))), default=0)
        by_height = {}
        for f in formats:
            if f.get('vcodec') in (None, 'none') or not f.get('height') or not f.get('format_id'):
                continue
            h = int(f['height'])
            old = by_height.get(h)
            if old is None or (f.get('tbr') or 0) > (old.get('tbr') or 0):
                by_height[h] = f
        for h in sorted(by_height, reverse=True):
            f = by_height[h]
            ext = (f.get('ext') or 'video').upper()
            size = f.get('filesize') or f.get('filesize_approx')
            if size:
                total = size + audio_size if audio_size else size
                size_text = fmt_size(total)
            else:
                size_text = 'size varies'
            fps = f.get('fps')
            fps_text = f' {int(fps)}fps' if fps and fps > 30 else ''
            label = f'{h}p{fps_text} · {ext} · {size_text}'
            self.format_combo.addItem(label, f"{f['format_id']}+bestaudio/best")
        self.download_btn.setEnabled(True)
        self.download_status.setText(f'{len(formats)} stream formats found. Estimated sizes can vary; final size depends on the selected stream and audio.')

    def _video_info_error(self, message):
        self.download_status.setText('Could not load download details: ' + str(message)[:220])
        # Still allow the automatic best-quality download attempt.
        self.download_btn.setEnabled(True)

    def _start_download(self):
        if self._download_worker and self._download_worker.isRunning():
            return
        out = get_download_dir(self)
        if not out:
            return
        fmt = self.format_combo.currentData() or 'bestvideo+bestaudio/best'
        self.download_btn.setEnabled(False)
        self.download_btn.setText('Downloading…')
        self.download_status.setText('Starting download…')
        worker = DownloadWorker(self._url, fmt, out, title=(self._info or {}).get('title', self.title_label.text()))
        self._download_worker = worker
        self.pause_download_btn.setText('Pause')
        self.pause_download_btn.setVisible(True)
        worker.progress.connect(self._download_progress)
        worker.done.connect(self._download_done)
        worker.error.connect(self._download_error)
        worker.start()
        self._download_worker = worker

    def _toggle_download_pause(self):
        worker = self._download_worker
        if not worker or not worker.isRunning():
            return
        if worker._paused:
            worker.resume(); self.pause_download_btn.setText('Pause')
            self.download_status.setText('Resuming download…')
        else:
            worker.pause(); self.pause_download_btn.setText('Continue')
            self.download_status.setText('Download paused · press Continue to resume.')

    def _download_progress(self, pct, label):
        self.download_status.setText(f'{pct:.1f}%  ·  {label}')

    def _download_done(self, filename):
        self.pause_download_btn.setVisible(False)
        self.download_btn.setEnabled(True)
        self.download_btn.setText('✓  Saved')
        self.download_status.setText(f'Saved: {filename}')
        info = self._info or {}
        self.download_saved.emit({
            'title': info.get('title', self.title_label.text()),
            'url': info.get('webpage_url', self._url),
            'duration': fmt_dur(info.get('duration')),
            'downloaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'save_path': filename,
            'thumbnail': best_thumbnail(info, 192) if info else '',
        })

    def _download_error(self, message):
        self.pause_download_btn.setVisible(False)
        self.download_btn.setEnabled(True)
        self.download_btn.setText('↓  Retry download')
        self.download_status.setText('Download failed: ' + str(message)[:240])

    def stop(self):
        self.web.setHtml('<html><body style="background:#08080d"></body></html>')


class DownloadProgressPanel(QFrame):
    """Live sidebar for every active download, regardless of which page started it."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('infoSection')
        self.setMinimumWidth(270)
        self.setMaximumWidth(350)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._rows = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        head = QHBoxLayout()
        title = QLabel('DOWNLOAD PROGRESS')
        title.setObjectName('dlLabel')
        self.count = QLabel('0 active')
        self.count.setObjectName('monoSmall')
        head.addWidget(title); head.addStretch(); head.addWidget(self.count)
        root.addLayout(head)

        self.empty = QLabel('No active downloads yet.\nStart a video download and its live progress will appear here.')
        self.empty.setObjectName('statusInfo')
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.host = QWidget()
        self.rows_layout = QVBoxLayout(self.host)
        self.rows_layout.setContentsMargins(0, 0, 4, 0)
        self.rows_layout.setSpacing(9)
        self.rows_layout.addStretch(1)
        scroll.setWidget(self.host)
        root.addWidget(scroll, 1)

        DOWNLOAD_HUB.changed.connect(self._sync)
        self._sync(DOWNLOAD_HUB.snapshot())

    def _make_row(self, job):
        card = QFrame()
        card.setObjectName('plRow')
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        title = QLabel(job['title'])
        title.setObjectName('plRowTitle')
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        status = QLabel('Starting…')
        status.setObjectName('monoSmall')
        status.setWordWrap(True)
        progress = SlimProgress()
        btn = QPushButton('Pause')
        btn.setObjectName('plDlBtn')
        btn.setMinimumHeight(32)
        btn.clicked.connect(partial(self._toggle, job['id']))
        lay.addWidget(title)
        lay.addWidget(status)
        lay.addWidget(progress)
        lay.addWidget(btn)
        card._title = title
        card._status = status
        card._progress = progress
        card._button = btn
        return card

    def _toggle(self, job_id):
        worker = DOWNLOAD_HUB.get(job_id)
        if worker is None:
            return
        if worker._paused:
            worker.resume()
        else:
            worker.pause()

    def _sync(self, jobs):
        active = {j['id'] for j in jobs}
        for job_id in list(self._rows):
            if job_id not in active:
                row = self._rows.pop(job_id)
                self.rows_layout.removeWidget(row)
                row.deleteLater()
        for job in jobs:
            row = self._rows.get(job['id'])
            if row is None:
                row = self._make_row(job)
                self._rows[job['id']] = row
                self.rows_layout.insertWidget(max(0, self.rows_layout.count() - 1), row)
            row._title.setText(job['title'])
            row._status.setText(f"{job['status']}  ·  {job['progress']:.1f}%  ·  {job['label']}")
            row._progress.setValue(job['progress'])
            row._button.setText('Continue' if job['paused'] else 'Pause')
            row._button.setEnabled(job['status'] not in ('Stopping…', 'Completed', 'Failed'))
        self.count.setText(f'{len(jobs)} active')
        self.empty.setVisible(not jobs)


class BrowsePage(QWidget):
    """Search and browse YouTube videos or playlists without pasting a URL."""
    open_video = pyqtSignal(str)
    play_video = pyqtSignal(str, str)
    open_playlist = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._thumb_workers = []
        self._loaded_once = False
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 24)
        outer.setSpacing(16)
        heading = QLabel('Browse YouTube'); heading.setObjectName('sectionTitle')
        subtitle = QLabel('Search videos and playlists, then open one directly in Prism.')
        subtitle.setObjectName('sectionSub')
        outer.addWidget(heading); outer.addWidget(subtitle)

        body = QHBoxLayout()
        body.setSpacing(16)
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(12)

        bar = QHBoxLayout(); bar.setSpacing(10)
        self.query = QLineEdit(); self.query.setObjectName('searchInput')
        self.query.setPlaceholderText('Search any video or playlist…')
        self.query.setMinimumHeight(48)
        self.query.setMinimumWidth(0)
        self.query.setStyleSheet(f"background:{C['bg3']};border:1px solid {C['border2']};border-radius:12px;padding:0 16px;font-size:14px;")
        self.query.returnPressed.connect(self.search)
        self.kind = QComboBox(); self.kind.setObjectName('smallSelect')
        self.kind.addItem('Videos', 'video'); self.kind.addItem('Playlists', 'playlist')
        self.kind.setMinimumHeight(46)
        self.search_btn = QPushButton('Search  ↗'); self.search_btn.setObjectName('fetchBtn'); self.search_btn.setMinimumHeight(46)
        self.search_btn.clicked.connect(self.search)
        bar.addWidget(self.query, 1); bar.addWidget(self.kind); bar.addWidget(self.search_btn)
        left_l.addLayout(bar)

        self.status = QLabel('Loading a few videos for you…')
        self.status.setObjectName('statusInfo'); left_l.addWidget(self.status)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results_host = QWidget(); self.results_layout = QVBoxLayout(self.results_host)
        self.results_layout.setContentsMargins(0, 0, 8, 0); self.results_layout.setSpacing(10)
        self.results_layout.addStretch()
        scroll.setWidget(self.results_host); left_l.addWidget(scroll, 1)
        body.addWidget(left, 1)

        self.progress_panel = DownloadProgressPanel()
        body.addWidget(self.progress_panel, 0)
        outer.addLayout(body, 1)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded_once:
            self._loaded_once = True
            self._run_search('', 'video', discover=True)

    def search(self):
        query = self.query.text().strip()
        if not query:
            # An empty search is intentionally the discovery feed, not an error.
            self._run_search('', 'video', discover=True)
            return
        self._run_search(query, self.kind.currentData(), discover=False)

    def _run_search(self, query, kind, discover=False):
        if self._worker and self._worker.isRunning():
            try: self._worker.requestInterruption()
            except Exception: pass
        self._clear_results()
        self.search_btn.setEnabled(False); self.search_btn.setText('Loading…' if discover else 'Searching…')
        self.status.setText('Finding recommended videos…' if discover else 'Searching YouTube…')
        worker = BrowseSearchWorker(query, kind)
        worker.results_ready.connect(self._show_results)
        worker.error.connect(self._show_error)
        worker.finished.connect(self._search_finished)
        self._worker = worker; worker.start()

    def _search_finished(self):
        self.search_btn.setEnabled(True); self.search_btn.setText('Search  ↗')

    def _clear_results(self):
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget: widget.deleteLater()

    def _show_error(self, message):
        self.status.setText('Search failed: ' + str(message)[:260])

    def _show_results(self, entries):
        self._clear_results()
        self.status.setText(f'{len(entries)} recommended videos' if entries and all(x.get('kind') == 'video' for x in entries) and not self.query.text().strip() else f'{len(entries)} {self.kind.currentText().lower()} found')
        if not entries:
            self.status.setText('No results found. Try another search.'); return
        for item in entries:
            card = QFrame()
            card.setObjectName('plRow')
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            card_l = QVBoxLayout(card)
            card_l.setContentsMargins(12, 12, 12, 12)
            card_l.setSpacing(10)

            content_row = QHBoxLayout()
            content_row.setContentsMargins(0, 0, 0, 0)
            content_row.setSpacing(14)
            thumb = BrowseThumbWidget(160, 90)
            thumb.setMinimumSize(160, 90)
            thumb.setMaximumSize(160, 90)
            content_row.addWidget(thumb, 0, Qt.AlignmentFlag.AlignTop)
            thumb.clicked.connect(partial(self._play_or_open_item, item))
            thumb.setToolTip('Click to play this video' if item['kind'] == 'video' else 'Click to open this playlist')
            if item.get('thumbnail'):
                fetcher = ThumbnailFetcher(item['thumbnail'], 320, 180)
                fetcher.ready.connect(thumb.set_pixmap)
                fetcher.start()
                self._thumb_workers.append(fetcher)

            info_col = QVBoxLayout()
            info_col.setContentsMargins(0, 0, 0, 0)
            info_col.setSpacing(6)
            title = QLabel(item['title'])
            title.setObjectName('plRowTitle')
            title.setWordWrap(True)
            title.setMinimumWidth(0)
            meta = QLabel(f"{item.get('channel','YouTube')}  ·  {item.get('duration','')}")
            meta.setObjectName('plRowMeta')
            meta.setWordWrap(True)
            meta.setMinimumWidth(0)
            info_col.addWidget(title)
            info_col.addWidget(meta)
            info_col.addStretch(1)
            content_row.addLayout(info_col, 1)
            card_l.addLayout(content_row)

            # Put actions on their own line so they never collide with text or
            # the thumbnail when the app window is narrow.
            action_row = QHBoxLayout()
            action_row.addStretch(1)
            action = QPushButton('Open playlist  ↗' if item['kind'] == 'playlist' else 'Open video  ↗')
            action.setObjectName('plDlBtn')
            action.setMinimumHeight(38)
            action.setMinimumWidth(132)
            if item['kind'] == 'playlist':
                action.clicked.connect(partial(self.open_playlist.emit, item['url']))
            else:
                action.clicked.connect(partial(self.open_video.emit, item['url']))
            action_row.addWidget(action)
            card_l.addLayout(action_row)
            self.results_layout.addWidget(card)
        self.results_layout.addStretch()


    def _play_or_open_item(self, item):
        if item.get('kind') == 'video':
            # Play in Prism's embedded player, not in an external browser.
            self.play_video.emit(item.get('url', ''), item.get('title', 'Now playing'))
        else:
            self.open_playlist.emit(item.get('url', ''))


class ThumbSaveWorker(Worker):
    """Download a thumbnail and save it as JPG/PNG (replaces the old raw thread that
    touched widgets from outside the GUI thread)."""
    saved = pyqtSignal(str)
    error = pyqtSignal(str)
    def __init__(self, url, path, fmt):
        super().__init__(); self.url = url; self.path = path; self.fmt = fmt
    def run(self):
        try:
            img = QImage.fromData(http_get(self.url, timeout=15))
            if img.isNull():
                raise ValueError('Could not decode the thumbnail image')
            img = img.convertToFormat(QImage.Format.Format_RGB32)
            if not img.save(self.path, self.fmt, 95):
                raise OSError(f'Could not write {self.path}')
            self.saved.emit(self.path)
        except Exception as e:
            self.error.emit(str(e))


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

def best_thumbnail(info, want_w=None):
    """URL of the largest thumbnail — or, with want_w, the smallest one at least that wide."""
    thumbs = [t for t in (info.get('thumbnails') or []) if t.get('url')]
    sized  = [t for t in thumbs if t.get('width')]
    if sized:
        if want_w:
            big_enough = [t for t in sized if t['width'] >= want_w]
            if big_enough:
                return min(big_enough, key=lambda t: t['width'])['url']
        return max(sized, key=lambda t: t['width'])['url']
    return info.get('thumbnail') or (thumbs[-1]['url'] if thumbs else '')

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


class BrowseThumbWidget(ThumbWidget):
    clicked = pyqtSignal()

    def __init__(self, w, h, parent=None):
        super().__init__(w, h, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


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


# ────────────────────── Video result card ───────────────────────────────────

class VideoResultCard(QFrame):
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

    def _build(self):
        cl = QHBoxLayout(self); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)

        left = QWidget(); left.setFixedWidth(320)
        left.setStyleSheet("background:#0a0a0e;border-radius:20px 0 0 20px;")
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(0)
        self.thumb = ThumbWidget(320, 215); ll.addWidget(self.thumb)
        dr = QHBoxLayout(); dr.setContentsMargins(10, 4, 10, 10)
        self.dur_badge = mk_lbl('—', 'durBadge')
        dr.addStretch(); dr.addWidget(self.dur_badge)
        ll.addLayout(dr); ll.addStretch()
        cl.addWidget(left)

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
        bc.addWidget(self.dl_btn)
        self.pause_btn = QPushButton('Pause')
        self.pause_btn.setObjectName('plDlBtn')
        self.pause_btn.setMinimumHeight(40)
        self.pause_btn.setVisible(False)
        self.pause_btn.clicked.connect(self._toggle_pause)
        bc.addWidget(self.pause_btn)
        row1.addLayout(bc); dl_l.addLayout(row1)

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

        turl = best_thumbnail(info, 640)
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

    def _set_fmt(self, key, _):
        self._active_fmt = key
        for k, b in self._pills.items():
            b.setProperty('active', k == key); b.style().unpolish(b); b.style().polish(b)

    def _start_dl(self):
        out = get_download_dir(self)
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
        w = DownloadWorker(url, fmt, out, audio_only=(self._active_fmt == 'ao'), title=self._info.get('title', ''))
        self._workers['dl'] = w
        self.pause_btn.setText('Pause'); self.pause_btn.setVisible(True)
        w.progress.connect(self._on_prog); w.done.connect(self._on_done)
        w.error.connect(self._on_err); w.start(); self._workers['dl'] = w

    def _toggle_pause(self):
        worker = self._workers.get('dl')
        if not worker or not worker.isRunning():
            return
        if worker._paused:
            worker.resume(); self.pause_btn.setText('Pause')
            self.prog_status.show_info('Resuming download…')
        else:
            worker.pause(); self.pause_btn.setText('Continue')
            self.prog_status.show_info('Download paused · press Continue to resume.')

    def _on_prog(self, pct, label):
        self.prog.setValue(pct)
        self.prog_pct.setText(f"{pct:.1f}%")
        self.prog_spd.setText(label)
        self.prog_status.show_info(f"{pct:.1f}%  ·  {label}")

    def _on_done(self, fname):
        self.pause_btn.setVisible(False)
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
            'thumbnail':     best_thumbnail(self._info, 192),
        })

    def _on_err(self, msg):
        self.pause_btn.setVisible(False)
        self.prog_status.show_err(msg[:140])
        self.dl_btn.setEnabled(True); self.dl_btn.setText('↓  Retry')
        self.dl_btn.setStyleSheet('')


# ────────────────────── Single video page ───────────────────────────────────

class SingleVideoPage(QWidget):
    download_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = {}
        self._cards: list[VideoResultCard] = []
        self._build()

    def _build(self):
        scroll = QScrollArea(self); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._container = QWidget(); scroll.setWidget(self._container)
        self._root = QVBoxLayout(self._container)
        self._root.setContentsMargins(0, 0, 0, 0); self._root.setSpacing(0)

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

        sbw = QWidget(); sbl = QHBoxLayout(sbw); sbl.setContentsMargins(0, 0, 0, 0)
        self.search = SearchBar('🔗', 'Paste a YouTube link…')
        self.search.setMaximumWidth(700)
        self.search.submitted.connect(self._fetch)
        sbl.addStretch(); sbl.addWidget(self.search, 0); sbl.addStretch()
        hl.addWidget(sbw)

        self._root.addWidget(hero)

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

        self._cards_w = QWidget()
        self._cards_l = QVBoxLayout(self._cards_w)
        self._cards_l.setContentsMargins(24, 0, 24, 60); self._cards_l.setSpacing(20)
        self._root.addWidget(self._cards_w)
        self._root.addStretch()

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

        anim = QPropertyAnimation(card, QByteArray(b'maximumHeight'))
        anim.setDuration(350)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(0)
        anim.setEndValue(500)
        anim.start()
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
            child = self.childAt(event.position().toPoint())
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
        old = self._workers.get('pl')
        if old is not None:
            old.stop()
            for sig in (old.total_found, old.video_ready, old.error):
                try: sig.disconnect()
                except (TypeError, RuntimeError): pass
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
        turl = best_thumbnail(info, 288)
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
        row._pause_btn = QPushButton('Pause')
        row._pause_btn.setObjectName('plDlBtn')
        row._pause_btn.setMinimumHeight(32)
        row._pause_btn.setVisible(False)
        row._pause_btn.clicked.connect(partial(self._toggle_row_pause, row))
        act.addWidget(row._pause_btn)
        row._active_worker = None
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

    def _toggle_row_pause(self, row):
        worker = getattr(row, '_active_worker', None)
        if not worker or not worker.isRunning():
            return
        if worker._paused:
            worker.resume(); row._pause_btn.setText('Pause')
            row._status_lbl.setText('Resuming download…')
        else:
            worker.pause(); row._pause_btn.setText('Continue')
            row._status_lbl.setText('Paused · press Continue to resume.')

    def _dl_one_now(self, row):
        out = get_download_dir(self)
        if not out: return
        vi  = row._vc.currentIndex(); ai = row._ac.currentIndex()
        vf  = row._vids[vi] if vi < len(row._vids) else 'bestvideo'
        af  = row._auds[ai] if ai < len(row._auds) else 'bestaudio'
        fmt = f"{vf}+{af}/best"; url = row._info.get('webpage_url', '')
        row._btn.setEnabled(False); row._btn.setText('Downloading…'); row._prog.reset()
        row._status_lbl.setText('')
        w = DownloadWorker(url, fmt, out, title=row._info.get('title', ''))
        row._active_worker = w
        row._pause_btn.setText('Pause'); row._pause_btn.setVisible(True)
        w.progress.connect(lambda pct, lbl, r=row: (
            r._prog.setValue(pct),
            r._status_lbl.setText(f"{pct:.1f}%  ·  {lbl}")
        ))
        w.done.connect(lambda f, r=row, i=row._info: self._mark_done_single(r, f, i))
        w.error.connect(lambda e, r=row: self._mark_err(r, e))
        w.start(); self._workers[url] = w

    def _mark_done_single(self, row, fname, info):
        row._pause_btn.setVisible(False)
        row._prog.setValue(100); row._btn.setText('✓  Done')
        row._btn.setProperty('done', True)
        row._btn.style().unpolish(row._btn); row._btn.style().polish(row._btn)
        row._status_lbl.setText('✓ Done')
        self._done += 1; self.st_done._n.setText(str(self._done))
        self.download_saved.emit({
            'title': info.get('title', ''), 'url': info.get('webpage_url', ''),
            'duration': fmt_dur(info.get('duration')),
            'downloaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'save_path': fname, 'thumbnail': best_thumbnail(info, 192),
        })

    def _mark_err(self, row, msg):
        row._pause_btn.setVisible(False)
        row._btn.setEnabled(True); row._btn.setText('↓  Retry')
        row._status_lbl.setText(f"✗ {msg[:50]}")
        self.search.set_error(msg[:80])

    def _dl_selected(self):
        out = get_download_dir(self)
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
        w = DownloadWorker(url, fmt, out, title=row._info.get('title', ''))
        row._active_worker = w
        row._pause_btn.setText('Pause'); row._pause_btn.setVisible(True)
        w.progress.connect(lambda pct, lbl, r=row: self._on_curr_prog(pct, lbl, r))
        w.done.connect(lambda f, r=row, i=row._info: self._on_curr_done(r, f, i))
        w.error.connect(lambda e, r=row: self._on_curr_err(r, e))
        w.start(); self._current_worker = w

    def _on_curr_prog(self, pct, lbl, row):
        self.curr_prog.setValue(pct); self.curr_pct.setText(f"{pct:.1f}%")
        self.curr_spd.setText(lbl); row._prog.setValue(pct)
        row._status_lbl.setText(f"{pct:.1f}%  ·  {lbl}")

    def _on_curr_done(self, row, fname, info):
        row._pause_btn.setVisible(False)
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
            'save_path': fname, 'thumbnail': best_thumbnail(info, 192),
        })
        self._next_in_queue()

    def _on_curr_err(self, row, msg):
        row._pause_btn.setVisible(False)
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
            except Exception: pass
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
        w = ThumbSaveWorker(turl, fname, 'JPG' if ext == 'jpg' else 'PNG')
        w.saved.connect(lambda p: self.search.set_done(f'Saved: {os.path.basename(p)}'))
        w.error.connect(lambda e: self.search.set_error(e[:100]))
        w.start(); self._workers['save'] = w


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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
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
        self.te.document().setMaximumBlockCount(3000)
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


# ────────────────────── Settings overlay (centered modal popup) ──────────────

class SettingsOverlay(QWidget):
    """Semi-transparent dark overlay behind the settings modal."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setStyleSheet('background:rgba(0,0,0,0.55);')

    def mousePressEvent(self, e):
        # clicking the overlay closes the modal
        self.parent()._close_set()


class SettingsPanel(QWidget):
    close_clicked            = pyqtSignal()
    nav_pos_changed          = pyqtSignal(str)
    bg_anim_changed          = pyqtSignal(bool)
    cursor_color_changed     = pyqtSignal(str)
    top_glow_color_changed   = pyqtSignal(str)
    corner_glow_color_changed= pyqtSignal(str)
    font_changed             = pyqtSignal(str)
    splash_font_changed      = pyqtSignal(str)
    settings_blur_changed    = pyqtSignal(int)

    DEFAULT_FONT        = 'Outfit'
    DEFAULT_SPLASH_FONT = 'Outfit'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('settingsModal')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        d = load_data()
        self._pending           = d.get('nav_position',      'top')
        self._bg_enabled        = d.get('bg_animate',        True)
        self._cursor_color      = d.get('cursor_color',      '#3b82f6')
        self._top_glow_color    = d.get('top_glow_color',    '#3b82f6')
        self._corner_glow_color = d.get('corner_glow_color', '#7c3aed')
        self._font_family       = d.get('font_family',       self.DEFAULT_FONT)
        self._splash_font       = d.get('splash_font',       self.DEFAULT_SPLASH_FONT)
        self._splash_enabled    = d.get('splash_enabled',    True)
        self._download_folder   = d.get('download_folder',   '')
        self._ask_dl_folder     = d.get('ask_download_folder', True)
        self._settings_blur     = d.get('settings_blur',     18)

        # helpers ─────────────────────────────────────────────────────────────
        def lbl(text, obj, wrap=False):
            l = QLabel(text); l.setObjectName(obj)
            if wrap: l.setWordWrap(True)
            return l

        def sec_label(text):
            l = lbl(text, 'sSecLabel')
            w = QWidget(); lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)
            line_l = QFrame(); line_l.setFixedHeight(1)
            line_l.setStyleSheet('background:rgba(255,255,255,0.06);')
            line_r = QFrame(); line_r.setFixedHeight(1)
            line_r.setStyleSheet('background:rgba(255,255,255,0.06);')
            lay.addWidget(line_l, 1); lay.addWidget(l); lay.addWidget(line_r, 1)
            return w

        def row(title_text, desc_text=None, right_widget=None):
            """Standard two-line info row with optional right-side control."""
            f = QFrame(); f.setObjectName('sRow')
            fl = QHBoxLayout(f); fl.setContentsMargins(18, 14, 18, 14); fl.setSpacing(16)
            txt_col = QVBoxLayout(); txt_col.setSpacing(3)
            txt_col.addWidget(lbl(title_text, 'sRowTitle'))
            if desc_text:
                txt_col.addWidget(lbl(desc_text, 'sRowDesc'))
            fl.addLayout(txt_col, 1)
            if right_widget:
                fl.addWidget(right_widget)
            return f

        def ghost_btn(text, danger=False):
            b = QPushButton(text); b.setObjectName('sGhostBtn')
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if danger:
                b.setProperty('danger', True)
            return b

        # ── Card ──────────────────────────────────────────────────────────────
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame(); card.setObjectName('settingsCard')
        card.setFixedWidth(580)
        card_lay = QVBoxLayout(card); card_lay.setContentsMargins(0, 0, 0, 0); card_lay.setSpacing(0)
        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QWidget(); hdr.setObjectName('sHdr')
        hl = QHBoxLayout(hdr); hl.setContentsMargins(26, 0, 20, 0); hl.setSpacing(0)

        title_col = QVBoxLayout(); title_col.setSpacing(2)
        title_col.addWidget(lbl('Settings', 'sHdrTitle'))
        title_col.addWidget(lbl('Appearance & system preferences', 'sHdrSub'))
        hl.addLayout(title_col)
        hl.addStretch()

        close_btn = QPushButton('×'); close_btn.setObjectName('sCloseBtn')
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.close_clicked.emit)
        hl.addWidget(close_btn)
        card_lay.addWidget(hdr)

        # thin gradient rule under header
        rule = QFrame(); rule.setFixedHeight(1)
        rule.setStyleSheet(
            f'background:qlineargradient(x1:0,y1:0,x2:1,y2:0,'
            f'stop:0 transparent, stop:0.2 rgba(59,130,246,0.35),'
            f'stop:0.6 rgba(59,130,246,0.10), stop:1 transparent);'
        )
        card_lay.addWidget(rule)

        # ── Scrollable body ───────────────────────────────────────────────────
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet('background:transparent; border:none;')
        body = QWidget(); body.setStyleSheet('background:transparent;')
        bl = QVBoxLayout(body); bl.setContentsMargins(22, 22, 22, 8); bl.setSpacing(6)
        scroll.setWidget(body)
        card_lay.addWidget(scroll, 1)

        # ── SECTION: DISPLAY ─────────────────────────────────────────────────
        bl.addWidget(sec_label('DISPLAY'))
        bl.addSpacing(4)

        # Nav position — single toggle button
        self.btn_nav_toggle = QPushButton()
        self.btn_nav_toggle.setObjectName('sToggleBtn')
        self.btn_nav_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_toggle.clicked.connect(self._toggle_nav_pos)
        bl.addWidget(row('Navigation Bar Position',
                         'Click to toggle the tab bar between top and bottom',
                         self.btn_nav_toggle))

        bl.addSpacing(4)

        # Background animation toggle row
        self.bg_toggle = QPushButton(); self.bg_toggle.setObjectName('sToggleBtn')
        self.bg_toggle.setProperty('on', self._bg_enabled)
        self.bg_toggle.setText('ON' if self._bg_enabled else 'OFF')
        self.bg_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bg_toggle.clicked.connect(self._toggle_bg)
        bl.addWidget(row('Background Animation',
                         'Animated squares behind the UI — disable on slower systems',
                         self.bg_toggle))

        bl.addSpacing(4)

        # Splash screen toggle row
        self.splash_toggle = QPushButton(); self.splash_toggle.setObjectName('sToggleBtn')
        self.splash_toggle.setProperty('on', self._splash_enabled)
        self.splash_toggle.setText('ON' if self._splash_enabled else 'OFF')
        self.splash_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.splash_toggle.clicked.connect(self._toggle_splash)
        bl.addWidget(row('Splash Screen',
                         'Show the animated intro screen every time Prism starts',
                         self.splash_toggle))

        bl.addSpacing(4)

        # Settings panel blur slider
        blur_card = QFrame(); blur_card.setObjectName('sRow')
        blur_cl = QVBoxLayout(blur_card); blur_cl.setContentsMargins(18, 14, 18, 14); blur_cl.setSpacing(8)
        blur_top = QHBoxLayout(); blur_top.setSpacing(0)
        blur_top.addWidget(lbl('Settings Panel Background Blur', 'sRowTitle'))
        blur_top.addStretch()
        self._blur_val_lbl = lbl(f'{self._settings_blur}px', 'sRowDesc')
        blur_top.addWidget(self._blur_val_lbl)
        blur_cl.addLayout(blur_top)
        blur_cl.addWidget(lbl('Controls frosted-glass blur intensity behind the settings panel', 'sRowDesc'))
        self.blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_slider.setMinimum(0); self.blur_slider.setMaximum(40)
        self.blur_slider.setValue(self._settings_blur)
        self.blur_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: rgba(255,255,255,0.08); border-radius: 3px; height: 6px;
            }}
            QSlider::handle:horizontal {{
                background: {C['accent']}; border-radius: 7px;
                width: 14px; height: 14px; margin: -4px 0;
            }}
            QSlider::sub-page:horizontal {{
                background: {C['accent']}; border-radius: 3px;
            }}
        """)
        self.blur_slider.valueChanged.connect(self._on_blur_changed)
        blur_cl.addWidget(self.blur_slider)
        bl.addWidget(blur_card)

        bl.addSpacing(18)

        # ── SECTION: COLOURS ─────────────────────────────────────────────────
        bl.addWidget(sec_label('COLOURS'))
        bl.addSpacing(4)

        # Cursor glow
        self.cursor_btn = ColorPickerBtn(self._cursor_color)
        self.cursor_btn.color_changed.connect(self._on_cursor_color)
        bl.addWidget(row('Cursor & Click Glow',
                         'Radial halo that follows your cursor and pulses on click',
                         self.cursor_btn))
        bl.addSpacing(4)

        # Background glows
        glow_card = QFrame(); glow_card.setObjectName('sRow')
        gcl = QVBoxLayout(glow_card); gcl.setContentsMargins(18, 14, 18, 14); gcl.setSpacing(10)
        gcl.addWidget(lbl('Background Glow', 'sRowTitle'))
        gcl.addWidget(lbl('Ambient light bleeding from the edges of the window', 'sRowDesc'))
        gcl.addSpacing(4)

        glow_top_row = QHBoxLayout(); glow_top_row.setSpacing(12)
        glow_top_row.addWidget(lbl('Top centre', 'sRowDesc'), 1)
        self.top_glow_btn = ColorPickerBtn(self._top_glow_color)
        self.top_glow_btn.color_changed.connect(self._on_top_glow)
        glow_top_row.addWidget(self.top_glow_btn)

        glow_sep = QFrame(); glow_sep.setFixedHeight(1)
        glow_sep.setStyleSheet('background:rgba(255,255,255,0.045); margin:0 0;')

        glow_corner_row = QHBoxLayout(); glow_corner_row.setSpacing(12)
        glow_corner_row.addWidget(lbl('Bottom corner', 'sRowDesc'), 1)
        self.corner_glow_btn = ColorPickerBtn(self._corner_glow_color)
        self.corner_glow_btn.color_changed.connect(self._on_corner_glow)
        glow_corner_row.addWidget(self.corner_glow_btn)

        gcl.addLayout(glow_top_row); gcl.addWidget(glow_sep); gcl.addLayout(glow_corner_row)
        bl.addWidget(glow_card)

        bl.addSpacing(18)

        # ── SECTION: TYPOGRAPHY ───────────────────────────────────────────────
        bl.addWidget(sec_label('TYPOGRAPHY'))
        bl.addSpacing(4)

        font_card = QFrame(); font_card.setObjectName('sRow')
        fcl = QVBoxLayout(font_card); fcl.setContentsMargins(18, 14, 18, 14); fcl.setSpacing(10)
        font_title_row = QHBoxLayout(); font_title_row.setSpacing(0)
        font_title_row.addWidget(lbl('Application Font', 'sRowTitle'))
        font_title_row.addStretch()
        self.reset_font_btn = ghost_btn('Reset', danger=True)
        self.reset_font_btn.setToolTip(f'Restore default ({self.DEFAULT_FONT})')
        self.reset_font_btn.clicked.connect(self._reset_font)
        font_title_row.addWidget(self.reset_font_btn)
        fcl.addLayout(font_title_row)
        fcl.addWidget(lbl(f'Applies across the entire application  —  Default: {self.DEFAULT_FONT}', 'sRowDesc'))

        self.font_combo = QFontComboBox(); self.font_combo.setObjectName('sFontCombo')
        self.font_combo.setCurrentFont(QFont(self._font_family))
        self.font_combo.currentFontChanged.connect(self._on_font_changed)
        fcl.addWidget(self.font_combo)
        bl.addWidget(font_card)

        bl.addSpacing(4)

        # Welcome screen font
        splash_card = QFrame(); splash_card.setObjectName('sRow')
        scl = QVBoxLayout(splash_card); scl.setContentsMargins(18, 14, 18, 14); scl.setSpacing(10)
        splash_title_row = QHBoxLayout(); splash_title_row.setSpacing(0)
        splash_title_row.addWidget(lbl('Welcome Screen Font', 'sRowTitle'))
        splash_title_row.addStretch()
        self.reset_splash_font_btn = ghost_btn('Reset', danger=True)
        self.reset_splash_font_btn.setToolTip(f'Restore default ({self.DEFAULT_SPLASH_FONT})')
        self.reset_splash_font_btn.clicked.connect(self._reset_splash_font)
        splash_title_row.addWidget(self.reset_splash_font_btn)
        scl.addLayout(splash_title_row)
        scl.addWidget(lbl(f'Font used for "PRISM" on the intro screen  —  Default: {self.DEFAULT_SPLASH_FONT}', 'sRowDesc'))
        self.splash_font_combo = QFontComboBox(); self.splash_font_combo.setObjectName('sFontCombo')
        self.splash_font_combo.setCurrentFont(QFont(self._splash_font))
        self.splash_font_combo.currentFontChanged.connect(self._on_splash_font_changed)
        scl.addWidget(self.splash_font_combo)
        bl.addWidget(splash_card)

        bl.addSpacing(18)

        # ── SECTION: DOWNLOAD ─────────────────────────────────────────────────
        bl.addWidget(sec_label('DOWNLOAD'))
        bl.addSpacing(4)

        dl_card = QFrame(); dl_card.setObjectName('sRow')
        dlcl = QVBoxLayout(dl_card); dlcl.setContentsMargins(18, 14, 18, 14); dlcl.setSpacing(12)

        # Ask every time checkbox
        ask_row = QHBoxLayout(); ask_row.setSpacing(12)
        self.ask_dl_chk = QCheckBox()
        self.ask_dl_chk.setChecked(self._ask_dl_folder)
        self.ask_dl_chk.toggled.connect(self._on_ask_dl_toggled)
        ask_txt = QVBoxLayout(); ask_txt.setSpacing(2)
        ask_txt.addWidget(lbl('Ask for folder every time', 'sRowTitle'))
        ask_txt.addWidget(lbl('A folder picker appears each time you start a download', 'sRowDesc'))
        ask_row.addWidget(self.ask_dl_chk, 0, Qt.AlignmentFlag.AlignTop)
        ask_row.addLayout(ask_txt, 1)
        dlcl.addLayout(ask_row)

        # Separator line
        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet('background:rgba(255,255,255,0.045);')
        dlcl.addWidget(sep)

        # Download folder row
        dl_folder_row = QHBoxLayout(); dl_folder_row.setSpacing(0)
        dl_folder_row.addWidget(lbl('Download Folder', 'sRowTitle'))
        dl_folder_row.addStretch()
        self.dl_folder_btn = ghost_btn('Browse…')
        self.dl_folder_btn.clicked.connect(self._pick_dl_folder)
        dl_folder_row.addWidget(self.dl_folder_btn)
        dlcl.addLayout(dl_folder_row)
        dlcl.addWidget(lbl('All downloads go here automatically — disables the per-download prompt above', 'sRowDesc'))
        path_str = self._download_folder if self._download_folder else '— Not set —'
        self.dl_path_lbl = lbl(path_str, 'sPathLbl', wrap=True)
        dlcl.addWidget(self.dl_path_lbl)

        # Clear folder button
        clear_dl_row = QHBoxLayout()
        clear_dl_row.addStretch()
        self.clear_dl_btn = ghost_btn('Clear Folder', danger=True)
        self.clear_dl_btn.clicked.connect(self._clear_dl_folder)
        self.clear_dl_btn.setVisible(bool(self._download_folder))
        clear_dl_row.addWidget(self.clear_dl_btn)
        dlcl.addLayout(clear_dl_row)

        bl.addWidget(dl_card)

        bl.addSpacing(18)

        # ── SECTION: STORAGE ──────────────────────────────────────────────────
        bl.addWidget(sec_label('STORAGE'))
        bl.addSpacing(4)

        storage_card = QFrame(); storage_card.setObjectName('sRow')
        stcl = QVBoxLayout(storage_card); stcl.setContentsMargins(18, 14, 18, 14); stcl.setSpacing(4)
        stcl.addWidget(lbl('Storage Location', 'sRowTitle'))
        stcl.addWidget(lbl('All settings, preferences and download history are stored in:', 'sRowDesc'))
        stcl.addWidget(lbl(str(DATA_FILE), 'sPathLbl', wrap=True))
        bl.addWidget(storage_card)

        bl.addStretch(1)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QWidget(); footer.setObjectName('sFooter')
        fl = QHBoxLayout(footer); fl.setContentsMargins(22, 0, 22, 0); fl.setSpacing(10)
        fl.addStretch()

        cancel_btn = QPushButton('Cancel'); cancel_btn.setObjectName('sCancelBtn')
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.close_clicked.emit)

        self.save_btn = QPushButton('Save Settings'); self.save_btn.setObjectName('sSaveBtn')
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._save)

        fl.addWidget(cancel_btn); fl.addWidget(self.save_btn)
        card_lay.addWidget(footer)

        self._refresh_nav()

    def _div(self):
        f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(f"background:{C['border']};max-height:1px;border:none;margin-bottom:18px;")
        return f

    def _pick(self, pos):
        self._pending = pos; self._refresh_nav()

    def _toggle_nav_pos(self):
        self._pending = 'bottom' if self._pending == 'top' else 'top'
        self._refresh_nav()

    def _toggle_bg(self):
        self._bg_enabled = not self._bg_enabled
        self.bg_toggle.setText('ON' if self._bg_enabled else 'OFF')
        self.bg_toggle.setProperty('on', self._bg_enabled)
        self.bg_toggle.style().unpolish(self.bg_toggle)
        self.bg_toggle.style().polish(self.bg_toggle)
        self.bg_anim_changed.emit(self._bg_enabled)

    def _toggle_splash(self):
        self._splash_enabled = not self._splash_enabled
        self.splash_toggle.setText('ON' if self._splash_enabled else 'OFF')
        self.splash_toggle.setProperty('on', self._splash_enabled)
        self.splash_toggle.style().unpolish(self.splash_toggle)
        self.splash_toggle.style().polish(self.splash_toggle)

    def _on_blur_changed(self, val: int):
        self._settings_blur = val
        self._blur_val_lbl.setText(f'{val}px')
        self.settings_blur_changed.emit(val)

    def _on_cursor_color(self, color: str):
        self._cursor_color = color; self.cursor_color_changed.emit(color)

    def _on_top_glow(self, color: str):
        self._top_glow_color = color; self.top_glow_color_changed.emit(color)

    def _on_corner_glow(self, color: str):
        self._corner_glow_color = color; self.corner_glow_color_changed.emit(color)

    def _on_font_changed(self, font: QFont):
        self._font_family = font.family()

    def _on_splash_font_changed(self, font: QFont):
        self._splash_font = font.family()

    def _reset_font(self):
        self._font_family = self.DEFAULT_FONT
        self.font_combo.setCurrentFont(QFont(self.DEFAULT_FONT))
        self.reset_font_btn.setText('Done')
        QTimer.singleShot(1200, lambda: self.reset_font_btn.setText('Reset'))

    def _reset_splash_font(self):
        self._splash_font = self.DEFAULT_SPLASH_FONT
        self.splash_font_combo.setCurrentFont(QFont(self.DEFAULT_SPLASH_FONT))
        self.reset_splash_font_btn.setText('Done')
        QTimer.singleShot(1200, lambda: self.reset_splash_font_btn.setText('Reset'))

    def _pick_dl_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, 'Choose Download Folder', self._download_folder or str(Path.home() / 'Downloads'),
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self._download_folder = folder
            self.dl_path_lbl.setText(folder)
            self.clear_dl_btn.setVisible(True)
            # Having a folder set → disable "ask every time"
            self._ask_dl_folder = False
            self.ask_dl_chk.setChecked(False)
            self.ask_dl_chk.setEnabled(False)
            self.dl_folder_btn.setText('Folder Set ✓')
            QTimer.singleShot(1800, lambda: self.dl_folder_btn.setText('Browse…'))

    def _clear_dl_folder(self):
        self._download_folder = ''
        self.dl_path_lbl.setText('— Not set —')
        self.clear_dl_btn.setVisible(False)
        self._ask_dl_folder = True
        self.ask_dl_chk.setChecked(True)
        self.ask_dl_chk.setEnabled(True)

    def _on_ask_dl_toggled(self, checked: bool):
        self._ask_dl_folder = checked

    def _refresh_nav(self):
        is_top = self._pending == 'top'
        self.btn_nav_toggle.setText('⬆  Top' if is_top else '⬇  Bottom')
        self.btn_nav_toggle.setProperty('on', is_top)
        self.btn_nav_toggle.style().unpolish(self.btn_nav_toggle)
        self.btn_nav_toggle.style().polish(self.btn_nav_toggle)

    def _save(self):
        d = load_data()
        d['nav_position']        = self._pending
        d['bg_animate']          = self._bg_enabled
        d['cursor_color']        = self._cursor_color
        d['top_glow_color']      = self._top_glow_color
        d['corner_glow_color']   = self._corner_glow_color
        d['font_family']         = self._font_family
        d['splash_font']         = self._splash_font
        d['splash_enabled']      = self._splash_enabled
        d['settings_blur']       = self._settings_blur
        d['download_folder']     = self._download_folder
        d['ask_download_folder'] = self._ask_dl_folder
        # Record settings change in history
        snap = {
            'changed_at':           datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'nav_position':         self._pending,
            'bg_animate':           self._bg_enabled,
            'cursor_color':         self._cursor_color,
            'top_glow_color':       self._top_glow_color,
            'corner_glow_color':    self._corner_glow_color,
            'font_family':          self._font_family,
            'splash_font':          self._splash_font,
            'splash_enabled':       self._splash_enabled,
            'settings_blur':        self._settings_blur,
            'download_folder':      self._download_folder,
            'ask_download_folder':  self._ask_dl_folder,
        }
        hist = d.get('settings_history', [])
        hist.insert(0, snap)
        d['settings_history'] = hist[:100]   # keep last 100 snapshots
        save_data(d)
        print(f'[Prism] Settings saved → nav={self._pending}, font={self._font_family}')
        self.nav_pos_changed.emit(self._pending)
        self.font_changed.emit(self._font_family)
        self.save_btn.setText('Saved ✓')
        QTimer.singleShot(1600, lambda: self.save_btn.setText('Save Settings'))
        QTimer.singleShot(800, self.close_clicked.emit)

    def sync_pos(self, pos):
        self._pending = pos; self._refresh_nav()

    def sync_bg(self, val: bool):
        self._bg_enabled = val
        self.bg_toggle.setText('ON' if val else 'OFF')
        self.bg_toggle.setProperty('on', val)
        self.bg_toggle.style().unpolish(self.bg_toggle)
        self.bg_toggle.style().polish(self.bg_toggle)

    def sync_cursor_color(self, color: str):
        self._cursor_color = color; self.cursor_btn.set_color(color)

    def sync_top_glow(self, color: str):
        self._top_glow_color = color; self.top_glow_btn.set_color(color)

    def sync_corner_glow(self, color: str):
        self._corner_glow_color = color; self.corner_glow_btn.set_color(color)

    def sync_font(self, family: str):
        self._font_family = family
        self.font_combo.setCurrentFont(QFont(family))

    def sync_splash_font(self, family: str):
        self._splash_font = family
        self.splash_font_combo.setCurrentFont(QFont(family))

    def sync_download_folder(self, folder: str):
        self._download_folder = folder
        self.dl_path_lbl.setText(folder if folder else '— Not set —')
        self.clear_dl_btn.setVisible(bool(folder))
        if folder:
            self.ask_dl_chk.setChecked(False)
            self.ask_dl_chk.setEnabled(False)
        else:
            self.ask_dl_chk.setEnabled(True)

    def sync_ask_dl_folder(self, val: bool):
        self._ask_dl_folder = val
        self.ask_dl_chk.setChecked(val)

    def sync_splash_enabled(self, val: bool):
        self._splash_enabled = val
        self.splash_toggle.setText('ON' if val else 'OFF')
        self.splash_toggle.setProperty('on', val)
        self.splash_toggle.style().unpolish(self.splash_toggle)
        self.splash_toggle.style().polish(self.splash_toggle)

    def sync_settings_blur(self, val: int):
        self._settings_blur = val
        self.blur_slider.setValue(val)
        self._blur_val_lbl.setText(f'{val}px')


# ────────────────────── Logo bar ────────────────────────────────────────────

class LogoBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('logoBar')
        lay = QHBoxLayout(self); lay.setContentsMargins(24, 0, 24, 0); lay.setSpacing(0)
        dot  = BreatheDot(C['accent'], 8)
        logo = QLabel('Prism'); logo.setObjectName('logoLabel')
        lay.addWidget(dot); lay.addSpacing(8); lay.addWidget(logo); lay.addStretch()
        ver = QLabel('v8.0'); ver.setObjectName('versionLabel'); lay.addWidget(ver)


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
        bb = QPushButton('Browse'); bb.setObjectName('navTab')
        bb.setProperty('active', False); bb.setCursor(Qt.CursorShape.PointingHandCursor)
        bb.clicked.connect(self._on_browse); tbl.addWidget(bb)
        self._btns.append(bb); self._bbtn = bb
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

    def _on_browse(self):
        for i, b in enumerate(self._btns):
            b.setProperty('active', i == 4); b.style().unpolish(b); b.style().polish(b)
        self.tab_changed.emit(4)

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
        self.setWindowTitle('Prism — YouTube Media Suite v8.0')
        self.setMinimumSize(1080, 700); self.resize(1300, 840)
        self._nav_pos  = 'top'
        self._con_open = False
        self._set_open = False
        self._con_anim = None
        self._set_anim = None
        self._nav_anim = None
        self._stk_anim = None
        self._splash_active  = True
        self._settings_blur  = 18   # default, overwritten by _load_prefs
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
        self.p_browse   = BrowsePage()
        self.p_player   = EmbeddedPlayerPage()
        for p in (self.p_video, self.p_playlist, self.p_thumb, self.p_history, self.p_browse, self.p_player):
            self.stack.addWidget(p)
        self.logo_bar = LogoBar(central)
        self.tab_nav = TabNav(central)
        self.tab_nav.tab_changed.connect(self.stack.setCurrentIndex)
        self.tab_nav.history_clicked.connect(lambda: self.stack.setCurrentIndex(3))
        self.p_browse.open_video.connect(self._open_browsed_video)
        self.p_browse.play_video.connect(self._play_browsed_video)
        self.p_browse.open_playlist.connect(self._open_browsed_playlist)
        self.p_player.back_btn.clicked.connect(self._back_to_browse)
        self.tab_nav.console_toggle.connect(self._on_con_toggle)
        self.tab_nav.settings_toggle.connect(self._on_set_toggle)
        self.con_panel = ConsolePanel(central)
        # ── Settings: dark overlay + centered modal ────────────────────────
        self.set_overlay = QWidget(central)
        self.set_overlay.setStyleSheet('background:rgba(0,0,0,0.60);')
        self.set_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.set_overlay.mousePressEvent = lambda e: self._close_set()
        self.set_overlay.hide()
        self.set_panel = SettingsPanel(central)
        self.set_panel.hide()
        self.con_panel.close_clicked.connect(self._close_con)
        self.set_panel.close_clicked.connect(self._close_set)
        self.set_panel.nav_pos_changed.connect(self._animate_nav)
        self.set_panel.bg_anim_changed.connect(self.bg_canvas.set_enabled)
        self.set_panel.cursor_color_changed.connect(self._on_cursor_color)
        self.set_panel.top_glow_color_changed.connect(self.bg_canvas.set_top_glow_color)
        self.set_panel.corner_glow_color_changed.connect(self.bg_canvas.set_corner_glow_color)
        self.set_panel.font_changed.connect(self._apply_font)
        self.set_panel.settings_blur_changed.connect(self._on_settings_blur)
        self.p_video.download_saved.connect(self._save_hist)
        self.p_playlist.download_saved.connect(self._save_hist)
        self.p_player.download_saved.connect(self._save_hist)
        self.glow = CursorGlow(central, color=d.get('cursor_color', '#3b82f6'))

        # ── Splash overlay — covers everything, fades out when animation ends ──
        splash_font    = d.get('splash_font',    'Outfit')
        splash_enabled = d.get('splash_enabled', True)
        if splash_enabled:
            self.splash = HelloSplash(central, font_family=splash_font)
            self.splash.finished.connect(self._dismiss_splash)
            self._splash_active = True
            # Hide all app UI — splash covers them; revealed by _dismiss_splash
            self.bg_canvas.hide()
            self.logo_bar.hide()
            self.tab_nav.hide()
            self.stack.hide()
            self.con_panel.hide()
            self.glow.hide()
        else:
            self.splash = None
            self._splash_active = False
            # App UI visible immediately

    def _play_browsed_video(self, url, title='Now playing'):
        self.p_player.play(url, title)
        self.stack.setCurrentWidget(self.p_player)

    def _back_to_browse(self):
        self.p_player.stop()
        self.stack.setCurrentWidget(self.p_browse)
        self.tab_nav._sel(4)

    def _open_browsed_video(self, url):
        self.tab_nav._sel(0)
        self.p_video.search.inp.setText(url)
        self.p_video._fetch(url)

    def _open_browsed_playlist(self, url):
        self.tab_nav._sel(1)
        self.p_playlist.search.inp.setText(url)
        self.p_playlist._fetch(url)

    def _dismiss_splash(self):
        """Fade splash out, then reveal the full app UI underneath."""
        eff = QGraphicsOpacityEffect(self.splash)
        self.splash.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, QByteArray(b'opacity'))
        anim.setDuration(500)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        def _on_done():
            self._splash_active = False
            self.splash.hide()
            self.splash.setGraphicsEffect(None)
            # Now reveal the real app
            self.bg_canvas.show()
            self.logo_bar.show()
            self.tab_nav.show()
            self.stack.show()
            self.glow.show()
            self._place_all()
        anim.finished.connect(_on_done)
        self._splash_anim = anim
        anim.start()

    def showEvent(self, e):
        super().showEvent(e)
        # First show — window now has real dimensions
        if self._splash_active and self.splash is not None:
            c = self.centralWidget()
            W = c.width(); H = c.height()
            self.splash.setGeometry(0, 0, W, H)
            self.splash.raise_()
            self.splash.show()
        elif not self._splash_active:
            # No splash — do initial layout now
            self._place_all()

    def _apply_font(self, family: str):
        app = QApplication.instance()
        if app:
            f = QFont(family)
            app.setFont(f)
            # Update the stylesheet's font-family while keeping all other rules intact
            new_ss = STYLESHEET.replace(
                "font-family:'Outfit','Segoe UI','Ubuntu',sans-serif",
                f"font-family:'{family}','Segoe UI','Ubuntu',sans-serif"
            )
            app.setStyleSheet(new_ss)
        self.set_panel.sync_font(family)
        print(f'[Prism] Font applied: {family}')

    def _on_cursor_color(self, color: str):
        self.glow.set_color(color)

    def _on_settings_blur(self, val: int):
        self._settings_blur = val
        # Live-update both background blur and card opacity while panel is open
        if self._set_open:
            self._apply_settings_blur(val)

    def _apply_settings_blur(self, val: int):
        """
        Two linked effects driven by a single 0-40 slider:
          - Background (bg_canvas): blur radius = val  (frosted-glass effect)
          - Settings card: opacity = val/40  (0 = fully transparent, 40 = fully opaque)
        """
        # 1. Background blur
        if val > 0:
            eff = QGraphicsBlurEffect()
            eff.setBlurRadius(val)
            self.bg_canvas.setGraphicsEffect(eff)
        else:
            self.bg_canvas.setGraphicsEffect(None)

        # 2. Card opacity: map 0→40 to alpha 0.08→1.0
        alpha = max(0.08, val / 40.0)
        r, g, b = 10, 10, 18
        self.set_panel.setStyleSheet(
            f'#settingsCard {{ background: rgba({r},{g},{b},{alpha:.3f}); '
            f'border: 1px solid rgba(255,255,255,{min(0.18, alpha * 0.18):.3f}); '
            f'border-radius: 18px; }}'
        )

    def _place_all(self):
        c = self.centralWidget()
        W = c.width()  or self.width()
        H = c.height() or self.height()
        if W == 0 or H == 0:
            return

        # During splash: just keep it fullscreen, nothing else to layout
        if self._splash_active:
            self.splash.setGeometry(0, 0, W, H)
            self.splash.raise_()
            return

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
        if self._con_anim is None or self._con_anim.state() != QAbstractAnimation.State.Running:
            self.con_panel.setGeometry(cx, 0, pw, H)
        # Settings overlay + modal
        self.set_overlay.setGeometry(0, 0, W, H)
        mw, mh = 620, min(700, H - 80)
        mx = (W - mw) // 2; my = (H - mh) // 2
        self.set_panel.setGeometry(mx, my, mw, mh)
        self.logo_bar.raise_(); self.tab_nav.raise_()
        self.con_panel.raise_()
        if self._set_open:
            self.set_overlay.raise_(); self.set_panel.raise_()
        self.glow.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e); self._place_all()

    def _load_prefs(self):
        d = load_data()
        pos          = d.get('nav_position',       'top')
        bg           = d.get('bg_animate',         True)
        cursor_color = d.get('cursor_color',       '#3b82f6')
        top_glow     = d.get('top_glow_color',     '#3b82f6')
        corner_glow  = d.get('corner_glow_color',  '#7c3aed')
        font_family  = d.get('font_family',        'Outfit')
        splash_font  = d.get('splash_font',        'Outfit')
        splash_en    = d.get('splash_enabled',     True)
        blur_val     = d.get('settings_blur',      18)
        dl_folder    = d.get('download_folder',    '')
        ask_dl       = d.get('ask_download_folder', True)
        self._nav_pos       = pos
        self._settings_blur = blur_val
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
        self.set_panel.sync_font(font_family)
        self.set_panel.sync_splash_font(splash_font)
        self.set_panel.sync_splash_enabled(splash_en)
        self.set_panel.sync_settings_blur(blur_val)
        self.set_panel.sync_download_folder(dl_folder)
        self.set_panel.sync_ask_dl_folder(ask_dl)
        self._apply_font(font_family)
        self._place_all()
        print(f'[Prism] Prefs loaded: nav={pos}, font={font_family}, splash={splash_en}, blur={blur_val}')

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
        if open_it:
            self._set_open = True
            self._place_all()
            # Apply background blur + card opacity from saved value
            self._apply_settings_blur(self._settings_blur)
            # Fade in overlay
            self.set_overlay.show()
            self.set_panel.show()
            eff_ov = QGraphicsOpacityEffect(self.set_overlay)
            self.set_overlay.setGraphicsEffect(eff_ov)
            eff_modal = QGraphicsOpacityEffect(self.set_panel)
            self.set_panel.setGraphicsEffect(eff_modal)
            self._set_eff_ov    = eff_ov
            self._set_eff_modal = eff_modal
            anim_ov = QPropertyAnimation(eff_ov, QByteArray(b'opacity'))
            anim_ov.setDuration(180); anim_ov.setStartValue(0.0); anim_ov.setEndValue(1.0)
            anim_modal = QPropertyAnimation(eff_modal, QByteArray(b'opacity'))
            anim_modal.setDuration(220)
            anim_modal.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim_modal.setStartValue(0.0); anim_modal.setEndValue(1.0)
            grp = QParallelAnimationGroup(self)
            grp.addAnimation(anim_ov); grp.addAnimation(anim_modal)
            self._set_anim = grp; grp.start()
        else:
            self._close_set()

    def _close_con(self):
        self.tab_nav.force_close_panels()
        self._slide(self.con_panel, False, '_con_anim', '_con_open')

    def _close_set(self):
        self.tab_nav.force_close_panels()
        if not self._set_open:
            return
        eff_ov    = QGraphicsOpacityEffect(self.set_overlay)
        eff_modal = QGraphicsOpacityEffect(self.set_panel)
        self.set_overlay.setGraphicsEffect(eff_ov)
        self.set_panel.setGraphicsEffect(eff_modal)
        anim_ov = QPropertyAnimation(eff_ov, QByteArray(b'opacity'))
        anim_ov.setDuration(160); anim_ov.setStartValue(1.0); anim_ov.setEndValue(0.0)
        anim_modal = QPropertyAnimation(eff_modal, QByteArray(b'opacity'))
        anim_modal.setDuration(160); anim_modal.setStartValue(1.0); anim_modal.setEndValue(0.0)
        grp = QParallelAnimationGroup(self)
        grp.addAnimation(anim_ov); grp.addAnimation(anim_modal)
        def _hide_all():
            self._set_open = False
            self.set_overlay.hide()
            self.set_panel.hide()
            self.set_overlay.setGraphicsEffect(None)
            self.set_panel.setGraphicsEffect(None)
            # Remove background blur
            self.bg_canvas.setGraphicsEffect(None)
            # Reset card stylesheet to CSS default
            self.set_panel.setStyleSheet('')
        grp.finished.connect(_hide_all)
        self._set_anim = grp; grp.start()

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

    print('[Prism] v8.0 starting…')

    win = NexusApp()
    win.show()
    startup_report()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()