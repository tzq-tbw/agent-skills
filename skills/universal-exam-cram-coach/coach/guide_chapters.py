"""Explicit source-to-chapter mapping and grounded authoring packets."""
import json
import re
from pathlib import Path

from .guide import digest, inspect, save

HEADINGS = ["学习目标", "重点知识与依据", "知识点详细讲解", "公式与推导",
            "典型例题与完整解答", "易错点与概念比较", "章节自测与答案解析", "资料来源与待核对问题"]


def load(run):
    out = Path(run)
    data = json.loads((out / "sources.json").read_text(encoding="utf-8"))
    return out, data, {u["id"]: (s, u) for s in data["sources"] for u in s["units"]}


def map_chapters(run, path):
    out, data, units = load(run)
    mapping = json.loads(Path(path).read_text(encoding="utf-8"))
    chapters = mapping.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("chapters list required")
    seen, ids = set(), set()
    for chapter in chapters:
        cid = chapter.get("id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", cid) or cid in ids:
            raise ValueError("invalid or duplicate chapter id")
        ids.add(cid)
        if not chapter.get("title", "").strip() or not chapter.get("units"):
            raise ValueError("chapter needs title and units")
        for uid in chapter["units"]:
            if uid not in units or uid in seen:
                raise ValueError("unknown or duplicate mapped unit: " + uid)
            seen.add(uid)
    excluded = mapping.get("excluded", {})
    if not isinstance(excluded, dict):
        raise ValueError("excluded must map unit IDs to reasons")
    for uid, reason in excluded.items():
        if uid not in units or uid in seen or not isinstance(reason, str) or not reason.strip():
            raise ValueError("invalid exclusion: " + uid)
        seen.add(uid)
    missing = sorted(set(units) - seen)
    if missing:
        raise ValueError("unmapped units: " + ", ".join(missing[:10]))
    mapping["sources_digest"] = digest(out / "sources.json")
    save(out / "chapters.json", mapping)
    return {"chapters": len(chapters), "mapped_units": len(units)-len(excluded),
            "excluded_units": len(excluded), "mapping_ready": True}


def packet(run, chapter_id):
    out, data, units = load(run)
    mapping = json.loads((out / "chapters.json").read_text(encoding="utf-8"))
    if mapping["sources_digest"] != digest(out / "sources.json"):
        raise ValueError("source extraction/reviews changed; revalidate chapter mapping")
    chapter = next((c for c in mapping["chapters"] if c["id"] == chapter_id), None)
    if chapter is None:
        raise ValueError("unknown chapter")
    report = inspect(out)
    used_sources = {units[uid][0]["id"] for uid in chapter["units"]}
    issues = [i for i in report["issues"] if i.get("unit") in chapter["units"] or i.get("source") in used_sources]
    lines = ["# " + chapter["title"], "", "Authoring packet, not a finished handout.",
             "Reading issues: %d" % len(issues), ""]
    for uid in chapter["units"]:
        source, unit = units[uid]
        where = ("%.2f–%.2fs" % (unit["start"], unit["end"])) if "start" in unit else unit.get("locator", "p.%s" % unit.get("page"))
        lines += ["## [%s] %s %s" % (uid, source["relative"], where), "",
                  "Type: " + unit.get("kind", "document"), ""]
        review = unit.get("review")
        text = review["text"] if review and review.get("unresolved") is False else unit["text"]
        lines += [text, ""]
        if unit.get("image"):
            lines += ["Original page: " + str((out / unit["image"]).resolve()), ""]
        if unit.get("ocr"):
            lines += ["Unverified OCR: " + " | ".join(x["text"] for x in unit["ocr"]["lines"]), ""]
    folder = out / "authoring"
    folder.mkdir(exist_ok=True)
    (folder / (chapter_id + "-packet.md")).write_text("\n".join(lines), encoding="utf-8")
    save(folder / (chapter_id + "-context.json"), {"chapter": chapter_id,
         "sources_digest": digest(out / "sources.json"), "mapping_digest": digest(out / "chapters.json"),
         "units": chapter["units"], "issues": issues})
    return {"packet": str(folder / (chapter_id + "-packet.md")), "reading_ready": not issues, "issues": issues}


def validate(run, chapter_id, draft_path, review_path):
    out, data, units = load(run)
    packet(run, chapter_id)
    ctx = json.loads((out / "authoring" / (chapter_id + "-context.json")).read_text(encoding="utf-8"))
    draft = Path(draft_path).read_text(encoding="utf-8")
    review = json.loads(Path(review_path).read_text(encoding="utf-8"))
    errors = ["unresolved reading issues"] if ctx["issues"] else []
    sections = review.get("sections", HEADINGS)
    if (not isinstance(sections, list) or not sections
            or any(not isinstance(h, str) or not h.strip() for h in sections)
            or len(set(sections)) != len(sections)):
        raise ValueError("content review requires a nonempty list of distinct section titles")
    for heading in sections:
        match = re.search(r"^## " + re.escape(heading) + r"\s*\n(.*?)(?=^## |\Z)", draft, re.M | re.S)
        if not match or not match.group(1).strip():
            errors.append("missing section: " + heading)
    cites = set(re.findall(r"\[(s\d{3}-(?:[prt]\d{4}|summary))\]", draft))
    if cites != set(ctx["units"]):
        errors.append("citations must cover exactly the mapped chapter units")
    if review.get("draft_sha256") != digest(draft_path) or review.get("sources_digest") != ctx["sources_digest"] or review.get("mapping_digest") != ctx["mapping_digest"]:
        errors.append("stale content review")
    for key in ("coverage", "correctness", "summary_reconciliation"):
        check = review.get(key, {})
        if check.get("passed") is not True or not isinstance(check.get("note"), str) or not check["note"].strip():
            errors.append("content review missing: " + key)
    if review.get("unresolved") != []:
        errors.append("unresolved content review")
    result = {"chapter": chapter_id, "valid": not errors, "errors": errors,
              "note": "Host content review is required; citation and format checks alone do not prove teaching quality."}
    save(out / "authoring" / (chapter_id + "-validation.json"), result)
    return result
