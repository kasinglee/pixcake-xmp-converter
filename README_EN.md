# PixCake → Lightroom XMP Converter

[中文](README.md) | [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-green.svg)](https://www.python.org/) [![PyQt5](https://img.shields.io/badge/GUI-PyQt5-orange.svg)](https://pypi.org/project/PyQt5/)

Convert **PixCake (像素蛋糕)** photo editing data into Adobe Lightroom-compatible **XMP sidecar files**.

## Features

- 🔍 Auto-scan PixCake database — list all users and projects
- 🖼️ Project card grid with thumbnails, names, and modification dates — click to select
- 🎨 39 PixCake internal parameters → Lightroom `crs:` field mapping (with calibration coefficients)
- 🌈 8-color HSL adjustments and color grading parameter mapping
- 📷 RAW file EXIF metadata fallback (PIL / exifread)
- ⚡ Batch conversion with multi-threaded XMP generation
- 🪟 Modern borderless window UI with Tailwind CSS-inspired QSS + responsive column layout

## Requirements

| Package | Version | Purpose |
|---------|---------|---------|
| Python | ≥ 3.8 | Runtime |
| PyQt5 | ≥ 5.15 | GUI framework |
| Pillow | ≥ 9.0 (optional) | RAW EXIF fallback |
| exifread | ≥ 3.0 (optional) | RAW EXIF fallback |

```bash
pip install -r requirements.txt
# or via Anaconda:
conda install pyqt
```

## Quick Start

```bash
python pixcake_xmp_converter.py
```

On Windows, double-click `run.bat`.

## Usage

| Step | Action |
|------|--------|
| 1 | Launch — auto-loads PixCake database from `%APPDATA%\PixCake-qt_pro\db\` |
| 2 | Use the top dropdown to switch users; the grid shows all projects for that user |
| 3 | Click a card to select a project (blue highlight); Select All / Deselect All supported |
| 4 | Set the XMP output folder at the bottom |
| 5 | Click **转换为 XMP** to batch-generate XMP sidecars |

## Parameter Mapping

### Basic Adjustments

| PixCake pfID | Lightroom Field | Scale |
|-------------|-----------------|:-----:|
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

### HSL

Eight colors (Red / Orange / Yellow / Green / Aqua / Blue / Purple / Magenta) × three channels (Hue / Saturation / Luminance).

### Color Grading

Shadow & highlight hue, saturation, and balance.

## Generated XMP Content

| Namespace | Content |
|-----------|---------|
| `crs:` | Edit parameters (exposure, contrast, HSL, etc.) |
| `exif:` / `tiff:` | Camera, lens, exposure metadata |
| `aux:` | Serial numbers, lens info |
| `xmpMM:` | Document ID, history |
| `photoshop:` | Original file extension |
| `dc:` | MIME format |

## PixCake Directory Structure

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

## Build

To build a standalone `.exe` with PyInstaller:

```bash
# Windows only
build.bat
```

The build process:
1. Creates a Python virtual environment
2. Installs dependencies + PyInstaller
3. Converts `dist/icon.png` → `dist/icon.ico`
4. Outputs `dist/PixCakeXmpConverter.exe`

> **Note:** You need to provide your own `dist/icon.png` before building.

## Known Limitations

- Only a subset of PixCake exported parameters is supported (16 basic + 24 HSL + 5 color grading)
- Some Lightroom parameters (tone curve, calibration, etc.) are not currently mapped
- White balance color temperature/tint must be read from `extendInfo` cache

## License

[MIT](LICENSE)
