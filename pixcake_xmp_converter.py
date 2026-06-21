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
from xml.dom import minidom
from datetime import datetime, timezone, timedelta
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QProgressBar,
    QScrollArea, QFrame, QFileDialog, QMessageBox, QSizePolicy,
    QGridLayout, QSpacerItem, QStatusBar, QMenuBar, QAction,
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QObject, QTimer, QSize, QPoint, QRect,
)
from PyQt5.QtGui import (
    QFont, QPixmap, QImage, QPalette, QColor, QIcon,
    QCursor, QPainter,
)

# ============================================================
# Configuration
# ============================================================

PIXCAKE_BASE = os.path.expandvars(r"%APPDATA%\PixCake-qt_pro")
DB_DIR = os.path.join(PIXCAKE_BASE, "db")
PROJECT_DIR = os.path.join(PIXCAKE_BASE, "project")
CST = timezone(timedelta(hours=8))
APP_TITLE = "PixCake → Lightroom XMP"

CARD_W = 220
CARD_H = 210
CARD_GAP = 16
THUMB_H = 140
THUMB_PADDING = 10


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
            return [dict(u) for u in conn.execute(
                "SELECT id, user_id, created_time, login_time FROM user")]
        finally:
            conn.close()

    def get_user_projects(self, user_id):
        user_dir = os.path.join(self.project_dir, f"user_{user_id}")
        if not os.path.exists(user_dir):
            return []
        return sorted(
            [e for e in os.listdir(user_dir)
             if os.path.isdir(os.path.join(user_dir, e))],
            reverse=True)

    def get_project_meta(self, user_id, project_id):
        proj_db_dir = self._proj_db_dir(project_id)
        proj_cache_dir = self._proj_cache_dir(project_id)
        proj_db = os.path.join(self.db_dir, f"user_{user_id}",
                               proj_db_dir, "project.db")
        result = {"name": f"Project {project_id}", "date": "",
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
            if folders:
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
            for proj_dir in self.get_user_projects(uid):
                pid = proj_dir.replace("project_", "")
                all_projects.append(self.get_project_meta(uid, pid))
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
    if not metadata:
        try:
            import exifread
            with open(filepath, "rb") as f:
                for tag, value in exifread.process_file(f, details=False).items():
                    metadata[tag] = str(value)
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

def generate_xmp(image_info, crs_fields, raw_metadata=None, exif_data=None):
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

    if image_info.get("capture_dt"):
        cd = image_info["capture_dt"].strftime("%Y-%m-%dT%H:%M:%S.00+08:00")
        desc.set(f"{{{NS['xmp']}}}CreateDate", cd)
        desc.set(f"{{{NS['photoshop']}}}DateCreated", cd)
        desc.set(f"{{{NS['exif']}}}DateTimeOriginal", cd)

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
    orientation = crs_fields.pop("Orientation", "1")
    desc.set(f"{{{NS['tiff']}}}Orientation", str(orientation))

    w, h = image_info.get("originalWidth", 0) or 0, image_info.get("originalHeight", 0) or 0
    if w and h:
        desc.set(f"{{{NS['tiff']}}}ImageWidth", str(w))
        desc.set(f"{{{NS['tiff']}}}ImageLength", str(h))

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
            desc.set(ns_key, v)

    iso = get_val("ISOSpeedRatings")
    if iso:
        iso_seq = ET.SubElement(desc, f"{{{NS['exif']}}}ISOSpeedRatings")
        seq = ET.SubElement(iso_seq, f"{{{NS['rdf']}}}Seq")
        li = ET.SubElement(seq, f"{{{NS['rdf']}}}li")
        li.text = str(iso)

    desc.set(f"{{{NS['exif']}}}PixelXDimension", str(w))
    desc.set(f"{{{NS['exif']}}}PixelYDimension", str(h))

    for ns_key, ek in [
        (f"{{{NS['aux']}}}SerialNumber", "SerialNumber"),
        (f"{{{NS['aux']}}}LensInfo", "LensSpecification"),
        (f"{{{NS['aux']}}}Lens", "LensModel"),
        (f"{{{NS['exifEX']}}}LensModel", "LensModel"),
        (f"{{{NS['aux']}}}LensSerialNumber", "LensSerialNumber"),
    ]:
        v = get_val(ek)
        if v:
            desc.set(ns_key, str(v))

    raw_ext = os.path.splitext(image_info.get("originalImagePath", ""))[1]
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

    for field, value in crs_fields.items():
        if field.endswith("__points"):
            # Tone curve: render as <rdf:Seq> of <rdf:li>x, y</rdf:li>
            base_field = field[:-8]  # strip "__points"
            tc = ET.SubElement(desc, f"{{{NS['crs']}}}{base_field}")
            tc_seq = ET.SubElement(tc, f"{{{NS['rdf']}}}Seq")
            for pt in value.split(";"):
                li = ET.SubElement(tc_seq, f"{{{NS['rdf']}}}li")
                li.text = pt
        else:
            desc.set(f"{{{NS['crs']}}}{field}", str(value))

    defaults = {
        "WhiteBalance": "As Shot", "AutoLateralCA": "1",
        "LensProfileEnable": "1", "PerspectiveUpright": "0",
        "HDREditMode": "0", "CurveRefineSaturation": "100",
        "OverrideLookVignette": "False", "CameraProfile": "Adobe Standard",
        "HasSettings": "True", "AlreadyApplied": "False", "AllowFilters": "1",
    }
    for field, value in defaults.items():
        if field not in crs_fields:
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

    # Write default (linear) tone curves for channels that don't have custom curves
    for suffix in ["", "Red", "Green", "Blue"]:
        field_name = f"ToneCurvePV2012{suffix}"
        if field_name not in crs_fields:
            tc = ET.SubElement(desc, f"{{{NS['crs']}}}{field_name}")
            tc_seq = ET.SubElement(tc, f"{{{NS['rdf']}}}Seq")
            for pt in ["0, 0", "255, 255"]:
                li = ET.SubElement(tc_seq, f"{{{NS['rdf']}}}li")
                li.text = pt

    rough = ET.tostring(root, encoding="unicode")
    try:
        return minidom.parseString(rough).toprettyxml(
            indent=" ", encoding="UTF-8").decode("utf-8")
    except Exception:
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + rough


# ============================================================
# QSS Stylesheet — Tailwind-inspired
# ============================================================

QSS = r"""
/* ===== Global ===== */
* {
    font-family: 'Inter', 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #F1F5F9;
}

/* ===== Title Bar ===== */
#titleBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    min-height: 42px;
    max-height: 42px;
}
#titleLabel {
    font-size: 13px;
    font-weight: 600;
    color: #1E293B;
    padding-left: 12px;
}
#btnMin, #btnMax, #btnClose {
    border: none;
    border-radius: 0;
    padding: 0;
    min-width: 46px;
    min-height: 42px;
    max-width: 46px;
    max-height: 42px;
    font-size: 15px;
}
#btnMin { color: #64748B; }
#btnMin:hover { background-color: #F1F5F9; color: #1E293B; }
#btnMax { color: #64748B; }
#btnMax:hover { background-color: #F1F5F9; color: #1E293B; }
#btnClose { color: #64748B; }
#btnClose:hover { background-color: #EF4444; color: #FFFFFF; }

/* ===== Top Toolbar ===== */
#toolbar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    padding: 12px 16px;
}

/* ===== ComboBox ===== */
QComboBox {
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 6px 12px;
    min-width: 120px;
    color: #1E293B;
}
QComboBox:hover { border-color: #CBD5E1; }
QComboBox:focus { border: 2px solid #3B82F6; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #E2E8F0;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 4px;
    selection-background-color: #EFF6FF;
    selection-color: #1E293B;
    outline: none;
}

/* ===== PushButton ===== */
QPushButton {
    background-color: #2563EB;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover { background-color: #1D4ED8; }
QPushButton:pressed { background-color: #1E40AF; }
QPushButton:disabled { background-color: #94A3B8; }

QPushButton#btnSecondary {
    background-color: #FFFFFF;
    color: #475569;
    border: 1px solid #E2E8F0;
    font-weight: 500;
}
QPushButton#btnSecondary:hover {
    background-color: #F8FAFC;
    border-color: #CBD5E1;
}

QPushButton#btnGhost {
    background-color: transparent;
    color: #475569;
    border: none;
    font-weight: 500;
    padding: 6px 12px;
}
QPushButton#btnGhost:hover {
    background-color: #F1F5F9;
    color: #1E293B;
}

QPushButton#btnConvert {
    background-color: #2563EB;
    color: #FFFFFF;
    border-radius: 6px;
    padding: 10px 28px;
    font-size: 14px;
    font-weight: 700;
    min-width: 160px;
}

/* ===== LineEdit ===== */
QLineEdit {
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 8px 12px;
    color: #1E293B;
    selection-background-color: #BFDBFE;
}
QLineEdit:hover { border-color: #CBD5E1; }
QLineEdit:focus { border: 2px solid #3B82F6; }

/* ===== Scroll Area ===== */
QScrollArea {
    border: none;
    background-color: #F1F5F9;
}
QScrollArea > QWidget > QWidget {
    background-color: #F1F5F9;
}
QScrollBar:vertical {
    background-color: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #CBD5E1;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background-color: #94A3B8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0; width: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

/* ===== Project Card ===== */
#cardFrame {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
}
#cardFrame:hover {
    border-color: #93C5FD;
}
#cardFrame[selected="true"] {
    border: 2px solid #3B82F6;
    background-color: #EFF6FF;
}
#cardThumb {
    background-color: #E2E8F0;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}
#cardName {
    font-size: 13px;
    font-weight: 600;
    color: #1E293B;
    padding: 4px 0 0 0;
}
#cardDate {
    font-size: 12px;
    color: #94A3B8;
    padding: 2px 0 0 0;
}

/* ===== Bottom Bar ===== */
#bottomBar {
    background-color: #FFFFFF;
    border-top: 1px solid #E2E8F0;
    padding: 12px 16px;
}

/* ===== ProgressBar ===== */
QProgressBar {
    background-color: #E2E8F0;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #2563EB;
    border-radius: 4px;
}

/* ===== StatusBar ===== */
QStatusBar {
    background-color: #F8FAFC;
    border-top: 1px solid #E2E8F0;
    color: #64748B;
    font-size: 12px;
    padding: 2px 8px;
}

/* ===== Info Label ===== */
#infoLabel {
    color: #64748B;
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

    def __init__(self, selected_projects, output_dir, overwrite_mode="skip"):
        super().__init__()
        self.selected_projects = selected_projects
        self.output_dir = output_dir
        self.overwrite_mode = overwrite_mode  # "overwrite" | "skip"

    def run(self):
        db = PixCakeDB()
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
            if wbt.get("AsShot_CCT"):
                mapped["WhiteBalance"] = "As Shot"
                base_temp = int(wbt["AsShot_CCT"])
            if wbt.get("AsShot_Tint") is not None:
                base_tint = int(wbt["AsShot_Tint"])

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

        raw_meta = read_raw_metadata(raw_path) if os.path.exists(raw_path) else None
        xmp_content = generate_xmp(img, mapped, raw_meta, exif_data)

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
# Project Card Widget
# ============================================================

class ProjectCard(QFrame):
    clicked = pyqtSignal(object)

    def __init__(self, meta, parent=None):
        super().__init__(parent)
        self.meta = meta
        self._selected = False
        self._thumb_pixmap = None
        self.setObjectName("cardFrame")
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Thumbnail
        self.thumb = QLabel()
        self.thumb.setObjectName("cardThumb")
        self.thumb.setFixedSize(CARD_W, THUMB_H)
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

        self.date_label = QLabel(meta.get("date", ""))
        self.date_label.setObjectName("cardDate")

        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.date_label)
        text_layout.addStretch()

        layout.addWidget(text_widget)

        # Load thumbnail in background
        self._load_thumbnail()

    def set_card_width(self, width):
        width = max(1, int(width))
        if width == self.width():
            return
        self.setFixedSize(width, CARD_H)
        self.thumb.setFixedSize(width, THUMB_H)
        self._refresh_thumbnail()

    def _load_thumbnail(self):
        path = self.meta.get("thumbnail")
        if path and os.path.exists(path):
            try:
                self._thumb_pixmap = QPixmap(path)
                self._refresh_thumbnail()
            except Exception:
                self.thumb.setText("📷")

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
        self.style().unpolish(self)
        self.style().polish(self)

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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # App icon + title
        title = QLabel(APP_TITLE)
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        layout.addStretch()

        # Min / Max / Close
        for obj_name, text in [("btnMin", "─"), ("btnMax", "□"), ("btnClose", "✕")]:
            btn = QPushButton(text)
            btn.setObjectName(obj_name)
            btn.setFlat(True)
            btn.clicked.connect(
                lambda checked, n=obj_name: self._window_action(n))
            layout.addWidget(btn)

    def _window_action(self, name):
        if name == "btnMin":
            self._parent.showMinimized()
        elif name == "btnMax":
            if self._parent.isMaximized():
                self._parent.showNormal()
            else:
                self._parent.showMaximized()
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
            if self._parent.isMaximized():
                self._parent.showNormal()
            else:
                self._parent.showMaximized()


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

        self.db = PixCakeDB()
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

        # User selector
        user_label = QLabel("用户")
        user_label.setStyleSheet("font-weight: 600; color: #475569;")
        tb_layout.addWidget(user_label)

        self.user_combo = QComboBox()
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
        main_layout.addWidget(self.scroll_area, 1)

        # ---- Bottom Bar ----
        bottom = QWidget()
        bottom.setObjectName("bottomBar")
        btm_layout = QHBoxLayout(bottom)
        btm_layout.setContentsMargins(16, 12, 16, 12)
        btm_layout.setSpacing(12)

        out_label = QLabel("输出到")
        out_label.setStyleSheet("font-weight: 600; color: #475569;")
        btm_layout.addWidget(out_label)

        self.out_path = QLineEdit()
        self.out_path.setPlaceholderText("选择 XMP 输出文件夹...")
        self.out_path.setMinimumWidth(300)
        btm_layout.addWidget(self.out_path, 1)

        browse_btn = QPushButton("浏览")
        browse_btn.setObjectName("btnSecondary")
        browse_btn.clicked.connect(self._browse_output)
        btm_layout.addWidget(browse_btn)

        btm_layout.addSpacing(16)

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

    def _apply_qss(self):
        self.setStyleSheet(QSS)

    # ============================================================
    # Data
    # ============================================================

    def _load_projects(self):
        """Load projects synchronously (fast, just DB reads). Threads only for conversion."""
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
        self.user_combo.blockSignals(True)
        self.user_combo.clear()
        self.user_combo.addItems([f"User {u}" for u in user_ids])
        self.user_combo.setCurrentIndex(0)
        self.user_combo.blockSignals(False)

        self.convert_btn.setEnabled(True)

        if user_ids:
            self._filter_projects(user_ids[0])
            self.status_bar.showMessage(
                f"已加载 {len(projects)} 个项目 — 点击卡片选择项目，然后设置输出路径并转换")
        else:
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
            QMessageBox.warning(self, "未选择", "请先选择至少一个项目")
            return

        output_dir = self.out_path.text().strip()
        if not output_dir:
            QMessageBox.critical(self, "错误", "请指定输出文件夹")
            return
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except OSError as e:
                QMessageBox.critical(self, "错误", f"无法创建文件夹:\n{e}")
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

        self._cvt_worker = ConvertWorker(selected_metas, output_dir, overwrite_mode)
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

        QMessageBox.information(self, "转换完成", msg)

        output_dir = self.out_path.text().strip()
        if success > 0 and output_dir:
            try:
                os.startfile(output_dir)
            except Exception:
                pass


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
