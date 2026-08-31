#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Windows SlowFetch — 系统信息展示工具，支持自定义图片徽标。

用法：
    python slowfetch.py                     # 默认启动
    python slowfetch.py --no-color          # 禁用颜色和图片
    python slowfetch.py --logo 图片路径     # 指定徽标
    python slowfetch.py --width 30          # 设置徽标宽度
    python slowfetch.py --structure OS:OS,Host,,Uptime:Uptime
    python slowfetch.py --debug             # 显示详细错误信息
    python slowfetch.py --help
"""

from __future__ import annotations

import argparse
import configparser
import ctypes
import hashlib
import locale
import logging
import os
import pickle
import platform
import shutil
import sys
import time
import winreg
from ctypes import wintypes
from datetime import datetime
from functools import lru_cache

# ----------------------------------------------------------------------------
# 全局常量
# ----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_NAME = "slowfetch.conf"
LOGO_DIR = "logos"
CACHE_DIR = os.path.join(BASE_DIR, ".cache")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")
DEFAULT_STRUCTURE = [
    ("OS", "os"),
    ("Host", "host"),
    ("Kernel", "kernel"),
    ("Uptime", "uptime"),
    ("Packages", "packages"),
    ("Shell", "shell"),
    ("Resolution", "resolution"),
    ("DE", "de"),
    ("WM", "wm"),
    ("WM Theme", "wm_theme"),
    ("Icons", "icons"),
    ("Terminal", "terminal"),
    ("CPU", "cpu"),
    ("GPU", "gpu"),
    ("Memory", "memory"),
    ("Swap", "swap"),
    ("Disk (/)", "disk"),
    ("Battery", "battery"),
    ("Locale", "locale"),
    ("System Time", "system_time"),
    ("Boot Time", "boot"),
]

# ----------------------------------------------------------------------------
# ANSI 颜色与 VT 支持
# ----------------------------------------------------------------------------
class ANSI:
    RESET = "\x1b[0m"

    @staticmethod
    def wrap(s: str, code: str) -> str:
        if not code:
            return s
        return f"\x1b[{code}m{s}{ANSI.RESET}"


def _enable_vt(no_color: bool) -> bool:
    if no_color or os.environ.get("NO_COLOR"):
        return False
    try:
        os.system("")
    except Exception:
        pass
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = wintypes.DWORD()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            return True
    except Exception:
        pass
    return sys.stdout.isatty()


# ----------------------------------------------------------------------------
# 配置加载 (使用 configparser)
# ----------------------------------------------------------------------------
def _normalize_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off", ""}:
        return False
    return default


def _strip_inline_comment(value: str) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if "#" in s:
        s = s.split("#", 1)[0].rstrip()
    if ";" in s and not s.startswith(";"):
        s = s.split(";", 1)[0].rstrip()
    return s.strip()


def _legacy_section_from_text(text: str):
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
        elif ":" in line:
            key, val = line.split(":", 1)
        else:
            continue
        key = key.strip().lower()
        val = _strip_inline_comment(val)
        if val and val[0] in {'"', "'"} and val[-1] == val[0]:
            val = val[1:-1]
        values[key] = val
    return values


def _write_default_config(cfg_path: str):
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write("""[slowfetch]
# 徽标图片路径（相对或绝对）
logo_image = logos/logo.png
# 徽标显示宽度（字符数）
logo_width = 40
# 低内存模式（限制最大高度）
low_memory = false
""")


def _repair_legacy_config(cfg_path: str):
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        _write_default_config(cfg_path)
        return "created default config"

    parsed = _legacy_section_from_text(text)
    if not parsed:
        _write_default_config(cfg_path)
        return "created default config"

    defaults = {
        "logo_image": "logos/logo.png",
        "logo_width": "40",
        "low_memory": "false",
    }
    for key, value in defaults.items():
        parsed.setdefault(key, value)

    try:
        logo_width = int(str(parsed.get("logo_width", defaults["logo_width"])))
    except (TypeError, ValueError):
        logo_width = 40

    low_memory = _normalize_bool(parsed.get("low_memory", defaults["low_memory"]), False)

    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write("[slowfetch]\n")
        f.write(f"logo_image = {parsed.get('logo_image', defaults['logo_image'])}\n")
        f.write(f"logo_width = {logo_width}\n")
        f.write(f"low_memory = {'true' if low_memory else 'false'}\n")
    return "repaired legacy config"


def ensure_resources():
    """确保 logos 文件夹和配置文件存在"""
    os.makedirs(os.path.join(BASE_DIR, LOGO_DIR), exist_ok=True)
    readme = os.path.join(BASE_DIR, LOGO_DIR, "README.txt")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write("把图片放到这里即可作为徽标。\n支持格式：png/jpg/jpeg/bmp/gif/webp\n")
    cfg_path = os.path.join(BASE_DIR, CONFIG_NAME)
    if not os.path.exists(cfg_path):
        _write_default_config(cfg_path)
        return

    try:
        cfg = configparser.ConfigParser()
        cfg.read(cfg_path, encoding="utf-8")
        if "slowfetch" not in cfg:
            raise configparser.Error("Missing [slowfetch] section")
    except (configparser.Error, OSError):
        _repair_legacy_config(cfg_path)


def load_config():
    cfg_path = os.path.join(BASE_DIR, CONFIG_NAME)
    cfg = configparser.ConfigParser()
    status = "loaded"
    try:
        cfg.read(cfg_path, encoding="utf-8")
    except (configparser.Error, OSError):
        _write_default_config(cfg_path)
        cfg.read(cfg_path, encoding="utf-8")
        status = "created default config"

    if "slowfetch" not in cfg:
        status = _repair_legacy_config(cfg_path)
        cfg.read(cfg_path, encoding="utf-8")

    section = cfg["slowfetch"]
    defaults = {
        "logo_image": "logos/logo.png",
        "logo_width": "40",
        "low_memory": "false",
    }
    for key, value in defaults.items():
        if key not in section or section[key] is None or str(section[key]).strip() == "":
            section[key] = value

    try:
        logo_width = int(str(section.get("logo_width", defaults["logo_width"])).strip())
    except (TypeError, ValueError):
        logo_width = 40
    section["logo_width"] = str(logo_width)

    try:
        low_memory = _normalize_bool(section.get("low_memory", defaults["low_memory"]), False)
    except Exception:
        low_memory = False
    section["low_memory"] = "true" if low_memory else "false"

    config = {
        "logo_image": str(section.get("logo_image", defaults["logo_image"])).strip() or defaults["logo_image"],
        "logo_width": logo_width,
        "low_memory": low_memory,
    }
    return config, status


# ----------------------------------------------------------------------------
# 图片渲染（带缓存）
# ----------------------------------------------------------------------------
def _iter_images(folder):
    if not os.path.isdir(folder):
        return []
    out = []
    for f in sorted(os.listdir(folder)):
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
            out.append(os.path.join(folder, f))
    return out


def resolve_image(cfg):
    spec = cfg.get("logo_image", "").strip()
    if spec:
        p = os.path.normpath(os.path.join(BASE_DIR, spec))
        if os.path.isfile(p):
            return p
    imgs = _iter_images(os.path.join(BASE_DIR, LOGO_DIR))
    return imgs[0] if imgs else None


def compute_render_rows(src_w, src_h, cols, low_memory):
    if src_w <= 0 or src_h <= 0:
        return max(1, cols)
    rows = max(1, round(cols * src_h / src_w * 2))
    max_rows = 96 if low_memory else 200
    return min(rows, max_rows)


def render_image_lines(path, width, low_memory=False):
    """渲染图片为 ANSI 半块字符，带文件缓存"""
    try:
        stat = os.stat(path)
        key = f"{path}_{width}_{low_memory}_{stat.st_mtime}_{stat.st_size}"
        key_hash = hashlib.md5(key.encode()).hexdigest()
        cache_file = os.path.join(CACHE_DIR, f"logo_{key_hash}.pkl")
        if os.path.exists(cache_file):
            with open(cache_file, "rb") as f:
                return pickle.load(f)
    except Exception:
        pass

    cols = max(2, int(width))
    try:
        from PIL import Image
        with Image.open(path) as im:
            src_w, src_h = im.size
            rows = compute_render_rows(src_w, src_h, cols, low_memory)
            im = im.convert("RGB")
            im = im.resize((cols, rows), Image.LANCZOS)
            px = im.load()
            lines = []
            for y in range(0, rows, 2):
                buf = []
                for x in range(cols):
                    top = px[x, y]
                    bot = px[x, y + 1] if y + 1 < rows else top
                    buf.append(
                        f"\x1b[38;2;{top[0]};{top[1]};{top[2]}m"
                        f"\x1b[48;2;{bot[0]};{bot[1]};{bot[2]}m▀"
                    )
                buf.append(ANSI.RESET)
                lines.append("".join(buf))
            result = (lines, cols)
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cache_file, "wb") as f:
                pickle.dump(result, f)
            return result
    except Exception as e:
        logging.debug(f"PIL 渲染失败: {e}")
        return _render_image_fallback(path, cols, low_memory)


def _render_image_fallback(path, cols, low_memory):
    """PowerShell 后备渲染：当前版本默认降级为不显示图标，并给出明确提示"""
    logging.warning("Pillow 未安装或图片无法解析，无法渲染徽标；请安装 Pillow 或使用 --no-color")
    return [], 0


# ----------------------------------------------------------------------------
# 系统信息获取模块（基于 psutil + wmi）
# ----------------------------------------------------------------------------
# 使用 lru_cache 确保每个 mod_* 函数在单次运行中只执行一次
@lru_cache(maxsize=None)
def mod_os():
    return f"Microsoft Windows {platform.version()}"


@lru_cache(maxsize=None)
def mod_host():
    try:
        import wmi
        c = wmi.WMI()
        cs = c.Win32_ComputerSystem()[0]
        manu = cs.Manufacturer or ""
        model = cs.Model or ""
        if manu and manu.lower() not in model.lower():
            return f"{manu} {model}"
        return model or platform.node()
    except Exception as e:
        logging.debug(f"wmi host 失败: {e}")
        return platform.node()


@lru_cache(maxsize=None)
def mod_kernel():
    return platform.version()


@lru_cache(maxsize=None)
def mod_uptime():
    try:
        import psutil
        secs = int(psutil.boot_time())
        now = int(datetime.now().timestamp())
        uptime = now - secs
        d, rem = divmod(uptime, 86400)
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        parts = []
        if d:
            parts.append(f"{d}d")
        if h:
            parts.append(f"{h}h")
        if m:
            parts.append(f"{m}m")
        if s:
            parts.append(f"{s}s")
        return " ".join(parts) or "0s"
    except Exception as e:
        logging.debug(f"uptime 失败: {e}")
        return ""


@lru_cache(maxsize=None)
def mod_packages():
    # 简单检测包管理器
    found = []
    for p in ("choco", "scoop", "winget"):
        try:
            subprocess.run([p, "--version"], capture_output=True, timeout=3, check=False)
            found.append(p)
        except:
            continue
    if not found:
        return "0 (none)"
    return f"{len(found)} ({', '.join(found)})"


@lru_cache(maxsize=None)
def mod_shell():
    shell = os.environ.get("ComSpec") or "cmd"
    base = os.path.basename(shell.replace("\\", "/")).lower()
    mapping = {
        "powershell.exe": "PowerShell",
        "pwsh.exe": "PowerShell (pwsh)",
        "cmd.exe": "cmd",
    }
    return mapping.get(base, base)


@lru_cache(maxsize=None)
def mod_resolution():
    try:
        user32 = ctypes.windll.user32
        return f"{user32.GetSystemMetrics(0)}x{user32.GetSystemMetrics(1)}"
    except:
        return ""


@lru_cache(maxsize=None)
def mod_de():
    return "Windows Explorer"


@lru_cache(maxsize=None)
def mod_wm():
    return "DWM"


@lru_cache(maxsize=None)
def mod_wm_theme():
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as k:
            val = winreg.QueryValueEx(k, "AppsUseLightTheme")[0]
            return "Dark" if val == 0 else "Light"
    except:
        return ""


@lru_cache(maxsize=None)
def mod_icons():
    return "Windows"


@lru_cache(maxsize=None)
def mod_terminal():
    return (
        os.environ.get("TERM_PROGRAM")
        or (os.environ.get("WT_SESSION") and "Windows Terminal")
        or "ConHost"
    )


@lru_cache(maxsize=None)
def mod_cpu():
    try:
        import psutil
        freq = psutil.cpu_freq()
        freq_str = f" @ {freq.current:.0f}MHz" if freq else ""
        return f"{platform.processor()} ({psutil.cpu_count(logical=False)} cores){freq_str}"
    except:
        return platform.processor() or "Unknown CPU"


@lru_cache(maxsize=None)
def mod_gpu():
    try:
        import wmi
        c = wmi.WMI()
        gpus = c.Win32_VideoController()
        names = [g.Name for g in gpus if g.Name]
        if names:
            return " / ".join(names)
    except Exception as e:
        logging.debug(f"wmi gpu 失败: {e}")
        # 降级：读取注册表
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}",
            ) as k:
                # 遍历子键找 DriverDesc
                for i in range(winreg.QueryInfoKey(k)[0]):
                    sub = winreg.EnumKey(k, i)
                    with winreg.OpenKey(k, sub) as sk:
                        try:
                            desc = winreg.QueryValueEx(sk, "DriverDesc")[0]
                            if desc:
                                return desc
                        except:
                            pass
        except:
            pass
    return ""


@lru_cache(maxsize=None)
def mod_memory():
    try:
        import psutil
        mem = psutil.virtual_memory()
        return f"{mem.used / 1024**3:.1f} GiB / {mem.total / 1024**3:.1f} GiB"
    except:
        return ""


@lru_cache(maxsize=None)
def mod_swap():
    try:
        import psutil
        swap = psutil.swap_memory()
        if swap.total == 0:
            return ""
        return f"{swap.used / 1024**3:.1f} GiB / {swap.total / 1024**3:.1f} GiB"
    except:
        return ""


@lru_cache(maxsize=None)
def mod_disk():
    try:
        import psutil
        usage = psutil.disk_usage(os.path.abspath(os.sep))
        return f"{usage.used / 1024**3:.1f} GiB / {usage.total / 1024**3:.1f} GiB"
    except:
        return ""


@lru_cache(maxsize=None)
def mod_battery():
    try:
        import psutil
        batt = psutil.sensors_battery()
        if batt is None:
            return ""
        pct = int(batt.percent)
        status = "Charging" if batt.power_plugged else "Discharging"
        if batt.power_plugged and pct == 100:
            status = "Full"
        return f"{pct}% ({status})"
    except:
        return ""


@lru_cache(maxsize=None)
def mod_locale():
    try:
        return locale.getdefaultlocale()[0] or "unknown"
    except:
        return "unknown"


@lru_cache(maxsize=None)
def mod_system_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@lru_cache(maxsize=None)
def mod_boot():
    try:
        import psutil
        return datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    except:
        return ""


# ----------------------------------------------------------------------------
# 渲染输出
# ----------------------------------------------------------------------------
def render(logo_lines, logo_width, info_lines, color_on):
    gap = 6
    max_len = max(len(logo_lines), len(info_lines))
    out = []
    for i in range(max_len):
        if i < len(logo_lines):
            col1 = logo_lines[i]
        elif logo_width:
            col1 = " " * logo_width
        else:
            col1 = ""

        info = ""
        if i < len(info_lines):
            key, val = info_lines[i]
            if color_on:
                info = (
                    ANSI.wrap(key + ":", "1;97")
                    + ANSI.wrap(" " + val, "36")
                )
            else:
                info = f"{key}: {val}"
        out.append(col1 + " " * gap + info)
    return "\n".join(row.rstrip() for row in out)


# ----------------------------------------------------------------------------
# 命令行入口
# ----------------------------------------------------------------------------
def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--help", "-h", action="store_true")
    parser.add_argument("--logo", default=None)
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--structure", default=None)
    parser.add_argument("--low-memory", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--color", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args, _ = parser.parse_known_args(argv)

    if args.help:
        print(__doc__)
        return 0

    # 日志
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.ERROR,
        format="[%(levelname)s] %(message)s",
    )

    color_on = args.color or _enable_vt(args.no_color)
    ensure_resources()
    cfg, config_status = load_config()
    width = args.width or cfg.get("logo_width", 40)
    low_memory = args.low_memory or cfg.get("low_memory", False)

    print(
        f"[slowfetch] config: {config_status} | logo_image={cfg.get('logo_image', 'n/a')} | logo_width={width} | low_memory={str(low_memory).lower()}",
        file=sys.stderr,
    )

    # 图片徽标
    logo_lines, logo_width = [], 0
    if color_on:
        img = args.logo or resolve_image(cfg)
        if img:
            try:
                logo_lines, logo_width = render_image_lines(
                    img, width, low_memory=low_memory
                )
            except Exception as e:
                logging.debug(f"徽标渲染失败: {e}")
                print(
                    f"[slowfetch] image render failed for '{img}'; install Pillow or use --no-color",
                    file=sys.stderr,
                )
                logo_lines, logo_width = [], 0
            if not logo_lines:
                print(
                    f"[slowfetch] no logo rendered for '{img}' (Pillow missing or image invalid); continuing without logo",
                    file=sys.stderr,
                )

    # 信息行
    info_lines = []
    if args.structure:
        for token in args.structure.split(","):
            token = token.strip()
            if not token:
                info_lines.append(("", ""))
                continue
            label, name = (token.split(":", 1) if ":" in token else (token, token))
            fn = globals().get("mod_" + name.strip().lower())
            if fn is None:
                info_lines.append((label.strip(), f"(未知模块 {name})"))
                continue
            try:
                info_lines.append((label.strip(), fn()))
            except Exception as e:
                logging.debug(f"模块 {name} 失败: {e}")
                info_lines.append((label.strip(), f"! {e}"))
    else:
        for label, name in DEFAULT_STRUCTURE:
            fn = globals()["mod_" + name]
            try:
                val = fn()
            except Exception as e:
                logging.debug(f"模块 {name} 失败: {e}")
                val = f"! {e}"
            if val:  # 非空才显示
                info_lines.append((label, val))

    print(render(logo_lines, logo_width, info_lines, color_on))
    return 0


if __name__ == "__main__":
    sys.exit(main())