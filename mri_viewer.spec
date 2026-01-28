# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for MRI Viewer
Cross-platform build configuration for macOS and Windows
"""

import sys
import os

block_cipher = None

# Platform-specific settings
is_mac = sys.platform == 'darwin'
is_win = sys.platform == 'win32'

# Hidden imports for medical imaging libraries
hidden_imports = [
    # NumPy
    'numpy',
    'numpy.core',
    'numpy.core._methods',
    'numpy.lib.format',

    # Pillow
    'PIL',
    'PIL.Image',
    'PIL.PngImagePlugin',

    # pydicom
    'pydicom',
    'pydicom.encoders',
    'pydicom.encoders.gdcm',
    'pydicom.encoders.pylibjpeg',
    'pydicom.encoders.native',

    # nibabel
    'nibabel',
    'nibabel.nifti1',
    'nibabel.nifti2',
    'nibabel.freesurfer',
    'nibabel.gifti',
    'nibabel.spm99analyze',
    'nibabel.spm2analyze',
    'nibabel.minc1',
    'nibabel.minc2',
    'nibabel.cifti2',
    'nibabel.streamlines',
    'nibabel.arrayproxy',

    # Standard library modules we use
    'http.server',
    'socketserver',
    'webbrowser',
    'json',
    'threading',
    'argparse',
    'tempfile',
    'shutil',
    'email.parser',
]

a = Analysis(
    ['mri_viewer_web.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unused modules to reduce size
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if is_mac:
    # macOS: Create .app bundle
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='MRI Viewer',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,  # Disable UPX to avoid antivirus false positives
        console=False,  # No console window on macOS
        disable_windowed_traceback=False,
        argv_emulation=True,  # Support file drag-and-drop on macOS
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='MRI Viewer',
    )
    app = BUNDLE(
        coll,
        name='MRI Viewer.app',
        icon=None,  # Add icon path here if you have one: 'icon.icns'
        bundle_identifier='com.mriviewer.app',
        info_plist={
            'CFBundleName': 'MRI Viewer',
            'CFBundleDisplayName': 'MRI Viewer',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.13.0',
        },
    )

else:
    # Windows: Create single .exe with console (shows server status)
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='MRI Viewer',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,  # Disable UPX to avoid antivirus false positives
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,  # Show console on Windows for server status
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,  # Add icon path here if you have one: 'icon.ico'
    )
