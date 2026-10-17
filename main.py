# -*- coding: utf-8 -*-
"""DualSense 电量热键：快捷键或长按 PS 键 1.5 秒，右下角弹自定义电量卡片。"""
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
import winreg
import zlib

import hid
import keyboard
import pystray
from PIL import Image, ImageDraw, ImageFont, ImageTk

import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

VID = 0x054C
PIDS = (0x0CE6, 0x0DF2)          # DualSense / DualSense Edge
PS_HOLD_SECONDS = 1.5

# 蓝牙模式：需先发输出报告启用完整输入报告 0x31（电量在 byte[54]，带 CRC32）
BT_IN_REPORT = 0x31
BT_OUT_CRC_SEED = 0xA2
BT_BATT_OFFSET = 54
BT_PS_OFFSET = 11
DEFAULT_HOTKEY = "ctrl+shift+b"
THROTTLE_SECONDS = 1.5

MAGIC = "#ffffff"                # 透明色（用于圆角，白色以贴合浅色背景）
CARD = "#14141e"                 # 卡片深色底
TRACK = "#2c2d3d"                # 电量条底色
SUB = "#8a90a0"                  # 名称/次要文字
FG = "#eef0f6"                   # 主要文字

BORDER_BLUE = "#3b82f6"
BORDER_GREEN = "#22c55e"
BORDER_ORANGE = "#f97316"
BORDER_RED = "#ef4444"
BORDER_GREY = "#6b7280"


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_app_dir(), "config.json")


def _load_hotkey():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("hotkey", DEFAULT_HOTKEY)
    except Exception:
        return DEFAULT_HOTKEY


def _save_hotkey(h):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"hotkey": h}, f, ensure_ascii=False)
    except Exception:
        pass


APP_NAME = "DualSenseBatteryHotkey"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command():
    if getattr(sys, "frozen", False):
        return '"%s"' % sys.executable
    script = os.path.abspath(__file__)
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(pyw):
        return '"%s" "%s"' % (pyw, script)
    return '"%s" "%s"' % (sys.executable, script)


def _is_autostart():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except Exception:
        return False


def _set_autostart(enable):
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
    try:
        if enable:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def _capture_hotkey(callback):
    """用键盘库全局钩子捕获一次快捷键；单独按修饰键会被忽略，Esc 取消。"""
    holder = []

    def on_event(e):
        if e.event_type != "down":
            return
        name = (e.name or "").lower()
        if name in ("shift", "right shift", "ctrl", "right ctrl", "alt",
                    "right alt", "alt gr", "windows", "right windows"):
            return
        mods = []
        if keyboard.is_pressed("shift"):
            mods.append("shift")
        if keyboard.is_pressed("ctrl"):
            mods.append("ctrl")
        if keyboard.is_pressed("alt"):
            mods.append("alt")
        if keyboard.is_pressed("windows"):
            mods.append("windows")
        if name == "esc" and not mods:
            keyboard.unhook(holder[0])
            callback(None)
            return
        combo = "+".join(mods + [name])
        keyboard.unhook(holder[0])
        callback(combo)

    holder.append(keyboard.hook(on_event))


def _rgb(hexstr):
    hexstr = hexstr.lstrip("#")
    return tuple(int(hexstr[i:i + 2], 16) for i in (0, 2, 4))


def _font(size, bold=False):
    paths = ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc"] if bold else \
            ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc"]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


# ---- 分层窗口：逐像素透明（圆角边缘带 alpha，任何背景都干净）----
from ctypes import wintypes

_ULW_ALPHA = 0x00000002
_AC_SRC_OVER = 0x00
_AC_SRC_ALPHA = 0x01


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


def _layered_hwnd(win):
    user32 = ctypes.windll.user32
    hwnd = user32.GetParent(win.winfo_id())
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_TOOLWINDOW = 0x00000080
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                         ex | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    return hwnd


def _premultiply_bgra(rgba):
    raw = rgba.convert("RGBA").tobytes("raw", "RGBA")
    out = bytearray(len(raw))
    for i in range(0, len(raw), 4):
        r = raw[i]
        g = raw[i + 1]
        b = raw[i + 2]
        a = raw[i + 3]
        out[i] = (b * a) // 255
        out[i + 1] = (g * a) // 255
        out[i + 2] = (r * a) // 255
        out[i + 3] = a
    return bytes(out)


def _draw_layered(win, bgra, w, h, x, y, alpha=255):
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hwnd = _layered_hwnd(win)

    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0

    pbits = ctypes.c_void_p()
    hbm = gdi32.CreateDIBSection(None, ctypes.byref(bmi), 0,
                                 ctypes.byref(pbits), None, 0)
    if not hbm:
        return
    ctypes.memmove(pbits, bgra, len(bgra))

    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    old = gdi32.SelectObject(hdc_mem, hbm)

    size = wintypes.SIZE(w, h)
    pt_src = wintypes.POINT(0, 0)
    pt_dst = wintypes.POINT(x, y)
    blend = _BLENDFUNCTION(_AC_SRC_OVER, 0, alpha, _AC_SRC_ALPHA)

    user32.UpdateLayeredWindow(hwnd, hdc_screen, ctypes.byref(pt_dst),
                               ctypes.byref(size), hdc_mem, ctypes.byref(pt_src),
                               0, ctypes.byref(blend), _ULW_ALPHA)

    gdi32.SelectObject(hdc_mem, old)
    gdi32.DeleteObject(hbm)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def _work_area():
    rect = _RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right, rect.bottom


_lock = threading.Lock()
_state = {
    "connected": False,
    "level": None,
    "full": False,
    "charging": False,
    "name": "DS5",
}
_ui_queue = queue.Queue()

_icon = None
_last_show = 0.0
_hotkey = DEFAULT_HOTKEY
_hotkey_handler = None


def _color_for(level, full, charging):
    if charging:
        return BORDER_GREEN
    if level <= 0:
        return BORDER_RED
    if level <= 2:
        return BORDER_ORANGE
    return BORDER_BLUE


def _display_info():
    with _lock:
        connected = _state["connected"]
        level = _state["level"]
        full = _state["full"]
        charging = _state["charging"]
        name = _state["name"]
    if not connected or level is None:
        return {"name": None, "pct": None, "color": BORDER_GREY}
    pct = 100 if full else min(level, 10) * 10
    return {"name": name, "pct": pct, "color": _color_for(level, full, charging)}


_last_icon = {"pct": None, "color": None}


def _make_tray_image(level, color):
    S = 128
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([1, 1, S - 1, S - 1], fill=_rgb(color))
    if level is not None:
        txt = str(level)
        size = 86 if len(txt) <= 2 else 64
        font = _font(size, bold=True)
        d.text((S // 2, S // 2 + 1), txt, fill=(20, 20, 30, 255), font=font,
               anchor="mm")
    return img


def _update_tray_icon(pct, color):
    global _icon
    with _lock:
        if pct == _last_icon["pct"] and color == _last_icon["color"]:
            return
        _last_icon["pct"] = pct
        _last_icon["color"] = color
    if _icon is not None:
        try:
            _icon.icon = _make_tray_image(pct, color)
        except Exception:
            pass


def _refresh_tray():
    with _lock:
        connected = _state["connected"]
        level = _state["level"]
        full = _state["full"]
        charging = _state["charging"]
    if not connected or level is None:
        _update_tray_icon(None, BORDER_GREY)
    else:
        pct = 100 if full else min(level, 10) * 10
        _update_tray_icon(pct, _color_for(level, full, charging))


def show_battery():
    global _last_show
    now = time.monotonic()
    with _lock:
        if now - _last_show < THROTTLE_SECONDS:
            return
        _last_show = now
    _ui_queue.put(("popup", _display_info()))


def _apply_hotkey(h):
    global _hotkey, _hotkey_handler
    try:
        handler = keyboard.add_hotkey(h, lambda: show_battery())
    except Exception:
        return
    try:
        if _hotkey_handler is not None:
            keyboard.remove_hotkey(_hotkey_handler)
    except Exception:
        pass
    _hotkey_handler = handler
    _hotkey = h


def open_settings():
    _ui_queue.put(("settings",))


def _open_device():
    dev = hid.device()
    for pid in PIDS:
        try:
            dev.open(VID, pid)
            return dev, pid
        except OSError:
            continue
    dev.close()
    return None, None


def _is_bluetooth():
    """通过设备路径里的蓝牙 HID 接口 GUID 判断是否蓝牙连接。"""
    for d in hid.enumerate():
        if d.get("vendor_id") == VID and d.get("product_id") in PIDS:
            p = d.get("path")
            if p is None:
                continue
            if isinstance(p, bytes):
                p = p.decode("utf-8", "ignore")
            return "{00001124" in p
    return False


def _bt_enable_report(seq=0):
    """构造蓝牙输出报告 0x31，启用完整输入报告（电量 + 传感器）。"""
    r = bytearray(78)
    r[0] = BT_IN_REPORT                  # report id 0x31
    r[1] = (seq << 4) & 0xF0             # seq_tag（高 4 位为序号）
    r[2] = 0x10                          # tag（固定魔数）
    r[4] = 0x04                          # valid_flag1：灯条控制使能
    r[41] = 0x02                         # valid_flag2：灯条设置使能
    r[44] = 0x02                         # lightbar_setup：灯灭
    r[49] = 255                          # lightbar_blue
    crc = zlib.crc32(bytes([BT_OUT_CRC_SEED]) + bytes(r[:74])) & 0xFFFFFFFF
    r[74:78] = crc.to_bytes(4, "little")
    return bytes(r)


def hid_reader():
    while True:
        dev, pid = _open_device()
        if dev is None:
            with _lock:
                _state["connected"] = False
                _state["level"] = None
            _refresh_tray()
            time.sleep(2)
            continue

        name = "DSE" if pid == 0x0DF2 else "DS5"
        is_bt = _is_bluetooth()
        rid = BT_IN_REPORT if is_bt else 0x01
        batt_off = BT_BATT_OFFSET if is_bt else 53
        ps_off = BT_PS_OFFSET if is_bt else 10

        with _lock:
            _state["connected"] = True
            _state["name"] = name
        _refresh_tray()

        ps_pressed_at = None
        ps_fired = False
        last_batt = None
        last_enable = 0.0
        try:
            dev.set_nonblocking(False)
            if is_bt:
                try:
                    dev.write(_bt_enable_report())
                except Exception:
                    pass
                last_enable = time.monotonic()
            while True:
                data = dev.read(128, timeout_ms=100)
                if not data:
                    continue
                b = bytes(data)
                now = time.monotonic()
                if b[0] != rid:
                    # 蓝牙完整报告丢失（退回 0x01）时重新启用
                    if is_bt and now - last_enable > 3:
                        try:
                            dev.write(_bt_enable_report())
                        except Exception:
                            pass
                        last_enable = now
                    continue
                # 蓝牙完整报告定期续期，避免自动退回精简报告
                if is_bt and now - last_enable > 30:
                    try:
                        dev.write(_bt_enable_report())
                    except Exception:
                        pass
                    last_enable = now

                batt = b[batt_off]
                if is_bt:
                    cs = (batt >> 4) & 0x0F
                    level = batt & 0x0F
                    full = (cs == 0x2)
                    charging = (cs == 0x1)
                else:
                    level = batt & 0x0F
                    full = bool(batt & 0x20)
                    charging = bool(batt & 0x10)
                with _lock:
                    _state["level"] = level
                    _state["full"] = full
                    _state["charging"] = charging
                if batt != last_batt:
                    last_batt = batt
                    _refresh_tray()

                ps_down = bool(b[ps_off] & 0x01)
                if ps_down:
                    if ps_pressed_at is None:
                        ps_pressed_at = now
                        ps_fired = False
                    elif not ps_fired and (now - ps_pressed_at) >= PS_HOLD_SECONDS:
                        ps_fired = True
                        show_battery()
                else:
                    ps_pressed_at = None
                    ps_fired = False
        except OSError:
            with _lock:
                _state["connected"] = False
                _state["level"] = None
            _refresh_tray()
            try:
                dev.close()
            except Exception:
                pass
            time.sleep(1)


def _render_card(info, W, H):
    S = 4
    border = _rgb(info["color"]) + (255,)
    card = _rgb(CARD) + (255,)
    track = _rgb(TRACK) + (255,)
    sub = _rgb(SUB) + (255,)
    fg = _rgb(FG) + (255,)

    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    R = 32 * S
    d.rounded_rectangle([0, 0, W * S - 1, H * S - 1], radius=R, fill=border)
    inset = 3 * S
    d.rounded_rectangle([inset, inset, W * S - 1 - inset, H * S - 1 - inset],
                        radius=R - inset, fill=card)

    sh = 1 * S
    if info.get("name"):
        name_font = _font(16 * S, bold=True)
        d.text((W * S // 2 + sh, 15 * S + sh), info["name"], fill=(0, 0, 0, 255),
               font=name_font, anchor="mm")
        d.text((W * S // 2, 15 * S), info["name"], fill=sub, font=name_font, anchor="mm")

    pct = info["pct"]
    if pct is None:
        f = _font(13 * S)
        d.text((W * S // 2 + sh, 51 * S + sh), "未检测到手柄", fill=(0, 0, 0, 255),
               font=f, anchor="mm")
        d.text((W * S // 2, 51 * S), "未检测到手柄", fill=fg, font=f, anchor="mm")
    else:
        bx, by, bw, bh = 28 * S, 29 * S, 124 * S, 48 * S
        r = bh // 2
        d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=r, fill=track)
        fw = int(bw * pct / 100)
        if fw > 0:
            d.rounded_rectangle([bx, by, bx + fw, by + bh], radius=r, fill=border)
        f = _font(21 * S, bold=True)
        txt = "%d%%" % pct
        d.text((bx + bw // 2 + sh, by + bh // 2 + sh), txt, fill=(0, 0, 0, 255),
               font=f, anchor="mm")
        d.text((bx + bw // 2, by + bh // 2), txt, fill=fg, font=f, anchor="mm")

    img = img.resize((W, H), Image.LANCZOS)
    return img


def _make_popup(root, info):
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)

    W, H = 180, 102
    win.geometry("%dx%d" % (W, H))
    _layered_hwnd(win)
    win.update_idletasks()
    img = _render_card(info, W, H)
    bgra = _premultiply_bgra(img)
    return win, bgra, W, H


def _make_settings_window(root):
    win = tk.Toplevel(root)
    win.title("设置 · DualSense 电量")
    win.configure(bg="#20212b")
    win.resizable(False, False)
    win.attributes("-topmost", True)

    rec = {"hotkey": _hotkey, "recording": False}

    tk.Label(win, text="键盘快捷键", bg="#20212b", fg="#8a90a0",
             font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=16, pady=(14, 4))

    hotkey_var = tk.StringVar(value=_hotkey)
    hotkey_lbl = tk.Label(win, textvariable=hotkey_var, bg="#2c2d3d", fg="#eef0f6",
                          font=("Microsoft YaHei UI", 13, "bold"),
                          width=26, height=2)
    hotkey_lbl.pack(padx=16, pady=6)

    status_var = tk.StringVar(value="")
    tk.Label(win, textvariable=status_var, bg="#20212b", fg="#8a90a0",
             font=("Microsoft YaHei UI", 9)).pack(padx=16)

    def start_recording():
        rec["recording"] = True
        status_var.set("请按下新的快捷键组合…")
        hotkey_lbl.config(fg="#ff9500")

        def got(h):
            def _apply():
                if h is None:
                    rec["recording"] = False
                    hotkey_lbl.config(fg="#eef0f6")
                    status_var.set("已取消")
                    return
                rec["recording"] = False
                rec["hotkey"] = h
                hotkey_var.set(h)
                hotkey_lbl.config(fg="#eef0f6")
                status_var.set("按「保存」生效")
            root.after(0, _apply)

        threading.Thread(target=lambda: _capture_hotkey(got), daemon=True).start()

    btn_row = tk.Frame(win, bg="#20212b")
    btn_row.pack(pady=(8, 14))
    tk.Button(btn_row, text="修改快捷键", command=start_recording,
              bg="#3b82f6", fg="#ffffff", activebackground="#2563eb",
              activeforeground="#ffffff", relief="flat", padx=12, pady=5,
              font=("Microsoft YaHei UI", 10)).pack(side="left", padx=6)

    def save():
        _save_hotkey(rec["hotkey"])
        _apply_hotkey(rec["hotkey"])
        hotkey_var.set(rec["hotkey"])
        status_var.set("已保存")

    tk.Button(btn_row, text="保存", command=save,
              bg="#22c55e", fg="#ffffff", activebackground="#16a34a",
              activeforeground="#ffffff", relief="flat", padx=12, pady=5,
              font=("Microsoft YaHei UI", 10)).pack(side="left", padx=6)

    auto_var = tk.BooleanVar(value=_is_autostart())

    def toggle_auto():
        _set_autostart(auto_var.get())

    bottom = tk.Frame(win, bg="#20212b")
    bottom.pack(fill="x", padx=16, pady=(4, 12))
    tk.Checkbutton(bottom, text="开机自启动", variable=auto_var, command=toggle_auto,
                   bg="#20212b", fg="#eef0f6", activebackground="#20212b",
                   activeforeground="#eef0f6", selectcolor="#2c2d3d",
                   font=("Microsoft YaHei UI", 10)).pack(side="left")
    tk.Label(bottom, text="小聪制作", bg="#20212b", fg="#4a4b5a",
             font=("Microsoft YaHei UI", 8)).pack(side="right")

    return win


def _ui_thread():
    root = tk.Tk()
    root.withdraw()
    cur = {"win": None, "bgra": None, "W": 0, "H": 0, "x": 0, "y": 0,
           "hide_job": None, "settings": None}

    def fade_out(win, bgra, W, H, x, y, alpha):
        try:
            if not win.winfo_exists():
                return
            if alpha <= 0:
                win.destroy()
                return
            _draw_layered(win, bgra, W, H, x, y, alpha)
            win.after(20, lambda: fade_out(win, bgra, W, H, x, y, alpha - 30))
        except Exception:
            pass

    def hide_current():
        w = cur["win"]
        bgra = cur["bgra"]
        W = cur["W"]
        H = cur["H"]
        x = cur["x"]
        y = cur["y"]
        cur["win"] = None
        cur["bgra"] = None
        cur["hide_job"] = None
        if w is not None:
            fade_out(w, bgra, W, H, x, y, 230)

    def show_popup(info):
        if cur["win"] is not None:
            try:
                cur["win"].destroy()
            except Exception:
                pass
        if cur["hide_job"] is not None:
            try:
                root.after_cancel(cur["hide_job"])
            except Exception:
                pass
        win, bgra, W, H = _make_popup(root, info)
        cur["win"] = win
        cur["bgra"] = bgra
        cur["W"] = W
        cur["H"] = H
        sw = win.winfo_screenwidth()
        wa = _work_area()
        final_x = sw - W - 16
        y = wa[3] - H - 16
        cur["x"] = final_x
        cur["y"] = y
        start_x = sw + 40
        steps = 14

        def slide(i):
            if not win.winfo_exists():
                return
            if i <= steps:
                t = i / steps
                eased = 1 - (1 - t) ** 3
                x = int(start_x + (final_x - start_x) * eased)
                _draw_layered(win, bgra, W, H, x, y, 255)
                win.after(8, lambda: slide(i + 1))
            else:
                cur["hide_job"] = root.after(2600, hide_current)

        slide(0)

    def open_settings_window():
        if cur["settings"] is not None:
            try:
                if cur["settings"].winfo_exists():
                    cur["settings"].lift()
                    return
            except Exception:
                pass
        cur["settings"] = _make_settings_window(root)

    def poll():
        try:
            while True:
                msg = _ui_queue.get_nowait()
                if msg[0] == "popup":
                    show_popup(msg[1])
                elif msg[0] == "settings":
                    open_settings_window()
        except queue.Empty:
            pass
        root.after(20, poll)

    root.after(60, poll)
    root.mainloop()


_SINGLE_INSTANCE_MUTEX = None


def _acquire_single_instance():
    """用命名互斥体保证只运行一个实例，返回 True 表示本进程是唯一实例。"""
    global _SINGLE_INSTANCE_MUTEX
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL,
                                      wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    _SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(
        None, False, "Local\\DualSenseBatteryHotkey")
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main():
    global _icon
    if not _acquire_single_instance():
        ctypes.windll.user32.MessageBoxW(
            None, "DualSense 电量已经在运行，请查看系统托盘图标。",
            "DualSense 电量", 0x40)
        return
    menu = pystray.Menu(
        pystray.MenuItem("显示电量", lambda icon, item: show_battery(), default=True),
        pystray.MenuItem("设置", lambda icon, item: open_settings()),
        pystray.MenuItem("退出", lambda icon, item: icon.stop()),
    )
    _icon = pystray.Icon("dualsense_battery", _make_tray_image(None, BORDER_GREY),
                         "DualSense 电量", menu)

    threading.Thread(target=hid_reader, daemon=True).start()
    threading.Thread(target=_ui_thread, daemon=True).start()
    _apply_hotkey(_load_hotkey())

    _icon.run()


if __name__ == "__main__":
    main()
