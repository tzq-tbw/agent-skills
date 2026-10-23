# Integrated chapter guides

This independent Flash route builds one handout per chapter from documents, page images, timestamped recordings and existing AI summaries. It does not change teaching sessions, quizzes, mock exams, study_state.json or Full. Python inventories and checks evidence; the host AI reads pages, verifies transcriptions, groups topics and authors the handout. Extraction alone is not understanding.

## Dependencies and installation boundary

The installed Skill contains `coach.py`, `coach/`, references and optional host helpers under `scripts/`, including `guide_render.py`, `guide_pdf_layers.py`, `guide_transcribe.py` and `guide_export.py`. Install their optional dependencies only when needed. Use equivalent host tools when unavailable, preserving the same evidence and checks. No model API or automatic cloud upload is configured.

Optional local packages: `pypdfium2 Pillow` for PDF page images; `rapidocr_onnxruntime` for OCR; `faster-whisper numpy` plus FFmpeg/ffprobe for local transcription; Pandoc and `python-docx` for editable Word equations; LibreOffice for Office page rendering and Word visual QA. Install only what the selected route needs. Cached Whisper models work offline; downloads require explicit `--download-model`. Chinese, handwriting and math recognition still need visual/audio checking.

## 1. Inventory, render and check reading

Run Skill commands from its directory (or use the repository's root coach.py):

```bash
python coach.py guide prepare MATERIALS --out ABSOLUTE_NEW_RUN
python coach.py guide inspect --run RUN
python coach.py guide ocr --run RUN --units s001-p0001 --rotate 0
```

Outputs must be outside the original materials. Nonempty runs are not overwritten. All files are inventoried; unknown formats and untranscribed audio remain explicit issues. PDF pages retain physical page numbers and original images. Private-use symbols, embedded pictures and blank extraction trigger review; they do not prove a page is scanned. OCR saves boxes, confidence and candidate text but never approves itself. Try rotation for sideways scans, then inspect the original image, tables and equations. Do not silently guess unreadable symbols.

For PDF overlays or superimposed animation states, use the optional repository helper before declaring content permanently unreadable:

```bash
python scripts/guide_pdf_layers.py --run RUN --unit s001-p0001
# Read the adjacent JSON object inventory, then hide explicitly selected occluders:
python scripts/guide_pdf_layers.py --run RUN --unit s001-p0001 --hide 143
```

It renders a derived view from the original PDF objects and records source/image hashes, bounds, text and hidden object indices. It never changes the original or grants reading approval. Compare each separate state with the original, including complement bars and condition symbols; do not combine conflicting states into an invented formula. If a photo is downscaled on the page, inspect its original embedded resolution. Record task-relevant content and explicitly name omitted noninstructional details; unreadable instructional content must remain unresolved.

For PPTX/DOCX, keep extracted text and slide notes, and render the original Office file using the repository helper:

```bash
python scripts/guide_render.py --run RUN --source s001 --office PATH_TO_SOFFICE
```

PPTX images stay aligned to slide IDs; notes remain in text. DOCX extraction blocks are not physical pages: additional rendered `rNNNN` units carry physical page images. Legacy PPT may use this rendering fallback. Unsupported extraction errors remain visible when rendering cannot repair them. Render before reviewing or mapping; adding page evidence invalidates affected reviews. Rendering cannot prove semantic correctness.

Import a JSON list of evidence-backed corrections:

```json
[{"unit":"s001-p0001","source_sha256":"COPY_FROM_sources.json","method":"visual","text":"Checked content","note":"Checked the original page; state limitations here","unresolved":false}]
```

```bash
python coach.py guide review --run RUN --file review.json
```

Use `visual` or `ocr_checked` for document pages, `audio_checked` for transcripts, `summary_checked` for summaries. Original extracted text is retained. Source hash changes invalidate reviews. Unreadable content stays `unresolved:true`; verified blank pages may have empty text with a reason. Exit 4 means outstanding evidence/content issues; exit 2 means an input or dependency error.

## 2. Transcribe recordings and reconcile summaries

```bash
python scripts/guide_transcribe.py AUDIO --task-dir TRANSCRIPTION --model CACHED_MODEL --language zh --pilot
# Inspect the first minute, then resume without --pilot using identical arguments:
python scripts/guide_transcribe.py AUDIO --task-dir TRANSCRIPTION --model CACHED_MODEL --language zh
python coach.py guide attach --run RUN --source s002 --kind transcript --file TRANSCRIPTION/transcript.json
python coach.py guide attach --run RUN --source s002 --kind summary --file summary.json
```

The helper normalizes to 16 kHz mono PCM, uses local CPU int8 Whisper, and saves resumable minute checkpoints. Its workflow is adapted from the local video-to-note transcription helper; it uses FFmpeg, faster-whisper and NumPy directly, without requiring that Skill at runtime. Minute boundaries can split sentences: replay uncertain terms, numbers and boundary audio before claiming fidelity. Empty recognized minutes require listening, not a silent-pass assumption. Partial/pilot transcripts cannot establish complete coverage.

A summary attachment is `{"source_sha256":"AUDIO_HASH","text":"Existing AI summary"}`. Transcripts require the same audio hash, completed coverage, duration and timestamped segments. Summary-only material cannot replace a missing transcript. A standalone document named with `summary` or `总结` is secondary evidence; explicitly associate it with the right recording during authoring. Check each useful summary claim against the audio/transcript and course pages, correct mistakes, add omitted conditions and examples, and mark unsupported claims. Without a summary, write study notes from checked transcript segments. Do not present a synthetic test recording as a classroom recording.

## 3. Map chapters and combine evidence

Write a mapping covering every unit once, or exclude a unit with a concrete reason:

```json
{"chapters":[{"id":"ch01","title":"Chapter 1","units":["s001-p0001","s002-t0001","s002-summary"]}],"excluded":{}}
```

```bash
python coach.py guide map --run RUN --file chapter-map.json
python coach.py guide packet --run RUN --chapter ch01
```

Use course headings and actual content, not filenames or lecture numbering alone. Timestamp segments may be assigned to different chapters; if a segment straddles a boundary, preserve its range and explain the overlap in the handout. Mapping binds the current sources/reviews; remap after changes. Packets are authoring evidence, not finished lessons.

## 4. Author, verify and deliver one document per chapter

A chapter handout is a teaching document. Organize it by the subject's knowledge points, with each topic explaining what the concept means, why a formula works, its conditions and a worked example. Integrate matching textbook, slide and lecture content in the same explanation. Keep extraction reports, OCR repair notes, source-error discussions and completeness audits in the internal run, outside the student-facing explanation. Use the correct mathematics directly; include a limitation in the handout only when it changes the learner's interpretation.

Choose meaningful level-two topic headings and record their exact titles in the content review's `sections` list. Do not force definitions, derivations and examples into separate repeated chapters, or require an engineering audit section in the handout. Reviews without `sections` retain the legacy eight-section check for compatibility.

Keep prose in short paragraphs. Important or lengthy equations belong on their own lines; split long derivations into aligned steps. Use explicit event intersections instead of adjacent letters when readability benefits. For this user's probability handouts, denote complements by `\overline{A}`, including a bar over the entire compound event when appropriate. Prefer roomy spacing over fewer pages; inspect bars, fractions and subscripts in the final renderer.

### 排版复盘与后续交付规则

适用于本用户的章节讲义。2026-10-18 用户认可《第一章 概率知识点讲义 符号修正版》的排版，后续以这一版为参考，不把本地示例的页数和路径作为固定要求。

| 已发生的问题 | 后续改法 |
|---|---|
| 内容混入“课件面积表达错误”、OCR恢复、资料审核等说明，偏离知识点讲解 | 围绕概念、符号含义、公式条件、推导与例题讲解；同一知识点融合对应教材、课件和录音。读取问题与审核记录留在内部，只有影响知识理解的真实不确定性才写入正文。 |
| 为压缩页数使正文、公式和相邻字母拥挤 | 沿用宽松版式：正文约12 pt、1.5倍行距，独立公式约14 pt，并保留段前段后间距。长公式分步换行，不靠缩小字号硬塞；短表格尽量完整放在同页，标题与后文相连，不强制每个主题另起一页。 |
| 补事件横杠断开，分数线、上下标和大并集显示不完整，并集外形容易被读成字母U | 本用户以稳定阅读为先，默认采用已验证的 MathJax 等数学排版器，将公式以高清图形嵌入 Word，并交付同版 PDF。正文保留可编辑；提前说明公式图形不能作为原生 Word 公式直接编辑。用户明确要求公式可编辑时保留原生公式，并单独验证兼容性。 |
| 公式结构正确，就认定用户看到的显示也正常 | XML检查、LibreOffice渲染、实际客户端显示是不同层次。不能用前两者否定用户报告的缺陷；先检查其指出的位置，并排查同类公式。未测试的客户端明确标为未验证。 |
| 仅摆出复杂符号，学习者仍无法读懂 | 先解释关键符号及作用范围，再给公式和例子；频率讲清分子分母，大并集与求和给出展开式。补充解释要服务知识理解，不增加工程说明或空泛提醒。 |

符号与排版检查：

- 补事件统一用上横杠。整体取反写 `\overline{A\cup B}`，一条连续长横杠覆盖整个事件；分别取反写 `\overline{A}`、`\overline{B}`。不擅自改为上标 `c`。
- 集合并、交使用标准 `\cup`、`\cap`；交事件明确写出符号，避免相邻字母混淆。逐项核对括号、条件概率竖线、等号、负号、分数线、根号、上下标、求和、连乘与大并集的范围、方向和位置。分清数学含义错误与显示缺陷，不为迁就显示而改错公式。
- 嵌入公式图形时使用透明背景、约288 dpi或更高的清晰度；按物理字号等比例插入，行内公式对齐基线，独立公式居中，不拉伸。保留公式源文本及顺序映射，核对转换前后数量与内容，防止漏式、错配；含中文的公式也要检查缺字。
- 多行推导逐行保持等价且留出间距。原生公式经过 Pandoc 与 LibreOffice 转换时，曾出现 `aligned` 的 `&` 被显示为字面字符；使用经验证的分行方式，最终页面不得遗留 LaTeX 命令或对齐标记。

交付检查：先核对数学内容，再渲染最终 Word/PDF并逐页查看，检查公式清晰度、横杠连续性、裁切、重叠、分页和表格。任何改动后重新渲染受影响的结果；可用页面哈希确认其余已检查页面未变。记录最终文件哈希、实际页数和已验证的渲染环境，不能把“导出成功”或“测试通过”当作用户已认可。用户再次指出问题时修复实际阅读结果，不重复交付同一个有显示问题的文件。

Keep provenance and source/AI distinctions in the internal authoring records. Exact source IDs and the complete coverage index may be retained in Markdown HTML comments so Word does not show long technical identifiers. Do not rely on the index as a semantic coverage check: the host must still check each taught claim and calculation against the packet. Retain unresolved instructional issues honestly; do not add absent classroom information.

Deliver chapter documents together, one per chapter, with extraction and review files kept separately.

Write content-review JSON bound to the actual draft and evidence:

```json
{"sections":["Exact topic title 1","Exact topic title 2"],"draft_sha256":"HASH","sources_digest":"HASH_OF_sources.json","mapping_digest":"HASH_OF_chapters.json","coverage":{"passed":true,"note":"What topics/examples were checked"},"correctness":{"passed":true,"note":"Calculations, conditions and corrections checked"},"summary_reconciliation":{"passed":true,"note":"What summaries were compared, or no recordings supplied"},"unresolved":[]}
```

```bash
python coach.py guide validate --run RUN --chapter ch01 --draft chapter.md --review content-review.json
python scripts/guide_export.py --run RUN --chapter ch01 --draft chapter.md --review content-review.json --out chapter.docx
```

Formal export requires reading issues resolved, complete mapping/citations, current hashes and a substantive host content review. It never invents those approvals. If source defects prevent completion, deliver a visibly labelled `样稿` with `--preview`, describe precisely what is missing, and retain the failed formal validation. Do not clear flags merely to export. The receipt stays `preview`, even after visual QA.

Render each Word file with the host's document renderer, inspect every page for formula symbols, line breaks, table clipping and missing images, fix and re-render. Record the reviewed output hash and actual page count. The optional exporter produces editable OMML; this user's accepted stable-display route additionally renders equations as images and exports a matching PDF, using host tools as needed. Disclose which equation representation was delivered. A successful export is not a visual or teaching-quality acceptance result.
