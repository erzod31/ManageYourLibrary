"""Synthetic format, multilingual and TSV regression checks for controlled OCR."""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_ocr_payload import validate_payload


def verify(directory):
    receipt = validate_payload(directory)
    os.environ['MANAGE_YOUR_LIBRARY_OCR_DIR'] = str(directory.resolve())
    import ocr_engine
    from PIL import Image, ImageDraw, ImageFont
    expected = 'LIBRARY TEST 2026'
    checks = {}
    with tempfile.TemporaryDirectory(prefix='myl_ocr_formats_') as temp:
        with Image.new('RGB', (1200, 230), 'white') as image:
            ImageDraw.Draw(image).text((45, 70), expected, fill='black', font=ImageFont.load_default(size=64))
            for suffix in ('png', 'jpg', 'jpeg', 'tif', 'tiff', 'bmp', 'webp'):
                path = Path(temp) / ('fixture.' + suffix)
                image.save(path)
                before = hashlib.sha256(path.read_bytes()).hexdigest()
                text, error = ocr_engine._run_tesseract_file(path, 'eng')
                if error or expected not in text.upper():
                    raise RuntimeError('OCR format regression ' + suffix + ': ' + str(error or text))
                if hashlib.sha256(path.read_bytes()).hexdigest() != before:
                    raise RuntimeError('OCR modified its input')
                checks[suffix] = 'passed; original unchanged'
            stream = BytesIO()
            image.save(stream, format='PNG')
            text, error = ocr_engine._run_tesseract_bytes(stream.getvalue(), 'eng+spa+fra+nld+chi_sim')
            if error or expected not in text.upper():
                raise RuntimeError('Multilingual model loading/recognition failed: ' + str(error or text))
            checks['five_models_loaded_together'] = 'passed'
            tokens, error = ocr_engine._run_tesseract_tsv_bytes(stream.getvalue(), 'eng')
            if error or not any(token.get('text', '').upper() == 'LIBRARY' for token in tokens):
                raise RuntimeError('TSV regression: ' + str(error or tokens))
            checks['tsv'] = 'passed'
    return {'passed': True, 'synthetic_only': True, 'payload': receipt, 'checks': checks}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite earlier evidence')
    result = verify(args.directory)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
