# -*- coding: utf-8 -*-
"""Offline preparation, validation and publication of agent-authored mock exams.

The host agent writes the blueprint, questions and solution review. This module
never calls a model, runs generated code, or changes the original study workspace.
"""
import datetime
import difflib
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import unicodedata

from . import extract, figures, guard, questions

TYPES = {"choice", "multiple_choice", "fill_blank", "true_false", "subjective",
         "calculation", "proof", "code", "diagram"}
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_FILES = 100
MAX_PAGES = 2000
MAX_QUESTIONS = 100
ID_PATTERN = re.compile(r"^[A-Za-z0-9_:.-]{1,80}$")
ASSET_PATH = re.compile(r"^assets/[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|gif|bmp|webp)$", re.I)
ANSWER_LABEL = re.compile(r"(?:^|\n)\s*(?:答案|参考答案|解析|answer|solution)\s*[:：]", re.I)


def digest_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inside(path, base):
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(base)]) == os.path.realpath(base)
    except ValueError:
        return False


def read_json(path):
    if os.path.islink(path) or os.path.getsize(path) > MAX_JSON_BYTES:
        raise ValueError("JSON must be a regular file no larger than 32 MB: " + path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object: " + path)
    return data


def write_json(path, data):
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_text(path, text):
    if os.path.islink(path):
        raise ValueError("Refusing to overwrite a symlink: " + path)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".write-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def normalized(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def positive(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 < value <= 10000)


def text_value(value, limit=30000):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit


def image_file(path):
    if not os.path.isfile(path) or os.path.getsize(path) > extract.MAX_FILE_BYTES:
        return False
    with open(path, "rb") as fh:
        head = fh.read(16)
    return (head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff")
            or head.startswith((b"GIF87a", b"GIF89a", b"BM"))
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))


def run_file(run, name):
    path = os.path.join(run, name)
    if not inside(path, run):
        raise ValueError("Run file escapes its directory: " + name)
    return path


def safe_output(out, roots):
    for root in roots:
        if inside(out, root):
            parts = os.path.relpath(os.path.realpath(out), os.path.realpath(root)).split(os.sep)
            if "exam-cram" not in parts:
                raise ValueError("Output inside source folders must be under exam-cram to avoid re-ingestion")


def collect(paths, role):
    files, roots = [], []
    for entry in paths:
        path = os.path.abspath(entry)
        if os.path.isdir(path):
            root, found = os.path.realpath(path), extract.list_files(path)
        elif os.path.isfile(path):
            root, found = os.path.realpath(os.path.dirname(path)), [path]
        else:
            raise ValueError("Input does not exist: " + path)
        roots.append(root)
        for file_path in found:
            if not inside(file_path, root):
                raise ValueError("Input symlink escapes its selected folder: " + file_path)
            if os.path.splitext(file_path)[1].lower() not in extract.SUPPORTED_EXT:
                raise ValueError("Unsupported input: " + file_path)
            if os.path.getsize(file_path) > extract.MAX_FILE_BYTES:
                raise ValueError("Input exceeds 200 MB: " + file_path)
            files.append((os.path.realpath(file_path), root, role))
    return files, roots


def prepare(args):
    files, roots = collect(args.papers, "paper")
    for paths, role in ((args.answers, "answer_reference"), (args.materials, "material")):
        extra, more_roots = collect(paths or [], role)
        files.extend(extra)
        roots.extend(more_roots)
    if not files or len(files) > MAX_FILES:
        raise ValueError("Select between 1 and 100 source files")
    out = os.path.abspath(args.out or os.path.join(roots[0], "exam-cram", "mock-exams"))
    safe_output(out, roots)
    inventory, by_digest, excerpts, total_pages = [], {}, [], 0
    for path, root, role in files:
        sha = digest_file(path)
        if sha in by_digest:
            old = by_digest[sha]
            if old["role"] != role:
                raise ValueError("The same file was selected with conflicting roles: " + path)
            if path not in old["aliases"]:
                old["aliases"].append(path)
            continue
        src = extract.extract_source(root, path)
        is_image = os.path.splitext(path)[1].lower() in extract.IMAGE_EXT
        pages = ([{"page": 1, "text": "", "needs_vision": True}] if is_image else
                 [{"page": p.number, "text": p.text, "needs_vision": len(p.text.strip()) < 20}
                  for p in src.pages])
        total_pages += len(pages)
        if total_pages > MAX_PAGES:
            raise ValueError("Selected files exceed 2000 pages; split the material into batches")
        source_id = "src-" + sha[:16]
        record = {"id": source_id, "path": path, "root": root, "sha256": sha,
                  "aliases": [path], "role": role, "pages": pages,
                  "error": src.error, "warnings": src.warnings, "candidates": []}
        if role == "paper" and not src.error:
            src.kind = "exam"  # Explicit paper selection, not a filename-based guess.
            for i, q in enumerate(questions.extract_questions([src], []), 1):
                record["candidates"].append({"id": "%s:p%d:q%d" % (source_id, q["source"]["page"], i),
                    "source": source_id, "page": q["source"]["page"], "locator": q["label"],
                    "prompt": q["question"], "options": q["options"], "points": q["points"],
                    "type": q["type"], "evidence": q["source"]["head"]})
        inventory.append(record)
        by_digest[sha] = record
        excerpts.append(guard.fence("%s | %s | %s" % (source_id, role, path)))
        for page in pages:
            excerpts.append("\n## %s p.%d\n\n%s" % (source_id, page["page"], guard.fence(page["text"])))
    sources = {"version": 1, "roots": sorted(set(roots)), "files": inventory}
    if len(json.dumps(sources, ensure_ascii=False).encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("Extracted text exceeds 32 MB; select fewer files")
    os.makedirs(out, exist_ok=True)
    run = tempfile.mkdtemp(prefix="mock-" + datetime.datetime.now().strftime("%Y%m%d-") , dir=out)
    write_json(run_file(run, "sources.json"), sources)
    write_text(run_file(run, "sources.sha256"), digest_file(run_file(run, "sources.json")) + "\n")
    write_text(run_file(run, "materials.md"), "# Source data / 原始资料\n\n" + "\n".join(excerpts) + "\n")
    write_json(run_file(run, "blueprint.json"), {
        "title": args.course or "模拟试卷 / Mock exam", "language": args.lang,
        "total_points": None, "duration_minutes": None, "structure_basis": "observed",
        "sections": [], "source_questions": [], "page_reviews": [],
        "assumptions": [], "gaps": [], "allow_extension": False})
    write_json(run_file(run, "draft.json"), {"questions": []})
    print("Run / 运行目录: " + run)
    print("Source files / 去重后资料: %d; pages / 页数: %d" % (len(inventory), total_pages))
    print("Read materials.md and source pages; author blueprint.json and draft.json with the host agent.")
    print("用当前助手读取资料、归纳结构并命题。准备材料不等于已生成模拟卷。")
    print("Next / 下一步: python coach.py mock validate --run \"%s\"" % run)
    return 0


def source_map(run, sources):
    with open(run_file(run, "sources.sha256"), encoding="utf-8") as fh:
        if fh.read().strip() != digest_file(run_file(run, "sources.json")):
            raise ValueError("Source inventory changed; prepare a new run")
    roots = sources.get("roots")
    files = sources.get("files")
    if (sources.get("version") != 1 or not isinstance(roots, list) or not roots
            or not all(isinstance(r, str) and os.path.isabs(r) for r in roots)
            or not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES):
        raise ValueError("Invalid sources.json inventory")
    safe_output(run, roots)
    result, seen = {}, set()
    for file in files:
        if not isinstance(file, dict):
            raise ValueError("Invalid source record")
        sid, path = file.get("id"), file.get("path")
        if not isinstance(sid, str) or not ID_PATTERN.fullmatch(sid) or sid in result:
            raise ValueError("Invalid or duplicate source ID")
        if (not isinstance(path, str) or not os.path.isabs(path)
                or not any(inside(path, root) for root in roots) or inside(path, run)):
            raise ValueError("Source path outside selected folders")
        if digest_file(path) != file.get("sha256"):
            raise ValueError("Source changed since prepare; prepare a new run: " + sid)
        if file["sha256"] in seen:
            raise ValueError("Duplicate source content in inventory")
        seen.add(file["sha256"])
        pages = file.get("pages")
        if not isinstance(pages, list) or len(pages) > MAX_PAGES:
            raise ValueError("Invalid page inventory")
        numbers = [p.get("page") for p in pages if isinstance(p, dict)]
        if numbers != list(range(1, len(pages) + 1)):
            raise ValueError("Invalid page sequence: " + sid)
        if file.get("role") not in {"paper", "answer_reference", "material"}:
            raise ValueError("Invalid source role")
        result[sid] = file
    return result


def page_view(args):
    run = os.path.abspath(args.run)
    files = source_map(run, read_json(run_file(run, "sources.json")))
    source = files.get(args.source)
    if not source or args.page < 1 or args.page > len(source["pages"]):
        raise ValueError("Unknown source or page")
    path, ext = source["path"], os.path.splitext(source["path"])[1].lower()
    assets = run_file(run, "assets")
    os.makedirs(assets, exist_ok=True)
    if ext == ".pdf":
        if not figures.has_pdfium():
            raise ValueError("PDF page rendering needs the existing optional pypdfium2 dependency")
        rel = "assets/%s-p%d.png" % (args.source, args.page)
        dest = run_file(run, rel)
        figures.render_region(path, args.page, None, dest)
    elif ext in extract.IMAGE_EXT and image_file(path):
        rel = "assets/%s-p%d%s" % (args.source, args.page, ext)
        dest = run_file(run, rel)
        shutil.copyfile(path, dest)
    else:
        raise ValueError("For this format, read materials.md or open the original document in the host")
    receipt_path = run_file(run, "page-views.json")
    receipts = read_json(receipt_path) if os.path.exists(receipt_path) else {"views": {}}
    key = "%s:p%d" % (args.source, args.page)
    receipts["views"][key] = {"path": rel, "sha256": digest_file(dest), "source_sha256": source["sha256"]}
    write_json(receipt_path, receipts)
    print(dest)
    print("Open this image before recording a vision review / 查看图片后才能记录视觉识别。")
    return 0


def has_view(run, source, page, views):
    record = views.get("%s:p%d" % (source["id"], page))
    if not isinstance(record, dict) or record.get("source_sha256") != source["sha256"]:
        return False
    rel = record.get("path")
    if not isinstance(rel, str):
        return False
    path = run_file(run, rel)
    return inside(path, run_file(run, "assets")) and image_file(path) and digest_file(path) == record.get("sha256")


def inspect_run(run):
    """Return structural errors, repeat warnings and an input-bound host-review digest."""
    sources = read_json(run_file(run, "sources.json"))
    files = source_map(run, sources)
    blueprint = read_json(run_file(run, "blueprint.json"))
    draft = read_json(run_file(run, "draft.json"))
    receipts = run_file(run, "page-views.json")
    views = read_json(receipts).get("views", {}) if os.path.exists(receipts) else {}
    if not isinstance(views, dict):
        raise ValueError("Invalid page-view receipts")
    errors, warnings, asset_digests = [], [], {}
    if not text_value(blueprint.get("title"), 200) or blueprint.get("language") not in {"zh", "en"}:
        errors.append("blueprint: provide title and language zh|en")
    if not positive(blueprint.get("total_points")):
        errors.append("blueprint: total_points must be positive")
    duration = blueprint.get("duration_minutes")
    if duration is not None and (not isinstance(duration, int) or isinstance(duration, bool) or not 1 <= duration <= 1440):
        errors.append("blueprint: duration_minutes must be null or 1..1440")
    if blueprint.get("structure_basis") not in {"observed", "inferred", "user_set"}:
        errors.append("blueprint: structure_basis must be observed|inferred|user_set")
    for key in ("assumptions", "gaps"):
        if not isinstance(blueprint.get(key), list) or not all(text_value(s) for s in blueprint.get(key, [])):
            errors.append("blueprint: %s must be a list of nonempty strings" % key)
    if not isinstance(blueprint.get("allow_extension", False), bool):
        errors.append("blueprint: allow_extension must be boolean")
    page_reviews = blueprint.get("page_reviews", [])
    if not isinstance(page_reviews, list) or len(page_reviews) > MAX_PAGES:
        raise ValueError("Invalid page_reviews")
    reviewed = set()
    for record in page_reviews:
        if not isinstance(record, dict):
            errors.append("Invalid page review")
            continue
        source, page = files.get(record.get("source")), record.get("page")
        if not source or not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= len(source["pages"]):
            errors.append("Page review references an unknown page")
            continue
        key = (source["id"], page)
        if key in reviewed:
            errors.append("Duplicate page review: %s p.%s" % key)
        reviewed.add(key)
        if record.get("status") == "excluded":
            warnings.append("Excluded source page: %s p.%s; %s" % (source["id"], page, record.get("reason", "")))
            if not text_value(record.get("reason")):
                errors.append("Excluded pages need a reason")
            continue
        if record.get("status") != "read" or record.get("method") not in {"text", "vision"}:
            errors.append("Read pages need method text|vision")
        elif record["method"] == "vision":
            if not has_view(run, source, page, views):
                errors.append("Vision review needs a current mock page image receipt")
        elif source["pages"][page - 1].get("needs_vision"):
            errors.append("Image-only pages cannot be recorded as text-read")
    for source in files.values():
        if source["role"] == "paper":
            if source.get("error") or not source["pages"]:
                warnings.append("Paper could not be extracted: " + source["id"])
            for page in source["pages"]:
                if (source["id"], page["page"]) not in reviewed:
                    errors.append("Paper page must be read or explicitly excluded: %s p.%d" % (source["id"], page["page"]))
    refs, topics = {}, set()
    source_questions = blueprint.get("source_questions")
    if not isinstance(source_questions, list) or not 1 <= len(source_questions) <= 1000:
        errors.append("blueprint: provide 1..1000 observed source_questions")
        source_questions = []
    for ref in source_questions:
        if not isinstance(ref, dict):
            errors.append("Invalid source question")
            continue
        rid, source, page = ref.get("id"), files.get(ref.get("source")), ref.get("page")
        if not isinstance(rid, str) or not ID_PATTERN.fullmatch(rid) or rid in refs:
            errors.append("Invalid or duplicate source-question ID")
            continue
        refs[rid] = ref
        if (not source or source["role"] != "paper" or not isinstance(page, int) or isinstance(page, bool)
                or not 1 <= page <= len(source["pages"]) or (source["id"], page) not in reviewed):
            errors.append("Source question must reference a reviewed paper page: " + rid)
            continue
        review = next((r for r in page_reviews if r.get("source") == source["id"] and r.get("page") == page), {})
        if review.get("status") != "read":
            errors.append("Source questions cannot reference excluded pages: " + rid)
        if not text_value(ref.get("locator"), 200) or not text_value(ref.get("prompt")):
            errors.append("Source question needs locator and prompt: " + rid)
        evidence = ref.get("evidence")
        if not text_value(evidence, 1000):
            errors.append("Source question needs an exact short source quote: " + rid)
        elif review.get("method") == "text" and normalized(evidence) not in normalized(source["pages"][page - 1].get("text", "")):
            errors.append("Source quote not found on its stated page: " + rid)
        if ref.get("type") not in TYPES:
            errors.append("Unsupported source-question type: " + rid)
        ref_topics = ref.get("topics")
        if not isinstance(ref_topics, list) or not ref_topics or not all(text_value(t, 200) for t in ref_topics):
            errors.append("Source question needs topics: " + rid)
        else:
            topics.update(ref_topics)
        if ref.get("points") is not None and not positive(ref["points"]):
            errors.append("Source-question points must be positive or null: " + rid)
    sections, planned_total, section_specs = blueprint.get("sections"), 0, {}
    if not isinstance(sections, list) or not 1 <= len(sections) <= MAX_QUESTIONS:
        errors.append("blueprint: provide sections")
        sections = []
    for section in sections:
        if not isinstance(section, dict):
            errors.append("Invalid section")
            continue
        sid = section.get("id")
        points = section.get("points")
        if not isinstance(sid, str) or not ID_PATTERN.fullmatch(sid) or sid in section_specs:
            errors.append("Invalid or duplicate section ID")
            continue
        section_specs[sid] = section
        if not text_value(section.get("title"), 200) or section.get("type") not in TYPES:
            errors.append("Section needs title and supported type: " + sid)
        if not isinstance(points, list) or not points or not all(positive(p) for p in points):
            errors.append("Section points must list each question's positive score: " + sid)
        else:
            planned_total += sum(points)
        if section.get("basis") not in {"observed", "inferred", "user_set"}:
            errors.append("Section needs basis observed|inferred|user_set: " + sid)
        if not isinstance(section.get("references"), list) or not section["references"] or not all(isinstance(r, str) and r in refs for r in section["references"]):
            errors.append("Section needs known source-question references: " + sid)
    if positive(blueprint.get("total_points")) and not math.isclose(planned_total, blueprint["total_points"], abs_tol=1e-8):
        errors.append("Section scores do not add up to total_points")
    items = draft.get("questions")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_QUESTIONS:
        errors.append("draft: provide 1..100 questions")
        items = []
    used_ids, actual, seen_prompts = set(), {sid: [] for sid in section_specs}, {}
    for item in items:
        if not isinstance(item, dict):
            errors.append("Invalid generated question")
            continue
        qid, sid = item.get("id"), item.get("section")
        if not isinstance(qid, str) or not ID_PATTERN.fullmatch(qid) or qid in used_ids:
            errors.append("Invalid or duplicate generated-question ID")
            continue
        used_ids.add(qid)
        if sid not in section_specs or item.get("type") != section_specs[sid].get("type"):
            errors.append("Question section/type mismatch: " + qid)
        elif positive(item.get("points")):
            actual[sid].append(item["points"])
        if not positive(item.get("points")):
            errors.append("Question needs positive points: " + qid)
        for field in ("prompt", "answer", "solution"):
            if not text_value(item.get(field)):
                errors.append("Question needs %s: %s" % (field, qid))
        if item.get("answer_provenance") != "ai_generated":
            errors.append("Generated answers must be labelled ai_generated: " + qid)
        options = item.get("options", {})
        if not isinstance(options, dict):
            errors.append("options must be an object: " + qid)
            options = {}
        choice = item.get("type") in {"choice", "multiple_choice"}
        if choice:
            keys = list(options)
            if (not 2 <= len(keys) <= 8 or keys != list("ABCDEFGH"[:len(keys)])
                    or not all(text_value(v, 3000) for v in options.values())):
                errors.append("Choice options must be consecutive A..H with text: " + qid)
            if all(isinstance(v, str) for v in options.values()) and len({normalized(v) for v in options.values()}) != len(options):
                errors.append("Duplicate choice options: " + qid)
            answer = item.get("answer")
            labels = re.sub(r"\s", "", answer).split(",") if isinstance(answer, str) else []
            if not labels or not all(a in options for a in labels) or len(labels) != len(set(labels)) or (item["type"] == "choice" and len(labels) != 1):
                errors.append("Choice answer must name valid unique option letters: " + qid)
        elif options:
            errors.append("Non-choice questions must not have options: " + qid)
        if item.get("type") == "true_false" and item.get("answer") not in {"true", "false"}:
            errors.append("true_false answer must be true|false: " + qid)
        prompt = item.get("prompt", "")
        public = "\n".join([prompt] + list(options.values())) if isinstance(prompt, str) and all(isinstance(v, str) for v in options.values()) else ""
        if ANSWER_LABEL.search(public):
            errors.append("Answer/solution label leaked into public question: " + qid)
        norm = normalized(public)
        if norm in seen_prompts:
            errors.append("Duplicate generated prompt: %s and %s" % (seen_prompts[norm], qid))
        seen_prompts[norm] = qid
        ref_ids = item.get("reference_items")
        if not isinstance(ref_ids, list) or not ref_ids or not all(isinstance(r, str) and r in refs for r in ref_ids):
            errors.append("Question needs known reference_items: " + qid)
        elif isinstance(prompt, str):
            for rid in ref_ids:
                original = normalized(refs[rid].get("prompt", ""))
                if original and normalized(prompt) == original:
                    errors.append("Question copies its source prompt verbatim: " + qid)
                elif len(original) > 15 and difflib.SequenceMatcher(None, normalized(prompt), original).ratio() > 0.85:
                    warnings.append("Near-source variant needs novelty review: " + qid)
        item_topics = item.get("topics")
        if not isinstance(item_topics, list) or not item_topics or not all(text_value(t, 200) for t in item_topics):
            errors.append("Question needs topics: " + qid)
        elif not blueprint.get("allow_extension", False) and not set(item_topics) <= topics:
            errors.append("Question outside observed topics: " + qid)
        rubric = item.get("rubric")
        if (not isinstance(rubric, list) or not rubric or not all(isinstance(r, dict) and positive(r.get("points"))
                and text_value(r.get("criterion")) for r in rubric)):
            errors.append("Question needs scored rubric criteria: " + qid)
        elif positive(item.get("points")) and not math.isclose(sum(r["points"] for r in rubric), item["points"], abs_tol=1e-8):
            errors.append("Rubric scores do not add up: " + qid)
        assets = item.get("assets", [])
        if not isinstance(assets, list) or not all(isinstance(a, str) for a in assets):
            errors.append("assets must list relative image paths: " + qid)
            assets = []
        if not isinstance(item.get("requires_assets", False), bool):
            errors.append("requires_assets must be boolean: " + qid)
        if (item.get("requires_assets") or item.get("type") == "diagram") and not assets:
            errors.append("Required question image missing: " + qid)
        for rel in assets:
            path = run_file(run, rel)
            if (not ASSET_PATH.fullmatch(rel) or not inside(path, run_file(run, "assets"))
                    or os.path.basename(path).startswith("src-") or not image_file(path)):
                errors.append("Question assets must be new images under run/assets: " + qid)
            else:
                asset_digests[rel] = digest_file(path)
    for sid, section in section_specs.items():
        if actual[sid] != section.get("points"):
            errors.append("Question count/order/scores differ from blueprint section: " + sid)
    # shortcut: textual similarity only; the host also reviews semantic repeats.
    prompt_pairs = list(seen_prompts.items())
    for i, (left, qid) in enumerate(prompt_pairs):
        for right, other_id in prompt_pairs[i + 1:]:
            if left and difflib.SequenceMatcher(None, left, right).ratio() > 0.9:
                warnings.append("Similar generated questions need review: %s, %s" % (qid, other_id))
    inputs = {name: digest_file(run_file(run, name)) for name in ("sources.json", "blueprint.json", "draft.json")}
    inputs["assets"] = asset_digests
    if os.path.exists(receipts):
        inputs["page_views"] = digest_file(receipts)
    input_digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode("utf-8")).hexdigest()
    review_path = run_file(run, "review.json")
    if os.path.exists(review_path):
        review = read_json(review_path)
        if review.get("input_digest") != input_digest:
            errors.append("Content review is stale; review current inputs after validate")
        if review.get("unresolved") != []:
            errors.append("Content review contains unresolved issues")
        records = review.get("questions")
        if not isinstance(records, list) or len(records) != len(used_ids):
            errors.append("Content review must cover every generated question exactly once")
            records = []
        record_map = {}
        for record in records:
            if not isinstance(record, dict) or record.get("id") in record_map:
                errors.append("Invalid or duplicate content-review record")
                continue
            record_map[record.get("id")] = record
        for item in items:
            if not isinstance(item, dict):
                continue
            record = record_map.get(item.get("id"), {})
            if (not all(record.get(k) is True for k in ("solution_recomputed", "scope_checked", "novelty_checked", "assets_checked", "agrees"))
                    or not text_value(record.get("recomputed_answer")) or not text_value(record.get("notes"))):
                errors.append("Incomplete host solution/content review: " + str(item.get("id")))
            elif item.get("type") in {"choice", "multiple_choice", "true_false"} and normalized(record["recomputed_answer"]) != normalized(item.get("answer", "")):
                errors.append("Recomputed answer differs: " + item["id"])
        if set(record_map) != used_ids:
            errors.append("Content review IDs do not match generated questions")
    else:
        errors.append("Missing review.json: the host must re-solve questions and record content review")
    return {"status": "needs_review" if errors else "ready", "errors": errors, "warnings": warnings,
            "input_digest": input_digest, "answer_provenance": "ai_generated"}, blueprint, draft


def validate(args):
    run = os.path.abspath(args.run)
    checks, _, _ = inspect_run(run)
    write_json(run_file(run, "checks.json"), checks)
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if checks["status"] == "ready" else 3


def publish(args):
    run = os.path.abspath(args.run)
    checks, blueprint, draft = inspect_run(run)
    write_json(run_file(run, "checks.json"), checks)
    if checks["status"] != "ready":
        print(json.dumps(checks, ensure_ascii=False, indent=2))
        return 3
    zh = blueprint["language"] == "zh"
    label = "⚠️ AI 新编模拟卷；答案为 AI 推导参考答案。" if zh else "⚠️ AI-generated mock exam; answers are AI-derived, not official."
    title = blueprint["title"]
    paper = ["# " + title, "", label, "", ("总分：%s" if zh else "Total points: %s") % blueprint["total_points"]]
    if blueprint.get("duration_minutes") is not None:
        paper.append(("时间：%s 分钟" if zh else "Time: %s minutes") % blueprint["duration_minutes"])
    answers = ["# " + title + (" · 参考答案与评分点" if zh else " · Answers and rubric"), "", label]
    order = 0
    for section in blueprint["sections"]:
        paper.extend(["", "## " + section["title"]])
        for item in draft["questions"]:
            if item["section"] != section["id"]:
                continue
            order += 1
            heading = "%d. (%s %s)" % (order, item["points"], "分" if zh else "points")
            paper.extend(["", "### " + heading, "", item["prompt"]])
            for key, option in item.get("options", {}).items():
                paper.append("\n%s. %s" % (key, option))
            for rel in item.get("assets", []):
                paper.append("\n![%s](../%s)" % ("题面图" if zh else "Question image", rel))
            answers.extend(["", "## " + heading, "", item["answer"], "", item["solution"], ""])
            for criterion in item["rubric"]:
                answers.append("- %s (%s)" % (criterion["criterion"], criterion["points"]))
            answers.append("\n%s: %s" % ("命题参考定位" if zh else "Design references", ", ".join(item["reference_items"])))
    report = ["# " + ("命题说明" if zh else "Design report"), "", label, "",
              "ready = structural checks + recorded host review; not an official accuracy guarantee.",
              "结构依据 / Structure basis: " + blueprint["structure_basis"], "",
              "Inputs digest: " + checks["input_digest"], "",
              "## " + ("考点与题源" if zh else "Topics and design references")]
    for item in draft["questions"]:
        report.append("- %s: %s → %s" % (item["id"], ", ".join(item["topics"]), ", ".join(item["reference_items"])))
    for key in ("assumptions", "gaps"):
        report.extend(["", "## " + key] + ["- " + line for line in blueprint[key]])
    report.extend(["", "## " + ("复核提醒" if zh else "Review warnings")] + ["- " + w for w in checks["warnings"]])
    target = run_file(run, "published")
    if os.path.lexists(target):
        raise ValueError("This run was already published; prepare a new run instead of overwriting it")
    staging = tempfile.mkdtemp(prefix=".publish-", dir=run)
    try:
        for name, lines in (("paper.md", paper), ("answers.md", answers), ("report.md", report)):
            write_text(os.path.join(staging, name), "\n".join(lines) + "\n")
        os.rename(staging, target)  # Publish all three files together after validation.
    finally:
        if os.path.exists(staging):
            shutil.rmtree(staging)
    print("Published / 已发布: " + target)
    print("paper.md | answers.md | report.md")
    return 0


def main(args):
    try:
        return {"prepare": prepare, "page": page_view, "validate": validate, "publish": publish}[args.mock_action](args)
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print("Mock exam / 模拟卷: " + str(exc), file=sys.stderr)
        return 2
