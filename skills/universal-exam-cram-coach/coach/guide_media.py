"""Optional local OCR and timestamped transcript import for chapter guides."""
import json
import math
from pathlib import Path

from .guide import digest, inspect, save


def ocr(run, unit_ids=None, rotate=0):
    from rapidocr_onnxruntime import RapidOCR
    from PIL import Image, ImageOps
    import numpy as np
    out = Path(run)
    data = json.loads((out / "sources.json").read_text(encoding="utf-8"))
    known = {u["id"] for s in data["sources"] for u in s["units"]}
    if unit_ids and not set(unit_ids) <= known:
        raise ValueError("unknown OCR unit")
    engine = RapidOCR()
    for source in data["sources"]:
        if digest(source["path"]) != source["sha256"]:
            raise ValueError("source changed")
        for unit in source["units"]:
            if unit_ids and unit["id"] not in unit_ids:
                continue
            if not unit_ids and not set(unit["flags"]) & {"no_text", "image_content"}:
                continue
            if not unit.get("image"):
                continue
            path = out / unit["image"]
            with Image.open(path) as im:
                image = ImageOps.exif_transpose(im).convert("RGB")
                if rotate:
                    image = image.rotate(rotate, expand=True)
                result, _ = engine(np.asarray(image))
            unit["ocr"] = {"source_sha256": source["sha256"], "rotation": rotate,
                           "lines": [{"box": box, "text": text, "confidence": float(score)}
                                     for box, text, score in (result or [])]}
            # OCR is evidence for review; it never grants its own approval.
            if "ocr_unreviewed" not in unit["flags"]:
                unit["flags"].append("ocr_unreviewed")
            save(out / "sources.json", data)
    return inspect(out)


def attach(run, source_id, path, kind):
    out = Path(run)
    data = json.loads((out / "sources.json").read_text(encoding="utf-8"))
    source = next((s for s in data["sources"] if s["id"] == source_id), None)
    if not source or source.get("kind") != "audio":
        raise ValueError("attachment requires an existing audio source")
    if digest(source["path"]) != source["sha256"]:
        raise ValueError("audio source changed")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    source_hash = payload.get("source_sha256") or payload.get("config", {}).get("source_sha256")
    if source_hash != source["sha256"]:
        raise ValueError("attachment does not match audio hash")
    if any(u.get("kind") == kind for u in source["units"]):
        raise ValueError("attachment already exists; use a new run to preserve mapped/reviewed segments")
    if kind == "summary":
        if not isinstance(payload.get("text"), str) or not payload["text"].strip():
            raise ValueError("summary text is empty")
        source["units"].append({"id": source_id + "-summary", "kind": "summary",
            "text": payload["text"], "page": None, "image": None,
            "flags": ["secondary_summary"], "review": None, "chapter": None})
    else:
        duration = payload.get("duration_seconds")
        processed = payload.get("processed_seconds")
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            raise ValueError("invalid audio duration")
        if payload.get("completed") is not True or not isinstance(processed, (int, float)) or abs(processed-duration) > .1:
            raise ValueError("partial/pilot transcript cannot establish complete audio coverage")
        segments = payload.get("segments")
        if not isinstance(segments, list) or not segments:
            raise ValueError("transcript segments required")
        previous = -1
        for i, seg in enumerate(segments, 1):
            start, end, text = seg.get("start"), seg.get("end"), seg.get("text")
            if (not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (start, end))
                    or not 0 <= start < end <= duration + .1 or start < previous
                    or not isinstance(text, str) or not text.strip()):
                raise ValueError("invalid transcript segment")
            previous = start
            source["units"].append({"id": "%s-t%04d" % (source_id, i), "kind": "transcript",
                "start": start, "end": end, "page": None, "text": text, "image": None,
                "flags": ["audio_review_required"], "review": None, "chapter": None})
        empty_chunks = payload.get("empty_chunks", [])
        if (not isinstance(empty_chunks, list) or len(set(empty_chunks)) != len(empty_chunks)
                or any(type(i) is not int or not 0 <= i < math.ceil(duration/60) for i in empty_chunks)):
            raise ValueError("invalid empty audio chunks")
        for offset, index in enumerate(empty_chunks, len(segments) + 1):
            source["units"].append({"id": "%s-t%04d" % (source_id, offset), "kind": "transcript",
                "start": index*60, "end": min((index+1)*60, duration), "page": None,
                "text": "[No speech recognized in this chunk; listen before classifying it as silence]",
                "image": None, "flags": ["audio_review_required", "empty_audio_chunk"],
                "review": None, "chapter": None})
        source["transcript"] = {"duration_seconds": duration,
                                "empty_chunks": empty_chunks,
                                "input_sha256": digest(path)}
        source["error"] = None
    save(out / "sources.json", data)
    return inspect(out)
