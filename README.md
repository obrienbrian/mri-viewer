# MRI Viewer

A simple desktop application for viewing MRI scans and other medical imaging data.

**Important:** This tool is for visualization only. It is NOT intended for clinical diagnosis or medical decision-making.

## Download

**No installation required** - just download and run:

| Platform | Download | Instructions |
|----------|----------|--------------|
| **macOS** | [MRI-Viewer-macOS.dmg](https://github.com/obrienbrian/mri-viewer/releases/latest/download/MRI-Viewer-macOS.dmg) | Open DMG, drag to Applications |
| **Windows** | [MRI-Viewer-Windows.zip](https://github.com/obrienbrian/mri-viewer/releases/latest/download/MRI-Viewer-Windows.zip) | Extract ZIP, run `MRI Viewer.exe` |

### First Launch Notes

**macOS**: Apple will show a warning because the app isn't signed with a paid developer certificate. To open it:
1. Click **Done** when you see the warning (don't move to trash)
2. Open **System Settings → Privacy & Security**
3. Scroll down and click **Open Anyway** next to the MRI Viewer message
4. Click **Open** in the confirmation dialog

**Windows**: If SmartScreen warns you, click "More info" → "Run anyway"

These warnings are normal for apps not distributed through the App Store or Microsoft Store.

## Supported Formats

- **DICOM** (.dcm) - Standard medical imaging format (from hospitals/imaging centers)
- **NIfTI** (.nii, .nii.gz) - Common research format

## Features

### Three-Plane View
View your scan in three orientations simultaneously:
- **Axial** (top-down view)
- **Sagittal** (side view)
- **Coronal** (front view)

### Window/Level Adjustment
Adjust brightness and contrast to see different tissue types:
- Use the **sliders** in the sidebar
- Use **presets** for common viewing modes (Brain, Bone, Soft Tissue, Lung)

### Navigation
- **Scroll wheel** over any view - Navigate through slices
- **Slider** below each view - Jump to specific slices

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| A | Auto window/level |
| R | Reset window/level |

## Loading Your Files

### DICOM Files
Most hospital/imaging center CDs contain DICOM files:
1. Click **Open DICOM Folder**
2. Select the folder containing your DICOM files
3. The viewer will automatically find and load all slices

### NIfTI Files
Research data is often in NIfTI format:
1. Click **Open NIfTI File**
2. Choose your .nii or .nii.gz file

## Troubleshooting

### Images look wrong
Press **A** to auto-adjust window/level, or try different presets (Brain, Bone, etc.)

### App won't open (macOS)
Go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway**

### App won't open (Windows)
Click "More info" on the SmartScreen popup → "Run anyway"

---

## For Developers

If you want to run from source instead of using the packaged app:

### Requirements
- Python 3.9+
- Dependencies: `pip install -r requirements.txt`

### Run
```bash
python mri_viewer_web.py
```

This starts a local web server and opens the viewer in your browser.

### Build
```bash
pip install pyinstaller
pyinstaller mri_viewer.spec
```

## License

MIT License - Free for personal and educational use.
