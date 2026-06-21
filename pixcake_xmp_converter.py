#!/usr/bin/env python3
"""
PixCake XMP Converter — 像素蛋糕编辑数据转 Lightroom XMP
============================================================
PyQt6 UI with modern Tailwind-inspired QSS design.
"""

import os
import sys
import json
import sqlite3
import re
import uuid
import threading
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr
from datetime import datetime, timezone, timedelta
from fractions import Fraction
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QProgressBar,
    QScrollArea, QFrame, QFileDialog, QMessageBox, QSizePolicy,
    QGridLayout, QSpacerItem, QStatusBar, QMenuBar, QAction, QListView,
    QCheckBox,
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QObject, QTimer, QSize, QPoint, QRect,
    QSettings,
)
from PyQt5.QtGui import (
    QPixmap,
    QCursor, QPainter, QColor, QPen,
)

# ============================================================
# Configuration
# ============================================================

def default_pixcake_base():
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, "PixCake-qt_pro")
    return os.path.join(str(Path.home()), "AppData", "Roaming", "PixCake-qt_pro")


PIXCAKE_BASE = default_pixcake_base()
DB_DIR = os.path.join(PIXCAKE_BASE, "db")
PROJECT_DIR = os.path.join(PIXCAKE_BASE, "project")
CST = timezone(timedelta(hours=8))
APP_TITLE = "PixCake → Lightroom XMP"
SETTINGS_ORG = "PixCakeXmpConverter"
SETTINGS_APP = "PixCakeXmpConverter"
SETTINGS_PIXCAKE_BASE_KEY = "pixcake/base_path"

CARD_W = 220
CARD_H = 210
CARD_GAP = 16
THUMB_H = 140
THUMB_PADDING = 10


MESSAGE_BOX_QSS = """
QMessageBox {
    background-color: #1E1E1E;
    color: #F5F5F7;
}
QMessageBox QLabel {
    color: #F5F5F7;
}
QMessageBox QPushButton {
    background-color: #2C2C2E;
    color: #F5F5F7;
    border: 1px solid #3A3A3C;
    border-radius: 6px;
    padding: 6px 14px;
    min-width: 80px;
}
QMessageBox QPushButton:hover {
    background-color: #3A3A3C;
}
"""


def show_message(parent, icon, title, text):
    msgbox = QMessageBox(parent)
    msgbox.setWindowTitle(title)
    msgbox.setIcon(icon)
    msgbox.setText(text)
    msgbox.setStyleSheet(MESSAGE_BOX_QSS)
    return msgbox.exec()


def pixcake_ts_to_datetime(ts_ms):
    if not ts_ms or ts_ms == 0:
        return None
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc)
    except (ValueError, OSError):
        return None


def format_dt(dt, fmt="%Y-%m-%d %H:%M"):
    if dt is None:
        return ""
    return dt.astimezone(CST).strftime(fmt)


# ============================================================
# PixCake → Lightroom Parameter Mapping
# ============================================================

PIXCAKE_TO_XMP_BASIC = {
    # --- Basic Tone ---
    3000:   ("crs", "Exposure2012",         5.0),      # 曝光
    3002:   ("crs", "Contrast2012",         100.0),     # 对比度
    3003:   ("crs", "Highlights2012",       40.0),      # 高光
    3004:   ("crs", "Shadows2012",          200.0),     # 阴影
    3020:   ("crs", "Whites2012",           275.0),     # 白色
    3021:   ("crs", "Blacks2012",           650.0),     # 黑色
    # --- Presence ---
    3006:   ("crs", "Saturation",           180.0),     # 饱和度
    90014:  ("crs", "Vibrance",             111.0),     # 自然饱和度
    3022:   ("crs", "Clarity2012",          73.0),      # 清晰度
    44799:  ("crs", "Dehaze",               76.0),      # 去朦胧
    # --- Detail ---
    90152:  ("crs", "Sharpness",            150.0),     # 锐化
    90153:  ("crs", "SharpenRadius",        3.0, "absolute"),   # 锐化半径
    90154:  ("crs", "SharpenDetail",        100.0),     # 锐化细节
    90155:  ("crs", "SharpenEdgeMasking",   100.0),     # 锐化蒙版
    91005:  ("crs", "LuminanceSmoothing",   200.0),     # 降噪-明亮度
    91006:  ("crs", "LuminanceNoiseReductionDetail",   100.0),   # 降噪-明亮度细节
    91007:  ("crs", "LuminanceNoiseReductionContrast", 100.0),   # 降噪-明亮度对比
    91003:  ("crs", "ColorNoiseReduction",  100.0),     # 降噪-颜色
    91004:  ("crs", "ColorNoiseReductionDetail",       100.0),   # 降噪-颜色细节
    91008:  ("crs", "ColorNoiseReductionSmoothness",   100.0),   # 降噪-颜色平滑度
    # --- Texture ---
    21001:  ("crs", "Texture",              150.0),     # 纹理
    # --- White Balance ---
    3007:   ("crs", "Temperature",           4000.0),    # 色温 (offset, 需叠加 ext info AsShot_CCT)
    3008:   ("crs", "Tint",                  300.0),     # 色调 (offset, 需叠加 ext info AsShot_Tint)
    # --- Effects ---
    201:    ("crs", "PostCropVignetteAmount", 100.0),   # 裁剪后暗角
    90118:  ("crs", "VignetteAmount",         100.0),   # 暗角
}

HSL_PARAMS = {
    # pf: (color, channel) — channel: "Hue"|"Saturation"|"Luminance"
    91170: ("Red",     "Hue"),
    91171: ("Red",     "Saturation"),
    91172: ("Red",     "Luminance"),
    91173: ("Orange",  "Hue"),
    91174: ("Orange",  "Saturation"),
    91175: ("Orange",  "Luminance"),
    91176: ("Yellow",  "Hue"),
    91177: ("Yellow",  "Saturation"),
    91178: ("Yellow",  "Luminance"),
    91179: ("Green",   "Hue"),
    91180: ("Green",   "Saturation"),
    91181: ("Green",   "Luminance"),
    91182: ("Aqua",    "Hue"),
    91183: ("Aqua",    "Saturation"),
    91184: ("Aqua",    "Luminance"),
    91185: ("Blue",    "Hue"),
    91186: ("Blue",    "Saturation"),
    91187: ("Blue",    "Luminance"),
    91188: ("Purple",  "Hue"),
    91189: ("Purple",  "Saturation"),
    91190: ("Purple",  "Luminance"),
    91191: ("Magenta", "Hue"),
    91192: ("Magenta", "Saturation"),
    91193: ("Magenta", "Luminance"),
}
HSL_COLORS = ["Red", "Orange", "Yellow", "Green",
              "Aqua", "Blue", "Purple", "Magenta"]

COLOR_GRADE_PARAMS = {
    # Color Grading (Lightroom 11+ style)
    130: ("crs", "ColorGradeShadowHue",          360.0),
    131: ("crs", "ColorGradeShadowSat",          100.0),
    132: ("crs", "ColorGradeHighlightHue",       360.0),
    133: ("crs", "ColorGradeHighlightSat",       100.0),
    134: ("crs", "ColorGradeBlending",           100.0),
    135: ("crs", "ColorGradeMidtoneHue",         360.0),
    136: ("crs", "ColorGradeMidtoneSat",         100.0),
    137: ("crs", "ColorGradeGlobalHue",          360.0),
    138: ("crs", "ColorGradeGlobalSat",          100.0),
    139: ("crs", "ColorGradeShadowLum",          100.0),
    140: ("crs", "ColorGradeMidtoneLum",         100.0),
    141: ("crs", "ColorGradeHighlightLum",       100.0),
    142: ("crs", "ColorGradeGlobalLum",          100.0),
}

UNSIGNED_FIELDS = {
    "Sharpness", "LuminanceSmoothing", "ColorNoiseReduction",
    "LuminanceNoiseReductionDetail", "LuminanceNoiseReductionContrast",
    "ColorNoiseReductionDetail", "ColorNoiseReductionSmoothness",
    "SharpenRadius", "SharpenDetail", "SharpenEdgeMasking",
    "Texture", "PostCropVignetteAmount", "VignetteAmount",
}

SYNC_HIERARCHY = {
    "Basic (基础)": {
        "Auto (自动)": ["AutoLateralCA", "LensProfileEnable"],
        "HDR (HDR)": ["HDREditMode"],
        "Profile (配置文件)": ["CameraProfile"],
        "WB (白平衡)": ["WhiteBalance", "Temperature", "Tint"],
        "Tone (色调)": [
            "Exposure2012", "Contrast2012", "Highlights2012",
            "Shadows2012", "Whites2012", "Blacks2012"
        ],
        "Presence (外貌/偏好)": [
            "Texture", "Clarity2012", "Dehaze", "Vibrance", "Saturation"
        ]
    },
    "Tone Curve (色调曲线)": {
        "Adjust (曲线调整)": [
            "ToneCurvePV2012", "ToneCurvePV2012Red", "ToneCurvePV2012Green",
            "ToneCurvePV2012Blue", "ToneCurveName2012"
        ]
    },
    "HSL (色彩调整)": {
        "HSL (色相/饱和度/明度)": ["HSL"]
    },
    "Color Grading (颜色分级)": {
        "Color Grading (分级参数)": ["ColorGrading"]
    },
    "Detail (细节/降噪)": {
        "Detail (锐化与降噪)": [
            "Sharpness", "SharpenRadius", "SharpenDetail", "SharpenEdgeMasking",
            "LuminanceSmoothing", "LuminanceNoiseReductionDetail", "LuminanceNoiseReductionContrast",
            "ColorNoiseReduction", "ColorNoiseReductionDetail", "ColorNoiseReductionSmoothness"
        ]
    },
    "Effects (效果)": {
        "Vignette (暗角与裁剪后暗角)": ["PostCropVignetteAmount", "VignetteAmount"]
    },
    "Crop (几何与裁剪)": {
        "Crop (裁剪比例与角度)": ["CropAngle", "CropLeft", "CropTop", "CropRight", "CropBottom", "HasCrop", "CropConstrainToWarp"]
    },
    "Metadata (评分与标记)": {
        "Rating & Pick (星级与旗标)": ["Rating", "Pick"],
        "Orientation (旋转)": ["Orientation"]
    }
}


def map_pixcake_to_xmp(palette_params, preset_params):
    crs_fields = {}
    all_params = {}

    def add_params(params_list):
        for item in (params_list or []):
            if not isinstance(item, dict):
                continue
            pf = item.get("pf")
            if pf is not None:
                all_params[pf] = {"fe": item.get("fe"), "se": item.get("se")}

    add_params(palette_params)
    add_params(preset_params)

    for pf_id, entry in all_params.items():
        if pf_id in PIXCAKE_TO_XMP_BASIC:
            mapping = PIXCAKE_TO_XMP_BASIC[pf_id]
            field, scale = mapping[1], mapping[2]
            mode = mapping[3] if len(mapping) > 3 else "relative"
            fe = entry["fe"]
            if fe is not None:
                value = fe * scale if mode == "absolute" else (fe - 0.5) * scale
                # Skip if value rounds to 0 (no adjustment)
                if abs(value) < 0.005:
                    continue
                if field in UNSIGNED_FIELDS:
                    crs_fields[field] = str(round(value))
                elif field == "Exposure2012" or abs(scale) < 20:
                    crs_fields[field] = f"{value:+.2f}"
                else:
                    crs_fields[field] = f"{round(value):+d}"

        if pf_id in HSL_PARAMS:
            color, channel = HSL_PARAMS[pf_id]
            fe = entry["fe"]
            if fe is not None:
                if channel == "Hue":
                    val = int((fe - 0.5) * 150)
                elif channel == "Saturation":
                    val = int((fe - 0.5) * 200)
                else:  # Luminance
                    val = int((fe - 0.5) * 240)
                if val != 0:
                    crs_fields[f"{channel}Adjustment{color}"] = f"{val:+d}"

        if pf_id in COLOR_GRADE_PARAMS:
            field, scale = COLOR_GRADE_PARAMS[pf_id][1], COLOR_GRADE_PARAMS[pf_id][2]
            fe = entry["fe"]
            if fe is not None:
                val = int((fe - 0.5) * scale)
                if val != 0:
                    crs_fields[field] = str(val)

    return crs_fields


# ============================================================
# Database Reader
# ============================================================

class PixCakeDB:
    def __init__(self, base_path=PIXCAKE_BASE):
        self.base_path = base_path
        self.db_dir = os.path.join(base_path, "db")
        self.project_dir = os.path.join(base_path, "project")

    def _user_base_db_paths(self, user_id):
        user_db_dir = os.path.join(self.db_dir, f"user_{user_id}", "db")
        return [
            os.path.join(user_db_dir, "user-base.db"),
            os.path.join(user_db_dir, "personal", "user-base.db"),
        ]

    def _proj_db_dir(self, project_id):
        pid = str(project_id)
        return f"project_{pid}" if not pid.startswith("project_") else pid

    def _proj_cache_dir(self, project_id):
        pid = str(project_id)
        return pid[len("project_"):] if pid.startswith("project_") else pid

    def get_users(self):
        base_db = os.path.join(self.db_dir, "base.db")
        if not os.path.exists(base_db):
            return []
        conn = sqlite3.connect(base_db)
        conn.row_factory = sqlite3.Row
        try:
            users = []
            rows = conn.execute(
                "SELECT id, user_id, merchant_id, organizationInfo, "
                "created_time, login_time FROM user").fetchall()
            for row in rows:
                user = dict(row)
                user["display_name"] = self._user_display_name(user)
                users.append(user)
            return users
        finally:
            conn.close()

    @staticmethod
    def _user_display_name(user):
        org_info = user.get("organizationInfo")
        if org_info:
            try:
                data = json.loads(org_info)
                for org in data.get("org_list", []):
                    name = org.get("organizationName")
                    if name:
                        return str(name)
            except (TypeError, json.JSONDecodeError):
                pass
        return str(user.get("user_id") or "")

    def get_user_projects(self, user_id):
        user_dir = os.path.join(self.project_dir, f"user_{user_id}")
        if not os.path.exists(user_dir):
            return []
        return sorted(
            [e for e in os.listdir(user_dir)
             if os.path.isdir(os.path.join(user_dir, e))],
            reverse=True)

    def get_project_records(self, user_id):
        records = {}
        for db_path in self._user_base_db_paths(user_id):
            if not os.path.exists(db_path):
                continue

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT id, userId, name, update_time, created_time, "
                    "disable FROM project"
                ).fetchall()
                for row in rows:
                    records[str(row["id"])] = {
                        "id": str(row["id"]),
                        "user_id": str(row["userId"]),
                        "name": row["name"] or "",
                        "update_time": row["update_time"],
                        "created_time": row["created_time"],
                        "disable": bool(row["disable"]),
                    }
            finally:
                conn.close()
        return records

    def get_project_meta(self, user_id, project_id, project_record=None):
        proj_db_dir = self._proj_db_dir(project_id)
        proj_cache_dir = self._proj_cache_dir(project_id)
        proj_db = os.path.join(self.db_dir, f"user_{user_id}",
                               proj_db_dir, "project.db")
        project_name = ((project_record or {}).get("name")
                        or f"Project {project_id}")
        project_update = (project_record or {}).get("update_time")
        result = {"name": project_name,
                  "date": format_dt(pixcake_ts_to_datetime(project_update)) if project_update else "",
                  "count": 0, "thumbnail": None,
                  "user_id": user_id, "project_id": project_id}

        if not os.path.exists(proj_db):
            return result

        conn = sqlite3.connect(proj_db)
        conn.row_factory = sqlite3.Row
        try:
            cr = conn.execute(
                "SELECT COUNT(*) as cnt, MAX(update_time) as last_update "
                "FROM thumbnail WHERE inRecycleBin=0").fetchone()
            result["count"] = cr["cnt"] or 0
            if cr["last_update"]:
                result["date"] = format_dt(
                    pixcake_ts_to_datetime(cr["last_update"]))

            rows = conn.execute(
                "SELECT DISTINCT originalImagePath FROM thumbnail "
                "WHERE inRecycleBin=0 LIMIT 3").fetchall()
            folders = set()
            for row in rows:
                parts = row[0].replace("\\", "/").split("/")
                if len(parts) >= 2:
                    folders.add(parts[-2])
            if folders and not project_record:
                result["name"] = "/".join(sorted(folders)[:2])
                if result["count"]:
                    result["name"] += f"  ({result['count']})"
        finally:
            conn.close()

        thumb_dir = os.path.join(self.project_dir, f"user_{user_id}",
                                 proj_cache_dir, "albumnThumbnail")
        if os.path.isdir(thumb_dir):
            for f in os.listdir(thumb_dir):
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    result["thumbnail"] = os.path.join(thumb_dir, f)
                    break

        return result

    def get_all_projects_with_meta(self):
        all_projects = []
        for user in self.get_users():
            uid = user["user_id"]
            display_name = user.get("display_name") or str(uid)
            project_records = self.get_project_records(uid)
            if project_records:
                active_records = [
                    record for record in project_records.values()
                    if not record.get("disable")
                ]
                active_records.sort(
                    key=lambda record: record.get("update_time") or 0,
                    reverse=True)
                for record in active_records:
                    meta = self.get_project_meta(uid, record["id"], record)
                    if meta["count"]:
                        meta["user_display_name"] = display_name
                        all_projects.append(meta)
            else:
                for proj_dir in self.get_user_projects(uid):
                    pid = proj_dir.replace("project_", "")
                    meta = self.get_project_meta(uid, pid)
                    if meta["count"]:
                        meta["user_display_name"] = display_name
                        all_projects.append(meta)
        return all_projects

    def get_project_images(self, user_id, project_id):
        proj_db_dir = self._proj_db_dir(project_id)
        proj_db = os.path.join(self.db_dir, f"user_{user_id}",
                               proj_db_dir, "project.db")
        if not os.path.exists(proj_db):
            return []
        conn = sqlite3.connect(proj_db)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT id, extendId, originalImagePath, thumbnailImagePath,
                       captureTime, created_time, update_time, presetId,
                       rotation, originalWidth, originalHeight, exifInfo,
                       isFavourite, inRecycleBin, fileSize,
                       currentOptRecordId, lastOptRecordId, uuidKey,
                       starLevel, selectFlag
                FROM thumbnail WHERE inRecycleBin = 0
                ORDER BY captureTime DESC, created_time DESC
            """).fetchall()
            images = []
            for row in rows:
                img = dict(row)
                img["_user_id"] = user_id
                img["_project_id"] = project_id
                exif = {}
                if img.get("exifInfo"):
                    try:
                        exif = json.loads(img["exifInfo"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                img["exif_parsed"] = exif
                img["capture_dt"] = pixcake_ts_to_datetime(
                    img.get("captureTime"))
                images.append(img)
            return images
        finally:
            conn.close()

    def get_opt_record_paths(self, user_id, project_id, thumb_id):
        proj_db_dir = self._proj_db_dir(project_id)
        proj_db = os.path.join(self.db_dir, f"user_{user_id}",
                               proj_db_dir, "project.db")
        if not os.path.exists(proj_db):
            return None, None
        conn = sqlite3.connect(proj_db)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("""
                SELECT presetJsonPath, paletteJsonPath
                FROM thumb_opt_record
                WHERE thumbnailId = ? AND enable = 1
                ORDER BY created_time DESC LIMIT 1
            """, (thumb_id,)).fetchone()
            return (row["presetJsonPath"], row["paletteJsonPath"]) if row else (None, None)
        finally:
            conn.close()

    def get_palette_params(self, file_path):
        if not file_path or not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                result = json.load(f)
                return result if isinstance(result, dict) else None
        except (json.JSONDecodeError, FileNotFoundError):
            return None

    def get_ext_info(self, user_id, project_id, thumb_uuid):
        proj_cache = os.path.join(
            self.project_dir, f"user_{user_id}",
            self._proj_cache_dir(project_id), "thumbnail_cache")
        if not os.path.exists(proj_cache):
            return None
        for entry in os.listdir(proj_cache):
            if entry.startswith("thumbnail_") and thumb_uuid in entry:
                cache_dir = os.path.join(proj_cache, entry)
                for sub in ["c_p_f_e", "c_p_f_o"]:
                    sub_dir = os.path.join(cache_dir, sub)
                    if os.path.isdir(sub_dir):
                        for f in os.listdir(sub_dir):
                            if f.endswith("_ext"):
                                try:
                                    with open(os.path.join(sub_dir, f),
                                              "r", encoding="utf-8") as fh:
                                        return json.load(fh)
                                except Exception:
                                    pass
        return None


# ============================================================
# RAW Metadata Reader (fallback)
# ============================================================

def read_raw_metadata(filepath):
    metadata = {}
    if not os.path.exists(filepath):
        return metadata
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(filepath)
        exif = img._getexif()
        if exif:
            for tag_id, value in exif.items():
                metadata[TAGS.get(tag_id, str(tag_id))] = str(value)
        metadata["ImageWidth"] = str(img.width)
        metadata["ImageLength"] = str(img.height)
    except ImportError:
        pass
    except Exception:
        pass
    try:
        import exifread
        with open(filepath, "rb") as f:
            for tag, value in exifread.process_file(f, details=False).items():
                metadata.setdefault(tag, str(value))
    except ImportError:
        pass
    except Exception:
        pass
    if not metadata:
        try:
            with open(filepath, "rb") as f:
                data = f.read(65536)
            text = data.decode("ascii", errors="ignore")
            for key, pat in [("Make", r"Canon|Nikon|Sony|Fujifilm|Olympus|Panasonic|Leica"),
                             ("Model", r"EOS[\s\w\d]+|NIKON[\s\w\d]+|ILCE-[\d\w]+")]:
                m = re.search(pat, text)
                if m:
                    metadata[key] = m.group(0)
        except Exception:
            pass
    return metadata


# ============================================================
# XMP Generator
# ============================================================

RAW_EXTENSIONS = {
    ".3FR", ".ARW", ".CR2", ".CR3", ".DNG", ".ERF", ".FFF", ".GPR",
    ".IIQ", ".MEF", ".MOS", ".MRW", ".NEF", ".NRW", ".ORF", ".PEF",
    ".RAF", ".RAW", ".RW2", ".SR2", ".SRF", ".X3F",
}


def _to_rational_str(value):
    """Convert EXIF display format to XMP rational string.

    "f/4" → "4/1",  "75 mm" → "75/1",  "0 EV" → "0/1",
    "1/2500" → "1/2500" (already rational).
    """
    if value is None:
        return None
    v = str(value).strip()
    # Already a rational like "1/2500", "+1/3", "4/1"
    if re.match(r'^[+-]?\d+/\d+$', v):
        return v
    # Strip common units
    v = re.sub(r'\s*(mm|EV|sec|s)\s*$', '', v, flags=re.IGNORECASE).strip()
    # Strip "f/" prefix  (f/4, f/5.6)
    v = re.sub(r'^f/', '', v).strip()
    if v == "0":
        return "0/1"
    try:
        num = float(v)
        if num == int(num):
            return f"{int(num)}/1"
        # Fractional aperture: f/1.8 → represent as rational
        frac = Fraction(num).limit_denominator(100)
        return f"{frac.numerator}/{frac.denominator}"
    except (ValueError, ImportError):
        return str(value)


def _to_lens_info_rational(value):
    """Convert comma-separated lens specs to rational format.

    "70,200,0,0" → "70/1 200/1 0/0 0/0"
    """
    if value is None:
        return None
    v = str(value).strip().strip("[]()")
    parts = re.split(r"[\s,]+", v)
    result = []
    for idx, p in enumerate(part for part in parts if part):
        if re.match(r'^[+-]?\d+/\d+$', p):
            result.append(p)
            continue
        try:
            num = float(p)
            if idx >= 2 and num == 0:
                result.append("0/0")
            elif num == int(num):
                result.append(f"{int(num)}/1")
            else:
                frac = Fraction(num).limit_denominator(100)
                result.append(f"{frac.numerator}/{frac.denominator}")
        except (ValueError, TypeError):
            result.append(p)
    return " ".join(result)


def _parse_int_like(value):
    """Parse integer-ish EXIF values such as "6000", "[6000]", or "6000 pixels"."""
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _parse_orientation_from_raw(raw_meta):
    """Extract EXIF orientation value from raw metadata dict.

    Returns int 1-8, or None if not found.
    """
    if not raw_meta:
        return None
    for rk, rv in raw_meta.items():
        if "orientation" in rk.lower():
            v = str(rv).strip()
            # "8" or "Rotated 90 CW" or "Horizontal (normal)"
            try:
                return int(v.split()[0])
            except ValueError:
                # Map common textual descriptions
                mapping = {
                    "horizontal": 1, "normal": 1, "top-left": 1,
                    "mirror": 2, "top-right": 2,
                    "rotate": None,  # need full phrase
                    "rotated": None,
                }
                v_lower = v.lower()
                if "180" in v_lower:
                    return 3
                if "90" in v_lower and ("ccw" in v_lower or "counter" in v_lower):
                    return 8
                if "90" in v_lower and "cw" in v_lower:
                    return 6
                if "270" in v_lower:
                    return 8
                return None
    return None


def _parse_raw_dimensions(raw_meta):
    """Extract image dimensions from raw metadata dict (sensor order).

    Returns (width, height) tuple, or (None, None).
    """
    if not raw_meta:
        return None, None
    w = h = None
    width_keys = ("imagewidth", "exifimagewidth", "pixelxdimension")
    height_keys = ("imagelength", "imageheight", "exifimagelength", "pixelydimension")
    for rk, rv in raw_meta.items():
        key_clean = re.sub(r"[^a-z0-9]", "", rk.lower())
        if "thumbnail" in key_clean:
            continue
        if any(key_clean.endswith(key) for key in width_keys):
            w = _parse_int_like(rv) or w
        if any(key_clean.endswith(key) for key in height_keys):
            h = _parse_int_like(rv) or h
    return w, h


def _parse_raw_capture_datetime(raw_meta):
    """Read the camera capture time from RAW EXIF and treat no-zone values as CST."""
    if not raw_meta:
        return None
    priority = ("datetimeoriginal", "createdate", "datetime")
    candidates = []
    for wanted in priority:
        for rk, rv in raw_meta.items():
            key_clean = re.sub(r"[^a-z0-9]", "", rk.lower())
            if key_clean.endswith(wanted):
                candidates.append(str(rv).strip())
    for value in candidates:
        match = re.search(
            r"(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})"
            r"(?:\s*(Z|[+-]\d{2}:?\d{2}))?",
            value,
        )
        if not match:
            continue
        year, month, day, hour, minute, second, tz_value = match.groups()
        dt = datetime(
            int(year), int(month), int(day),
            int(hour), int(minute), int(second),
        )
        if tz_value:
            if tz_value == "Z":
                return dt.replace(tzinfo=timezone.utc).astimezone(CST)
            sign = 1 if tz_value[0] == "+" else -1
            offset_text = tz_value[1:].replace(":", "")
            offset = timedelta(
                hours=int(offset_text[:2]),
                minutes=int(offset_text[2:4] or "0"),
            )
            return dt.replace(tzinfo=timezone(sign * offset)).astimezone(CST)
        return dt.replace(tzinfo=CST)
    return None


def _prefixed_xml_name(name, ns_by_uri):
    if name.startswith("{"):
        uri, local = name[1:].split("}", 1)
        prefix = ns_by_uri.get(uri)
        return f"{prefix}:{local}" if prefix else local
    return name


def _format_attr(name, value, ns_by_uri):
    return f"{_prefixed_xml_name(name, ns_by_uri)}={quoteattr(str(value))}"


def _format_xmp_element(elem, ns_by_uri, level):
    indent = " " * level
    name = _prefixed_xml_name(elem.tag, ns_by_uri)
    attrs = [_format_attr(k, v, ns_by_uri) for k, v in elem.attrib.items()]
    children = list(elem)
    text = (elem.text or "").strip()

    if not children and not text:
        if not attrs:
            return [f"{indent}<{name}/>"]
        lines = [f"{indent}<{name}"]
        for attr in attrs[:-1]:
            lines.append(f"{indent} {attr}")
        lines.append(f"{indent} {attrs[-1]}/>")
        return lines

    if not children:
        attr_text = f" {' '.join(attrs)}" if attrs else ""
        return [f"{indent}<{name}{attr_text}>{escape(text)}</{name}>"]

    if attrs:
        lines = [f"{indent}<{name}"]
        for attr in attrs[:-1]:
            lines.append(f"{indent} {attr}")
        lines.append(f"{indent} {attrs[-1]}>")
    else:
        lines = [f"{indent}<{name}>"]

    for child in children:
        lines.extend(_format_xmp_element(child, ns_by_uri, level + 1))
    lines.append(f"{indent}</{name}>")
    return lines


def _format_xmp_document(root, desc, NS):
    ns_by_uri = {uri: prefix for prefix, uri in NS.items()}
    desc_ns_order = [
        "xmp", "photoshop", "exif", "xmpDM", "tiff", "aux", "exifEX",
        "dc", "xmpMM", "stEvt", "crd", "crs",
    ]
    xmptk_key = f"{{{NS['x']}}}xmptk"
    rdf_about_key = f"{{{NS['rdf']}}}about"

    lines = [
        f"<x:xmpmeta xmlns:x={quoteattr(NS['x'])} "
        f"x:xmptk={quoteattr(root.get(xmptk_key, ''))}>",
        f" <rdf:RDF xmlns:rdf={quoteattr(NS['rdf'])}>",
        f"  <rdf:Description rdf:about={quoteattr(desc.get(rdf_about_key, ''))}",
    ]

    for prefix in desc_ns_order:
        lines.append(f"    xmlns:{prefix}={quoteattr(NS[prefix])}")

    attrs = [
        _format_attr(key, value, ns_by_uri)
        for key, value in desc.attrib.items()
        if key != rdf_about_key
    ]
    if attrs:
        for attr in attrs[:-1]:
            lines.append(f"   {attr}")
        lines.append(f"   {attrs[-1]}>")
    else:
        lines[-1] += ">"

    for child in list(desc):
        lines.extend(_format_xmp_element(child, ns_by_uri, 3))

    lines.extend(["  </rdf:Description>", " </rdf:RDF>", "</x:xmpmeta>"])
    return "\n".join(lines) + "\n"


def _find_nested_value(data, normalized_keys):
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in normalized_keys:
                return value
            found = _find_nested_value(value, normalized_keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_nested_value(item, normalized_keys)
            if found is not None:
                return found
    return None


def _to_int_or_none(value):
    if value is None:
        return None
    try:
        return int(round(float(str(value).strip())))
    except (TypeError, ValueError):
        return None


def _is_signed_offset(value):
    return bool(re.match(r"^[+-]\d+(?:\.\d+)?$", str(value).strip()))


def generate_xmp(image_info, crs_fields, raw_metadata=None, exif_data=None, selected_fields=None):
    NS = {
        "x": "adobe:ns:meta/",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "xmp": "http://ns.adobe.com/xap/1.0/",
        "tiff": "http://ns.adobe.com/tiff/1.0/",
        "exif": "http://ns.adobe.com/exif/1.0/",
        "aux": "http://ns.adobe.com/exif/1.0/aux/",
        "exifEX": "http://cipa.jp/exif/1.0/",
        "photoshop": "http://ns.adobe.com/photoshop/1.0/",
        "xmpMM": "http://ns.adobe.com/xap/1.0/mm/",
        "stEvt": "http://ns.adobe.com/xap/1.0/sType/ResourceEvent#",
        "dc": "http://purl.org/dc/elements/1.1/",
        "crd": "http://ns.adobe.com/camera-raw-defaults/1.0/",
        "crs": "http://ns.adobe.com/camera-raw-settings/1.0/",
        "xmpDM": "http://ns.adobe.com/xmp/1.0/DynamicMedia/",
    }
    for prefix, uri in NS.items():
        ET.register_namespace(prefix, uri)

    root = ET.Element(f"{{{NS['x']}}}xmpmeta")
    root.set(f"{{{NS['x']}}}xmptk", "PixCake XMP Converter 1.0")
    rdf = ET.SubElement(root, f"{{{NS['rdf']}}}RDF")
    desc = ET.SubElement(rdf, f"{{{NS['rdf']}}}Description")
    desc.set(f"{{{NS['rdf']}}}about", "")

    exif = exif_data or {}
    raw_meta = raw_metadata or {}

    def get_val(key, exif_key=None):
        ek = exif_key or key
        if ek in exif:
            v = exif[ek]
            return v.get("value", str(v)) if isinstance(v, dict) else str(v)
        if raw_meta:
            for rk, rv in raw_meta.items():
                if ek.lower() in rk.lower():
                    return str(rv)
        return None

    now = datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S.00+08:00")
    desc.set(f"{{{NS['xmp']}}}ModifyDate", now)
    desc.set(f"{{{NS['xmp']}}}MetadataDate", now)

    raw_capture_dt = _parse_raw_capture_datetime(raw_meta)
    capture_dt = raw_capture_dt or image_info.get("capture_dt")
    if capture_dt:
        # Prefer RAW EXIF capture time; PixCake's DB timestamp can be shifted by timezone.
        local_dt = capture_dt.astimezone(CST)
        cd_tz = local_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        cd_no_tz = local_dt.strftime("%Y-%m-%dT%H:%M:%S")
        desc.set(f"{{{NS['xmp']}}}CreateDate", cd_tz)
        desc.set(f"{{{NS['photoshop']}}}DateCreated", cd_no_tz)
        desc.set(f"{{{NS['exif']}}}DateTimeOriginal", cd_no_tz)

    if selected_fields is None or "Rating" in selected_fields:
        rating = crs_fields.pop("Rating", None)
        if rating is not None:
            desc.set(f"{{{NS['xmp']}}}Rating", str(rating))
        elif "Rating" in exif:
            rv = exif["Rating"]
            rating = str(rv.get("value", "0")) if isinstance(rv, dict) else str(rv)
            desc.set(f"{{{NS['xmp']}}}Rating", rating)
        else:
            desc.set(f"{{{NS['xmp']}}}Rating", "0")

    # Pick flag (xmpDM:pick)
    if selected_fields is None or "Pick" in selected_fields:
        pick = crs_fields.pop("Pick", None)
        if pick is not None:
            desc.set(f"{{{NS['xmpDM']}}}pick", str(pick))

    for ns_key, ek in [
        (f"{{{NS['tiff']}}}Make", "Make"),
        (f"{{{NS['tiff']}}}Model", "Model"),
    ]:
        v = get_val(ek)
        if v:
            desc.set(ns_key, v)
    raw_ext = os.path.splitext(image_info.get("originalImagePath", ""))[1]
    raw_w, raw_h = _parse_raw_dimensions(raw_meta)
    orig_w = _parse_int_like(image_info.get("originalWidth"))
    orig_h = _parse_int_like(image_info.get("originalHeight"))

    # ---- Orientation ----
    # Prefer raw-file EXIF orientation (sensor-native); fall back to PixCake rotation.
    orientation = "1"
    if selected_fields is None or "Orientation" in selected_fields:
        raw_orient = _parse_orientation_from_raw(raw_meta)
        orientation = crs_fields.pop("Orientation", "1")
        if raw_orient is not None and 1 <= raw_orient <= 8:
            orientation = str(raw_orient)
        elif (
            orientation == "1"
            and orig_w and orig_h and orig_h > orig_w
            and raw_ext.upper() in RAW_EXTENSIONS
            and (not raw_w or not raw_h or raw_w > raw_h)
        ):
            # PixCake stores display pixels as portrait, while RAW/XMP uses sensor order
            # plus orientation. Canon CR3 portrait files commonly need Orientation=8.
            orientation = "8"
        desc.set(f"{{{NS['tiff']}}}Orientation", orientation)

    # ---- Dimensions ----
    # Use raw-file sensor dimensions when available; otherwise derive from PixCake data
    if raw_w and raw_h:
        w, h = raw_w, raw_h
    elif orientation in ("5", "6", "7", "8") and orig_w and orig_h:
        # Orientation indicates rotation; PixCake stores display dims → swap for sensor order
        w, h = orig_h, orig_w
    else:
        w, h = orig_w, orig_h
    if w and h:
        desc.set(f"{{{NS['tiff']}}}ImageWidth", str(w))
        desc.set(f"{{{NS['tiff']}}}ImageLength", str(h))
        desc.set(f"{{{NS['exif']}}}PixelXDimension", str(w))
        desc.set(f"{{{NS['exif']}}}PixelYDimension", str(h))

    # EXIF fields that should be written in rational (n/d) format
    _RATIONAL_FIELDS = {
        "ExposureTime", "FNumber", "ApertureValue",
        "ExposureBiasValue", "FocalLength",
    }
    for ns_key, ek in [
        (f"{{{NS['exif']}}}ExifVersion", "ExifVersion"),
        (f"{{{NS['exif']}}}ExposureTime", "ExposureTime"),
        (f"{{{NS['exif']}}}FNumber", "FNumber"),
        (f"{{{NS['exif']}}}ApertureValue", "ApertureValue"),
        (f"{{{NS['exif']}}}ExposureProgram", "ExposureProgram"),
        (f"{{{NS['exif']}}}ExposureBiasValue", "ExposureBiasValue"),
        (f"{{{NS['exif']}}}FocalLength", "FocalLength"),
        (f"{{{NS['exif']}}}MeteringMode", "MeteringMode"),
        (f"{{{NS['exif']}}}WhiteBalance", "WhiteBalance"),
    ]:
        v = get_val(ek)
        if v:
            desc.set(ns_key, _to_rational_str(v) if ek in _RATIONAL_FIELDS else str(v))

    iso = get_val("ISOSpeedRatings")
    if iso:
        iso_seq = ET.SubElement(desc, f"{{{NS['exif']}}}ISOSpeedRatings")
        seq = ET.SubElement(iso_seq, f"{{{NS['rdf']}}}Seq")
        li = ET.SubElement(seq, f"{{{NS['rdf']}}}li")
        li.text = str(iso)

    for ns_key, ek in [
        (f"{{{NS['aux']}}}SerialNumber", "SerialNumber"),
        (f"{{{NS['aux']}}}Lens", "LensModel"),
        (f"{{{NS['exifEX']}}}LensModel", "LensModel"),
        (f"{{{NS['aux']}}}LensSerialNumber", "LensSerialNumber"),
    ]:
        v = get_val(ek)
        if v:
            desc.set(ns_key, str(v))

    # LensInfo / LensSpecification — convert to rational format
    lens_info = get_val("LensSpecification") or get_val("LensInfo")
    if lens_info:
        desc.set(f"{{{NS['aux']}}}LensInfo", _to_lens_info_rational(lens_info))

    desc.set(f"{{{NS['photoshop']}}}SidecarForExtension",
             raw_ext.lstrip(".").upper())

    mime_map = {".CR3": "image/x-canon-cr3", ".CR2": "image/x-canon-cr2",
                ".NEF": "image/x-nikon-nef", ".ARW": "image/x-sony-arw",
                ".DNG": "image/x-adobe-dng", ".RAF": "image/x-fuji-raf"}
    desc.set(f"{{{NS['dc']}}}format",
             mime_map.get(raw_ext.upper(), f"image/{raw_ext.lstrip('.').lower()}"))

    raw_name = os.path.basename(image_info.get("originalImagePath", "unknown"))
    doc_id = uuid.uuid4().hex.upper()
    desc.set(f"{{{NS['xmpMM']}}}DocumentID", doc_id)
    desc.set(f"{{{NS['xmpMM']}}}PreservedFileName", raw_name)
    desc.set(f"{{{NS['xmpMM']}}}OriginalDocumentID", doc_id)
    desc.set(f"{{{NS['xmpMM']}}}InstanceID", f"xmp.iid:{uuid.uuid4()}")

    desc.set(f"{{{NS['crs']}}}Version", "18.0")
    desc.set(f"{{{NS['crs']}}}CompatibleVersion", "285212672")
    desc.set(f"{{{NS['crs']}}}ProcessVersion", "15.4")
    desc.set(f"{{{NS['crs']}}}RawFileName", raw_name)

    curve_points = {}
    for field, value in crs_fields.items():
        if field.endswith("__points"):
            curve_points[field[:-8]] = value
        else:
            desc.set(f"{{{NS['crs']}}}{field}", str(value))

    defaults = {
        "WhiteBalance": "As Shot", "AutoLateralCA": "1",
        "LensProfileEnable": "1", "PerspectiveUpright": "0",
        "HDREditMode": "0", "CurveRefineSaturation": "100",
        "OverrideLookVignette": "False", "CameraProfile": "Adobe Standard",
        "HasSettings": "True", "AlreadyApplied": "False", "AllowFilters": "1",
        # Default full-frame crop (no-op)
        "CropTop": "0", "CropLeft": "0",
        "CropBottom": "1", "CropRight": "1",
        "CropAngle": "0", "CropConstrainToUnitSquare": "1",
    }
    for field, value in defaults.items():
        if field not in crs_fields:
            # Check if this default field is allowed by selected_fields
            is_allowed = True
            if selected_fields is not None:
                if field == "WhiteBalance":
                    is_allowed = "WhiteBalance" in selected_fields
                elif field in ("AutoLateralCA", "LensProfileEnable"):
                    is_allowed = "AutoLateralCA" in selected_fields or "LensProfileEnable" in selected_fields
                elif field == "HDREditMode":
                    is_allowed = "HDREditMode" in selected_fields
                elif field == "CameraProfile":
                    is_allowed = "CameraProfile" in selected_fields
                elif field == "CurveRefineSaturation":
                    is_allowed = "ToneCurvePV2012" in selected_fields
                elif field in ("CropTop", "CropLeft", "CropBottom", "CropRight", "CropAngle", "CropConstrainToUnitSquare"):
                    is_allowed = "CropAngle" in selected_fields or "CropLeft" in selected_fields
            
            if is_allowed:
                desc.set(f"{{{NS['crs']}}}{field}", value)

    history = ET.SubElement(desc, f"{{{NS['xmpMM']}}}History")
    seq = ET.SubElement(history, f"{{{NS['rdf']}}}Seq")
    li = ET.SubElement(seq, f"{{{NS['rdf']}}}li")
    li.set(f"{{{NS['stEvt']}}}action", "saved")
    li.set(f"{{{NS['stEvt']}}}instanceID", f"xmp.iid:{uuid.uuid4()}")
    li.set(f"{{{NS['stEvt']}}}when", now)
    li.set(f"{{{NS['stEvt']}}}softwareAgent", "PixCake XMP Converter 1.0")
    li.set(f"{{{NS['stEvt']}}}changed", "/metadata")

    flash = ET.SubElement(desc, f"{{{NS['exif']}}}Flash")
    for attr, val in [("Fired", "False"), ("Return", "0"), ("Mode", "0"),
                       ("Function", "False"), ("RedEyeMode", "False")]:
        flash.set(f"{{{NS['exif']}}}{attr}", val)

    # Write each tone curve once, using custom PixCake points where present.
    if selected_fields is None or "ToneCurvePV2012" in selected_fields:
        for suffix in ["", "Red", "Green", "Blue"]:
            field_name = f"ToneCurvePV2012{suffix}"
            points = curve_points.get(field_name, "0, 0;255, 255")
            tc = ET.SubElement(desc, f"{{{NS['crs']}}}{field_name}")
            tc_seq = ET.SubElement(tc, f"{{{NS['rdf']}}}Seq")
            for pt in points.split(";"):
                li = ET.SubElement(tc_seq, f"{{{NS['rdf']}}}li")
                li.text = pt

    try:
        return _format_xmp_document(root, desc, NS)
    except Exception:
        rough = ET.tostring(root, encoding="unicode")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + rough


# ============================================================
# QSS Stylesheet — Tailwind-inspired
# ============================================================

QSS = r"""
/* ===== Global ===== */
* {
    font-family: 'SF Pro Display', '-apple-system', 'BlinkMacSystemFont', 'Inter', 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
    font-size: 13px;
    color: #F5F5F7;
}

QMainWindow {
    background-color: #1E1E1E;
}

/* ===== Title Bar ===== */
#titleBar {
    background-color: #1E1E1E;
    border-bottom: 1px solid #2D2D2D;
    min-height: 48px;
    max-height: 48px;
}
#titleLabel {
    font-size: 13px;
    font-weight: 600;
    color: #FFFFFF;
    padding-left: 8px;
}

/* Windows-style title bar buttons */
#btnMin, #btnMax, #btnClose {
    border: none;
    border-radius: 4px;
    padding: 0;
    min-width: 46px;
    min-height: 32px;
    max-width: 46px;
    max-height: 32px;
    font-size: 10px;
    font-weight: 400;
    color: #CCCCCC;
    background-color: transparent;
}
#btnMin:hover, #btnMax:hover {
    background-color: #3A3A3C;
    color: #FFFFFF;
}
#btnClose:hover {
    background-color: #C42B1C;
    color: #FFFFFF;
}
#btnClose {
    border-top-right-radius: 8px;
}

/* ===== Top Toolbar ===== */
#toolbar {
    background-color: #1E1E1E;
    border-bottom: 1px solid #2D2D2D;
    padding: 12px 20px;
}

/* ===== ComboBox ===== */
QComboBox {
    background-color: #242426;
    border: 1px solid #3A3A3C;
    border-radius: 10px;
    padding: 7px 34px 7px 12px;
    min-width: 140px;
    color: #F5F5F7;
    font-size: 13px;
    font-weight: 600;
}
QComboBox:hover {
    background-color: #2C2C2E;
    border-color: #48484A;
}
QComboBox:focus {
    border: 1px solid #0A84FF;
    background-color: #2C2C2E;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 32px;
    border-left: none;
    border-top-right-radius: 10px;
    border-bottom-right-radius: 10px;
}
QComboBox::down-arrow {
    image: none;
}
QComboBox QAbstractItemView {
    background-color: #1C1C1E;
    border: 1px solid #48484A;
    border-radius: 10px;
    padding: 6px;
    selection-background-color: #0A84FF;
    selection-color: #FFFFFF;
    color: #F5F5F7;
    outline: none;
}
QComboBox QAbstractItemView::viewport {
    background-color: #1C1C1E;
    border-radius: 10px;
}
QComboBox QAbstractItemView::item {
    min-height: 34px;
    padding: 0 12px;
    border-radius: 7px;
}
QComboBox QAbstractItemView::item:hover {
    background-color: #2C2C2E;
}
QComboBox QAbstractItemView::item:selected {
    background-color: #0A84FF;
    color: #FFFFFF;
}

/* ===== PushButton ===== */
QPushButton {
    background-color: #0A84FF;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #007AFF;
}
QPushButton:pressed {
    background-color: #0066CC;
}
QPushButton:disabled {
    background-color: #3A3A3C;
    color: #8E8E93;
}

QPushButton#btnSecondary {
    background-color: #2C2C2E;
    color: #FFFFFF;
    border: 1px solid #3A3A3C;
    font-weight: 500;
}
QPushButton#btnSecondary:hover {
    background-color: #3A3A3C;
    border-color: #48484A;
}
QPushButton#btnSecondary:pressed {
    background-color: #48484A;
}

QPushButton#btnSoftwarePath {
    background-color: #2C2C2E;
    color: #FFFFFF;
    border: 1px solid #3A3A3C;
    font-weight: 500;
}
QPushButton#btnSoftwarePath:hover {
    background-color: #3A3A3C;
    border-color: #48484A;
}
QPushButton#btnSoftwarePath:pressed {
    background-color: #48484A;
}
QPushButton#btnSoftwarePath[pathValid="true"] {
    background-color: #2D3A33;
    border-color: #496B55;
}
QPushButton#btnSoftwarePath[pathValid="true"]:hover {
    background-color: #35483C;
    border-color: #5D8068;
}
QPushButton#btnSoftwarePath[pathValid="false"] {
    background-color: #3A2D2D;
    border-color: #6B4949;
}
QPushButton#btnSoftwarePath[pathValid="false"]:hover {
    background-color: #483535;
    border-color: #805D5D;
}

QPushButton#btnGhost {
    background-color: transparent;
    color: #AEAEB2;
    border: none;
    font-weight: 500;
    padding: 6px 12px;
}
QPushButton#btnGhost:hover {
    background-color: #2C2C2E;
    color: #FFFFFF;
}

QPushButton#btnConvert {
    background-color: #0A84FF;
    color: #FFFFFF;
    border-radius: 10px;
    padding: 12px 32px;
    font-size: 14px;
    font-weight: 700;
    min-width: 180px;
}
QPushButton#btnConvert:hover {
    background-color: #007AFF;
}
QPushButton#btnConvert:pressed {
    background-color: #0066CC;
}

/* ===== LineEdit ===== */
QLineEdit {
    background-color: #2C2C2E;
    border: 1px solid #3A3A3C;
    border-radius: 8px;
    padding: 8px 12px;
    color: #FFFFFF;
    selection-background-color: #0A84FF;
}
QLineEdit:hover {
    border-color: #48484A;
    background-color: #3A3A3C;
}
QLineEdit:focus {
    border: 1px solid #0A84FF;
    background-color: #1C1C1E;
}

/* ===== Scroll Area ===== */
QScrollArea {
    border: none;
    background-color: #121212;
}
QScrollArea > QWidget > QWidget {
    background-color: #121212;
}
QScrollBar:vertical {
    background-color: transparent;
    width: 8px;
    margin: 4px;
}
QScrollBar::handle:vertical {
    background-color: #3A3A3C;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #48484A;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0; width: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

/* ===== Project Card ===== */
#cardFrame {
    background-color: #1C1C1E;
    border: none;
    border-radius: 12px;
}
#cardFrame:hover {
    background-color: #2C2C2E;
}
#cardFrame[selected="true"] {
    background-color: #242C3E;
}
#cardThumb {
    background-color: #2C2C2E;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
#cardName {
    font-size: 13px;
    font-weight: 600;
    color: #FFFFFF;
    padding: 4px 0 0 0;
}
#cardDate {
    font-size: 12px;
    color: #8E8E93;
    padding: 2px 0 0 0;
}

/* ===== Bottom Bar ===== */
#bottomBar {
    background-color: #1E1E1E;
    border-top: 1px solid #2D2D2D;
    padding: 16px 20px;
}

/* ===== ProgressBar ===== */
QProgressBar {
    background-color: #2C2C2E;
    border: none;
    border-radius: 6px;
    height: 12px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #0A84FF;
    border-radius: 6px;
}

/* ===== StatusBar ===== */
QStatusBar {
    background-color: #1E1E1E;
    border-top: 1px solid #2D2D2D;
    color: #8E8E93;
    font-size: 12px;
    padding: 4px 12px;
}

/* ===== Info Label ===== */
#infoLabel {
    color: #8E8E93;
    font-size: 13px;
}
"""


# ============================================================
# Worker Threads
# ============================================================

class LoadProjectsWorker(QObject):
    finished = pyqtSignal(list)

    def run(self):
        db = PixCakeDB()
        projects = db.get_all_projects_with_meta()
        self.finished.emit(projects)


class ConvertWorker(QObject):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(int, int, list)

    def __init__(self, selected_projects, output_dir, overwrite_mode="skip",
                 selected_fields=None, base_path=PIXCAKE_BASE):
        super().__init__()
        self.selected_projects = selected_projects
        self.output_dir = output_dir
        self.overwrite_mode = overwrite_mode  # "overwrite" | "skip"
        self.selected_fields = selected_fields if selected_fields is not None else set()
        self.base_path = base_path

    def run(self):
        db = PixCakeDB(self.base_path)
        success, skipped, errors = 0, 0, []

        # Flatten all images
        all_images = []
        for meta in self.selected_projects:
            imgs = db.get_project_images(meta["user_id"], meta["project_id"])
            for img in imgs:
                img["_user_id"] = meta["user_id"]
                img["_project_id"] = meta["project_id"]
                img["_meta"] = meta
            all_images.extend(imgs)

        total = len(all_images)
        for i, img in enumerate(all_images):
            try:
                result = self._convert_one(db, img, self.output_dir)
                if result is True:
                    success += 1
                elif result == "skip":
                    skipped += 1
                else:
                    errors.append(f"{os.path.basename(img.get('originalImagePath', '?'))}: {result}")
            except Exception as e:
                errors.append(f"{os.path.basename(img.get('originalImagePath', '?'))}: {e}")

            self.progress.emit(i + 1)
            self.status.emit(f"转换中... {i+1}/{total}")

        self.finished.emit(success, skipped, errors)

    def _convert_one(self, db, img, output_dir):
        uid = img.get("_user_id")
        pid = img.get("_project_id")
        tid = img.get("id")
        raw_path = img.get("originalImagePath", "")

        exif_data = img.get("exif_parsed", {})
        _, palette_path = db.get_opt_record_paths(uid, pid, tid)

        mapped = {}
        palette_data = None

        # ---- Step 1: Read base WB from ext info first (so palette can override) ----
        ext = db.get_ext_info(uid, pid, img.get("uuidKey", ""))
        base_temp = None
        base_tint = None
        if isinstance(ext, dict):
            ei = ext.get("extendInfo", {})
            if not isinstance(ei, dict):
                ei = {}
            wbt = ei.get("WBT", {})
            if not isinstance(wbt, dict):
                wbt = {}
            as_shot_cct = (
                wbt.get("AsShot_CCT")
                if wbt.get("AsShot_CCT") is not None
                else _find_nested_value(ext, {"asshotcct"})
            )
            as_shot_tint = (
                wbt.get("AsShot_Tint")
                if wbt.get("AsShot_Tint") is not None
                else _find_nested_value(ext, {"asshottint"})
            )
            base_temp = _to_int_or_none(as_shot_cct)
            base_tint = _to_int_or_none(as_shot_tint)
            if base_temp is not None:
                mapped["WhiteBalance"] = "As Shot"

        # ---- Step 2: Process palette params (basic, HSL, color grading, curves, crop) ----
        if palette_path:
            palette_data = db.get_palette_params(palette_path)
            if isinstance(palette_data, dict):
                # Common.Params — basic + HSL
                common = palette_data.get("Common", {})
                if isinstance(common, dict):
                    common_params = common.get("Params", [])
                    mapped.update(map_pixcake_to_xmp(common_params, None))

                # Local[].StrParams — color grading, curves, etc.
                for local in palette_data.get("Local", []):
                    if not isinstance(local, dict):
                        continue
                    str_params = local.get("StrParams", [])
                    if isinstance(str_params, list):
                        mapped.update(map_pixcake_to_xmp(str_params, None))

                # Crop / geometry from Common.Crop or palette root
                crop = palette_data.get("Common", {}).get("Crop", {}) or palette_data.get("Crop", {})
                if isinstance(crop, dict):
                    if crop.get("Angle") is not None:
                        mapped["CropAngle"] = str(round(crop["Angle"], 2))
                    if crop.get("Left") is not None:
                        mapped["CropLeft"] = str(round(crop["Left"], 4))
                    if crop.get("Top") is not None:
                        mapped["CropTop"] = str(round(crop["Top"], 4))
                    if crop.get("Right") is not None:
                        mapped["CropRight"] = str(round(crop["Right"], 4))
                    if crop.get("Bottom") is not None:
                        mapped["CropBottom"] = str(round(crop["Bottom"], 4))
                    if any(k in crop for k in ("Angle", "Left", "Top")):
                        mapped["HasCrop"] = "True"
                        mapped["CropConstrainToWarp"] = "0"
                        mapped["AlreadyApplied"] = "False"

                # Tone Curve from ae arrays
                self._extract_curves(palette_data, mapped)

        # ---- Step 3: Merge Temperature / Tint ----
        # palette may have written offset values for Temperature/Tint (pf 3007/3008)
        # If we have base values from ext info, apply the palette offset on top
        if base_temp is not None:
            if "Temperature" in mapped:
                # mapped value is the offset from palette; apply to base
                try:
                    offset = float(mapped["Temperature"])
                    mapped["Temperature"] = str(int(base_temp + offset))
                except ValueError:
                    mapped["Temperature"] = str(base_temp)
            else:
                mapped["Temperature"] = str(base_temp)

        if base_tint is not None:
            if "Tint" in mapped:
                try:
                    offset = float(mapped["Tint"])
                    mapped["Tint"] = f"{int(base_tint + offset):+d}"
                except ValueError:
                    mapped["Tint"] = f"{base_tint:+d}"
            else:
                mapped["Tint"] = f"{base_tint:+d}"

        if base_temp is None and _is_signed_offset(mapped.get("Temperature", "")):
            mapped.pop("Temperature", None)
        if base_tint is None and _is_signed_offset(mapped.get("Tint", "")):
            mapped.pop("Tint", None)

        # ---- Step 4: Read star / pick / rotation from thumbnail table ----
        star = img.get("starLevel")
        if star is not None and 0 <= star <= 5:
            mapped["Rating"] = str(int(star))

        pick = img.get("selectFlag")
        if pick is not None:
            mapped["Pick"] = str(int(pick))

        rotation = img.get("rotation")
        if rotation is not None:
            mapped["Orientation"] = str(self._rotation_to_orientation(rotation))

        # ---- Step 5: Filter mapped fields based on selected_fields ----
        filtered_mapped = {}
        for k, v in mapped.items():
            is_allowed = False
            
            # 1. HSL
            if k.startswith(("HueAdjustment", "SaturationAdjustment", "LuminanceAdjustment")):
                if "HSL" in self.selected_fields:
                    is_allowed = True
            # 2. Color Grading
            elif k.startswith("ColorGrade"):
                if "ColorGrading" in self.selected_fields:
                    is_allowed = True
            # 3. Tone Curve points
            elif k.endswith("__points"):
                base_k = k[:-8]
                if base_k in self.selected_fields:
                    is_allowed = True
            # 4. Standard fields
            elif k in self.selected_fields:
                is_allowed = True
            # 5. Always allowed (standard non-configurable metadata or structural tags)
            elif k in ("Version", "CompatibleVersion", "ProcessVersion", "RawFileName", "AlreadyApplied", "HasSettings", "AllowFilters"):
                is_allowed = True
                
            if is_allowed:
                filtered_mapped[k] = v

        raw_meta = read_raw_metadata(raw_path) if os.path.exists(raw_path) else None
        xmp_content = generate_xmp(img, filtered_mapped, raw_meta, exif_data, self.selected_fields)

        xmp_name = os.path.splitext(os.path.basename(raw_path))[0] + ".xmp"
        xmp_path = os.path.join(output_dir, xmp_name)

        if os.path.exists(xmp_path) and self.overwrite_mode != "overwrite":
            return "skip"

        with open(xmp_path, "w", encoding="utf-8") as f:
            f.write(xmp_content)
        return True

    @staticmethod
    def _rotation_to_orientation(rotation):
        """Convert PixCake rotation (degrees) to EXIF Orientation."""
        rotation = int(rotation) % 360
        if rotation == 0:
            return 1    # Normal
        elif rotation == 90:
            return 6    # Rotate 90 CW
        elif rotation == 180:
            return 3    # Rotate 180
        elif rotation == 270:
            return 8    # Rotate 270 CW
        return 1        # Default: Normal

    @staticmethod
    def _extract_curves(palette_data, mapped):
        """Extract tone curve data from paletteCfg ae arrays."""
        curve_map = {
            21000: "",        # RGB combined
            90069: "Red",     # Red channel
            90070: "Green",   # Green channel
            90071: "Blue",    # Blue channel
        }
        params = palette_data.get("Common", {}).get("Params", [])
        for param in params:
            pf = param.get("pf")
            ae = param.get("ae")
            if pf in curve_map and ae and isinstance(ae, list) and len(ae) >= 4:
                suffix = curve_map[pf]
                field = f"ToneCurvePV2012{suffix}"
                # ae is flat: [x1,y1,x2,y2,...] → pair up
                points = []
                for i in range(0, len(ae) - 1, 2):
                    points.append(f"{round(ae[i])}, {round(ae[i+1])}")
                mapped[f"{field}__points"] = ";".join(points)
                mapped["ToneCurveName2012"] = "Custom"


# ============================================================
# Sync Settings Selector Widgets (Sidebar version)
# ============================================================

class SyncGroup(QFrame):
    """Collapsible rounded-border group containing a category header and option checkboxes."""

    state_changed = pyqtSignal()

    def __init__(self, title, options_dict, parent=None):
        super().__init__(parent)
        self.setObjectName("syncGroup")
        self._title = title
        self._options = options_dict  # {opt_label: field_list}
        self._collapsed = True
        self._updating = False

        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        # ---- Header row ----
        header = QWidget()
        header.setObjectName("syncGroupHeader")
        header.setCursor(QCursor(Qt.PointingHandCursor))
        header.mousePressEvent = self._on_header_click

        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 8, 10, 8)
        h_layout.setSpacing(8)

        # Collapse arrow
        self._arrow = QLabel("▶")
        self._arrow.setFixedWidth(14)
        self._arrow.setStyleSheet("color: #8E8E93; font-size: 10px; background: transparent;")
        h_layout.addWidget(self._arrow)

        # Category checkbox only controls selection. The title row controls collapse.
        self._cat_cb = self._make_checkbox("")
        self._cat_cb.setCursor(QCursor(Qt.PointingHandCursor))
        self._cat_cb.setFixedWidth(20)
        h_layout.addWidget(self._cat_cb)

        self._title_label = QLabel(self._title)
        self._title_label.setCursor(QCursor(Qt.PointingHandCursor))
        self._title_label.setStyleSheet("""
            QLabel {
                color: #F5F5F7;
                font-size: 13px;
                font-weight: 600;
                background: transparent;
            }
        """)
        self._title_label.mousePressEvent = self._on_header_click
        h_layout.addWidget(self._title_label, 1)

        self._outer.addWidget(header)

        # ---- Content area (collapsed by default) ----
        self._content = QWidget()
        self._content.setObjectName("syncGroupContent")
        self._content.setVisible(False)
        c_layout = QVBoxLayout(self._content)
        c_layout.setContentsMargins(12, 6, 12, 10)
        c_layout.setSpacing(8)

        self._opt_checkboxes = {}
        for opt_label, fields in self._options.items():
            cb = self._make_checkbox(opt_label)
            c_layout.addWidget(cb)
            self._opt_checkboxes[opt_label] = (cb, fields)

        self._outer.addWidget(self._content)

        # ---- Connect signals ----
        self._cat_cb.stateChanged.connect(self._on_cat_toggled)

    # ------------------------------------------------------------------
    @staticmethod
    def _make_checkbox(text):
        cb = QCheckBox(text)
        cb.setChecked(True)
        cb.setStyleSheet("""
            QCheckBox {
                color: #F5F5F7;
                font-size: 13px;
                spacing: 8px;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        return cb

    # ------------------------------------------------------------------
    def _on_header_click(self, event):
        self.set_collapsed(not self._collapsed)

    def _on_cat_toggled(self, state):
        if self._updating:
            return
        self._updating = True
        checked = (state == Qt.Checked)
        for cb, _ in self._opt_checkboxes.values():
            cb.setChecked(checked)
        self._updating = False
        self.state_changed.emit()

    def _on_opt_toggled(self):
        if self._updating:
            return
        self._updating = True
        self._sync_cat_state()
        self._updating = False
        self.state_changed.emit()

    def _sync_cat_state(self):
        checked = 0
        total = len(self._opt_checkboxes)
        for cb, _ in self._opt_checkboxes.values():
            if cb.isChecked():
                checked += 1
        if checked == total:
            self._cat_cb.setCheckState(Qt.Checked)
        elif checked == 0:
            self._cat_cb.setCheckState(Qt.Unchecked)
        else:
            self._cat_cb.setCheckState(Qt.PartiallyChecked)

    # ------------------------------------------------------------------
    def set_collapsed(self, collapsed):
        self._collapsed = collapsed
        self._content.setVisible(not collapsed)
        self._arrow.setText("▶" if collapsed else "▼")

    def set_all_checked(self, checked):
        self._updating = True
        for cb, _ in self._opt_checkboxes.values():
            cb.setChecked(checked)
        self._cat_cb.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._updating = False

    def are_all_checked(self):
        return all(cb.isChecked() for cb, _ in self._opt_checkboxes.values())

    def get_checked_fields(self):
        fields = set()
        for cb, f_list in self._opt_checkboxes.values():
            if cb.isChecked():
                fields.update(f_list)
        return fields


class SyncSettingsSidebar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("syncSidebar")
        self.setFixedWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(10)

        # ---- Title header ----
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(0)

        title_label = QLabel("同步设置")
        title_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #FFFFFF;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setObjectName("btnGhost")
        self.select_all_btn.setStyleSheet(
            "QPushButton#btnGhost { font-size: 13px; font-weight: 600; }"
        )
        self.select_all_btn.clicked.connect(self._toggle_select_all)
        header_layout.addWidget(self.select_all_btn)

        layout.addLayout(header_layout)

        # ---- Scroll area for groups ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical { background-color: transparent; width: 6px; margin: 2px; }
            QScrollBar::handle:vertical { background-color: #3A3A3C; border-radius: 3px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background-color: #48484A; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; width: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

        self._groups_container = QWidget()
        self._groups_container.setObjectName("groupsContainer")
        self._groups_container.setStyleSheet(
            "#groupsContainer { background-color: #1C1C1E; }"
        )
        self._groups_layout = QVBoxLayout(self._groups_container)
        self._groups_layout.setContentsMargins(14, 8, 14, 8)
        self._groups_layout.setSpacing(8)
        self._groups_layout.addStretch()

        scroll.setWidget(self._groups_container)
        layout.addWidget(scroll, 1)

        # ---- Sidebar QSS ----
        self.setStyleSheet("""
            QFrame#syncSidebar {
                background-color: #1C1C1E;
                border-left: 1px solid #2D2D2D;
            }
            QFrame#syncGroup {
                background-color: #1E1E20;
                border: 1px solid #2D2D2D;
                border-radius: 10px;
            }
            #syncGroupHeader {
                background-color: transparent;
            }
            #syncGroupContent {
                background-color: transparent;
            }
        """)

        # ---- Populate groups ----
        self._groups = []
        for cat_name, options in SYNC_HIERARCHY.items():
            group = SyncGroup(cat_name, options)
            group.state_changed.connect(self._update_select_all_button)
            self._groups.append(group)
            self._groups_layout.insertWidget(self._groups_layout.count() - 1, group)

        # Connect child checkboxes to parent sync
        for group in self._groups:
            for cb, _ in group._opt_checkboxes.values():
                cb.stateChanged.connect(group._on_opt_toggled)

        self._update_select_all_button()

    # ------------------------------------------------------------------
    def _toggle_select_all(self):
        all_checked = all(g.are_all_checked() for g in self._groups)
        new_state = not all_checked
        for group in self._groups:
            group.set_all_checked(new_state)
        self._update_select_all_button()

    def _update_select_all_button(self):
        total = sum(len(g._opt_checkboxes) for g in self._groups)
        checked = sum(
            sum(1 for cb, _ in g._opt_checkboxes.values() if cb.isChecked())
            for g in self._groups
        )
        if checked == total and total > 0:
            self.select_all_btn.setText("取消全选")
        else:
            self.select_all_btn.setText("全选")

    def get_selected_fields(self):
        selected = set()
        for group in self._groups:
            selected.update(group.get_checked_fields())
        return selected


class DarkComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMinimumHeight(34)

        popup = QListView(self)
        popup.setFrameShape(QFrame.NoFrame)
        popup.setUniformItemSizes(True)
        popup.setMouseTracking(True)
        popup.setSpacing(4)
        popup.setStyleSheet("""
            QListView {
                background-color: #1C1C1E;
                border: 1px solid #48484A;
                border-radius: 10px;
                padding: 6px;
                color: #F5F5F7;
                outline: 0;
            }
            QListView::item {
                min-height: 34px;
                padding: 0 12px;
                border-radius: 7px;
            }
            QListView::item:hover {
                background-color: #2C2C2E;
            }
            QListView::item:selected {
                background-color: #0A84FF;
                color: #FFFFFF;
            }
        """)
        self.setView(popup)
        self.setMaxVisibleItems(7)

    def showPopup(self):
        self.view().setMinimumWidth(self.width())
        if self.currentIndex() >= 0:
            self.view().scrollTo(self.model().index(self.currentIndex(), 0))
        super().showPopup()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#AEAEB2"), 1.8))

        center_x = self.width() - 18
        center_y = self.height() // 2
        painter.drawLine(center_x - 4, center_y - 2, center_x, center_y + 2)
        painter.drawLine(center_x, center_y + 2, center_x + 4, center_y - 2)


class CardBorderOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        card = self.parent()
        selected = bool(getattr(card, "selected", False))
        hovered = bool(getattr(card, "_hovered", False))
        color = "#0A84FF" if selected else "#48484A" if hovered else "#2D2D2D"

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(color), 2))
        painter.setBrush(Qt.NoBrush)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.drawRoundedRect(rect, 12, 12)


# ============================================================
# Project Card Widget
# ============================================================


# ============================================================
# Project Card Widget
# ============================================================

class ProjectCard(QFrame):
    clicked = pyqtSignal(object)

    def __init__(self, meta, parent=None):
        super().__init__(parent)
        self.meta = meta
        self._selected = False
        self._hovered = False
        self._thumb_pixmap = None
        self.setObjectName("cardFrame")
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        # Thumbnail
        self.thumb = QLabel()
        self.thumb.setObjectName("cardThumb")
        self.thumb.setFixedSize(CARD_W - 4, THUMB_H)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setScaledContents(False)
        layout.addWidget(self.thumb)

        # Text area
        text_widget = QWidget()
        text_widget.setStyleSheet("background: transparent;")
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(12, 10, 12, 12)
        text_layout.setSpacing(2)

        self.name_label = QLabel(meta.get("name", "Unknown"))
        self.name_label.setObjectName("cardName")
        self.name_label.setWordWrap(True)
        self.name_label.setMaximumHeight(38)

        details = meta.get("date", "")
        count = meta.get("count") or 0
        if count:
            details = f"{details} · {count} 张" if details else f"{count} 张"
        self.date_label = QLabel(details)
        self.date_label.setObjectName("cardDate")

        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.date_label)
        text_layout.addStretch()

        layout.addWidget(text_widget)

        # Rounded Selection Badge floating on top
        self.select_badge = QLabel(self)
        self.select_badge.setFixedSize(22, 22)
        self.select_badge.setStyleSheet(
            "background-color: #0A84FF;"
            "color: #FFFFFF;"
            "border-radius: 11px;"
            "font-weight: bold;"
            "font-size: 12px;"
            "border: 1.5px solid #1C1C1E;"
        )
        self.select_badge.setText("✓")
        self.select_badge.setAlignment(Qt.AlignCenter)
        self.select_badge.move(CARD_W - 36, 10)
        self.select_badge.setVisible(False)

        self.border_overlay = CardBorderOverlay(self)
        self.border_overlay.setGeometry(self.rect())
        self.border_overlay.raise_()
        self.select_badge.raise_()

        # Load thumbnail in background
        self._load_thumbnail()

    def set_card_width(self, width):
        width = max(1, int(width))
        if width == self.width():
            return
        self.setFixedSize(width, CARD_H)
        self.thumb.setFixedSize(max(1, width - 4), THUMB_H)
        self.select_badge.move(width - 36, 10)
        self.border_overlay.setGeometry(self.rect())
        self.border_overlay.raise_()
        self.select_badge.raise_()
        self._refresh_thumbnail()

    def _load_thumbnail(self):
        path = self.meta.get("thumbnail")
        if path and os.path.exists(path):
            try:
                self._thumb_pixmap = QPixmap(path)
                self._refresh_thumbnail()
            except Exception:
                self.thumb.setText("📷 Error")
        else:
            self.thumb.setStyleSheet(
                "background-color: #2C2C2E;"
                "color: #8E8E93;"
                "font-weight: 500;"
                "font-size: 14px;"
                "border-top-left-radius: 8px;"
                "border-top-right-radius: 8px;"
            )
            self.thumb.setText("📁 空白项目")

    def _refresh_thumbnail(self):
        if not self._thumb_pixmap or self._thumb_pixmap.isNull():
            return
        thumb_size = self.thumb.size()
        scaled = self._thumb_pixmap.scaled(
            max(1, thumb_size.width() - THUMB_PADDING),
            max(1, thumb_size.height() - THUMB_PADDING),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.thumb.setPixmap(scaled)

    @property
    def selected(self):
        return self._selected

    @selected.setter
    def selected(self, val):
        self._selected = val
        self.setProperty("selected", "true" if val else "false")
        self.select_badge.setVisible(val)
        self.style().unpolish(self)
        self.style().polish(self)
        self.border_overlay.update()

    def enterEvent(self, event):
        self._hovered = True
        self.border_overlay.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.border_overlay.update()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "border_overlay"):
            self.border_overlay.setGeometry(self.rect())
            self.border_overlay.raise_()
            self.select_badge.raise_()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self)
        super().mousePressEvent(event)


# ============================================================
# Custom Title Bar
# ============================================================

class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self._parent = parent
        self._drag_pos = None
        self.setObjectName("titleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)

        # Title (left side, Windows style)
        title = QLabel(APP_TITLE)
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        layout.addStretch()

        # Right: Windows-style window controls (Min, Max, Close)
        win_buttons = [("btnMin", "—"), ("btnMax", "□"), ("btnClose", "✕")]
        for obj_name, text in win_buttons:
            btn = QPushButton(text)
            btn.setObjectName(obj_name)
            btn.setFixedSize(46, 32)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(
                lambda checked, n=obj_name: self._window_action(n))
            layout.addWidget(btn)

    def _window_action(self, name):
        if name == "btnMin":
            self._parent.showMinimized()
        elif name == "btnMax":
            btn = self.findChild(QPushButton, "btnMax")
            if self._parent.isMaximized():
                self._parent.showNormal()
                if btn:
                    btn.setText("□")
            else:
                self._parent.showMaximized()
                if btn:
                    btn.setText("❐")
        elif name == "btnClose":
            self._parent.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            delta = event.globalPos() - self._drag_pos
            self._parent.move(self._parent.pos() + delta)
            self._drag_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            btn = self.findChild(QPushButton, "btnMax")
            if self._parent.isMaximized():
                self._parent.showNormal()
                if btn:
                    btn.setText("□")
            else:
                self._parent.showMaximized()
                if btn:
                    btn.setText("❐")


# ============================================================
# Main Window
# ============================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.resize(1100, 720)
        self.setMinimumSize(800, 500)
        self.setAttribute(Qt.WA_TranslucentBackground,
                          False)

        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        saved_base_path = self.settings.value(
            SETTINGS_PIXCAKE_BASE_KEY, PIXCAKE_BASE, type=str)
        self.db = PixCakeDB(self._normalize_pixcake_base(saved_base_path))
        self.all_projects = []
        self.cards = []
        self.selected_cards = set()

        self._build_ui()
        self._apply_qss()

    def showEvent(self, event):
        super().showEvent(event)
        # Load projects after window is shown so viewport has correct size
        if not self.all_projects:
            QTimer.singleShot(50, self._load_projects)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Title bar
        self.title_bar = TitleBar(self)
        main_layout.addWidget(self.title_bar)

        # ---- Toolbar ----
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 12, 16, 12)
        tb_layout.setSpacing(12)

        self.software_path_btn = QPushButton("软件路径")
        self.software_path_btn.setObjectName("btnSoftwarePath")
        self.software_path_btn.clicked.connect(self._browse_software_path)
        tb_layout.addWidget(self.software_path_btn)

        # User selector
        user_label = QLabel("用户")
        user_label.setStyleSheet("font-weight: 600; color: #AEAEB2;")
        tb_layout.addWidget(user_label)

        self.user_combo = DarkComboBox()
        self.user_combo.setMinimumWidth(140)
        self.user_combo.currentIndexChanged.connect(self._on_user_changed)
        tb_layout.addWidget(self.user_combo)

        tb_layout.addSpacing(16)

        self.info_label = QLabel("")
        self.info_label.setObjectName("infoLabel")
        tb_layout.addWidget(self.info_label)

        tb_layout.addStretch()

        # Buttons
        for text, obj_name, slot in [
            ("全选", "btnGhost", self._select_all),
            ("取消", "btnGhost", self._deselect_all),
        ]:
            btn = QPushButton(text)
            btn.setObjectName(obj_name)
            btn.clicked.connect(slot)
            tb_layout.addWidget(btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("btnSecondary")
        refresh_btn.clicked.connect(self._load_projects)
        tb_layout.addWidget(refresh_btn)

        main_layout.addWidget(toolbar)

        # ---- Main Body Horizontal Layout (Left: Cards Grid, Right: Sync Settings Sidebar) ----
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # ---- Card Grid (Scroll Area) ----
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.card_container = QWidget()
        self.card_container.setObjectName("cardContainer")
        # Use a VBox with stretch so cards stay at top
        container_layout = QVBoxLayout(self.card_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self._card_grid = QGridLayout()
        self._card_grid.setContentsMargins(CARD_GAP, CARD_GAP, CARD_GAP, CARD_GAP)
        self._card_grid.setSpacing(CARD_GAP)
        self._card_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        container_layout.addLayout(self._card_grid)
        container_layout.addStretch()

        self.scroll_area.setWidget(self.card_container)
        body_layout.addWidget(self.scroll_area, 1)

        # ---- Sync Settings Sidebar ----
        self.sync_sidebar = SyncSettingsSidebar()
        body_layout.addWidget(self.sync_sidebar)

        main_layout.addLayout(body_layout, 1)

        # ---- Bottom Bar ----
        bottom = QWidget()
        bottom.setObjectName("bottomBar")
        btm_layout = QHBoxLayout(bottom)
        btm_layout.setContentsMargins(16, 12, 16, 12)
        btm_layout.setSpacing(12)

        out_label = QLabel("输出到")
        out_label.setStyleSheet("font-weight: 600; color: #AEAEB2;")
        btm_layout.addWidget(out_label)

        self.out_path = QLineEdit()
        self.out_path.setPlaceholderText("选择 XMP 输出文件夹...")
        self.out_path.setFixedWidth(320)
        btm_layout.addWidget(self.out_path)

        browse_btn = QPushButton("浏览")
        browse_btn.setObjectName("btnSecondary")
        browse_btn.clicked.connect(self._browse_output)
        btm_layout.addWidget(browse_btn)

        btm_layout.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(180)
        self.progress.setVisible(False)
        btm_layout.addWidget(self.progress)

        self.convert_btn = QPushButton("转换为 XMP")
        self.convert_btn.setObjectName("btnConvert")
        self.convert_btn.clicked.connect(self._convert)
        btm_layout.addWidget(self.convert_btn)

        main_layout.addWidget(bottom)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("就绪 — 正在加载项目...")
        main_layout.addWidget(self.status_bar)
        self._update_software_path_button()

    def _apply_qss(self):
        self.setStyleSheet(QSS)

    def _normalize_pixcake_base(self, path):
        path = os.path.expandvars(os.path.expanduser(path or PIXCAKE_BASE))
        path = os.path.normpath(path)
        if (os.path.basename(path).lower() == "db"
                and os.path.isfile(os.path.join(path, "base.db"))):
            return os.path.dirname(path)
        if os.path.basename(path).lower() == "project":
            return os.path.dirname(path)
        nested = os.path.join(path, "PixCake-qt_pro")
        if (os.path.isdir(nested)
                and not os.path.isdir(os.path.join(path, "db"))):
            return nested
        return path

    def _is_software_path_readable(self):
        return os.path.isfile(os.path.join(self.db.base_path, "db", "base.db"))

    def _update_software_path_button(self):
        valid = self._is_software_path_readable()
        self.software_path_btn.setProperty(
            "pathValid", "true" if valid else "false")
        self.software_path_btn.setToolTip(
            f"{'已读取到 PixCake 数据' if valid else '未读取到 PixCake 数据'}\n"
            f"{self.db.base_path}")
        self.software_path_btn.style().unpolish(self.software_path_btn)
        self.software_path_btn.style().polish(self.software_path_btn)

    def _browse_software_path(self):
        folder = QFileDialog.getExistingDirectory(
            self, "选择 PixCake 软件数据文件夹", self.db.base_path)
        if not folder:
            return

        base_path = self._normalize_pixcake_base(folder)
        self.db = PixCakeDB(base_path)
        self.settings.setValue(SETTINGS_PIXCAKE_BASE_KEY, base_path)
        self.all_projects = []
        self._update_software_path_button()
        self._load_projects()

    # ============================================================
    # Data
    # ============================================================

    def _load_projects(self):
        """Load projects synchronously (fast, just DB reads). Threads only for conversion."""
        self._update_software_path_button()
        self.status_bar.showMessage("正在加载项目...")
        self.convert_btn.setEnabled(False)
        QApplication.processEvents()

        try:
            projects = self.db.get_all_projects_with_meta()
        except Exception as e:
            self.status_bar.showMessage(f"加载失败: {e}")
            return

        self._on_projects_loaded(projects)

    def _on_projects_loaded(self, projects):
        self.all_projects = projects

        # Collect unique user IDs
        user_ids = list(dict.fromkeys(p["user_id"] for p in projects))
        user_labels = []
        for uid in user_ids:
            label = next(
                (p.get("user_display_name") for p in projects
                 if p["user_id"] == uid and p.get("user_display_name")),
                f"User {uid}")
            user_labels.append(label)

        self.user_combo.blockSignals(True)
        self.user_combo.clear()
        self.user_combo.addItems(user_labels)
        self.user_combo.setCurrentIndex(0)
        self.user_combo.blockSignals(False)

        self.convert_btn.setEnabled(bool(user_ids))

        if user_ids:
            self._filter_projects(user_ids[0])
            self.status_bar.showMessage(
                f"已加载 {len(projects)} 个项目 — 点击卡片选择项目，然后设置输出路径并转换")
        else:
            self._show_cards([])
            self.status_bar.showMessage("未找到 PixCake 数据")

    def _on_user_changed(self, idx):
        if idx < 0 or not self.all_projects:
            return
        user_ids = list(dict.fromkeys(p["user_id"] for p in self.all_projects))
        if idx < len(user_ids):
            self._filter_projects(user_ids[idx])

    def _filter_projects(self, user_id):
        projects = [p for p in self.all_projects if p["user_id"] == user_id]
        projects.sort(key=lambda p: p.get("date", ""), reverse=True)
        self._show_cards(projects)

    # ============================================================
    # Card Grid
    # ============================================================

    def _grid_metrics(self):
        grid = self._card_grid
        margins = grid.contentsMargins()
        scroll_w = (self.scroll_area.viewport().width()
                    if self.scroll_area.viewport() else self.width())
        content_w = scroll_w - margins.left() - margins.right()
        cols = max(1, (content_w + CARD_GAP) // (CARD_W + CARD_GAP))
        card_w = (content_w - (CARD_GAP * (cols - 1))) // cols
        return cols, max(1, card_w)

    def _show_cards(self, projects):
        # Clear existing cards
        for card in self.cards:
            card.setParent(None)
            card.deleteLater()
        self.cards.clear()
        self.selected_cards.clear()

        # Clear grid (keep spacers too)
        grid = self._card_grid
        while grid.count():
            item = grid.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        if not projects:
            self.info_label.setText("没有项目")
            return

        cols, card_w = self._grid_metrics()

        for i, meta in enumerate(projects):
            card = ProjectCard(meta)
            card.set_card_width(card_w)
            card.clicked.connect(self._on_card_clicked)
            self.cards.append(card)
            row, col = divmod(i, cols)
            grid.addWidget(card, row, col, Qt.AlignTop | Qt.AlignLeft)

        # Fill last row with invisible spacers so cards stay left-aligned
        last_row_cols = len(projects) % cols
        if last_row_cols > 0:
            for j in range(cols - last_row_cols):
                spacer = QWidget()
                spacer.setFixedSize(card_w, CARD_H)
                grid.addWidget(spacer, len(projects) // cols, last_row_cols + j)

        # Keep columns at card width so thumbnail frames do not drift in wider rows.
        for c in range(grid.columnCount()):
            grid.setColumnStretch(c, 0)
        grid.invalidate()

        self.info_label.setText(f"共 {len(projects)} 个项目")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.cards:
            self._relayout_cards()

    def _relayout_cards(self):
        if not self.cards:
            return
        grid = self._card_grid
        cols, card_w = self._grid_metrics()

        # Remove all items from grid (preserve card widgets, destroy spacers)
        while grid.count():
            item = grid.takeAt(0)
            w = item.widget()
            if w and w not in self.cards:
                w.setParent(None)
                w.deleteLater()

        # Re-add cards with new column count
        for i, card in enumerate(self.cards):
            card.set_card_width(card_w)
            row, col = divmod(i, cols)
            grid.addWidget(card, row, col, Qt.AlignTop | Qt.AlignLeft)

        # Fill last row
        last_row_cols = len(self.cards) % cols
        if last_row_cols > 0:
            for j in range(cols - last_row_cols):
                spacer = QWidget()
                spacer.setFixedSize(card_w, CARD_H)
                grid.addWidget(spacer, len(self.cards) // cols, last_row_cols + j)

        # Keep columns at card width so thumbnail frames do not drift in wider rows.
        for c in range(grid.columnCount()):
            grid.setColumnStretch(c, 0)
        grid.invalidate()

    # ============================================================
    # Selection
    # ============================================================

    def _on_card_clicked(self, card):
        if card in self.selected_cards:
            self.selected_cards.discard(card)
            card.selected = False
        else:
            self.selected_cards.add(card)
            card.selected = True

    def _select_all(self):
        for card in self.cards:
            self.selected_cards.add(card)
            card.selected = True

    def _deselect_all(self):
        for card in self.cards:
            self.selected_cards.discard(card)
            card.selected = False
        self.selected_cards.clear()

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(
            self, "选择 XMP 输出文件夹")
        if folder:
            self.out_path.setText(folder)

    # ============================================================
    # Conversion
    # ============================================================

    def _convert(self):
        if not self.selected_cards:
            show_message(self, QMessageBox.Warning, "未选择",
                         "请先选择至少一个项目")
            return

        output_dir = self.out_path.text().strip()
        if not output_dir:
            show_message(self, QMessageBox.Critical, "错误",
                         "请指定输出文件夹")
            return
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except OSError as e:
                show_message(self, QMessageBox.Critical, "错误",
                             f"无法创建文件夹:\n{e}")
                return

        selected_metas = [card.meta for card in self.selected_cards]

        # ---- Pre-scan for existing XMP files ----
        overwrite_mode = "skip"  # default: skip existing
        existing_files = []
        db = self.db
        for meta in selected_metas:
            imgs = db.get_project_images(meta["user_id"], meta["project_id"])
            for img in imgs:
                raw_path = img.get("originalImagePath", "")
                if not raw_path:
                    continue
                xmp_name = os.path.splitext(os.path.basename(raw_path))[0] + ".xmp"
                xmp_path = os.path.join(output_dir, xmp_name)
                if os.path.exists(xmp_path):
                    existing_files.append(xmp_name)

        if existing_files:
            existing_files.sort()
            preview = "\n".join(f"  • {f}" for f in existing_files[:10])
            if len(existing_files) > 10:
                preview += f"\n  ...及其他 {len(existing_files) - 10} 个文件"

            msgbox = QMessageBox(self)
            msgbox.setWindowTitle("文件已存在")
            msgbox.setText(
                f"发现 {len(existing_files)} 个 XMP 文件已存在：\n\n{preview}\n\n如何处理？")
            msgbox.setIcon(QMessageBox.Question)
            msgbox.setStyleSheet(MESSAGE_BOX_QSS)
            overwrite_btn = msgbox.addButton("覆盖全部", QMessageBox.YesRole)
            skip_btn = msgbox.addButton("跳过已存在", QMessageBox.NoRole)
            cancel_btn = msgbox.addButton("取消", QMessageBox.RejectRole)
            msgbox.setDefaultButton(skip_btn)
            msgbox.exec()
            clicked = msgbox.clickedButton()

            if clicked == cancel_btn:
                return
            elif clicked == overwrite_btn:
                overwrite_mode = "overwrite"
            # else: keep "skip"

        self.progress.setVisible(True)
        self.progress.setMaximum(len(selected_metas))  # placeholder, updated by worker
        self.progress.setValue(0)
        self.convert_btn.setEnabled(False)
        self.status_bar.showMessage("转换中...")

        selected_fields = self.sync_sidebar.get_selected_fields()
        self._cvt_worker = ConvertWorker(
            selected_metas, output_dir, overwrite_mode, selected_fields,
            self.db.base_path)
        self._cvt_thread = QThread()
        self._cvt_worker.moveToThread(self._cvt_thread)
        self._cvt_thread.started.connect(self._cvt_worker.run)
        self._cvt_worker.progress.connect(self.progress.setValue)
        self._cvt_worker.status.connect(self.status_bar.showMessage)
        self._cvt_worker.finished.connect(self._on_convert_done)
        self._cvt_worker.finished.connect(self._cvt_thread.quit)
        self._cvt_thread.start()

    def _on_convert_done(self, success, skipped, errors):
        self.convert_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status_bar.showMessage(
            f"完成 — {success} 成功, {skipped} 跳过, {len(errors)} 失败")

        msg = f"转换完成！\n\n成功: {success} 个 XMP 文件"
        if skipped:
            msg += f"\n跳过(已存在): {skipped}"
        if errors:
            msg += f"\n失败: {len(errors)}"
            if len(errors) <= 8:
                msg += "\n\n" + "\n".join(errors)
            else:
                msg += "\n\n" + "\n".join(errors[:8]) + \
                       f"\n...及其他 {len(errors) - 8} 个错误"

        show_message(self, QMessageBox.Information, "转换完成", msg)


# ============================================================
# Main
# ============================================================

def main():
    # High-DPI support
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("PixCake XMP Converter")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
