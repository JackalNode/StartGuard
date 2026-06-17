# startguard.spec
# PyInstaller configuration for StartGuard v0.9.0
#
# HOW TO USE:
#   Open a terminal in your project root folder and run:
#   pyinstaller startguard.spec
#
# The finished .exe will appear in: dist\StartGuard\StartGuard.exe

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

a = Analysis(
    # Entry point — the file Python runs first
    ['main.py'],

    # Where to look for imported modules (your project root)
    pathex=['.'],

    # Any .dll or .so binary files your app needs (none for now)
    binaries=[],

    # Non-Python files to bundle (JSON data, etc.)
    # Format: ('source path relative to project root', 'destination folder inside the bundle')
    datas=[
        ('data/known_processes.json', 'data'),   # Known process database
        ('core/*.py', 'core'),                   # Core module sources (belt-and-braces)
        ('platforms/*.py', 'platforms'),         # Platform stubs
        ('constants.py', '.'),                   # App-level constants (webhook URL etc.)
        ('main_window.py', '.'),                 # Main UI module
        ('settings.py', '.'),                    # Settings module
        ('settings_dialog.py', '.'),             # Settings UI dialog
    ],

    # Hidden imports — modules PyInstaller sometimes misses with PyQt6
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'psutil',
        'winreg',
        'win32com.client',   # Used for .lnk shortcut resolution
        'win32com.shell',
        'pywintypes',
        'json',
        'logging',
        'socket',
        'urllib.request',
        'urllib.error',
        'requests',
        'requests.adapters',
        'requests.auth',
        'requests.models',
        'certifi',
        'charset_normalizer',
        'idna',
        'urllib3',
    ],

    # Let PyInstaller auto-discover everything else
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude things we definitely don't use — keeps the build smaller
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'IPython',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='StartGuard',           # The .exe will be named StartGuard.exe
    debug=False,                 # Set to True temporarily if the app crashes on launch
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                    # Compresses the bundle — reduces file size
    console=False,               # False = no black terminal window behind the app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # uac_admin=True tells Windows this app needs admin rights
    # This is what triggers the UAC prompt on launch
    uac_admin=True,
    icon=None,                   # Add icon path here later e.g. 'assets/icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    # Output folder name: dist\StartGuard\
    name='StartGuard',
)
