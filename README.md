# PixCake → Lightroom XMP 转换器

[English](README_EN.md) | [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-green.svg)](https://www.python.org/) [![PyQt5](https://img.shields.io/badge/GUI-PyQt5-orange.svg)](https://pypi.org/project/PyQt5/)

将**像素蛋糕 (PixCake)** 的照片编辑数据转换为 Adobe Lightroom 可读取的 **XMP 附属文件**。

## 功能

- 🔍 自动扫描 PixCake 数据库，列出所有用户及项目
- 🖼️ 项目卡片网格：缩略图、名称、修改日期，点击选中
- 🎨 39 个 PixCake 内部参数 → Lightroom `crs:` 字段映射（含校准系数）
- 🌈 HSL 八色调节、色彩分级参数映射
- 📷 RAW 文件 EXIF 元数据回退读取（PIL / exifread）
- ⚡ 批量转换，多线程生成 XMP
- 🪟 现代无边框窗口 UI + Tailwind CSS 风格 QSS + 动态列数布局

## 环境要求

| 包 | 版本 | 用途 |
|---------|---------|---------|
| Python | ≥ 3.8 | 运行环境 |
| PyQt5 | ≥ 5.15 | GUI 框架 |
| Pillow | ≥ 9.0（可选） | RAW EXIF 回退 |
| exifread | ≥ 3.0（可选） | RAW EXIF 回退 |

```bash
pip install -r requirements.txt
# 或通过 Anaconda：
conda install pyqt
```

## 快速启动

```bash
python pixcake_xmp_converter.py
```

Windows 下可直接双击 `run.bat`。

## 用法

| 步骤 | 操作 |
|------|------|
| 1 | 启动后自动加载 PixCake 数据库（`%APPDATA%\PixCake-qt_pro\db\`） |
| 2 | 顶部下拉框切换用户，下方网格展示该用户的所有项目 |
| 3 | 点击卡片选中项目（蓝色高亮），支持全选/取消 |
| 4 | 底部设置 XMP 输出文件夹 |
| 5 | 点击「转换为 XMP」批量生成 |

## 参数映射

### 基础调节

| PixCake pfID | Lightroom 字段 | 缩放系数 |
|-------------|---------------|:-----:|
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
| 3006 | Sharpness | ×82.0（绝对值） |
| 91005 | LuminanceSmoothing | ×280.0 |
| 91003 | ColorNoiseReduction | ×(-47.0) |
| 201 | PostCropVignetteAmount | ×100.0 |
| 90118 | VignetteAmount | ×100.0 |

### HSL 调节

八色（红/橙/黄/绿/青/蓝/紫/洋红）× 三通道（色相/饱和度/明度）

### 色彩分级

阴影/高光色相、饱和度及平衡

## 生成的 XMP 内容

| 命名空间 | 内容 |
|-----------|---------|
| `crs:` | 编辑参数（曝光、对比度、HSL 等） |
| `exif:` / `tiff:` | 相机、镜头、曝光参数 |
| `aux:` | 序列号、镜头信息 |
| `xmpMM:` | 文档 ID、历史记录 |
| `photoshop:` | 原始文件扩展名 |
| `dc:` | MIME 格式 |

## PixCake 路径约定

```
%APPDATA%\PixCake-qt_pro\
├── db\                          ← SQLite 数据库
│   ├── base.db                  ← 用户列表
│   └── user_{uid}\
│       └── project_{pid}\       ← 项目数据库（注意 project_ 前缀）
│           └── project.db
└── project\                     ← 文件缓存
    └── user_{uid}\
        └── {pid}\               ← 缓存目录（无 project_ 前缀）
            ├── albumnThumbnail\  ← 项目缩略图
            └── thumbnail_cache\ ← 编辑参数缓存
```

## 构建

使用 PyInstaller 构建独立 `.exe`：

```bash
# 仅限 Windows
build.bat
```

构建流程：
1. 创建 Python 虚拟环境
2. 安装依赖 + PyInstaller
3. 转换 `dist/icon.png` → `dist/icon.ico`
4. 输出 `dist/PixCakeXmpConverter.exe`

> **注意：** 构建前需要自行准备 `dist/icon.png` 图标文件。

## 已知限制

- 仅支持 PixCake 导出的参数子集（16 个基础 + 24 HSL + 5 色彩分级）
- 部分 LR 参数（曲线、校准等）当前未映射
- 白平衡色温/色调需从 `extendInfo` 缓存读取

## 许可

[MIT](LICENSE)
