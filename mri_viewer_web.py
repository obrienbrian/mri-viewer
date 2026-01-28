#!/usr/bin/env python3
"""
MRI Viewer - Web-based version
Opens in your browser for maximum compatibility
"""

import http.server
import socketserver
import webbrowser
import json
import os
import sys
import threading
import time
import socket
import numpy as np
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import base64
from io import BytesIO
import argparse

# Global for tracking browser heartbeat
last_heartbeat = time.time()
server_instance = None
HEARTBEAT_TIMEOUT = 30  # Shutdown after 30 seconds of no heartbeat

# Check for PIL
try:
    from PIL import Image
except ImportError:
    print("Error: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)

# Optional imports for file formats
DICOM_AVAILABLE = False
NIFTI_AVAILABLE = False

try:
    import pydicom
    DICOM_AVAILABLE = True
except ImportError:
    pass

try:
    import nibabel as nib
    NIFTI_AVAILABLE = True
except ImportError:
    pass


class MRIData:
    """Holds the loaded MRI volume and metadata"""
    volume = None
    metadata = {}

    @classmethod
    def load_dicom_folder(cls, folder_path: str):
        """Load DICOM series from folder"""
        if not DICOM_AVAILABLE:
            raise ImportError("pydicom required")

        dicom_files = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                filepath = os.path.join(root, file)
                try:
                    ds = pydicom.dcmread(filepath, force=True)
                    if hasattr(ds, 'pixel_array'):
                        dicom_files.append(ds)
                except:
                    continue

        if not dicom_files:
            raise ValueError("No valid DICOM files found")

        # Sort slices
        try:
            dicom_files.sort(key=lambda x: float(x.InstanceNumber) if hasattr(x, 'InstanceNumber') else 0)
        except:
            try:
                dicom_files.sort(key=lambda x: float(x.SliceLocation) if hasattr(x, 'SliceLocation') else 0)
            except:
                pass

        slices = [ds.pixel_array.astype(np.float64) for ds in dicom_files]
        cls.volume = np.stack(slices, axis=0)

        ds = dicom_files[0]
        slope = float(getattr(ds, 'RescaleSlope', 1))
        intercept = float(getattr(ds, 'RescaleIntercept', 0))
        cls.volume = cls.volume * slope + intercept

        cls.metadata = {
            'format': 'DICOM',
            'patient_name': str(getattr(ds, 'PatientName', 'Unknown')),
            'patient_id': str(getattr(ds, 'PatientID', 'Unknown')),
            'study_date': str(getattr(ds, 'StudyDate', 'Unknown')),
            'modality': str(getattr(ds, 'Modality', 'Unknown')),
            'series_description': str(getattr(ds, 'SeriesDescription', 'Unknown')),
            'dimensions': list(cls.volume.shape),
            'num_slices': len(dicom_files),
            'data_min': float(np.min(cls.volume)),
            'data_max': float(np.max(cls.volume)),
        }

    @classmethod
    def load_nifti(cls, file_path: str):
        """Load NIfTI file"""
        if not NIFTI_AVAILABLE:
            raise ImportError("nibabel required")

        img = nib.load(file_path)
        cls.volume = np.asanyarray(img.dataobj).astype(np.float64)

        if cls.volume.ndim == 4:
            cls.volume = cls.volume[..., 0]
        elif cls.volume.ndim == 2:
            cls.volume = cls.volume[np.newaxis, ...]

        # Transpose to get axial slices first
        # NIfTI is typically (x, y, z) so we want (z, y, x) for axial-first
        cls.volume = np.transpose(cls.volume, (2, 1, 0))

        header = img.header
        cls.metadata = {
            'format': 'NIfTI',
            'dimensions': list(cls.volume.shape),
            'voxel_size': list(header.get_zooms()[:3]) if hasattr(header, 'get_zooms') else [1, 1, 1],
            'num_slices': cls.volume.shape[0],
            'data_min': float(np.min(cls.volume)),
            'data_max': float(np.max(cls.volume)),
        }

    @classmethod
    def get_slice(cls, axis: int, index: int, wc: float, ww: float) -> str:
        """Get a slice as base64 PNG"""
        if cls.volume is None:
            return ""

        # Extract slice
        if axis == 0:  # Axial
            data = cls.volume[index, :, :]
        elif axis == 1:  # Coronal
            data = cls.volume[:, index, :]
        else:  # Sagittal
            data = cls.volume[:, :, index]

        # Apply window/level
        vmin = wc - ww / 2
        vmax = wc + ww / 2
        data = np.clip(data, vmin, vmax)
        data = ((data - vmin) / (vmax - vmin) * 255).astype(np.uint8)

        # Convert to image
        img = Image.fromarray(data, mode='L')

        # Encode as base64 PNG
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode('utf-8')


HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <title>MRI Viewer</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #1a1a2e;
            color: #eee;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            overflow: hidden;
        }
        .container {
            display: grid;
            grid-template-columns: 1fr 1fr 300px;
            grid-template-rows: 1fr 1fr;
            height: 100vh;
            gap: 4px;
            padding: 4px;
        }
        .view-panel {
            background: #16213e;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .view-title {
            padding: 8px 12px;
            background: #0f3460;
            font-weight: 600;
            font-size: 14px;
        }
        .view-content {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            overflow: hidden;
        }
        .view-content img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            image-rendering: pixelated;
        }
        .slice-controls {
            padding: 8px 12px;
            background: #0f3460;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .slice-controls input[type="range"] {
            flex: 1;
        }
        .slice-label {
            min-width: 60px;
            text-align: right;
            font-size: 12px;
            color: #aaa;
        }
        .sidebar {
            grid-row: 1 / 3;
            background: #16213e;
            border-radius: 8px;
            padding: 16px;
            overflow-y: auto;
        }
        .sidebar h2 {
            font-size: 16px;
            margin-bottom: 12px;
            color: #e94560;
        }
        .sidebar h3 {
            font-size: 14px;
            margin: 16px 0 8px 0;
            color: #0f3460;
            background: #e94560;
            padding: 4px 8px;
            border-radius: 4px;
        }
        .metadata {
            background: #0f3460;
            border-radius: 6px;
            padding: 12px;
            font-size: 12px;
            line-height: 1.6;
        }
        .metadata-row {
            display: flex;
            justify-content: space-between;
        }
        .metadata-key { color: #aaa; }
        .metadata-value { color: #fff; font-family: monospace; }
        .control-group {
            margin-bottom: 16px;
        }
        .control-group label {
            display: block;
            margin-bottom: 4px;
            font-size: 12px;
            color: #aaa;
        }
        .control-group input[type="range"] {
            width: 100%;
        }
        .control-value {
            text-align: right;
            font-size: 11px;
            color: #888;
            font-family: monospace;
        }
        .presets {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
        }
        .preset-btn {
            background: #0f3460;
            border: none;
            color: #fff;
            padding: 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            transition: background 0.2s;
        }
        .preset-btn:hover {
            background: #e94560;
        }
        .load-section {
            margin-bottom: 20px;
        }
        .load-btn {
            width: 100%;
            background: #e94560;
            border: none;
            color: #fff;
            padding: 10px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            margin-bottom: 8px;
            transition: background 0.2s;
        }
        .load-btn:hover {
            background: #ff6b6b;
        }
        .load-btn:disabled {
            background: #444;
            cursor: not-allowed;
        }
        .instructions {
            font-size: 11px;
            color: #888;
            line-height: 1.5;
            margin-top: 16px;
        }
        .instructions kbd {
            background: #0f3460;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
        }
        .welcome {
            text-align: center;
            color: #666;
            padding: 40px;
        }
        .welcome h3 { margin-bottom: 10px; color: #888; }
        input[type="file"] { display: none; }
        .status {
            position: fixed;
            bottom: 10px;
            left: 10px;
            background: rgba(0,0,0,0.7);
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="view-panel" id="axial-panel">
            <div class="view-title">Axial (Top)</div>
            <div class="view-content" id="axial-view">
                <div class="welcome"><h3>No image loaded</h3>Load a DICOM folder or NIfTI file</div>
            </div>
            <div class="slice-controls">
                <input type="range" id="axial-slider" min="0" max="100" value="50" disabled>
                <span class="slice-label" id="axial-label">-/-</span>
            </div>
        </div>

        <div class="view-panel" id="sagittal-panel">
            <div class="view-title">Sagittal (Side)</div>
            <div class="view-content" id="sagittal-view">
                <div class="welcome"><h3>No image loaded</h3></div>
            </div>
            <div class="slice-controls">
                <input type="range" id="sagittal-slider" min="0" max="100" value="50" disabled>
                <span class="slice-label" id="sagittal-label">-/-</span>
            </div>
        </div>

        <div class="sidebar">
            <h2>MRI Viewer</h2>

            <div class="load-section">
                <button class="load-btn" onclick="loadDicom()" ''' + ('disabled title="pydicom not installed"' if not DICOM_AVAILABLE else '') + '''>
                    Open DICOM Folder
                </button>
                <button class="load-btn" onclick="loadNifti()" ''' + ('disabled title="nibabel not installed"' if not NIFTI_AVAILABLE else '') + '''>
                    Open NIfTI File
                </button>
                <input type="file" id="folder-input" webkitdirectory>
                <input type="file" id="file-input" accept=".nii,.nii.gz">
            </div>

            <h3>Image Info</h3>
            <div class="metadata" id="metadata">
                <div class="metadata-row">
                    <span class="metadata-key">Status:</span>
                    <span class="metadata-value">No file loaded</span>
                </div>
            </div>

            <h3>Window / Level</h3>
            <div class="control-group">
                <label>Window Center (Brightness)</label>
                <input type="range" id="wc-slider" min="-2000" max="2000" value="0">
                <div class="control-value" id="wc-value">0</div>
            </div>
            <div class="control-group">
                <label>Window Width (Contrast)</label>
                <input type="range" id="ww-slider" min="1" max="4000" value="1000">
                <div class="control-value" id="ww-value">1000</div>
            </div>

            <h3>Presets</h3>
            <div class="presets">
                <button class="preset-btn" onclick="applyPreset(40, 80)">Brain</button>
                <button class="preset-btn" onclick="applyPreset(400, 2000)">Bone</button>
                <button class="preset-btn" onclick="applyPreset(50, 400)">Soft Tissue</button>
                <button class="preset-btn" onclick="applyPreset(-600, 1500)">Lung</button>
            </div>

            <div class="instructions">
                <strong>Controls:</strong><br>
                <kbd>Scroll</kbd> Navigate slices<br>
                <kbd>A</kbd> Auto window/level<br>
                <kbd>R</kbd> Reset window/level
            </div>
        </div>

        <div class="view-panel" id="coronal-panel">
            <div class="view-title">Coronal (Front)</div>
            <div class="view-content" id="coronal-view">
                <div class="welcome"><h3>No image loaded</h3></div>
            </div>
            <div class="slice-controls">
                <input type="range" id="coronal-slider" min="0" max="100" value="50" disabled>
                <span class="slice-label" id="coronal-label">-/-</span>
            </div>
        </div>
    </div>

    <div class="status" id="status"></div>

    <script>
        let volumeLoaded = false;
        let dimensions = [0, 0, 0];
        let dataMin = 0, dataMax = 1000;

        const views = ['axial', 'sagittal', 'coronal'];
        const sliders = {};
        const labels = {};
        const images = {};

        views.forEach(view => {
            sliders[view] = document.getElementById(view + '-slider');
            labels[view] = document.getElementById(view + '-label');
        });

        const wcSlider = document.getElementById('wc-slider');
        const wwSlider = document.getElementById('ww-slider');
        const wcValue = document.getElementById('wc-value');
        const wwValue = document.getElementById('ww-value');
        const metadataDiv = document.getElementById('metadata');
        const statusDiv = document.getElementById('status');

        function showStatus(msg) {
            statusDiv.textContent = msg;
            setTimeout(() => statusDiv.textContent = '', 3000);
        }

        function loadDicom() {
            document.getElementById('folder-input').click();
        }

        function loadNifti() {
            document.getElementById('file-input').click();
        }

        document.getElementById('folder-input').addEventListener('change', async (e) => {
            if (e.target.files.length === 0) return;

            showStatus('Loading DICOM files...');
            const formData = new FormData();
            for (let file of e.target.files) {
                formData.append('files', file, file.webkitRelativePath);
            }

            try {
                const resp = await fetch('/load_dicom', { method: 'POST', body: formData });
                const data = await resp.json();
                if (data.error) throw new Error(data.error);
                onVolumeLoaded(data);
            } catch (err) {
                alert('Error loading DICOM: ' + err.message);
            }
        });

        document.getElementById('file-input').addEventListener('change', async (e) => {
            if (e.target.files.length === 0) return;

            showStatus('Loading NIfTI file...');
            const formData = new FormData();
            formData.append('file', e.target.files[0]);

            try {
                const resp = await fetch('/load_nifti', { method: 'POST', body: formData });
                const data = await resp.json();
                if (data.error) throw new Error(data.error);
                onVolumeLoaded(data);
            } catch (err) {
                alert('Error loading NIfTI: ' + err.message);
            }
        });

        function onVolumeLoaded(data) {
            volumeLoaded = true;
            dimensions = data.dimensions;
            dataMin = data.data_min;
            dataMax = data.data_max;

            // Setup sliders
            sliders.axial.max = dimensions[0] - 1;
            sliders.axial.value = Math.floor(dimensions[0] / 2);
            sliders.axial.disabled = false;

            sliders.coronal.max = dimensions[1] - 1;
            sliders.coronal.value = Math.floor(dimensions[1] / 2);
            sliders.coronal.disabled = false;

            sliders.sagittal.max = dimensions[2] - 1;
            sliders.sagittal.value = Math.floor(dimensions[2] / 2);
            sliders.sagittal.disabled = false;

            // Auto window/level
            const wc = (dataMax + dataMin) / 2;
            const ww = dataMax - dataMin;
            wcSlider.min = dataMin;
            wcSlider.max = dataMax;
            wcSlider.value = wc;
            wwSlider.max = (dataMax - dataMin) * 2;
            wwSlider.value = ww;
            wcValue.textContent = Math.round(wc);
            wwValue.textContent = Math.round(ww);

            // Update metadata
            let html = '';
            for (let [key, val] of Object.entries(data)) {
                if (key === 'dimensions') val = val.join(' x ');
                if (key === 'voxel_size') val = val.map(v => v.toFixed(2)).join(' x ') + ' mm';
                html += `<div class="metadata-row"><span class="metadata-key">${key.replace(/_/g, ' ')}:</span><span class="metadata-value">${val}</span></div>`;
            }
            metadataDiv.innerHTML = html;

            // Create image elements
            views.forEach(view => {
                const container = document.getElementById(view + '-view');
                container.innerHTML = '<img id="' + view + '-img">';
                images[view] = document.getElementById(view + '-img');
            });

            updateAllViews();
            showStatus('Loaded successfully');
        }

        async function updateView(axis, view) {
            if (!volumeLoaded) return;

            const slice = parseInt(sliders[view].value);
            const wc = parseFloat(wcSlider.value);
            const ww = parseFloat(wwSlider.value);

            const resp = await fetch(`/slice?axis=${axis}&index=${slice}&wc=${wc}&ww=${ww}`);
            const data = await resp.json();

            if (data.image) {
                images[view].src = 'data:image/png;base64,' + data.image;
            }

            const maxSlice = axis === 0 ? dimensions[0] : (axis === 1 ? dimensions[1] : dimensions[2]);
            labels[view].textContent = `${slice + 1}/${maxSlice}`;
        }

        function updateAllViews() {
            updateView(0, 'axial');
            updateView(1, 'coronal');
            updateView(2, 'sagittal');
        }

        // Event listeners
        sliders.axial.addEventListener('input', () => updateView(0, 'axial'));
        sliders.coronal.addEventListener('input', () => updateView(1, 'coronal'));
        sliders.sagittal.addEventListener('input', () => updateView(2, 'sagittal'));

        wcSlider.addEventListener('input', () => {
            wcValue.textContent = Math.round(wcSlider.value);
            updateAllViews();
        });

        wwSlider.addEventListener('input', () => {
            wwValue.textContent = Math.round(wwSlider.value);
            updateAllViews();
        });

        function applyPreset(wc, ww) {
            wcSlider.value = wc;
            wwSlider.value = ww;
            wcValue.textContent = wc;
            wwValue.textContent = ww;
            updateAllViews();
        }

        // Scroll to navigate slices
        document.querySelectorAll('.view-content').forEach((el, i) => {
            el.addEventListener('wheel', (e) => {
                if (!volumeLoaded) return;
                e.preventDefault();
                const view = views[i < 2 ? i : 2 - (i - 2)]; // Map to correct view
                const viewName = el.parentElement.id.replace('-panel', '');
                const slider = sliders[viewName];
                const delta = e.deltaY > 0 ? -1 : 1;
                slider.value = Math.max(0, Math.min(parseInt(slider.max), parseInt(slider.value) + delta));
                const axis = viewName === 'axial' ? 0 : (viewName === 'coronal' ? 1 : 2);
                updateView(axis, viewName);
            });
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'a' || e.key === 'A') {
                const wc = (dataMax + dataMin) / 2;
                const ww = dataMax - dataMin;
                applyPreset(wc, ww);
            } else if (e.key === 'r' || e.key === 'R') {
                applyPreset(0, 1000);
            }
        });

        // Heartbeat to keep server alive (server shuts down when browser closes)
        setInterval(() => {
            fetch('/heartbeat').catch(() => {});
        }, 5000);

        // Send heartbeat immediately on load
        fetch('/heartbeat').catch(() => {});
    </script>
</body>
</html>
'''


class MRIHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler for the MRI viewer"""

    def log_message(self, format, *args):
        pass  # Suppress logging

    def do_GET(self):
        global last_heartbeat
        parsed = urlparse(self.path)

        if parsed.path == '/heartbeat':
            last_heartbeat = time.time()
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ok')

        elif parsed.path == '/' or parsed.path == '/index.html':
            last_heartbeat = time.time()  # Page load counts as heartbeat
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode())

        elif parsed.path == '/slice':
            params = parse_qs(parsed.query)
            axis = int(params.get('axis', [0])[0])
            index = int(params.get('index', [0])[0])
            wc = float(params.get('wc', [0])[0])
            ww = float(params.get('ww', [1000])[0])

            image_b64 = MRIData.get_slice(axis, index, wc, ww)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'image': image_b64}).encode())

        else:
            self.send_error(404)

    def _parse_multipart(self):
        """Parse multipart form data without using deprecated cgi module.

        Returns a dict where keys are field names and values are lists of
        (filename, data) tuples for file fields or raw data for regular fields.
        """
        import email.parser
        import re

        content_type = self.headers.get('Content-Type', '')
        content_length = int(self.headers.get('Content-Length', 0))

        # Read the body
        body = self.rfile.read(content_length)

        # Extract boundary from content type
        boundary_match = re.search(r'boundary=([^\s;]+)', content_type)
        if not boundary_match:
            raise ValueError("No boundary found in Content-Type header")

        boundary = boundary_match.group(1).strip('"')
        boundary_bytes = ('--' + boundary).encode()
        end_boundary_bytes = ('--' + boundary + '--').encode()

        # Split by boundary
        parts = body.split(boundary_bytes)

        result = {}

        for part in parts:
            # Skip empty parts and end boundary
            if not part or part.strip() == b'' or part.strip() == b'--':
                continue

            # Remove leading/trailing CRLF
            part = part.strip(b'\r\n')
            if part == b'--':
                continue

            # Split headers from content
            if b'\r\n\r\n' in part:
                headers_raw, content = part.split(b'\r\n\r\n', 1)
            elif b'\n\n' in part:
                headers_raw, content = part.split(b'\n\n', 1)
            else:
                continue

            # Parse headers
            headers_text = headers_raw.decode('utf-8', errors='replace')

            # Extract field name and filename from Content-Disposition
            name_match = re.search(r'name="([^"]*)"', headers_text)
            filename_match = re.search(r'filename="([^"]*)"', headers_text)

            if not name_match:
                continue

            field_name = name_match.group(1)
            filename = filename_match.group(1) if filename_match else None

            # Remove trailing boundary marker if present
            if content.endswith(b'\r\n'):
                content = content[:-2]

            if field_name not in result:
                result[field_name] = []

            if filename:
                result[field_name].append((filename, content))
            else:
                result[field_name].append((None, content))

        return result

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == '/load_dicom':
            try:
                # Parse multipart form data
                form = self._parse_multipart()

                # Save files to temp directory
                import tempfile
                temp_dir = tempfile.mkdtemp()

                files_data = form.get('files', [])
                for filename, data in files_data:
                    if filename:
                        # Use just the filename, not the full path
                        safe_filename = os.path.basename(filename)
                        filepath = os.path.join(temp_dir, safe_filename)
                        with open(filepath, 'wb') as f:
                            f.write(data)

                MRIData.load_dicom_folder(temp_dir)

                # Cleanup
                import shutil
                shutil.rmtree(temp_dir)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(MRIData.metadata).encode())

            except Exception as e:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())

        elif parsed.path == '/load_nifti':
            try:
                form = self._parse_multipart()

                file_data = form.get('file', [])
                if not file_data:
                    raise ValueError("No file uploaded")

                filename, data = file_data[0]

                import tempfile
                # Preserve original extension for nibabel to detect format
                suffix = '.nii.gz' if filename and filename.endswith('.gz') else '.nii'
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                    f.write(data)
                    temp_path = f.name

                MRIData.load_nifti(temp_path)
                os.unlink(temp_path)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(MRIData.metadata).encode())

            except Exception as e:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())

        else:
            self.send_error(404)


def is_port_in_use(port):
    """Check if a port is already in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect(('localhost', port))
            return True
        except (ConnectionRefusedError, OSError):
            return False


def heartbeat_monitor(httpd):
    """Monitor heartbeat and shutdown server if browser closes"""
    global last_heartbeat
    while True:
        time.sleep(5)
        if time.time() - last_heartbeat > HEARTBEAT_TIMEOUT:
            print("\nBrowser closed. Shutting down server...")
            httpd.shutdown()
            break


def main():
    global last_heartbeat, server_instance

    parser = argparse.ArgumentParser(description='MRI Viewer - Web-based medical image viewer')
    parser.add_argument('--port', type=int, default=8765, help='Port to run server on')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser automatically')
    args = parser.parse_args()

    port = args.port

    # Check if server is already running on this port
    if is_port_in_use(port):
        url = f"http://localhost:{port}"
        print(f"MRI Viewer is already running at: {url}")
        print("Opening browser...")
        webbrowser.open(url)
        return

    print("=" * 50)
    print("MRI Viewer - Web Edition")
    print("=" * 50)
    print(f"DICOM support: {'Yes' if DICOM_AVAILABLE else 'No (pip install pydicom)'}")
    print(f"NIfTI support: {'Yes' if NIFTI_AVAILABLE else 'No (pip install nibabel)'}")
    print()

    # Reset heartbeat
    last_heartbeat = time.time()

    # Find available port
    while True:
        try:
            # Allow socket reuse to prevent "address already in use" errors
            socketserver.TCPServer.allow_reuse_address = True
            with socketserver.TCPServer(("", port), MRIHandler) as httpd:
                server_instance = httpd
                url = f"http://localhost:{port}"
                print(f"Server running at: {url}")
                print("Server will automatically close when you close the browser.")
                print("(Or press Ctrl+C to stop manually)")
                print()

                # Start heartbeat monitor thread
                monitor_thread = threading.Thread(target=heartbeat_monitor, args=(httpd,), daemon=True)
                monitor_thread.start()

                if not args.no_browser:
                    webbrowser.open(url)

                httpd.serve_forever()
                break  # Exit after shutdown
        except OSError as e:
            if "Address already in use" in str(e) or e.errno == 48:
                port += 1
                if port > 9000:
                    print("Could not find available port")
                    sys.exit(1)
            else:
                raise
        except KeyboardInterrupt:
            print("\nShutting down...")
            break


if __name__ == "__main__":
    main()
