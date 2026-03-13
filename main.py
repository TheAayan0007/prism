#!/usr/bin/env python3
"""
╔═══════════════════════════════════════╗
║   NEXUS DOWNLOADER  ·  v2.0 SCIFI    ║
║   Advanced YouTube Media Suite       ║
║   Powered by yt-dlp + PyQt6          ║
╚═══════════════════════════════════════╝
"""

import sys, os, re, threading, tempfile, subprocess
from pathlib import Path
from io import BytesIO
from functools import partial

# ── Auto-install dependencies ─────────────────────────────────────────────────
def pip_install(pkg):
    subprocess.run([sys.executable, '-m', 'pip', 'install', pkg,
                    '--break-system-packages', '-q'], check=False)

for pkg, imp in [('yt-dlp','yt_dlp'), ('Pillow','PIL'), ('requests','requests')]:
    try: __import__(imp)
    except ImportError: pip_install(pkg)

import yt_dlp, requests
from PIL import Image as PILImage
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

# ── Global palette ────────────────────────────────────────────────────────────
C = {
    'bg':        '#06090f',
    'bg1':       '#0b1120',
    'bg2':       '#0e1628',
    'bg3':       '#121e38',
    'panel':     '#0d1830',
    'cyan':      '#00d4ff',
    'cyan_dim':  '#0077aa',
    'purple':    '#8855ff',
    'green':     '#00e58a',
    'red':       '#ff3355',
    'yellow':    '#ffcc00',
    'txt':       '#d8e8ff',
    'txt2':      '#6888bb',
    'border':    '#1a2d55',
    'border2':   '#223366',
    'hover':     '#162040',
}

STYLESHEET = f"""
* {{
    font-family: 'Segoe UI', 'Ubuntu', 'Cantarell', sans-serif;
    outline: none;
}}
QMainWindow, QWidget {{ background: {C['bg']}; color: {C['txt']}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ─ SIDEBAR ─────────────────── */
#sidebar {{
    background: {C['bg1']};
    border-right: 1px solid {C['border']};
    min-width: 68px; max-width: 68px;
}}
QPushButton#navBtn {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: {C['txt2']};
    padding: 14px 4px;
    font-size: 20px;
    text-align: center;
    border-radius: 0;
}}
QPushButton#navBtn:hover {{
    background: {C['hover']};
    border-left: 3px solid {C['cyan_dim']};
    color: {C['cyan']};
}}
QPushButton#navBtn[active=true] {{
    background: {C['bg2']};
    border-left: 3px solid {C['cyan']};
    color: {C['cyan']};
}}
#logoBox {{
    background: {C['bg']};
    border-bottom: 1px solid {C['border']};
    padding: 10px 0px;
}}
#logoLbl {{
    color: {C['cyan']};
    font-size: 20px;
    font-weight: bold;
    text-align: center;
    padding: 6px 0;
}}
#appTitle {{
    color: {C['cyan']};
    font-size: 9px;
    letter-spacing: 3px;
    text-align: center;
}}

/* ─ PANELS ───────────────────── */
QFrame#panel {{
    background: {C['panel']};
    border: 1px solid {C['border']};
    border-radius: 8px;
}}
QFrame#panelGlow {{
    background: {C['bg2']};
    border: 1px solid {C['cyan_dim']};
    border-radius: 8px;
}}

/* ─ INPUTS ───────────────────── */
QLineEdit {{
    background: {C['bg2']};
    border: 1px solid {C['border']};
    border-radius: 6px;
    color: {C['txt']};
    padding: 9px 14px;
    font-size: 13px;
    selection-background-color: {C['cyan_dim']};
}}
QLineEdit:focus {{
    border: 1px solid {C['cyan']};
    background: {C['bg3']};
}}
QLineEdit::placeholder {{
    color: {C['txt2']};
}}

/* ─ COMBO ────────────────────── */
QComboBox {{
    background: {C['bg2']};
    border: 1px solid {C['border']};
    border-radius: 6px;
    color: {C['txt']};
    padding: 7px 12px;
    font-size: 12px;
    min-height: 16px;
}}
QComboBox:hover {{ border: 1px solid {C['cyan_dim']}; }}
QComboBox:focus {{ border: 1px solid {C['cyan']}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: right center;
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {C['cyan_dim']};
    width: 0; height: 0;
}}
QComboBox QAbstractItemView {{
    background: {C['bg2']};
    border: 1px solid {C['border2']};
    border-radius: 0 0 6px 6px;
    color: {C['txt']};
    selection-background-color: {C['bg3']};
    selection-color: {C['cyan']};
    padding: 4px;
}}

/* ─ CHECKBOXES ───────────────── */
QCheckBox {{
    color: {C['txt2']};
    spacing: 8px;
    font-size: 12px;
}}
QCheckBox:hover {{ color: {C['txt']}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {C['border2']};
    border-radius: 3px;
    background: {C['bg2']};
}}
QCheckBox::indicator:checked {{
    background: {C['cyan']};
    border: 1px solid {C['cyan']};
    image: none;
}}

/* ─ BUTTONS ──────────────────── */
QPushButton#btnCyan {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #005599, stop:1 #0099cc);
    border: 1px solid {C['cyan_dim']};
    border-radius: 6px;
    color: white;
    font-weight: 700;
    font-size: 12px;
    padding: 9px 20px;
}}
QPushButton#btnCyan:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #0066bb, stop:1 #00bbdd);
    border: 1px solid {C['cyan']};
}}
QPushButton#btnCyan:pressed {{ background: #003366; }}
QPushButton#btnCyan:disabled {{ background: #112233; color: {C['txt2']}; border: 1px solid {C['border']}; }}

QPushButton#btnGreen {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #005533, stop:1 #008855);
    border: 1px solid #006644;
    border-radius: 6px;
    color: white;
    font-weight: 700;
    font-size: 12px;
    padding: 9px 20px;
}}
QPushButton#btnGreen:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #007744, stop:1 #00bb77);
    border: 1px solid {C['green']};
}}
QPushButton#btnGreen:disabled {{ background: #0a1f16; color: {C['txt2']}; }}

QPushButton#btnPurple {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #330077, stop:1 #6622cc);
    border: 1px solid {C['purple']};
    border-radius: 6px;
    color: white; font-weight: 700;
    font-size: 12px; padding: 9px 20px;
}}
QPushButton#btnPurple:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #4400aa, stop:1 #8833ff);
}}
QPushButton#btnSmall {{
    background: {C['bg3']};
    border: 1px solid {C['border2']};
    border-radius: 5px;
    color: {C['txt']};
    font-size: 11px;
    padding: 5px 14px;
}}
QPushButton#btnSmall:hover {{
    background: {C['hover']};
    border: 1px solid {C['cyan_dim']};
    color: {C['cyan']};
}}
QPushButton#btnDlSmall {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #004422, stop:1 #007744);
    border: 1px solid #005533;
    border-radius: 5px;
    color: white; font-size: 11px;
    font-weight: 700; padding: 5px 14px;
}}
QPushButton#btnDlSmall:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #006633, stop:1 #00aa55);
    border: 1px solid {C['green']};
}}

/* ─ LABELS ───────────────────── */
QLabel#tag {{
    color: {C['cyan']};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
}}
QLabel#val {{
    color: {C['txt']};
    font-size: 12px;
}}
QLabel#bigTitle {{
    color: {C['txt']};
    font-size: 14px;
    font-weight: 600;
}}
QLabel#pageHeader {{
    color: {C['cyan']};
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 3px;
}}
QLabel#statusLbl {{
    color: {C['txt2']};
    font-size: 11px;
    font-style: italic;
}}
QLabel#errorLbl {{
    color: {C['red']};
    font-size: 12px;
}}
QLabel#successLbl {{
    color: {C['green']};
    font-size: 12px;
}}

/* ─ PROGRESS ─────────────────── */
QProgressBar {{
    background: {C['bg2']};
    border: 1px solid {C['border']};
    border-radius: 5px;
    color: {C['cyan']};
    text-align: center;
    font-size: 11px;
    font-weight: bold;
    min-height: 18px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {C['cyan_dim']}, stop:1 {C['cyan']});
    border-radius: 4px;
}}

/* ─ TEXT EDIT ────────────────── */
QTextEdit {{
    background: {C['bg2']};
    border: 1px solid {C['border']};
    border-radius: 6px;
    color: {C['txt2']};
    font-size: 11px;
    padding: 6px;
}}

/* ─ SCROLL BARS ──────────────── */
QScrollBar:vertical {{
    background: {C['bg']};
    width: 5px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C['border2']};
    border-radius: 2px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {C['cyan_dim']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 5px; background: {C['bg']}; }}
QScrollBar::handle:horizontal {{ background: {C['border2']}; border-radius: 2px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ─ SEPARATOR ────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    border: none;
    background: {C['border']};
    max-height: 1px;
}}

/* ─ PLAYLIST ITEM ────────────── */
QFrame#plItem {{
    background: {C['bg2']};
    border: 1px solid {C['border']};
    border-radius: 8px;
}}
QFrame#plItem:hover {{
    border: 1px solid {C['border2']};
    background: {C['bg3']};
}}
"""


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER THREADS
# ──────────────────────────────────────────────────────────────────────────────

class VideoInfoWorker(QThread):
    info_ready   = pyqtSignal(dict)
    error        = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            opts = {'quiet': True, 'no_warnings': True,
                    'extract_flat': False, 'skip_download': True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            self.info_ready.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class DownloadWorker(QThread):
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, url, fmt, out_dir, filename_tmpl='%(title)s.%(ext)s'):
        super().__init__()
        self.url          = url
        self.fmt          = fmt
        self.out_dir      = out_dir
        self.filename_tmpl = filename_tmpl

    def run(self):
        def hook(d):
            if d['status'] == 'downloading':
                total     = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                speed     = d.get('speed', 0) or 0
                pct       = (downloaded / total * 100) if total else 0
                spd_str   = f"{speed/1024/1024:.1f} MB/s" if speed else "—"
                self.progress.emit(pct, spd_str)
            elif d['status'] == 'finished':
                self.progress.emit(100, "Merging…")

        try:
            os.makedirs(self.out_dir, exist_ok=True)
            opts = {
                'format':          self.fmt,
                'outtmpl':         os.path.join(self.out_dir, self.filename_tmpl),
                'progress_hooks':  [hook],
                'quiet':           True,
                'no_warnings':     True,
                'merge_output_format': 'mp4',
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url)
                fname = ydl.prepare_filename(info)
            self.finished.emit(fname)
        except Exception as e:
            self.error.emit(str(e))


class PlaylistInfoWorker(QThread):
    info_ready    = pyqtSignal(dict)
    video_ready   = pyqtSignal(int, dict)
    error         = pyqtSignal(str)
    total_found   = pyqtSignal(int)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            flat_opts = {'quiet': True, 'no_warnings': True,
                         'extract_flat': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(flat_opts) as ydl:
                playlist = ydl.extract_info(self.url, download=False)

            entries = playlist.get('entries', [])
            self.total_found.emit(len(entries))

            for i, entry in enumerate(entries):
                if entry:
                    try:
                        vid_opts = {'quiet': True, 'no_warnings': True,
                                    'skip_download': True}
                        with yt_dlp.YoutubeDL(vid_opts) as ydl2:
                            vid = ydl2.extract_info(
                                entry.get('url') or entry.get('webpage_url', ''),
                                download=False)
                        self.video_ready.emit(i, vid)
                    except Exception:
                        self.video_ready.emit(i, entry)
        except Exception as e:
            self.error.emit(str(e))


class ThumbnailFetcher(QThread):
    ready = pyqtSignal(QPixmap)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            r = requests.get(self.url, timeout=10)
            img = PILImage.open(BytesIO(r.content)).convert('RGB')
            img.thumbnail((320, 180), PILImage.LANCZOS)
            data = BytesIO()
            img.save(data, 'PNG')
            pm = QPixmap()
            pm.loadFromData(data.getvalue())
            self.ready.emit(pm)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def fmt_size(b):
    if not b: return 'N/A'
    for u in ('B','KB','MB','GB'):
        if b < 1024: return f"{b:.2f} {u}"
        b /= 1024
    return f"{b:.2f} TB"

def fmt_dur(s):
    if not s: return 'N/A'
    h, m, sec = int(s)//3600, (int(s)%3600)//60, int(s)%60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

def fmt_views(n):
    if not n: return 'N/A'
    if n >= 1_000_000: return f"{n/1_000_000:.2f}M"
    if n >= 1_000:     return f"{n/1_000:.2f}K"
    return str(n)

def best_thumbnail(info):
    thumbs = info.get('thumbnails', [])
    if thumbs:
        best = max(thumbs, key=lambda t: (t.get('width',0) or 0))
        return best.get('url','')
    return info.get('thumbnail','')

def parse_formats(info):
    """Return (video_formats, audio_formats) as lists of (label, format_id)."""
    formats = info.get('formats', [])
    video_fmts, audio_fmts = [], []
    seen_v, seen_a = set(), set()

    for f in reversed(formats):
        vcodec = f.get('vcodec', 'none')
        acodec = f.get('acodec', 'none')
        fid    = f.get('format_id','')
        ext    = f.get('ext','?')
        h      = f.get('height')
        fps    = f.get('fps')
        abr    = f.get('abr')
        tbr    = f.get('tbr')
        size   = f.get('filesize') or f.get('filesize_approx')
        note   = f.get('format_note','')

        if vcodec and vcodec != 'none' and h:
            key = f"{h}_{fps}"
            if key not in seen_v:
                seen_v.add(key)
                fps_str = f" {int(fps)}fps" if fps and fps > 30 else ""
                lbl = f"{h}p{fps_str}  [{ext.upper()}]  {fmt_size(size)}"
                video_fmts.append((lbl, fid))

        if acodec and acodec != 'none' and vcodec in (None, 'none', ''):
            key = round(abr or tbr or 0)
            if key not in seen_a and key > 0:
                seen_a.add(key)
                lang = f.get('language','')
                lang_str = f"  [{lang.upper()}]" if lang else ""
                lbl = f"{key} kbps  [{ext.upper()}]{lang_str}  {fmt_size(size)}"
                audio_fmts.append((lbl, fid))

    # Also add combined best
    video_fmts = [('⭐ Best Video (auto)', 'bestvideo')] + video_fmts
    audio_fmts = [('⭐ Best Audio (auto)', 'bestaudio')] + audio_fmts
    return video_fmts, audio_fmts

def parse_audio_tracks(info):
    """Return list of (label, format_id) for different language audio streams."""
    tracks = []
    seen = set()
    for f in info.get('formats', []):
        acodec = f.get('acodec','none')
        vcodec = f.get('vcodec','none')
        lang   = f.get('language','')
        if acodec not in (None,'none') and vcodec in (None,'none',''):
            key = lang or 'original'
            if key not in seen:
                seen.add(key)
                label = lang.capitalize() if lang else 'Original'
                tracks.append((label, f.get('format_id','')))
    if not tracks:
        tracks = [('Original', 'bestaudio')]
    return tracks

def parse_subtitles(info):
    subs = {}
    for lang, items in (info.get('subtitles') or {}).items():
        subs[lang] = items
    for lang, items in (info.get('automatic_captions') or {}).items():
        if lang not in subs:
            subs[f"{lang} (auto)"] = items
    return subs


# ──────────────────────────────────────────────────────────────────────────────
#  REUSABLE WIDGETS
# ──────────────────────────────────────────────────────────────────────────────

def make_sep():
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"background: {C['border']}; max-height:1px; border:none;")
    return f

def lbl(text, obj_name='val', wrap=False):
    l = QLabel(text); l.setObjectName(obj_name)
    if wrap: l.setWordWrap(True)
    return l

def tag(text):
    l = QLabel(text); l.setObjectName('tag')
    return l

class GlowButton(QPushButton):
    def __init__(self, text, obj_name='btnCyan', parent=None):
        super().__init__(text, parent)
        self.setObjectName(obj_name)

class UrlBar(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self, placeholder='Paste YouTube URL here…', parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(8)
        self.inp = QLineEdit(); self.inp.setPlaceholderText(placeholder)
        self.inp.returnPressed.connect(self._go)
        self.btn = GlowButton('  ⚡  FETCH', 'btnCyan')
        self.btn.setFixedWidth(110)
        self.btn.clicked.connect(self._go)
        lay.addWidget(self.inp); lay.addWidget(self.btn)

    def _go(self):
        u = self.inp.text().strip()
        if u: self.submitted.emit(u)

    def set_url(self, url): self.inp.setText(url)
    def url(self): return self.inp.text().strip()


class ThumbnailBox(QLabel):
    def __init__(self, w=320, h=180, parent=None):
        super().__init__(parent)
        self.setFixedSize(w, h)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._draw_placeholder()

    def _draw_placeholder(self):
        pm = QPixmap(self.width(), self.height())
        pm.fill(QColor(C['bg2']))
        p = QPainter(pm)
        p.setPen(QColor(C['border2']))
        p.drawRect(0, 0, self.width()-1, self.height()-1)
        p.setPen(QColor(C['txt2']))
        p.setFont(QFont('Segoe UI', 11))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, '🎬  No Thumbnail')
        p.end()
        self.setPixmap(pm)

    def set_pixmap_scaled(self, pm):
        scaled = pm.scaled(self.width(), self.height(),
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        final = QPixmap(self.width(), self.height())
        final.fill(QColor(C['bg2']))
        p = QPainter(final)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        p.drawPixmap(x, y, scaled)
        p.end()
        self.setPixmap(final)


# ──────────────────────────────────────────────────────────────────────────────
#  PAGE 1: SINGLE VIDEO DOWNLOADER
# ──────────────────────────────────────────────────────────────────────────────

class SingleVideoPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._info = None
        self._worker = None
        self._dl_worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        ico = lbl('📥', 'pageHeader'); ico.setFixedWidth(36)
        ttl = lbl('SINGLE VIDEO DOWNLOADER', 'pageHeader')
        hdr.addWidget(ico); hdr.addWidget(ttl); hdr.addStretch()
        root.addLayout(hdr)
        root.addWidget(make_sep())

        # URL bar
        self.url_bar = UrlBar('Paste YouTube video URL here…')
        self.url_bar.submitted.connect(self._fetch)
        root.addWidget(self.url_bar)

        # Status
        self.status_lbl = lbl('Enter a URL and press FETCH', 'statusLbl')
        root.addWidget(self.status_lbl)

        # ── Info area ─────────────────────────────────────────────────────
        self.info_panel = QFrame(); self.info_panel.setObjectName('panel')
        self.info_panel.setVisible(False)
        ip_lay = QHBoxLayout(self.info_panel)
        ip_lay.setContentsMargins(14, 14, 14, 14); ip_lay.setSpacing(18)

        # Thumbnail
        self.thumb = ThumbnailBox(300, 170)
        ip_lay.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)

        # Details grid
        det = QWidget()
        det_lay = QGridLayout(det); det_lay.setSpacing(8); det_lay.setContentsMargins(0,0,0,0)
        det_lay.setColumnMinimumWidth(0, 100)

        fields = ['Title','File Size','Duration','Views','Channel','Watch URL','Description']
        self._det_vals = {}
        for i, f in enumerate(fields):
            det_lay.addWidget(tag(f.upper()+' :'), i, 0, Qt.AlignmentFlag.AlignTop)
            if f == 'Description':
                w = QTextEdit(); w.setReadOnly(True)
                w.setFixedHeight(80); w.setObjectName('descBox')
            elif f == 'Watch URL':
                w = lbl('', 'val')
                w.setStyleSheet(f"color: {C['cyan']}; font-size:12px;")
            else:
                w = lbl('—', 'val'); w.setWordWrap(True)
            self._det_vals[f] = w
            det_lay.addWidget(w, i, 1)

        ip_lay.addWidget(det, 1)
        root.addWidget(self.info_panel)

        # ── Download options ───────────────────────────────────────────────
        self.dl_panel = QFrame(); self.dl_panel.setObjectName('panelGlow')
        self.dl_panel.setVisible(False)
        dl_lay = QVBoxLayout(self.dl_panel)
        dl_lay.setContentsMargins(14, 12, 14, 12); dl_lay.setSpacing(10)

        dl_hdr = QHBoxLayout()
        dl_hdr.addWidget(lbl('⚙  DOWNLOAD OPTIONS', 'tag'))
        dl_hdr.addStretch()
        self.size_lbl = lbl('File Download Size: —', 'statusLbl')
        dl_hdr.addWidget(self.size_lbl)
        dl_lay.addLayout(dl_hdr)
        dl_lay.addWidget(make_sep())

        row1 = QHBoxLayout(); row1.setSpacing(10)

        # Video quality
        vbox = QVBoxLayout(); vbox.setSpacing(4)
        vbox.addWidget(tag('VIDEO QUALITY'))
        self.vid_combo = QComboBox(); self.vid_combo.setMinimumWidth(220)
        self.vid_combo.currentIndexChanged.connect(self._update_size)
        vbox.addWidget(self.vid_combo)
        row1.addLayout(vbox)

        # Audio quality
        abox = QVBoxLayout(); abox.setSpacing(4)
        abox.addWidget(tag('AUDIO QUALITY'))
        self.aud_combo = QComboBox(); self.aud_combo.setMinimumWidth(220)
        self.aud_combo.currentIndexChanged.connect(self._update_size)
        abox.addWidget(self.aud_combo)
        row1.addLayout(abox)

        # Multi-lang audio
        mbox = QVBoxLayout(); mbox.setSpacing(4)
        mbox.addWidget(tag('AUDIO LANGUAGE'))
        self.lang_combo = QComboBox(); self.lang_combo.setMinimumWidth(160)
        mbox.addWidget(self.lang_combo)
        row1.addLayout(mbox)
        row1.addStretch()
        dl_lay.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(10)
        # Subtitles
        self.sub_chk = QCheckBox('Download Subtitles')
        self.sub_chk.stateChanged.connect(
            lambda s: self.sub_lang_combo.setEnabled(bool(s)))
        row2.addWidget(self.sub_chk)
        self.sub_lang_combo = QComboBox(); self.sub_lang_combo.setMinimumWidth(160)
        self.sub_lang_combo.setEnabled(False)
        row2.addWidget(self.sub_lang_combo)
        row2.addStretch()

        # Format type
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(['VIDEO + AUDIO  (MP4)', 'AUDIO ONLY  (MP3/M4A)',
                                 'VIDEO ONLY  (MP4)'])
        row2.addWidget(self.fmt_combo)
        dl_lay.addLayout(row2)

        # Buttons row
        row3 = QHBoxLayout(); row3.setSpacing(10)
        self.dl_btn   = GlowButton('  ▶  START DOWNLOAD', 'btnGreen')
        self.dl_btn.clicked.connect(self._start_download)
        row3.addWidget(self.dl_btn)
        row3.addStretch()
        dl_lay.addLayout(row3)

        # Progress
        self.prog_bar = QProgressBar(); self.prog_bar.setValue(0)
        self.prog_bar.setVisible(False); self.prog_bar.setFixedHeight(20)
        dl_lay.addWidget(self.prog_bar)
        self.prog_lbl = lbl('', 'statusLbl'); self.prog_lbl.setVisible(False)
        dl_lay.addWidget(self.prog_lbl)

        root.addWidget(self.dl_panel)
        root.addStretch()

    def _fetch(self, url):
        self.status_lbl.setObjectName('statusLbl')
        self.status_lbl.setText('🔄  Fetching video info…')
        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)
        self.info_panel.setVisible(False)
        self.dl_panel.setVisible(False)
        self._worker = VideoInfoWorker(url)
        self._worker.info_ready.connect(self._on_info)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_error(self, msg):
        self.status_lbl.setObjectName('errorLbl')
        self.status_lbl.setText(f'⚠  Error: {msg[:120]}')
        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)

    def _on_info(self, info):
        self._info = info
        self.status_lbl.setObjectName('successLbl')
        self.status_lbl.setText('✔  Video info loaded successfully')
        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)

        # Fill details
        size = info.get('filesize') or info.get('filesize_approx')
        self._det_vals['Title'].setText(info.get('title','N/A'))
        self._det_vals['File Size'].setText(fmt_size(size))
        self._det_vals['Duration'].setText(fmt_dur(info.get('duration')))
        self._det_vals['Views'].setText(fmt_views(info.get('view_count')))
        self._det_vals['Channel'].setText(info.get('uploader') or info.get('channel','N/A'))
        self._det_vals['Watch URL'].setText(info.get('webpage_url',''))
        self._det_vals['Description'].setPlainText(
            (info.get('description') or '').strip()[:500])
        self.info_panel.setVisible(True)

        # Thumbnail
        turl = best_thumbnail(info)
        if turl:
            self._thumb_worker = ThumbnailFetcher(turl)
            self._thumb_worker.ready.connect(self.thumb.set_pixmap_scaled)
            self._thumb_worker.start()

        # Formats
        vfmts, afmts = parse_formats(info)
        self.vid_combo.blockSignals(True); self.aud_combo.blockSignals(True)
        self.vid_combo.clear(); self.aud_combo.clear()
        self._vid_ids = []; self._aud_ids = []
        for lbl_txt, fid in vfmts:
            self.vid_combo.addItem(lbl_txt); self._vid_ids.append(fid)
        for lbl_txt, fid in afmts:
            self.aud_combo.addItem(lbl_txt); self._aud_ids.append(fid)
        self.vid_combo.blockSignals(False); self.aud_combo.blockSignals(False)

        # Language audio tracks
        tracks = parse_audio_tracks(info)
        self.lang_combo.clear()
        for lbl_txt, _ in tracks:
            self.lang_combo.addItem(lbl_txt)

        # Subtitles
        subs = parse_subtitles(info)
        self.sub_lang_combo.clear()
        if subs:
            for lang in subs.keys():
                self.sub_lang_combo.addItem(lang)
        else:
            self.sub_lang_combo.addItem('No subtitles found')

        self._update_size()
        self.dl_panel.setVisible(True)

    def _update_size(self):
        if not self._info: return
        fmts = self._info.get('formats', [])
        vid_idx = self.vid_combo.currentIndex()
        aud_idx = self.aud_combo.currentIndex()
        vid_id = self._vid_ids[vid_idx] if vid_idx < len(self._vid_ids) else ''
        aud_id = self._aud_ids[aud_idx] if aud_idx < len(self._aud_ids) else ''
        total = 0
        for f in fmts:
            if f.get('format_id') in (vid_id, aud_id):
                total += f.get('filesize') or f.get('filesize_approx') or 0
        self.size_lbl.setText(f"Estimated Size: {fmt_size(total) if total else 'N/A'}")

    def _start_download(self):
        if not self._info: return
        out_dir = QFileDialog.getExistingDirectory(self, 'Select Download Folder',
                                                   str(Path.home()/'Downloads'))
        if not out_dir: return

        vid_idx = self.vid_combo.currentIndex()
        aud_idx = self.aud_combo.currentIndex()
        vid_id  = self._vid_ids[vid_idx] if vid_idx < len(self._vid_ids) else 'bestvideo'
        aud_id  = self._aud_ids[aud_idx] if aud_idx < len(self._aud_ids) else 'bestaudio'

        fmt_choice = self.fmt_combo.currentIndex()
        if fmt_choice == 0:   fmt = f"{vid_id}+{aud_id}/best"
        elif fmt_choice == 1: fmt = aud_id
        else:                 fmt = vid_id

        url = self._info.get('webpage_url','') or self.url_bar.url()
        self.prog_bar.setValue(0); self.prog_bar.setVisible(True)
        self.prog_lbl.setVisible(True); self.dl_btn.setEnabled(False)

        self._dl_worker = DownloadWorker(url, fmt, out_dir)
        self._dl_worker.progress.connect(self._on_progress)
        self._dl_worker.finished.connect(self._on_done)
        self._dl_worker.error.connect(self._on_dl_error)
        self._dl_worker.start()

    def _on_progress(self, pct, speed):
        self.prog_bar.setValue(int(pct))
        self.prog_lbl.setText(f"Downloading… {pct:.1f}%  •  {speed}")

    def _on_done(self, fname):
        self.prog_bar.setValue(100)
        self.prog_lbl.setText(f"✔  Saved: {os.path.basename(fname)}")
        self.dl_btn.setEnabled(True)

    def _on_dl_error(self, msg):
        self.prog_lbl.setObjectName('errorLbl')
        self.prog_lbl.setText(f"⚠  {msg[:100]}")
        self.dl_btn.setEnabled(True)


# ──────────────────────────────────────────────────────────────────────────────
#  PAGE 2: THUMBNAIL DOWNLOADER
# ──────────────────────────────────────────────────────────────────────────────

class ThumbnailPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._info   = None
        self._pixmap = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16); root.setSpacing(14)

        hdr = QHBoxLayout()
        hdr.addWidget(lbl('🖼', 'pageHeader'))
        hdr.addWidget(lbl('THUMBNAIL DOWNLOADER', 'pageHeader'))
        hdr.addStretch()
        root.addLayout(hdr)
        root.addWidget(make_sep())

        self.url_bar = UrlBar('Paste YouTube video or shorts URL here…')
        self.url_bar.submitted.connect(self._fetch)
        root.addWidget(self.url_bar)

        self.status_lbl = lbl('Enter a URL and press FETCH', 'statusLbl')
        root.addWidget(self.status_lbl)

        # Preview panel
        self.panel = QFrame(); self.panel.setObjectName('panel')
        self.panel.setVisible(False)
        p_lay = QVBoxLayout(self.panel)
        p_lay.setContentsMargins(20, 20, 20, 20); p_lay.setSpacing(14)

        p_lay.addWidget(lbl('THUMBNAIL PREVIEW', 'tag'),
                        alignment=Qt.AlignmentFlag.AlignHCenter)

        self.thumb = ThumbnailBox(640, 360)
        p_lay.addWidget(self.thumb, alignment=Qt.AlignmentFlag.AlignHCenter)

        info_row = QHBoxLayout()
        self.title_lbl = lbl('—', 'bigTitle'); self.title_lbl.setWordWrap(True)
        info_row.addWidget(self.title_lbl, 1)
        p_lay.addLayout(info_row)

        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        self.dl_jpg = GlowButton('⬇  Download JPG', 'btnCyan')
        self.dl_png = GlowButton('⬇  Download PNG', 'btnPurple')
        self.dl_jpg.clicked.connect(lambda: self._download('jpg'))
        self.dl_png.clicked.connect(lambda: self._download('png'))
        btn_row.addWidget(self.dl_jpg); btn_row.addWidget(self.dl_png)
        btn_row.addStretch()
        p_lay.addLayout(btn_row)
        root.addWidget(self.panel)
        root.addStretch()

    def _fetch(self, url):
        self.status_lbl.setText('🔄  Fetching thumbnail…')
        self.panel.setVisible(False)
        self._worker = VideoInfoWorker(url)
        self._worker.info_ready.connect(self._on_info)
        self._worker.error.connect(lambda e: self.status_lbl.setText(f'⚠  {e[:100]}'))
        self._worker.start()

    def _on_info(self, info):
        self._info = info
        self.status_lbl.setText('✔  Thumbnail ready')
        self.title_lbl.setText(info.get('title',''))
        turl = best_thumbnail(info)
        if turl:
            self._fetch_thumb = ThumbnailFetcher(turl)
            self._fetch_thumb.ready.connect(self._on_thumb)
            self._fetch_thumb.start()
        self.panel.setVisible(True)

    def _on_thumb(self, pm):
        self._pixmap = pm
        self.thumb.set_pixmap_scaled(pm)

    def _download(self, ext):
        if not self._info: return
        turl = best_thumbnail(self._info)
        if not turl: return
        title = re.sub(r'[^\w\s-]', '', self._info.get('title','thumbnail'))[:60].strip()
        fname, _ = QFileDialog.getSaveFileName(
            self, 'Save Thumbnail',
            str(Path.home()/'Downloads'/f"{title}.{ext}"),
            f"Image (*.{ext})")
        if not fname: return

        def _save():
            try:
                r = requests.get(turl, timeout=10)
                img = PILImage.open(BytesIO(r.content)).convert('RGB')
                img.save(fname, ext.upper() if ext!='jpg' else 'JPEG')
                self.status_lbl.setText(f'✔  Saved: {os.path.basename(fname)}')
            except Exception as e:
                self.status_lbl.setText(f'⚠  {e}')
        threading.Thread(target=_save, daemon=True).start()


# ──────────────────────────────────────────────────────────────────────────────
#  PLAYLIST ITEM WIDGET
# ──────────────────────────────────────────────────────────────────────────────

class PlaylistItemWidget(QFrame):
    download_requested = pyqtSignal(dict, str)  # (info, format_str)

    def __init__(self, index, info, parent=None):
        super().__init__(parent)
        self.setObjectName('plItem')
        self._info = info
        self._build(index, info)

    def _build(self, idx, info):
        lay = QHBoxLayout(self); lay.setContentsMargins(10,10,10,10); lay.setSpacing(12)

        # Index
        num_lbl = lbl(f"{idx+1:02d}", 'tag')
        num_lbl.setFixedWidth(28)
        num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(num_lbl)

        # Thumbnail
        self.thumb = ThumbnailBox(128, 72)
        lay.addWidget(self.thumb)
        turl = best_thumbnail(info)
        if turl:
            w = ThumbnailFetcher(turl)
            w.ready.connect(self.thumb.set_pixmap_scaled)
            w.start()
            self._tw = w

        # Info
        inf_col = QVBoxLayout(); inf_col.setSpacing(4)
        title = info.get('title','Unknown Video')
        tl = lbl(title[:80]+'…' if len(title)>80 else title, 'bigTitle')
        tl.setWordWrap(True)
        inf_col.addWidget(tl)

        meta = QHBoxLayout(); meta.setSpacing(16)
        meta.addWidget(lbl(fmt_dur(info.get('duration')), 'statusLbl'))
        meta.addWidget(lbl(fmt_views(info.get('view_count'))+' views', 'statusLbl'))
        size = info.get('filesize') or info.get('filesize_approx')
        meta.addWidget(lbl(fmt_size(size), 'statusLbl'))
        meta.addStretch()
        inf_col.addLayout(meta)
        lay.addLayout(inf_col, 1)

        # Quality + download
        q_col = QVBoxLayout(); q_col.setSpacing(6)
        vfmts, afmts = parse_formats(info)
        self._vid_ids = [fid for _,fid in vfmts]
        self._aud_ids = [fid for _,fid in afmts]

        self.vid_cb = QComboBox(); self.vid_cb.setMinimumWidth(160)
        for lb,_ in vfmts: self.vid_cb.addItem(lb)
        self.aud_cb = QComboBox(); self.aud_cb.setMinimumWidth(160)
        for lb,_ in afmts: self.aud_cb.addItem(lb)
        q_col.addWidget(self.vid_cb); q_col.addWidget(self.aud_cb)

        self.dl_btn = GlowButton('⬇  Download', 'btnDlSmall')
        self.dl_btn.clicked.connect(self._emit_dl)
        self.prog = QProgressBar(); self.prog.setValue(0); self.prog.setVisible(False)
        self.prog.setFixedHeight(14)
        q_col.addWidget(self.dl_btn); q_col.addWidget(self.prog)
        lay.addLayout(q_col)

    def _emit_dl(self):
        vi = self.vid_cb.currentIndex()
        ai = self.aud_cb.currentIndex()
        vid_id = self._vid_ids[vi] if vi < len(self._vid_ids) else 'bestvideo'
        aud_id = self._aud_ids[ai] if ai < len(self._aud_ids) else 'bestaudio'
        fmt = f"{vid_id}+{aud_id}/best"
        self.download_requested.emit(self._info, fmt)

    def set_progress(self, pct):
        self.prog.setVisible(True)
        self.prog.setValue(int(pct))

    def mark_done(self):
        self.prog.setValue(100)
        self.dl_btn.setText('✔  Done')
        self.dl_btn.setEnabled(False)


# ──────────────────────────────────────────────────────────────────────────────
#  PAGE 3: PLAYLIST DOWNLOADER
# ──────────────────────────────────────────────────────────────────────────────

class PlaylistPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items   = []
        self._workers = {}
        self._dl_queue = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16); root.setSpacing(14)

        hdr = QHBoxLayout()
        hdr.addWidget(lbl('📋', 'pageHeader'))
        hdr.addWidget(lbl('PLAYLIST DOWNLOADER', 'pageHeader'))
        hdr.addStretch()
        root.addLayout(hdr)
        root.addWidget(make_sep())

        self.url_bar = UrlBar('Paste YouTube playlist URL here…')
        self.url_bar.submitted.connect(self._fetch)
        root.addWidget(self.url_bar)

        # Stats bar
        self.stats_row = QWidget(); self.stats_row.setVisible(False)
        stats_lay = QHBoxLayout(self.stats_row)
        stats_lay.setContentsMargins(0,0,0,0); stats_lay.setSpacing(20)
        self.total_lbl = lbl('Total Videos: —', 'tag')
        self.loaded_lbl = lbl('Loaded: 0', 'statusLbl')
        stats_lay.addWidget(self.total_lbl)
        stats_lay.addWidget(self.loaded_lbl)
        stats_lay.addStretch()

        # Batch download options
        batch_lbl = lbl('BATCH QUALITY:', 'tag')
        self.batch_vid = QComboBox(); self.batch_vid.setMinimumWidth(180)
        self.batch_vid.addItems(['Best Video (auto)', '1080p', '720p', '480p', '360p'])
        self.batch_aud = QComboBox(); self.batch_aud.setMinimumWidth(150)
        self.batch_aud.addItems(['Best Audio (auto)', '256kbps', '128kbps'])
        self.dl_all_btn = GlowButton('⬇  DOWNLOAD ALL VIDEOS', 'btnGreen')
        self.dl_all_btn.clicked.connect(self._download_all)
        stats_lay.addWidget(batch_lbl)
        stats_lay.addWidget(self.batch_vid)
        stats_lay.addWidget(self.batch_aud)
        stats_lay.addWidget(self.dl_all_btn)
        root.addWidget(self.stats_row)

        self.status_lbl = lbl('Enter a playlist URL and press FETCH', 'statusLbl')
        root.addWidget(self.status_lbl)

        # Scroll list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVisible(False)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0,0,4,0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_widget)
        root.addWidget(self.scroll, 1)

    def _fetch(self, url):
        # Clear previous
        for i in reversed(range(self.list_layout.count())):
            w = self.list_layout.itemAt(i).widget()
            if w: w.deleteLater()
        self.list_layout.addStretch()
        self._items.clear()
        self.status_lbl.setText('🔄  Fetching playlist info…')
        self.stats_row.setVisible(False); self.scroll.setVisible(False)

        self._pl_worker = PlaylistInfoWorker(url)
        self._pl_worker.total_found.connect(self._on_total)
        self._pl_worker.video_ready.connect(self._on_video)
        self._pl_worker.error.connect(lambda e: self.status_lbl.setText(f'⚠  {e[:120]}'))
        self._pl_worker.start()

    def _on_total(self, n):
        self.total_lbl.setText(f'Total Videos: {n}')
        self.stats_row.setVisible(True)
        self.scroll.setVisible(True)
        self._total = n
        self._loaded = 0

    def _on_video(self, idx, info):
        item = PlaylistItemWidget(idx, info)
        item.download_requested.connect(self._dl_single_item)
        # Insert before the trailing stretch
        insert_pos = self.list_layout.count() - 1
        self.list_layout.insertWidget(insert_pos, item)
        self._items.append(item)
        self._loaded += 1
        self.loaded_lbl.setText(f'Loaded: {self._loaded}')
        self.status_lbl.setText(f'✔  {self._loaded} videos loaded')

    def _dl_single_item(self, info, fmt):
        out_dir = QFileDialog.getExistingDirectory(
            self, 'Select Download Folder', str(Path.home()/'Downloads'))
        if not out_dir: return
        url = info.get('webpage_url','')
        item = self.sender()
        worker = DownloadWorker(url, fmt, out_dir)
        worker.progress.connect(lambda pct,_: item.set_progress(pct))
        worker.finished.connect(lambda _: item.mark_done())
        worker.error.connect(lambda e: self.status_lbl.setText(f'⚠  {e[:80]}'))
        worker.start()
        self._workers[url] = worker

    def _download_all(self):
        out_dir = QFileDialog.getExistingDirectory(
            self, 'Select Download Folder', str(Path.home()/'Downloads'))
        if not out_dir: return

        bv = self.batch_vid.currentIndex()
        ba = self.batch_aud.currentIndex()
        v_map = {0:'bestvideo', 1:'bestvideo[height<=1080]',
                 2:'bestvideo[height<=720]', 3:'bestvideo[height<=480]',
                 4:'bestvideo[height<=360]'}
        a_map = {0:'bestaudio', 1:'bestaudio[abr<=256]', 2:'bestaudio[abr<=128]'}
        fmt = f"{v_map.get(bv,'bestvideo')}+{a_map.get(ba,'bestaudio')}/best"

        for item in self._items:
            info = item._info
            url  = info.get('webpage_url','')
            if not url: continue
            w = DownloadWorker(url, fmt, out_dir)
            w.progress.connect(lambda pct, _, it=item: it.set_progress(pct))
            w.finished.connect(lambda _, it=item: it.mark_done())
            w.start()
            self._workers[url] = w
        self.status_lbl.setText(
            f'🔄  Batch download started for {len(self._items)} videos…')


# ──────────────────────────────────────────────────────────────────────────────
#  SIDEBAR
# ──────────────────────────────────────────────────────────────────────────────

class Sidebar(QWidget):
    page_changed = pyqtSignal(int)

    PAGES = [
        ('📥', 'Single\nVideo'),
        ('🖼', 'Thumb\nDL'),
        ('📋', 'Playlist'),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('sidebar')
        self._btns = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        # Logo box
        logo_box = QWidget(); logo_box.setObjectName('logoBox')
        logo_box.setFixedHeight(72)
        lb = QVBoxLayout(logo_box); lb.setContentsMargins(0,0,0,0); lb.setSpacing(0)
        ico_lbl = QLabel('⬇'); ico_lbl.setObjectName('logoLbl')
        ico_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ico_lbl.setStyleSheet(f"font-size:26px; color:{C['cyan']}; "
                              f"background:{C['bg']}; padding:8px 0;")
        sub_lbl = QLabel('NEXUS'); sub_lbl.setObjectName('appTitle')
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setStyleSheet(f"color:{C['cyan']}; font-size:8px; "
                              f"letter-spacing:3px; background:{C['bg']}; padding-bottom:6px;")
        lb.addWidget(ico_lbl); lb.addWidget(sub_lbl)
        lay.addWidget(logo_box)

        for i, (icon, tip) in enumerate(self.PAGES):
            btn = QPushButton(f"{icon}\n{tip}")
            btn.setObjectName('navBtn')
            btn.setCheckable(False)
            btn.setProperty('active', i == 0)
            btn.clicked.connect(partial(self._select, i))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tip.replace('\n',' '))
            btn.setFixedHeight(72)
            btn.setStyleSheet(btn.styleSheet())  # force repaint
            lay.addWidget(btn)
            self._btns.append(btn)

        lay.addStretch()

        # Version label
        ver = QLabel('v2.0')
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"color:{C['border2']}; font-size:9px; padding:8px 0;")
        lay.addWidget(ver)

    def _select(self, idx):
        for i, btn in enumerate(self._btns):
            btn.setProperty('active', i == idx)
            btn.style().unpolish(btn); btn.style().polish(btn)
        self.page_changed.emit(idx)


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN WINDOW
# ──────────────────────────────────────────────────────────────────────────────

class NexusDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('NEXUS DOWNLOADER  ·  YouTube Media Suite')
        self.setMinimumSize(1080, 700)
        self.resize(1200, 780)
        self._build()

    def _build(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QHBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self._switch_page)
        root.addWidget(self.sidebar)

        # Divider line
        line = QFrame(); line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet(f"background:{C['border']}; max-width:1px;")
        root.addWidget(line)

        self.stack = QStackedWidget()
        self.pages = [SingleVideoPage(), ThumbnailPage(), PlaylistPage()]
        for p in self.pages: self.stack.addWidget(p)
        root.addWidget(self.stack, 1)

    def _switch_page(self, idx):
        self.stack.setCurrentIndex(idx)


# ──────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Nexus Downloader')
    app.setStyle('Fusion')
    app.setStyleSheet(STYLESHEET)

    # Set app-wide dark palette for menus/dialogs
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,          QColor(C['bg']))
    pal.setColor(QPalette.ColorRole.WindowText,      QColor(C['txt']))
    pal.setColor(QPalette.ColorRole.Base,            QColor(C['bg2']))
    pal.setColor(QPalette.ColorRole.AlternateBase,   QColor(C['bg1']))
    pal.setColor(QPalette.ColorRole.ToolTipBase,     QColor(C['bg2']))
    pal.setColor(QPalette.ColorRole.ToolTipText,     QColor(C['txt']))
    pal.setColor(QPalette.ColorRole.Text,            QColor(C['txt']))
    pal.setColor(QPalette.ColorRole.Button,          QColor(C['bg2']))
    pal.setColor(QPalette.ColorRole.ButtonText,      QColor(C['txt']))
    pal.setColor(QPalette.ColorRole.BrightText,      QColor(C['cyan']))
    pal.setColor(QPalette.ColorRole.Link,            QColor(C['cyan']))
    pal.setColor(QPalette.ColorRole.Highlight,       QColor(C['cyan_dim']))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor('#ffffff'))
    app.setPalette(pal)

    win = NexusDownloader()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()