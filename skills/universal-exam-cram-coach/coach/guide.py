"""Isolated study-guide ingestion. Never reads or writes ordinary study state."""
import hashlib
import json
from pathlib import Path
import re
import zipfile

from . import extract

AUDIO = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".mp4"}


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def prepare(materials, output):
    root, out = Path(materials).resolve(), Path(output).resolve()
    if not root.is_dir():
        raise ValueError("materials must be a directory")
    if root == out or root in out.parents:
        raise ValueError("guide output must be outside the materials directory")
    if out.exists() and any(out.iterdir()):
        raise ValueError("output is not empty; use a new run to preserve prior reviews")
    files = sorted((p for p in root.rglob("*") if p.is_file()
                    and not any(x.startswith(".") for x in p.relative_to(root).parts)),
                   key=lambda p: extract.natural_key(p.name))
    if not files:
        raise ValueError("no materials found")
    out.mkdir(parents=True, exist_ok=True)
    (out / "pages").mkdir()
    records = []
    for index, path in enumerate(files, 1):
        sid = "s%03d" % index
        record = {"id": sid, "path": str(path), "relative": path.relative_to(root).as_posix(),
                  "sha256": digest(path), "units": [], "error": None}
        records.append(record)
        try:
            ext = path.suffix.lower()
            if path.stat().st_size > extract.MAX_FILE_BYTES and ext not in AUDIO:
                raise ValueError("document exceeds extraction size limit")
            if ext in AUDIO:
                record["kind"] = "audio"
                record["error"] = "transcript_required"
            elif ext == ".pdf":
                import pypdfium2 as pdfium
                doc = pdfium.PdfDocument(str(path))
                try:
                    for n in range(len(doc)):
                        page = doc[n]
                        tp = page.get_textpage()
                        text = tp.get_text_range()
                        tp.close()
                        image_name = "pages/%s-p%04d.png" % (sid, n + 1)
                        bitmap = page.render(scale=1.5)
                        bitmap.to_pil().save(out / image_name)
                        bitmap.close()
                        images = sum(obj.type == 3 for obj in page.get_objects())
                        flags = []
                        if not text.strip():
                            flags.append("no_text")
                        if images:
                            flags.append("image_content")
                        if any(0xE000 <= ord(c) <= 0xF8FF for c in text):
                            flags.append("symbol_encoding")
                        record["units"].append({"id": "%s-p%04d" % (sid, n + 1),
                            "page": n + 1, "text": text, "image": image_name,
                            "flags": flags, "review": None, "chapter": None})
                        page.close()
                finally:
                    doc.close()
            elif ext in extract.IMAGE_EXT:
                record["units"].append({"id": sid + "-p0001", "page": 1,
                    "text": "", "image": str(path), "flags": ["image_content", "no_text"],
                    "review": None, "chapter": None})
            elif ext in extract.READERS:
                summary = bool(re.search(r"summary|总结", path.stem, re.I))
                visual = ext == ".pptx"
                if ext in (".docx", ".pptx"):
                    with zipfile.ZipFile(path) as archive:
                        visual = visual or any(n.startswith("word/media/") for n in archive.namelist())
                        visual = visual or any(b":oMath" in archive.read(n) for n in archive.namelist()
                                              if n in ("word/document.xml",))
                for p in extract.READERS[ext](str(path)):
                    flags = ["visual_check_required"] if visual else []
                    if not p.text.strip():
                        flags.append("no_text")
                    if summary:
                        flags.append("secondary_summary")
                    record["units"].append({"id": "%s-p%04d" % (sid, p.number),
                        "page": p.number, "text": p.text, "image": None,
                        "flags": flags, "kind": "summary" if summary else "document",
                        "locator": ("extracted block %d (not a physical page)" % p.number)
                                   if ext == ".docx" else "p.%d" % p.number,
                        "review": None, "chapter": None})
                if not record["units"]:
                    record["error"] = "no_content_extracted"
            else:
                record["error"] = "unsupported_format"
        except Exception as exc:
            record["error"] = "%s: %s" % (type(exc).__name__, exc)
        save(out / "sources.json", {"version": 1, "materials": str(root), "sources": records})
    return inspect(out)


def inspect(output):
    out = Path(output)
    data = json.loads((out / "sources.json").read_text(encoding="utf-8"))
    issues = []
    total = 0
    for source in data["sources"]:
        if not Path(source["path"]).is_file() or digest(source["path"]) != source["sha256"]:
            issues.append({"source": source["id"], "issue": "source_changed"})
        if source.get("error"):
            issues.append({"source": source["id"], "issue": source["error"]})
        for unit in source["units"]:
            total += 1
            review = unit.get("review") or {}
            checked = (review.get("source_sha256") == source["sha256"]
                       and review.get("method") in ("visual", "ocr_checked", "audio_checked", "summary_checked")
                       and bool(review.get("note", "").strip())
                       and not review.get("unresolved", True))
            if unit["flags"] and not checked:
                issues.append({"unit": unit["id"], "issue": "review_required", "flags": unit["flags"]})
    report = {"sources": len(data["sources"]), "units": total,
              "reading_ready": not issues, "issues": issues,
              "note": "Extraction checks do not prove semantic correctness or chapter coverage."}
    save(out / "reading-report.json", report)
    return report


def import_review(output, review_file):
    out = Path(output)
    data = json.loads((out / "sources.json").read_text(encoding="utf-8"))
    updates = json.loads(Path(review_file).read_text(encoding="utf-8"))
    units = {u["id"]: (s, u) for s in data["sources"] for u in s["units"]}
    seen = set()
    if not isinstance(updates, list):
        raise ValueError("review must be a list")
    for review in updates:
        uid = review["unit"]
        if uid not in units or uid in seen:
            raise ValueError("unknown or duplicate unit: " + uid)
        seen.add(uid)
        source, unit = units[uid]
        if review["source_sha256"] != source["sha256"] or digest(source["path"]) != source["sha256"]:
            raise ValueError("stale review: " + uid)
        allowed = {"visual", "ocr_checked"}
        if unit.get("kind") == "transcript":
            allowed = {"audio_checked"}
        elif unit.get("kind") == "summary":
            allowed = {"summary_checked"}
        if review.get("method") not in allowed or not review.get("note", "").strip():
            raise ValueError("review requires method and evidence note")
        if not isinstance(review.get("unresolved"), bool):
            raise ValueError("review requires unresolved boolean")
        if not isinstance(review.get("text"), str):
            raise ValueError("review requires corrected text; blank allowed for verified blank page")
        unit["review"] = review
    save(out / "sources.json", data)
    return inspect(out)


def main(args):
    try:
        if args.guide_action == "prepare":
            report = prepare(args.materials, args.out)
        elif args.guide_action == "review":
            report = import_review(args.run, args.file)
        elif args.guide_action == "ocr":
            from .guide_media import ocr
            report = ocr(args.run, args.units, args.rotate)
        elif args.guide_action == "attach":
            from .guide_media import attach
            report = attach(args.run, args.source, args.file, args.kind)
        elif args.guide_action in ("map", "packet", "validate"):
            from . import guide_chapters
            if args.guide_action == "map":
                report = guide_chapters.map_chapters(args.run, args.file)
            elif args.guide_action == "packet":
                report = guide_chapters.packet(args.run, args.chapter)
            else:
                report = guide_chapters.validate(args.run, args.chapter, args.draft, args.review)
        else:
            report = inspect(args.run)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("valid", report.get("reading_ready", report.get("mapping_ready", False))) else 4
    except (ValueError, OSError, KeyError, TypeError, ImportError) as exc:
        print(str(exc))
        return 2
