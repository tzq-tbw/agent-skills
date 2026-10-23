"""Inspect PDF page objects and render an auditable view with selected objects hidden."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'universal-exam-cram-coach'))
from coach.guide import digest, save


def render_layers(run, unit_id, hidden=()):
    import pypdfium2 as pdfium
    from pypdfium2 import raw
    out = Path(run).resolve()
    data = json.loads((out / 'sources.json').read_text(encoding='utf-8'))
    found = [(s, u) for s in data['sources'] for u in s['units'] if u['id'] == unit_id]
    if len(found) != 1:
        raise ValueError('unknown unit')
    source, unit = found[0]
    original = Path(source['path'])
    if original.suffix.lower() != '.pdf' or digest(original) != source['sha256']:
        raise ValueError('current original PDF required')
    hidden = sorted(set(hidden))
    document = pdfium.PdfDocument(str(original))
    try:
        page = document[unit['page'] - 1]
        objects = list(page.get_objects())
        if any(type(i) is not int or i < 0 or i >= len(objects) for i in hidden):
            raise ValueError('invalid object index')
        if any(objects[i].type == raw.FPDF_PAGEOBJ_FORM for i in hidden):
            raise ValueError('select leaf objects rather than a parent form')
        inventory = []
        textpage = page.get_textpage()
        try:
            for index, obj in enumerate(objects):
                record = {'index': index, 'type': obj.type, 'bounds': list(obj.get_bounds())}
                if obj.type == raw.FPDF_PAGEOBJ_TEXT:
                    length = raw.FPDFTextObj_GetText(obj, textpage, None, 0)
                    buffer = (ctypes.c_ushort * ((length + 1) // 2))()
                    raw.FPDFTextObj_GetText(obj, textpage, buffer, length)
                    record['text'] = bytes(buffer).decode('utf-16-le').rstrip('\x00')
                    color = [ctypes.c_uint() for _ in range(4)]
                    if raw.FPDFPageObj_GetFillColor(obj, *[ctypes.byref(c) for c in color]):
                        record['rgba'] = [c.value for c in color]
                inventory.append(record)
        finally:
            textpage.close()
        folder = out / 'layer-audit' / unit_id
        folder.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(json.dumps(hidden).encode()).hexdigest()[:12]
        image = folder / ('view-' + key + '.png')
        if image.exists():
            raise ValueError('view already exists; retain the existing evidence')
        for index in hidden:
            page.remove_obj(objects[index])
            objects[index].close()
        page.gen_content()
        bitmap = page.render(scale=2.5)
        try:
            bitmap.to_pil().save(image)
        finally:
            bitmap.close()
        page.close()
    finally:
        document.close()
    if digest(original) != source['sha256']:
        raise ValueError('source changed during inspection')
    receipt = {'unit': unit_id, 'source_sha256': source['sha256'], 'hidden_objects': hidden,
               'image': str(image), 'image_sha256': digest(image), 'objects': inventory,
               'note': 'Derived inspection view; original unchanged. Hidden content may belong to separate animation states. No reading approval granted.'}
    save(image.with_suffix('.json'), receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--unit', required=True)
    parser.add_argument('--hide', type=int, nargs='*', default=[])
    args = parser.parse_args()
    try:
        result = render_layers(args.run, args.unit, args.hide)
        print(json.dumps({k: v for k, v in result.items() if k != 'objects'}, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, ImportError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
