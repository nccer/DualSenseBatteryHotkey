# -*- coding: utf-8 -*-
"""DualSense 电量 —— 安装程序"""
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

APP_NAME = "DualSenseBatteryHotkey"
APP_DISPLAY = "DualSense电量"
MAIN_EXE = "DualSenseBatteryHotkey.exe"
UNINSTALL_EXE = "Uninstall.exe"


def resource_path(name):
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def default_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def _create_shortcut(lnk_path, target, workdir, icon=None):
    ps = ("$ws = New-Object -ComObject WScript.Shell; "
          "$s = $ws.CreateShortcut('%s'); "
          "$s.TargetPath = '%s'; "
          "$s.WorkingDirectory = '%s';" % (lnk_path, target, workdir))
    if icon:
        ps += " $s.IconLocation = '%s';" % icon
    ps += " $s.Save()"
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True)


def do_install(target_dir):
    target_dir = os.path.abspath(target_dir.strip().rstrip("\\/"))
    if not target_dir:
        raise RuntimeError("请选择安装目录")
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError as e:
        raise RuntimeError("无法创建目录：%s" % e)

    main_dst = os.path.join(target_dir, MAIN_EXE)
    un_dst = os.path.join(target_dir, UNINSTALL_EXE)
    shutil.copy2(resource_path(MAIN_EXE), main_dst)
    shutil.copy2(resource_path(UNINSTALL_EXE), un_dst)

    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    _create_shortcut(os.path.join(desktop, APP_DISPLAY + ".lnk"),
                     main_dst, target_dir, main_dst)
    startmenu = os.path.join(os.environ["APPDATA"],
                             "Microsoft", "Windows", "Start Menu", "Programs")
    _create_shortcut(os.path.join(startmenu, APP_DISPLAY + ".lnk"),
                     main_dst, target_dir, main_dst)

    import winreg
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
                           r"\\" + APP_NAME)
    winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_DISPLAY)
    winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, '"%s"' % un_dst)
    winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, target_dir)
    winreg.CloseKey(key)
    return main_dst


def main():
    root = tk.Tk()
    root.title("安装 " + APP_DISPLAY)
    root.geometry("560x210")
    root.resizable(False, False)
    root.configure(bg="#1e1e2e")
    try:
        root.iconbitmap(default=resource_path("icon.ico"))
    except Exception:
        pass

    tk.Label(root, text=APP_DISPLAY + " 安装程序", bg="#1e1e2e", fg="#eef0f6",
             font=("Microsoft YaHei UI", 14, "bold")).pack(pady=(16, 4))
    tk.Label(root, text="选择安装目录：", bg="#1e1e2e", fg="#8a90a0",
             font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=20)

    dir_var = tk.StringVar(value=default_dir())
    row = tk.Frame(root, bg="#1e1e2e")
    row.pack(padx=20, pady=6, fill="x")
    entry = tk.Entry(row, textvariable=dir_var, width=46)
    entry.pack(side="left", fill="x", expand=True, ipady=3)

    def browse():
        d = filedialog.askdirectory(initialdir=dir_var.get())
        if d:
            dir_var.set(os.path.normpath(d))

    tk.Button(row, text="浏览…", command=browse, bg="#3b82f6", fg="#ffffff",
              activebackground="#2563eb", activeforeground="#ffffff",
              relief="flat", padx=10).pack(side="left", padx=(8, 0))

    status = tk.StringVar(value="")
    tk.Label(root, textvariable=status, bg="#1e1e2e", fg="#ff9500",
             font=("Microsoft YaHei UI", 9)).pack(pady=4)

    def install():
        try:
            do_install(dir_var.get())
            messagebox.showinfo("完成", "安装成功！")
            root.destroy()
        except Exception as e:
            messagebox.showerror("安装失败", str(e))

    btns = tk.Frame(root, bg="#1e1e2e")
    btns.pack(pady=12)
    tk.Button(btns, text="安装", command=install, bg="#22c55e", fg="#ffffff",
              activebackground="#16a34a", activeforeground="#ffffff",
              relief="flat", padx=24, pady=6,
              font=("Microsoft YaHei UI", 11, "bold")).pack(side="left", padx=8)
    tk.Button(btns, text="取消", command=root.destroy, bg="#3a3b4a", fg="#eef0f6",
              activebackground="#4a4b5a", activeforeground="#eef0f6",
              relief="flat", padx=24, pady=6,
              font=("Microsoft YaHei UI", 11)).pack(side="left", padx=8)

    root.mainloop()


if __name__ == "__main__":
    main()
