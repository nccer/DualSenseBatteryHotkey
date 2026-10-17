# DualSense 电量（DualSenseBatteryHotkey）

Windows 下的小工具：一键查看 PS5 DualSense / DualSense Edge 手柄的电量，右下角弹出深色圆角卡片。支持有线直连、[DS5Dongle](https://github.com/awalol/DS5Dongle) 无线接收器和蓝牙连接。

## 功能

- **快捷键**（默认 `Ctrl+Shift+B`）弹出电量卡片，可自定义
- **长按手柄 PS 键 1.5 秒** 弹出电量卡片
- **托盘图标** 实时显示电量百分比（圆形，颜色随状态变化）
- 电量卡片：深色圆角、深蓝电量条、百分比、从屏幕右侧滑入、自动渐隐
- **颜色规则**：正常=蓝、充电=绿、10%~20%=橙、<10%=红
- **设置界面**：改快捷键、开机自启动
- 支持标准 DualSense 与 DualSense Edge（名称分别显示 DS5 / DSE）

## 下载

到 [Releases](../../releases) 页面下载最新版：

- `DualSense电量.exe` —— 安装程序（可选安装目录，自动创建桌面/开始菜单快捷方式）
- `DualSense电量便携版.exe` —— 绿色便携版（免安装，解压即用）

## 安装

1. 运行 `Setup.exe`，选择安装目录，点「安装」
2. 卸载：运行安装目录下的 `Uninstall.exe`，或在「设置 → 应用」里卸载

## 使用

- 手柄用 USB 线连接，或通过 DS5Dongle / 蓝牙无线连接
- 按快捷键 / 长按 PS 键 → 右下角弹出电量卡片
- 托盘图标右键：显示电量 / 设置 / 退出

## 设置

托盘图标右键 →「设置」：

- **修改快捷键**：点按钮后直接按新组合键（支持 `Ctrl/Shift/Alt/Win + 字母/数字/F键`），点「保存」
- **开机自启动**：勾选后写入注册表 `HKCU\...\Run`

## 关于电量精度

DualSense 手柄通过 HID 上报的电量只有 0~10 共 11 档，因此电量只能按 **10% 步进**显示（0%、10%、…、100%），这是手柄硬件限制。

## 从源码构建

```powershell
pip install hidapi keyboard pystray Pillow pyinstaller
pyinstaller --onefile --windowed --name DualSenseBatteryHotkey --icon icon.ico main.py
pyinstaller --onefile --windowed --name Uninstall --icon icon.ico uninstaller.py
pyinstaller --onefile --windowed --name Setup --icon icon.ico `
  --add-data "dist/DualSenseBatteryHotkey.exe;." `
  --add-data "dist/Uninstall.exe;." installer.py
```

## 依赖

- Python 3.10+
- [hidapi](https://pypi.org/project/hidapi/) —— 读取手柄 HID 数据
- [keyboard](https://pypi.org/project/keyboard/) —— 全局快捷键
- [pystray](https://pypi.org/project/pystray/) —— 托盘图标
- [Pillow](https://pypi.org/project/Pillow/) —— 绘制电量卡片 / 托盘图标

## License

[MIT](LICENSE)

本项目与 Sony Interactive Entertainment 无关。
