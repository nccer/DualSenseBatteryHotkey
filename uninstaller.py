# -*- coding: utf-8 -*-
"""DualSense 电量 —— 卸载程序"""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

APP_NAME = "DualSenseBatteryHotkey"
APP_DISPLAY = "DualSense电量"


def _kill_app():
    subprocess.run(["taskkill", "/F", "/IM", "DualSenseBatteryHotkey.exe"],
                   capture_output=True)


def _remove_registry():
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
    except OSError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
                         r"\\" + APP_NAME)
    except OSError:
        pass


def _remove_shortcuts():
    paths = [
        os.path.join(os.environ["USERPROFILE"], "Desktop", APP_DISPLAY + ".lnk"),
        os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                     "Start Menu", "Programs", APP_DISPLAY + ".lnk"),
    ]
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


def do_uninstall():
    _kill_app()
    _remove_registry()
    _remove_shortcuts()

    if getattr(sys, "frozen", False):
        install_dir = os.path.dirname(sys.executable)
    else:
        install_dir = os.path.dirname(os.path.abspath(__file__))
    return install_dir


def _schedule_self_delete(install_dir):
    subprocess.Popen('cmd /c ping 127.0.0.1 -n 5 > nul & rmdir /s /q "%s"'
                     % install_dir, shell=True)


def main():
    root = tk.Tk()
    root.title("卸载 " + APP_DISPLAY)
    root.geometry("420x160")
    root.resizable(False, False)
    root.configure(bg="#1e1e2e")
    try:
        if getattr(sys, "frozen", False):
            icon = os.path.join(sys._MEIPASS, "icon.ico")
        else:
            icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        root.iconbitmap(default=icon)
    except Exception:
        pass

    tk.Label(root, text="确定要卸载 " + APP_DISPLAY + " 吗？", bg="#1e1e2e",
             fg="#eef0f6", font=("Microsoft YaHei UI", 13, "bold")
             ).pack(pady=(22, 8))
    tk.Label(root, text="将删除程序文件、快捷方式和自启动项。", bg="#1e1e2e",
             fg="#8a90a0", font=("Microsoft YaHei UI", 10)).pack()

    btns = tk.Frame(root, bg="#1e1e2e")
    btns.pack(pady=18)
    tk.Button(btns, text="卸载", command=lambda: _confirm(root),
              bg="#ef4444", fg="#ffffff", activebackground="#dc2626",
              activeforeground="#ffffff", relief="flat", padx=22, pady=6,
              font=("Microsoft YaHei UI", 11, "bold")).pack(side="left", padx=8)
    tk.Button(btns, text="取消", command=root.destroy,
              bg="#3a3b4a", fg="#eef0f6", activebackground="#4a4b5a",
              activeforeground="#eef0f6", relief="flat", padx=22, pady=6,
              font=("Microsoft YaHei UI", 11)).pack(side="left", padx=8)

    root.mainloop()


def _confirm(root):
    try:
        install_dir = do_uninstall()
        messagebox.showinfo("完成", "卸载完成，正在清理残留文件…")
        _schedule_self_delete(install_dir)
    except Exception as e:
        messagebox.showerror("卸载失败", str(e))
    root.destroy()


if __name__ == "__main__":
    main()
