# -*- mode: python ; coding: utf-8 -*-
# Optimized one-file build: minimal PyQt5 plugins + excluded unused libs.

block_cipher = None

EXCLUDES = [
    'numpy', 'scipy', 'pandas', 'matplotlib', 'sklearn', 'skimage',
    'cv2', 'torch', 'tensorflow', 'IPython', 'jupyter', 'notebook',
    'tkinter', '_tkinter', 'tcl', 'tk',
    'unittest', 'test', 'tests', 'pytest', 'pydoc', 'doctest',
    'distutils', 'setuptools', 'pkg_resources', 'wheel', 'pip',
    'xmlrpc', 'curses', 'readline', 'lib2to3',
    'multiprocessing.dummy', 'concurrent.futures.process',
    'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngineCore',
    'PyQt5.QtQuick', 'PyQt5.QtQml', 'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets',
    'PyQt5.QtBluetooth', 'PyQt5.QtSensors', 'PyQt5.QtLocation', 'PyQt5.QtWebKit',
    'PyQt5.QtWebKitWidgets', 'PyQt5.QtDesigner', 'PyQt5.QtHelp', 'PyQt5.QtTest',
    'PyQt5.QtXmlPatterns', 'PyQt5.QtCharts', 'PyQt5.QtDataVisualization',
    'PyQt5.QtNetworkAuth', 'PyQt5.QtOpenGL', 'PyQt5.QtSql', 'PyQt5.QtSvg',
    'PyQt5.QtPrintSupport', 'PyQt5.QtSerialPort', 'PyQt5.QtNfc',
]

HIDDEN_IMPORTS = [
    'PyQt5.sip',
    'PIL',
    'PIL.Image',
    'PIL.ExifTags',
    'exifread',
]

QT_BINARY_DROP = (
    'Qt5WebEngine', 'Qt5Quick', 'Qt5Qml', 'Qt5Multimedia', 'Qt5Bluetooth',
    'Qt5Sensors', 'Qt5Location', 'Qt5WebKit', 'Qt5Designer', 'Qt5Help',
    'Qt5Test', 'Qt5XmlPatterns', 'Qt5Charts', 'Qt5DataVisualization',
    'Qt5NetworkAuth', 'Qt5OpenGL', 'Qt5Sql', 'Qt5Svg', 'Qt5PrintSupport',
    'Qt5SerialPort', 'Qt5Nfc', 'Qt5Positioning', 'Qt5RemoteObjects',
    'Qt5Scxml', 'Qt5TextToSpeech', 'Qt5WinExtras', 'Qt5Xml',
    'd3dcompiler', 'opengl32sw', 'libEGL', 'libGLESv2',
)

QT_PLUGIN_KEEP = {
    'platforms/qwindows.dll',
    'imageformats/qjpeg.dll',
    'imageformats/qgif.dll',
    'imageformats/qico.dll',
    'imageformats/qpng.dll',
    'imageformats/qwebp.dll',
}


def _norm(path):
    return path.replace('\\', '/').lower()


def filter_binaries(binaries):
    out = []
    for src, dst, typ in binaries:
        src_l = _norm(src)
        if any(x.lower() in src_l for x in QT_BINARY_DROP):
            continue
        out.append((src, dst, typ))
    return out


def filter_datas(datas):
    out = []
    for src, dst, typ in datas:
        src_l = _norm(src)
        if '/plugins/' in src_l or '\\plugins\\' in src_l:
            rel = src_l.split('plugins/', 1)[-1]
            if rel not in QT_PLUGIN_KEEP:
                continue
        out.append((src, dst, typ))
    return out


a = Analysis(
    ['pixcake_xmp_converter.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

a.binaries = filter_binaries(a.binaries)
a.datas = filter_datas(a.datas)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PixCakeXmpConverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='dist/icon.ico',
)
