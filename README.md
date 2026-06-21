# PixCake → Lightroom XMP Converter<br><small>像素蛋糕 → Lightroom XMP 转换器</small>

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-green.svg)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/GUI-PyQt5-orange.svg)](https://pypi.org/project/PyQt5/)

Convert **PixCake (像素蛋糕)** photo editing data into Adobe Lightroom-compatible **XMP sidecar files**.

将**像素蛋糕 (PixCake)** 的照片编辑数据转换为 Adobe Lightroom 可读取的 **XMP 附属文件**。

---

## Features / 功能

- 🔍 Auto-scan PixCake database — list all users and projects
- 🖼️ Project card grid with thumbnails, names, and modification dates — click to select
- 🎨 39 PixCake internal parameters → Lightroom `crs:` field mapping (with calibration coefficients)
- 🌈 8-color HSL adjustments and color grading parameter mapping
- 📷 RAW file EXIF metadata fallback reading (PIL / exifread)
- ⚡ Batch conversion with multi-threaded XMP generation
- 🪟 Modern borderless window UI with Tailwind CSS-inspired QSS + responsive column layout

---

- 🔍 自动扫描 PixCake 数据库，列出所有用户及项目
- 🖼️ 项目卡片网格：缩略图、名称、修改日期，点击选中
- 🎨 39 个 PixCake 内部参数 → Lightroom `crs:` 字段映射（含校准系数）
- 🌈 HSL 八色调节、色彩分级参数映射
- 📷 RAW 文件 EXIF 元数据回退读取（PIL / exifread）
- ⚡ 批量转换，多线程生成 XMP
- 🪟 现代无边框窗口 UI + Tailwind CSS 风格 QSS + 动态列数布局

---

## Screenshot / 截图

<!-- TODO: add a screenshot here -->
<!-- 在此处添加截图 -->

---

## Requirements / 环境要求

| Package | Version | Purpose |
|---------|---------|---------|
| Python | ≥ 3.8 | Runtime |
| PyQt5 | ≥ 5.15 | GUI framework |
| Pillow | ≥ 9.0 (optional) | RAW EXIF fallback |
| exifread | ≥ 3.0 (optional) | RAW EXIF fallback |

```bash
pip install -r requirements.txt
# or via Anaconda / 或通过 Anaconda：
conda install pyqt
```

---

## Quick Start / 快速启动

```bash
python pixcake_xmp_converter.py
```

On Windows, double-click `run.bat`. / Windows 下可直接双击 `run.bat`。

---

## Usage / 用法

| Step | Action |
|------|--------|
| 1 | Launch — auto-loads PixCake database from `%APPDATA%\PixCake-qt_pro\db\` |
| 2 | Use the top dropdown to switch users; the grid shows all projects for that user |
| 3 | Click a card to select a project (blue highlight); Select All / Deselect All supported |
| 4 | Set the XMP output folder at the bottom |
| 5 | Click **转换为 XMP** to batch-generate XMP sidecars |

---

| 步骤 | 操作 |
|------|------|
| 1 | 启动后自动加载 PixCake 数据库（`%APPDATA%\PixCake-qt_pro\db\`） |
| 2 | 顶部下拉框切换用户，下方网格展示该用户的所有项目 |
| 3 | 点击卡片选中项目（蓝色高亮），支持全选/取消 |
| 4 | 底部设置 XMP 输出文件夹 |
| 5 | 点击「转换为 XMP」批量生成 |

---

## Parameter Mapping / 参数映射

### Basic Adjustments / 基础调节

| PixCake pfID | Lightroom Field | Scale Factor |
|-------------|-----------------|:-----------:|
| 3000 | Exposure2012 | ×5.0 |
| 21001 | Contrast2012 | ×(-25.0) |
| 3003 | Highlights2012 | ×40.0 |
| 44799 | Shadows2012 | ×48.0 |
| 3002 | Whites2012 | ×240.0 |
| 3004 | Blacks2012 | ×370.0 |
| 3020 | Texture | ×150.0 |
| 3021 | Clarity2012 | ×200.0 |
| 3022 | Dehaze | ×200.0 |
| 90152 | Vibrance | ×250.0 |
| 90014 | Saturation | ×200.0 |
| 3006 | Sharpness | ×82.0 (absolute) |
| 91005 | LuminanceSmoothing | ×280.0 |
| 91003 | ColorNoiseReduction | ×(-47.0) |
| 201 | PostCropVignetteAmount | ×100.0 |
| 90118 | VignetteAmount | ×100.0 |

### HSL / HSL 调节

Eight colors (Red / Orange / Yellow / Green / Aqua / Blue / Purple / Magenta) × three channels (Hue / Saturation / Luminance).

八色（红/橙/黄/绿/青/蓝/紫/洋红）× 三通道（色相/饱和度/明度）。

### Color Grading / 色彩分级

Shadow & highlight hue, saturation, and balance.

阴影/高光色相、饱和度及平衡。

---

## Generated XMP Content / 生成的 XMP 内容

| Namespace | Content |
|-----------|---------|
| `crs:` | Edit parameters (exposure, contrast, HSL, etc.) |
| `exif:` / `tiff:` | Camera, lens, exposure metadata |
| `aux:` | Serial numbers, lens info |
| `xmpMM:` | Document ID, history |
| `photoshop:` | Original file extension |
| `dc:` | MIME format |

---

## PixCake Directory Structure / 路径约定

PixCake default data location:

```
%APPDATA%\PixCake-qt_pro\
├── db\                          ← SQLite databases
│   ├── base.db                  ← User list
│   └── user_{uid}\
│       └── project_{pid}\       ← Project DB (note project_ prefix)
│           └── project.db
└── project\                     ← File cache
    └── user_{uid}\
        └── {pid}\               ← Cache dir (no project_ prefix)
            ├── albumnThumbnail\  ← Project thumbnails
            └── thumbnail_cache\ ← Edit parameter cache
```

---

## Build / 构建

To build a standalone `.exe` with PyInstaller:

```bash
# Windows only / 仅限 Windows
build.bat
```

The build process:
1. Creates a Python virtual environment
2. Installs dependencies + PyInstaller
3. Converts `dist/icon.png` → `dist/icon.ico`
4. Builds `dist/PixCakeXmpConverter.exe`

> **Note:** You need to provide your own `dist/icon.png` before building.
> **注意：** 构建前需要自行准备 `dist/icon.png` 图标文件。

---

## Known Limitations / 已知限制

- Only a subset of PixCake exported parameters is supported (16 basic + 24 HSL + 5 color grading)
- Some Lightroom parameters (tone curve, calibration, etc.) are not currently mapped
- White balance color temperature/tint must be read from `extendInfo` cache

---

- 仅支持 PixCake 导出的参数子集（16 个基础 + 24 HSL + 5 色彩分级）
- 部分 LR 参数（曲线、校准等）当前未映射
- 白平衡色温/色调需从 `extendInfo` 缓存读取

---

## License / 许可

[MIT](LICENSE)
