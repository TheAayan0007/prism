#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║           PRISM — YouTube Media Suite v7.3                      ║
║                    Installer Script                              ║
╚══════════════════════════════════════════════════════════════════╝

  Run this script to automatically install all requirements:
    - Python (guides user if missing)
    - pip (auto-installs if missing)
    - PyQt6, yt-dlp, Pillow, requests
    - FFmpeg (Windows / Linux / macOS)
"""

import os
import sys
import platform
import subprocess
import shutil
import zipfile
import tarfile
import tempfile
import urllib.request
import urllib.error
import json
from pathlib import Path

# ─────────────────────────── Colours (ANSI) ─────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
WHITE  = "\033[97m"
DIM    = "\033[2m"

def c(color, text): return f"{color}{text}{RESET}"

def banner():
    print()
    print(c(CYAN, "╔══════════════════════════════════════════════════════════════════╗"))
    print(c(CYAN, "║") + c(BOLD + WHITE, "           PRISM — YouTube Media Suite v7.3                      ") + c(CYAN, "║"))
    print(c(CYAN, "║") + c(DIM,          "                    Installer Script                              ") + c(CYAN, "║"))
    print(c(CYAN, "╚══════════════════════════════════════════════════════════════════╝"))
    print()

def step(msg):   print(c(CYAN,   f"\n  ▶  {msg}"))
def ok(msg):     print(c(GREEN,  f"  ✔  {msg}"))
def warn(msg):   print(c(YELLOW, f"  ⚠  {msg}"))
def error(msg):  print(c(RED,    f"  ✖  {msg}"))
def info(msg):   print(c(DIM,    f"     {msg}"))

OS   = platform.system()          # 'Windows' | 'Linux' | 'Darwin'
ARCH = platform.machine().lower() # 'x86_64' | 'arm64' | 'aarch64' …

# ─────────────────────────── Helpers ────────────────────────────────────────

def run(cmd, capture=True, check=False):
    """Run a shell command; return (returncode, stdout+stderr)."""
    try:
        r = subprocess.run(
            cmd, shell=isinstance(cmd, str),
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT if capture else None,
            text=True
        )
        return r.returncode, (r.stdout or "").strip()
    except Exception as e:
        return 1, str(e)

def download(url, dest: Path, label=""):
    """Download url → dest with a simple progress indicator."""
    label = label or dest.name
    print(f"     Downloading {label} …", end="", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            done  = 0
            chunk = 1 << 16   # 64 KB
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                if total:
                    pct = done * 100 // total
                    print(f"\r     Downloading {label} … {pct:3d}%", end="", flush=True)
        print(f"\r     Downloading {label} … done       ")
        return True
    except Exception as e:
        print()
        error(f"Download failed: {e}")
        return False

def which(name):
    return shutil.which(name)

# ─────────────────────────── 1. Python check ────────────────────────────────

def check_python():
    step("Checking Python version")
    major, minor = sys.version_info[:2]
    info(f"Found Python {major}.{minor}.{sys.version_info[2]} — {sys.executable}")
    if (major, minor) < (3, 10):
        error(f"Python 3.10+ is required (you have {major}.{minor}).")
        _guide_python_install()
        sys.exit(1)
    ok(f"Python {major}.{minor} — OK")

def _guide_python_install():
    print()
    warn("Please install or upgrade Python manually:")
    if OS == "Windows":
        info("  1. Go to  https://www.python.org/downloads/")
        info("  2. Download the latest Python 3.x installer")
        info("  3. Run it — tick  'Add Python to PATH'  before clicking Install")
        info("  4. Re-run this installer afterwards")
    elif OS == "Darwin":
        info("  Option A (recommended):  brew install python")
        info("  Option B:  https://www.python.org/downloads/macos/")
    else:
        info("  Ubuntu/Debian :  sudo apt install python3 python3-pip")
        info("  Fedora        :  sudo dnf install python3 python3-pip")
        info("  Arch          :  sudo pacman -S python python-pip")

# ─────────────────────────── 2. pip check ───────────────────────────────────

def ensure_pip():
    step("Checking pip")
    code, out = run([sys.executable, "-m", "pip", "--version"])
    if code == 0:
        ok(f"pip found — {out.split()[1] if len(out.split()) > 1 else out}")
        return
    warn("pip not found — attempting to install via ensurepip …")
    code, out = run([sys.executable, "-m", "ensurepip", "--upgrade"])
    if code != 0:
        error("Could not install pip automatically.")
        info("Try:  python -m ensurepip --upgrade")
        info("  or: curl https://bootstrap.pypa.io/get-pip.py | python")
        sys.exit(1)
    ok("pip installed")

# ─────────────────────────── 3. Python packages ─────────────────────────────

PACKAGES = [
    ("PyQt6",    "PyQt6",    "from PyQt6.QtWidgets import QApplication"),
    ("yt-dlp",   "yt_dlp",   "import yt_dlp"),
    ("Pillow",   "PIL",      "from PIL import Image"),
    ("requests", "requests", "import requests"),
]

def install_packages():
    step("Installing Python packages")
    failed = []
    for pip_name, import_name, check_stmt in PACKAGES:
        # quick import check first
        code, _ = run([sys.executable, "-c", check_stmt])
        if code == 0:
            ok(f"{pip_name} — already installed")
            continue
        info(f"Installing {pip_name} …")
        install_cmd = [
            sys.executable, "-m", "pip", "install",
            pip_name, "--upgrade", "--break-system-packages", "-q"
        ]
        code, out = run(install_cmd)
        if code != 0:
            # retry without --break-system-packages (older pip)
            install_cmd2 = [
                sys.executable, "-m", "pip", "install", pip_name, "--upgrade", "-q"
            ]
            code, out = run(install_cmd2)
        if code == 0:
            ok(f"{pip_name} — installed")
        else:
            error(f"{pip_name} — FAILED")
            info(out[-400:])
            failed.append(pip_name)
    if failed:
        error(f"Could not install: {', '.join(failed)}")
        info("Try running:  pip install " + " ".join(failed))
        sys.exit(1)

# ─────────────────────────── 4. FFmpeg ──────────────────────────────────────

def check_ffmpeg():
    step("Checking FFmpeg")
    p = which("ffmpeg")
    if p:
        code, ver = run(["ffmpeg", "-version"])
        first_line = ver.splitlines()[0] if ver else "?"
        ok(f"FFmpeg found — {first_line}")
        return True
    warn("FFmpeg not found on PATH")
    return False

def install_ffmpeg():
    """Dispatch to OS-specific installer."""
    if OS == "Windows":
        _install_ffmpeg_windows()
    elif OS == "Darwin":
        _install_ffmpeg_macos()
    else:
        _install_ffmpeg_linux()

# ── Windows ──────────────────────────────────────────────────────────────────

def _install_ffmpeg_windows():
    info("Fetching latest FFmpeg build info from GitHub …")
    # Use the gyan.dev stable essentials build (most popular Windows FFmpeg distro)
    api_url = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
    try:
        with urllib.request.urlopen(api_url, timeout=15) as r:
            data = json.loads(r.read())
    except Exception as e:
        warn(f"Could not reach GitHub API: {e}")
        _guide_ffmpeg_windows()
        return

    # find the 'essentials' zip asset
    asset = None
    for a in data.get("assets", []):
        name = a["name"].lower()
        if "essentials" in name and name.endswith(".zip"):
            asset = a
            break
    if asset is None:
        warn("Could not locate essentials zip in release assets.")
        _guide_ffmpeg_windows()
        return

    dl_url = asset["browser_download_url"]
    zip_name = asset["name"]
    info(f"Asset: {zip_name}")

    tmp = Path(tempfile.mkdtemp())
    zip_path = tmp / zip_name
    if not download(dl_url, zip_path, zip_name):
        _guide_ffmpeg_windows()
        return

    info("Extracting …")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
    except Exception as e:
        error(f"Extraction failed: {e}")
        _guide_ffmpeg_windows()
        return

    # find extracted ffmpeg.exe
    ffmpeg_exe = None
    for p in tmp.rglob("ffmpeg.exe"):
        ffmpeg_exe = p
        break
    if not ffmpeg_exe:
        error("ffmpeg.exe not found in archive.")
        _guide_ffmpeg_windows()
        return

    # copy to a permanent location
    dest_dir = Path(os.environ.get("LOCALAPPDATA", "C:\\ffmpeg")) / "ffmpeg" / "bin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for exe in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
        src = ffmpeg_exe.parent / exe
        if src.exists():
            shutil.copy2(src, dest_dir / exe)
    ok(f"FFmpeg copied to: {dest_dir}")

    # add to user PATH permanently
    _add_to_path_windows(str(dest_dir))
    ok("FFmpeg installed — restart your terminal / reboot for PATH to take effect")
    # also patch os.environ for the rest of this session
    os.environ["PATH"] = str(dest_dir) + os.pathsep + os.environ.get("PATH", "")

def _add_to_path_windows(new_dir: str):
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE
        )
        try:
            current, _ = winreg.QueryValueEx(key, "PATH")
        except FileNotFoundError:
            current = ""
        if new_dir.lower() not in current.lower():
            new_val = current + ";" + new_dir if current else new_dir
            winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_val)
            ok("Added FFmpeg to user PATH (registry)")
        winreg.CloseKey(key)
        # broadcast WM_SETTINGCHANGE so Explorer picks it up
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None
        )
    except Exception as e:
        warn(f"Could not update PATH automatically: {e}")
        info(f"Please add manually:  {new_dir}")

def _guide_ffmpeg_windows():
    warn("Please install FFmpeg manually:")
    info("  1. Go to  https://ffmpeg.org/download.html")
    info("  2. Click 'Windows builds from gyan.dev'")
    info("  3. Download the 'essentials' build zip")
    info("  4. Extract and copy the bin folder contents to  C:\\ffmpeg\\bin")
    info("  5. Add  C:\\ffmpeg\\bin  to your system PATH")

# ── macOS ─────────────────────────────────────────────────────────────────────

def _install_ffmpeg_macos():
    if which("brew"):
        info("Homebrew found — running:  brew install ffmpeg")
        code, out = run("brew install ffmpeg", capture=False)
        if code == 0:
            ok("FFmpeg installed via Homebrew")
        else:
            error("brew install failed.")
            _guide_ffmpeg_macos()
    else:
        warn("Homebrew not found.")
        _guide_ffmpeg_macos()

def _guide_ffmpeg_macos():
    info("Option A:  Install Homebrew first →  https://brew.sh")
    info("           then run:  brew install ffmpeg")
    info("Option B:  Download static build from  https://ffmpeg.org/download.html")

# ── Linux ─────────────────────────────────────────────────────────────────────

def _install_ffmpeg_linux():
    # Detect package manager
    managers = [
        ("apt-get", ["sudo", "apt-get", "install", "-y", "ffmpeg"]),
        ("apt",     ["sudo", "apt",     "install", "-y", "ffmpeg"]),
        ("dnf",     ["sudo", "dnf",     "install", "-y", "ffmpeg"]),
        ("yum",     ["sudo", "yum",     "install", "-y", "ffmpeg"]),
        ("pacman",  ["sudo", "pacman",  "-S",  "--noconfirm", "ffmpeg"]),
        ("zypper",  ["sudo", "zypper",  "install", "-y", "ffmpeg"]),
        ("apk",     ["sudo", "apk",     "add", "ffmpeg"]),
    ]
    for mgr, cmd in managers:
        if which(mgr):
            info(f"Package manager found: {mgr}")
            info(f"Running: {' '.join(cmd)}")
            code, out = run(cmd, capture=False)
            if code == 0:
                ok("FFmpeg installed")
                return
            else:
                warn(f"Install via {mgr} failed (may need sudo / manual install).")
                break
    # Fall back: static binary from johnvansickle.com
    _install_ffmpeg_linux_static()

def _install_ffmpeg_linux_static():
    info("Trying static FFmpeg binary from johnvansickle.com …")
    if "aarch64" in ARCH or "arm64" in ARCH:
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
        fname = "ffmpeg-release-arm64-static.tar.xz"
    else:
        url   = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        fname = "ffmpeg-release-amd64-static.tar.xz"

    tmp = Path(tempfile.mkdtemp())
    tar_path = tmp / fname
    if not download(url, tar_path, fname):
        _guide_ffmpeg_linux()
        return

    info("Extracting …")
    try:
        with tarfile.open(tar_path) as tf:
            tf.extractall(tmp)
    except Exception as e:
        error(f"Extraction failed: {e}")
        _guide_ffmpeg_linux()
        return

    ffmpeg_bin = None
    for p in tmp.rglob("ffmpeg"):
        if p.is_file() and os.access(p, os.X_OK):
            ffmpeg_bin = p
            break
    if not ffmpeg_bin:
        error("ffmpeg binary not found in archive.")
        _guide_ffmpeg_linux()
        return

    dest = Path("/usr/local/bin/ffmpeg")
    try:
        shutil.copy2(ffmpeg_bin, dest)
        dest.chmod(0o755)
        # copy ffprobe if present
        ffprobe = ffmpeg_bin.parent / "ffprobe"
        if ffprobe.exists():
            dp = Path("/usr/local/bin/ffprobe")
            shutil.copy2(ffprobe, dp); dp.chmod(0o755)
        ok(f"FFmpeg installed to {dest}")
        return
    except PermissionError:
        pass

    # No sudo? Install to ~/.local/bin
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    dest = local_bin / "ffmpeg"
    shutil.copy2(ffmpeg_bin, dest); dest.chmod(0o755)
    ffprobe = ffmpeg_bin.parent / "ffprobe"
    if ffprobe.exists():
        dp = local_bin / "ffprobe"; shutil.copy2(ffprobe, dp); dp.chmod(0o755)
    ok(f"FFmpeg installed to {dest}")
    # patch PATH for current session
    os.environ["PATH"] = str(local_bin) + os.pathsep + os.environ.get("PATH", "")
    warn(f"Add  {local_bin}  to your PATH in ~/.bashrc or ~/.zshrc:")
    info(f'  export PATH="{local_bin}:$PATH"')

def _guide_ffmpeg_linux():
    warn("Please install FFmpeg manually:")
    info("  Ubuntu/Debian :  sudo apt install ffmpeg")
    info("  Fedora/RHEL   :  sudo dnf install ffmpeg")
    info("  Arch          :  sudo pacman -S ffmpeg")
    info("  Static build  :  https://johnvansickle.com/ffmpeg/")

# ─────────────────────────── 5. Final verification ──────────────────────────

def verify_all():
    step("Verifying all requirements")
    all_ok = True

    # Python
    code, _ = run([sys.executable, "--version"])
    if code == 0:
        ok(f"Python  {sys.version.split()[0]}")
    else:
        error("Python not working"); all_ok = False

    # Packages
    for pip_name, _, check_stmt in PACKAGES:
        code, _ = run([sys.executable, "-c", check_stmt])
        if code == 0:
            ok(f"{pip_name}")
        else:
            error(f"{pip_name} — NOT FOUND"); all_ok = False

    # FFmpeg
    p = which("ffmpeg")
    if p:
        code, ver = run(["ffmpeg", "-version"])
        line = ver.splitlines()[0] if ver else "?"
        ok(f"FFmpeg — {line[:60]}")
    else:
        error("FFmpeg — NOT FOUND"); all_ok = False

    return all_ok

# ─────────────────────────── Main ───────────────────────────────────────────

def main():
    # enable ANSI on Windows
    if OS == "Windows":
        os.system("color")
        try:
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.SetConsoleMode(kernel.GetStdHandle(-11), 7)
        except Exception:
            pass

    banner()
    print(c(WHITE, f"  Platform : {OS} {platform.release()}  [{ARCH}]"))
    print(c(WHITE, f"  Python   : {sys.executable}"))
    print()

    check_python()
    ensure_pip()
    install_packages()

    if not check_ffmpeg():
        step("Installing FFmpeg")
        install_ffmpeg()
        # re-check after install
        if not check_ffmpeg():
            warn("FFmpeg may not be on PATH yet — this is often expected.")
            info("Restart your terminal/system and run  ffmpeg -version  to confirm.")

    print()
    all_good = verify_all()
    print()

    if all_good:
        print(c(GREEN + BOLD, "  ✔  All requirements satisfied — Prism is ready to run!"))
        print(c(DIM, "     Launch with:  python prism.py"))
    else:
        print(c(YELLOW + BOLD, "  ⚠  Some requirements could not be verified automatically."))
        print(c(DIM, "     Please review the errors above and install missing items manually."))

    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(c(YELLOW, "\n\n  Installation cancelled by user."))
        sys.exit(0)
