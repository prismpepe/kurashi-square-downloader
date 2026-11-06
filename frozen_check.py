import json
import traceback
from pathlib import Path

def run(report):
    results = {}
    def checkpoint(stage):
        results['stage'] = stage
        report.write_text(json.dumps(results, ensure_ascii=False, indent=2), 'utf-8')
    checkpoint('starting')
    try:
        checkpoint('tk')
        import tkinter as tk
        from launcher import configure_style
        root = tk.Tk(); root.withdraw(); configure_style(root); root.update(); root.destroy()
        results['tk'] = True
        checkpoint('pdf')
        import pdfplumber, pypdfium2, pytesseract
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new('RGB', (1000, 300), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc', 48)
        draw.text((25, 25), '入出金明細書', fill='black', font=font)
        fixture = report.parent / 'ocr-test.pdf'
        image.save(fixture, 'PDF', resolution=100)
        from pdf_title import extract_title
        checkpoint('ocr')
        results['ocr'] = extract_title(fixture)
        import pdf_title
        from unittest.mock import patch
        with patch.object(pdf_title.shutil, 'which', return_value=None), patch.dict(pdf_title.os.environ, {'ProgramFiles': str(report.parent / 'missing')}):
            results['without_ocr'] = extract_title(fixture)
        assert results['without_ocr'][0] == '' and results['without_ocr'][1] == 'fallback'
        checkpoint('playwright-driver')
        import subprocess
        from playwright._impl._driver import compute_driver_executable
        node, cli = compute_driver_executable()
        completed = subprocess.run([node, cli, '--version'], capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        assert completed.returncode == 0, completed.stderr
        results['playwright_driver'] = completed.stdout.strip()
        results['browser_check'] = 'Not run: local loopback is blocked in build sandbox'
        assert results['ocr'][1] == 'ocr', results['ocr']
        results['passed'] = True
    except Exception:
        results['passed'] = False
        results['error'] = traceback.format_exc()
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), 'utf-8')
