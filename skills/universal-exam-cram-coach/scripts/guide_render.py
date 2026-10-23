"""Render original Office documents locally, keeping slide notes and extracted text intact."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "universal-exam-cram-coach"))
from coach.guide import digest, inspect, save


def render(run, source_id, office=None):
    import pypdfium2 as pdfium
    out = Path(run).resolve()
    data = json.loads((out / "sources.json").read_text(encoding="utf-8"))
    source = next((s for s in data["sources"] if s["id"] == source_id), None)
    if not source:
        raise ValueError("unknown source")
    original = Path(source["path"])
    if original.suffix.lower() not in (".pptx", ".docx", ".ppt"):
        raise ValueError("Office document required")
    if digest(original) != source["sha256"]:
        raise ValueError("source changed")
    executable = office or shutil.which("soffice") or shutil.which("soffice.exe")
    if not executable:
        raise RuntimeError("LibreOffice required; pass --office with its executable path")
    folder = out / "office"
    folder.mkdir(exist_ok=True)
    if (folder / (source_id + ".pdf")).exists():
        raise ValueError("Office source already rendered; use a new run to preserve reviews")
    with tempfile.TemporaryDirectory(prefix="office-render-", dir=out) as tmp:
        profile = Path(tmp) / "profile"
        subprocess.run([executable, "-env:UserInstallation=" + profile.as_uri(), "--headless",
                        "--convert-to", "pdf", "--outdir", tmp, str(original)], check=True,
                       capture_output=True, text=True, timeout=180)
        pdf = Path(tmp) / (original.stem + ".pdf")
        if not pdf.is_file():
            raise RuntimeError("Office conversion did not produce a PDF")
        document = pdfium.PdfDocument(str(pdf))
        try:
            # DOCX extracted pages follow explicit breaks, not physical layout. Keep rendered units separate.
            slides = original.suffix.lower() in (".pptx", ".ppt")
            if slides and source["units"] and len(document) != len(source["units"]):
                raise ValueError("slide count differs after rendering")
            if not slides or not source["units"]:
                prefix = "r" if source["units"] else "p"
                for i in range(len(document)):
                    source["units"].append({"id": "%s-%s%04d" % (source_id, prefix, i+1),
                        "page": i+1, "text": "", "image": None,
                        "flags": ["visual_check_required"], "review": None, "chapter": None,
                        "kind": "rendered_document"})
                targets = source["units"][-len(document):]
            else:
                targets = source["units"]
            for i, unit in enumerate(targets):
                page = document[i]
                image = "pages/%s-render-%04d.png" % (source_id, i+1)
                bitmap = page.render(scale=1.5)
                bitmap.to_pil().save(out / image)
                bitmap.close()
                if not slides or not unit["text"]:
                    textpage = page.get_textpage()
                    unit["text"] = textpage.get_text_range()
                    textpage.close()
                unit["image"] = image
                if "visual_check_required" not in unit["flags"]:
                    unit["flags"].append("visual_check_required")
                unit["review"] = None
                page.close()
        finally:
            document.close()
        if digest(original) != source["sha256"]:
            raise ValueError("source changed during conversion")
        shutil.copy2(pdf, folder / (source_id + ".pdf"))
    if source.get("error") in ("unsupported_format", "no_content_extracted"):
        source["error"] = None
    source["rendered_pdf_sha256"] = digest(folder / (source_id + ".pdf"))
    save(out / "sources.json", data)
    return inspect(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--office")
    args = parser.parse_args()
    try:
        result = render(args.run, args.source, args.office)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["reading_ready"] else 4)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
