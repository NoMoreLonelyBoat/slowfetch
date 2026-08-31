"""
Windows SlowFetch — 一款受 linux fastfetch 启发的系统信息展示工具。

把任意图片放入 logos/ 文件夹即可作为徽标显示（也支持在 slowfetch.conf 中
指定图片 / --logo 参数 / --width 调整宽度）。图片会在支持真彩色的终端中
以 ANSI 24 位色块渲染。

用法:
    python slowfetch.py                      # 默认读取 logos/ 或配置中的图片
    python slowfetch.py --no-color           # 禁用颜色（此时不渲染图片徽标）
    python slowfetch.py --logo 图片路径      # 手动指定徽标图片
    python slowfetch.py --width 30           # 调整徽标显示宽度(字符数)
    python slowfetch.py --structure OS:OS,Host,,Uptime:Uptime
    python slowfetch.py --help
"""

from __future__ import annotations

import argparse
import ctypes
import locale
import os
import platform
import shutil
import socket
import subprocess
import sys
import winreg
from ctypes import wintypes
from datetime import datetime


# ----------------------------------------------------------------------------
# ANSI 颜色
# ----------------------------------------------------------------------------

class ANSI:
    RESET = "\x1b[0m"

    @staticmethod
    def wrap(s: str, code: str) -> str:
        if not code:
            return s
        return f"\x1b[{code}m{s}{ANSI.RESET}"


def _enable_vt(no_color: bool) -> bool:
    """在 Windows 下开启 VT 处理以支持 ANSI 彩色，返回是否启用彩色。"""
    if no_color or os.environ.get("NO_COLOR"):
        return False
    try:
        os.system("")          # 打开 VT 标志（副作用小）
    except Exception:
        pass
    try:
        from ctypes import byref
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = wintypes.DWORD()
        if kernel32.GetConsoleMode(handle, byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            return True
    except Exception:
        pass
    return sys.stdout.isatty()


# ----------------------------------------------------------------------------
# 徽标（图片）—— 使用用户提供的图片作为徽标，可自行更换
# ----------------------------------------------------------------------------
# 徽标读取自图片文件：默认扫描 logos/ 目录，也可通过 slowfetch.conf 指定。
# 渲染原理：把图片降采样到终端字符网格，用 24 位真彩色“上半块”字符(▀)绘制，
# 每个字符上、下各一个像素，垂直分辨率提升一倍。

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_NAME = "slowfetch.conf"
LOGO_DIR = "logos"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")


def _iter_images(folder: str):
    if not os.path.isdir(folder):
        return []
    out = []
    for n in sorted(os.listdir(folder)):
        if os.path.splitext(n)[1].lower() in IMAGE_EXTS:
            out.append(os.path.join(folder, n))
    return out


def ensure_resources():
    """保证徽标配置文件和图片文件夹存在；缺失则自动创建。"""
    folder = os.path.join(BASE_DIR, LOGO_DIR)
    if not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "README.txt"), "w", encoding="utf-8") as f:
            f.write("把要作为徽标显示的图片放到本文件夹即可。\n"
                    "支持格式：png / jpg / jpeg / bmp / gif / webp\n"
                    "你可以随时删除或替换这里的图片。\n")
    cfg_path = os.path.join(BASE_DIR, CONFIG_NAME)
    if not os.path.isfile(cfg_path):
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("# slowfetch 徽标配置文件（可自行编辑）\n"
                    "# logo_image: 徽标图片路径，相对于本文件目录；可用相对路径或绝对路径。\n"
                    "#             若不填，则自动使用 logos/ 目录中的第一张图片。\n"
                    "# logo_width: 徽标显示的字符宽度（终端列数），建议 30-50。\n"
                    "logo_image = logos/logo.png\n"
                    "logo_width = 40\n")


def load_config() -> dict:
    cfg = {"logo_image": os.path.join(LOGO_DIR, "logo.png"), "logo_width": 40}
    path = os.path.join(BASE_DIR, CONFIG_NAME)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.split("#", 1)[0].strip()
                    if not line or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
        except Exception:
            pass
    return cfg


def resolve_image(cfg: dict):
    """返回实际可用的图片路径；找不到返回 None。"""
    spec = (cfg.get("logo_image") or "").strip()
    if spec:
        p = os.path.normpath(os.path.join(BASE_DIR, spec))
        if os.path.isfile(p):
            return p
    imgs = _iter_images(os.path.join(BASE_DIR, LOGO_DIR))
    return imgs[0] if imgs else None


def _load_pixels(path: str, cols: int, rows: int):
    """解码并降采样图片为 RGB 网格 [[(r,g,b), ...], ...]。"""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im = im.resize((cols, rows), Image.LANCZOS)
        px = im.load()
        return [[px[x, y] for x in range(cols)] for y in range(rows)]
    except Exception:
        pass
    # 兜底：使用 Windows 自带 System.Drawing，无需安装 PIL
    return _load_pixels_powershell(path, cols, rows)


def _load_pixels_powershell(path: str, cols: int, rows: int):
    path = path.replace("'", "''")
    script = (r"""
Add-Type -AssemblyName System.Drawing
$img=[System.Drawing.Image]::FromFile('__PATH__')
$cols=__COLS__; $rows=__ROWS__
$bmp=New-Object System.Drawing.Bitmap $cols,$rows
$g=[System.Drawing.Graphics]::FromImage($bmp)
$g.InterpolationMode=[System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.DrawImage($img,0,0,$cols,$rows)
$lines=@()
for($y=0;$y -lt $rows;$y++){
  $t=@()
  for($x=0;$x -lt $cols;$x++){
    $c=$bmp.GetPixel($x,$y)
    $t += (''+$c.R+','+$c.G+','+$c.B)
  }
  $lines += ($t -join ';')
}
$g.Dispose(); $bmp.Dispose(); $img.Dispose()
Write-Output ($lines -join "`n")
""").replace("__PATH__", path).replace("__COLS__", str(cols))\
            .replace("__ROWS__", str(rows))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, timeout=30, creationflags=flags,
    ).stdout.decode("utf-8", errors="replace")
    grid = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            grid.append([tuple(map(int, px.split(","))) for px in line.split(";")])
        except Exception:
            continue
    return grid


def render_image_lines(path: str, width: int):
    """渲染图片为真彩色半块字符行。返回 (行列表, 显示宽度字符数)。"""
    cols = max(2, int(width))
    try:
        from PIL import Image
        im = Image.open(path)
        rows = max(1, round(cols * im.size[1] / im.size[0] * 2))
        rows = min(rows, 200)
    except Exception:
        rows = cols
    grid = _load_pixels(path, cols, rows)
    lines = []
    for y in range(0, len(grid), 2):
        buf = []
        for x in range(cols):
            top = grid[y][x]
            bot = grid[y + 1][x] if y + 1 < len(grid) else top
            buf.append(f"\x1b[38;2;{top[0]};{top[1]};{top[2]}m"
                       f"\x1b[48;2;{bot[0]};{bot[1]};{bot[2]}m▀")
        buf.append(ANSI.RESET)
        lines.append("".join(buf))
    return lines, cols


# ----------------------------------------------------------------------------
# ctypes 系统调用
# ----------------------------------------------------------------------------

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


def _kernel():
    if os.name == "nt":
        return ctypes.windll.kernel32
    return None


_kernel32 = _kernel()


def _get_resolution():
    try:
        w = _kernel32.GetSystemMetrics(0)   # SM_CXSCREEN
        h = _kernel32.GetSystemMetrics(1)   # SM_CYSCREEN
        return (w, h) if w and h else None
    except Exception:
        return None


def _get_uptime_ms():
    try:
        return _kernel32.GetTickCount64()
    except Exception:
        return 0


def _get_memory_status():
    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if _kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return stat
    except Exception:
        pass
    return None


def _get_battery():
    try:
        st = SYSTEM_POWER_STATUS()
        if _kernel32.GetSystemPowerStatus(ctypes.byref(st)):
            return st
    except Exception:
        pass
    return None


def _registry_current(value: str, default: str = "") -> str:
    """读取 HKCU 当前用户主题类注册表值。"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as k:
            return str(winreg.QueryValueEx(k, value)[0])
    except Exception:
        return default


def _registry_local(key: str, value: str, default: str = "") -> str:
    """读取 HKLM 注册表字符串值。"""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
            return str(winreg.QueryValueEx(k, value)[0])
    except Exception:
        return default


def _pow(query: str) -> str:
    """执行 powershell 只读查询，返回去除空白后的结果。失败返回 ''。"""
    if os.name != "nt":
        return ""
    try:
        script = ("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
                  "& {" + query + "} | ForEach-Object { \"$($_)\" }")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=8, creationflags=flags,
        ).stdout.decode("utf-8", errors="replace")
        return out.strip()
    except Exception:
        return ""


# ----------------------------------------------------------------------------
# 信息模块
# ----------------------------------------------------------------------------

def mod_os():
    win32 = sys.getwindowsversion()
    release = platform.release() or "10"
    product = _registry_local(
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "ProductName",
    ) or f"Windows {release}"
    build = win32.build
    disp = _registry_local(
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "DisplayVersion", "")
    ver = f"{win32.major}.{win32.minor}.{build}"
    if disp:
        ver += f" ({disp})"
    return f"Microsoft {product} {ver}"


def mod_host():
    manu = _pow("Get-CimInstance Win32_ComputerSystem | % Manufacturer")
    model = _pow("Get-CimInstance Win32_ComputerSystem | % Model")
    if not model:
        return ""
    if manu and manu.lower() not in model.lower():
        return f"{manu} {model}"
    return model


def mod_kernel():
    w = sys.getwindowsversion()
    return f"{w.major}.{w.minor}.{w.build}"


def mod_uptime():
    secs = _get_uptime_ms() // 1000
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d: parts.append(f"{d} days")
    if h: parts.append(f"{h} hours")
    if m: parts.append(f"{m} mins")
    if s: parts.append(f"{s} secs")
    return " ".join(parts) or "0 secs"


def mod_packages():
    found = []
    for probe in ("choco", "scoop", "winget"):
        try:
            r = subprocess.run([probe, "--version"], capture_output=True,
                               text=True, timeout=6)
            if r.returncode == 0:
                found.append(probe)
        except Exception:
            continue
    if not found:
        return f"0 ({', '.join(found) or '无包管理器'})"
    return f"{len(found)} ({', '.join(found)})"


def mod_shell():
    shell = os.environ.get("ComSpec") or os.environ.get("SHELL") or "cmd"
    base = os.path.basename(shell.replace("\\", "/")).lower()
    mapping = {
        "powershell.exe": "PowerShell",
        "powershell": "PowerShell",
        "pwsh.exe": "PowerShell (pwsh)",
        "pwsh": "PowerShell (pwsh)",
        "cmd.exe": "cmd",
        "cmd": "cmd",
    }
    return mapping.get(base, base or "cmd")


def mod_resolution():
    r = _get_resolution()
    return f"{r[0]}x{r[1]}" if r else ""


def mod_de():
    return "Windows Explorer"


def mod_wm():
    return "Windows (DWM)"


def mod_wm_theme():
    v = _registry_current("AppsUseLightTheme")
    return "Dark" if v == "0" else "Light" if v == "1" else ""


def mod_icons():
    return "Windows"


def mod_terminal():
    return (os.environ.get("TERM_PROGRAM")
            or os.environ.get("WT_SESSION") and "Windows Terminal"
            or "ConHost")


def mod_cpu():
    name = _pow("Get-CimInstance Win32_Processor | % Name") \
        or os.environ.get("PROCESSOR_IDENTIFIER", "")
    cores = os.cpu_count() or 0
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            desc = str(winreg.QueryValueEx(k, "ProcessorNameString")[0])
        if desc:
            name = desc
    except Exception:
        pass
    return f"{name} ({cores} cores)"


def mod_gpu():
    raw = _pow("(Get-CimInstance Win32_VideoController).Name")
    if raw:
        names = [l for l in raw.splitlines() if l.strip()]
        return " / ".join(names)
    return ""


def mod_memory():
    st = _get_memory_status()
    if not st:
        return ""
    used = st.ullTotalPhys - st.ullAvailPhys
    return f"{used/1024**3:.1f} GiB / {st.ullTotalPhys/1024**3:.1f} GiB"


def mod_swap():
    st = _get_memory_status()
    if not st or st.ullTotalPageFile == 0:
        return ""
    used = st.ullTotalPageFile - st.ullAvailPageFile
    return f"{used/1024**3:.1f} GiB / {st.ullTotalPageFile/1024**3:.1f} GiB"


def mod_disk():
    try:
        usage = shutil.disk_usage(os.path.abspath(os.sep))
        return f"{usage.used/1024**3:.1f} GiB / {usage.total/1024**3:.1f} GiB"
    except Exception:
        return ""


def mod_battery():
    st = _get_battery()
    if st is None:
        return ""
    pct = st.BatteryLifePercent & 0xFF          # BYTE 是有符号的，需取低 8 位
    if pct == 255:                              # 无电池（纯 AC 供电）
        return ""
    if st.ACLineStatus == 1:
        state = "Charging" if pct < 100 else "Full"
    elif st.ACLineStatus == 0:
        state = "Discharging"
    else:
        state = "Unknown"
    return f"{pct}% ({state})"


def mod_locale():
    try:
        lc = locale.getdefaultlocale()[0] or "unknown"
    except Exception:
        lc = "unknown"
    return lc


def mod_system_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def mod_boot():
    return _registry_local(
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "CurrentBuildNumber",
        "") or ""


DEFAULT_STRUCTURE = [
    ("OS",          "os"),
    ("Host",        "host"),
    ("Kernel",      "kernel"),
    ("Uptime",      "uptime"),
    ("Packages",    "packages"),
    ("Shell",       "shell"),
    ("Resolution",  "resolution"),
    ("DE",          "de"),
    ("WM",          "wm"),
    ("WM Theme",    "wm_theme"),
    ("Icons",       "icons"),
    ("Terminal",    "terminal"),
    ("CPU",         "cpu"),
    ("GPU",         "gpu"),
    ("Memory",      "memory"),
    ("Swap",        "swap"),
    ("Disk (/)",    "disk"),
    ("Battery",     "battery"),
    ("Locale",      "locale"),
]


# ----------------------------------------------------------------------------
# 布局与渲染
# ----------------------------------------------------------------------------

def render(logo_lines, logo_width, info_lines, color_on):
    gap = 6

    n = max(len(logo_lines), len(info_lines))
    out = []
    for i in range(n):
        # 徽标列
        if i < len(logo_lines):
            col1 = logo_lines[i]
        elif logo_width:
            col1 = " " * logo_width
        else:
            col1 = ""

        # 信息列
        info = ""
        if i < len(info_lines):
            key, val = info_lines[i]
            if color_on:
                info = (ANSI.wrap(key + ":", "1;97")
                        + ANSI.wrap(" " + val, "36"))
            else:
                info = key + ": " + val
        out.append(col1 + " " * gap + info)
    return "\n".join(row.rstrip() for row in out)


# ----------------------------------------------------------------------------
# 命令行入口
# ----------------------------------------------------------------------------

HELP = __doc__ + """

结构语法（--structure）：
    逗号分隔的模块项；空项输出空行。项为 标签:模块名 或直接 模块名，如：
        --structure OS:OS,Host,,Uptime:Uptime,Memory:Memory

    可用模块名: os host kernel uptime packages shell resolution de wm
        wm_theme theme icons terminal cpu gpu memory swap disk battery locale
        system_time boot

颜色选项：
    --no-color   强制禁用颜色（关闭颜色时也将不渲染图片徽标）

徽标（图片）：
    默认从 logos/ 目录或 slowfetch.conf 指定的图片读取并作为徽标显示。
    --logo <图片路径>   手动指定一张徽标图片（覆盖配置文件）
    --width <字符数>    徽标显示宽度（终端列数，覆盖配置文件的 logo_width）
    你可以直接把喜欢的图片放进 logos/ 文件夹即可替换徽标。
    需彩色(-c)启用；若 PIL 不可用会自动改用系统 System.Drawing 解码。
"""


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--help", "-h", action="store_true")
    parser.add_argument("--logo", default=None)
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--structure", default=None)
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--color", action="store_true")
    args, _ = parser.parse_known_args(argv)

    if args.help:
        print(HELP)
        return 0

    color_on = args.color or _enable_vt(args.no_color)
    ensure_resources()
    cfg = load_config()
    width = args.width or int(cfg.get("logo_width") or 40)

    # 构建图片徽标行
    logo_lines, logo_width = [], 0
    if color_on:
        img = args.logo or resolve_image(cfg)
        if img:
            try:
                logo_lines, logo_width = render_image_lines(img, width)
            except Exception:
                logo_lines, logo_width = [], 0
    else:
        img = None
        logo_width = 0

    if args.structure:
        info_lines = []
        for token in args.structure.split(","):
            token = token.strip()
            if not token:
                info_lines.append(("", ""))
                continue
            label, name = (token.split(":", 1) if ":" in token
                           else (token, token))
            fn = globals().get("mod_" + name.strip().lower())
            if fn is None:
                info_lines.append((label.strip(), f"(未知模块 {name})"))
                continue
            try:
                info_lines.append((label.strip(), fn()))
            except Exception as e:
                info_lines.append((label.strip(), f"! {e}"))
    else:
        info_lines = []
        for label, name in DEFAULT_STRUCTURE:
            fn = globals()["mod_" + name]
            try:
                val = fn()
            except Exception as e:
                val = f"! {e}"
            if val:                              # 空值模块隐藏（同 fastfetch）
                info_lines.append((label, val))

    print(render(logo_lines, logo_width, info_lines, color_on))
    return 0


if __name__ == "__main__":
    sys.exit(main())