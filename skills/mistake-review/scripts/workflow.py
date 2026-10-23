"""Incremental, review-preserving mistake archives. Recognition/teaching stays with the agent."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from datetime import date, timedelta

FILES = ('错题分析.md', '错题分析.pdf', '错题分析.tex', '复习记录.json')
FIELDS = ('原题', '核心知识点', '解题思路', '详细解答', '易错点与错因', '方法总结')
KEYS = ('statement', 'knowledge', 'approach', 'solution', 'errors', 'method')
INTERVALS = dict(zip(('L0', 'L1', 'L2', 'L3', 'L4'), (1, 3, 7, 14, 30)))


def read_json(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def write_json(p, data):
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).is_file() else None


def fingerprint(text):
    return hashlib.sha256(re.sub(r'\s+', '', text).encode()).hexdigest()


def safe_name(value):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError('名称必须是非空且无首尾空格的字符串')
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', value) or value in ('.', '..') or value.endswith(('.', ' ')):
        raise ValueError('无效目录名: ' + value)
    if re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]', value.split('.')[0], re.I):
        raise ValueError('Windows 保留目录名')
    return value


def hashes(target):
    return {name: digest(target / name) for name in FILES}


def figure_files(md):
    paths = []
    for match in re.finditer(r'!\[[^\]\n]*\]\(([^)\n]+)\)', md):
        path = match[1]
        if not re.fullmatch(r'assets/[A-Za-z0-9_-]+\.(?:png|jpg|pdf)', path):
            raise ValueError('示意图必须使用 assets/ 中的安全相对路径')
        paths.append(path)
    return paths


def prepare(batch_path, library, stage, test_only=False):
    batch = read_json(batch_path)
    names = [safe_name(batch[k]) for k in ('subject', 'chapter', 'section')]
    library, stage = Path(library).resolve(), Path(stage).resolve()
    if stage.is_relative_to(library) or library.is_relative_to(stage):
        raise ValueError('草稿目录必须位于错题库之外且不包含错题库')
    if test_only and '测试验证' not in library.parts:
        raise ValueError('测试库路径必须含独立目录“测试验证”')
    target = library.joinpath(*names).resolve()
    if not target.is_relative_to(library):
        raise ValueError('目标越界')
    section_id = str(uuid.uuid5(uuid.NAMESPACE_URL, '/'.join(names)))
    state_path = target / '复习记录.json'
    if state_path.exists():
        state = read_json(state_path)
        if state['section_id'] != section_id:
            raise ValueError('已有小节身份不一致')
        if bool(state.get('test_only')) != test_only:
            raise ValueError('不能混用测试与正式记录')
    else:
        state = dict(schema_version=1, section_id=section_id, subject=names[0], chapter=names[1],
                     section=names[2], test_only=test_only, questions=[])
    state = copy.deepcopy(state)
    md_path = target / '错题分析.md'
    if md_path.exists() != state_path.exists():
        raise ValueError('已有 Markdown 与复习记录不配套，先核对恢复')
    md = md_path.read_text(encoding='utf-8') if md_path.exists() else f'# {names[2]}\n\n学科：{names[0]}；章节：{names[1]}\n'
    if test_only and not md_path.exists():
        md += '\n> 测试验证样本，未作为正式学习记录归档。\n'
    marker = '\n## 本小节知识总结\n'
    old_summary = md.split(marker, 1)[1] if marker in md else ''
    md = md.split(marker, 1)[0].rstrip() + '\n'
    seen = {q['fingerprint'] for q in state['questions']}
    new_count = 0
    new_assets = {}
    for q in batch['questions']:
        for k in KEYS:
            if not isinstance(q.get(k), str) or not q[k].strip():
                raise ValueError('缺少正文: ' + k)
            if re.search(r'^## ', q[k], re.M):
                raise ValueError('正文不能含二级标题')
        fp = fingerprint(q['statement'])
        if fp in seen:
            raise ValueError('发现重复题，请人工核对后局部修改而非重复追加')
        seen.add(fp)
        qid = 'Q-' + uuid.uuid5(uuid.UUID(section_id), fp).hex[:12]
        md += f'\n## 题目 {qid}\n'
        for field, key in zip(FIELDS, KEYS):
            md += f'\n### {field}\n\n{q[key].strip()}\n'
        if q.get('diagram'):
            image = Path(q['diagram']['path']).resolve()
            if not image.is_file() or image.suffix.lower() not in ('.png', '.jpg'):
                raise ValueError('示意图须为已绘制并检查的 PNG/JPG')
            name = f'assets/{qid}-figure{image.suffix.lower()}'
            caption = q['diagram'].get('caption', '区域示意图')
            if any(c in caption for c in '\n[]'):
                raise ValueError('图注不能含换行或方括号')
            md += f'\n### 示意图\n\n![{caption}]({name})\n'
            new_assets[name] = image
            if image.with_suffix('.pdf').is_file():
                new_assets[f'assets/{qid}-figure.pdf'] = image.with_suffix('.pdf')
        sources = []
        for source in q.get('sources', []):
            src = Path(source['path']).resolve()
            if not src.is_file():
                raise ValueError('原始材料不存在: ' + str(src))
            sources.append(dict(path=str(src), sha256=digest(src), location=source.get('location', '')))
        if not sources:
            raise ValueError('须提供来源文件；纯文字应先保存为库外原始文本')
        md += '\n### 来源\n\n' + '\n'.join(f"- {s['path']}；位置：{s['location']}；SHA256：{s['sha256']}" for s in sources) + '\n'
        state['questions'].append(dict(id=qid, fingerprint=fp, knowledge_tags=q.get('tags', []),
                                       error_type=q.get('error_type', '待确认'), sources=sources,
                                       mastery='unreviewed', review_count=0, last_review=None,
                                       next_review=None, history=[]))
        new_count += 1
    if not new_count:
        raise ValueError('没有新增题目')
    # Existing summaries stay intact; new material is a clearly scoped addition.
    summary = batch.get('summary', '').strip()
    md += marker + '\n' + old_summary.strip()
    if summary:
        md += ('\n\n本次补充：\n\n' if old_summary.strip() else '') + summary
    md = md.rstrip() + '\n'
    stage.mkdir(parents=True, exist_ok=True)
    assets = {}
    for name in figure_files(md):
        for candidate in dict.fromkeys((name, str(Path(name).with_suffix('.pdf')).replace('\\', '/'))):
            source = new_assets.get(candidate, target / candidate)
            if not source.is_file():
                if candidate == name:
                    raise ValueError('缺少图形附件: ' + candidate)
                (stage / candidate).unlink(missing_ok=True)
                continue
            destination = stage / candidate
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            assets[candidate] = digest(destination)
    (stage / '预览.md').write_text(md, encoding='utf-8')
    write_json(stage / '复习记录候选.json', state)
    receipt = dict(target=str(target), library=str(library), base=hashes(target), test_only=test_only,
                   layout_hash=digest(library / '排版设置.json'),
                   assets=assets, assets_base={name: digest(target / name) for name in assets},
                   preview_hash=digest(stage / '预览.md'), state_hash=digest(stage / '复习记录候选.json'),
                   new_count=new_count, batch_id=uuid.uuid4().hex)
    write_json(stage / 'receipt.json', receipt)
    return receipt


def escape_tex(text):
    replacements = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
                    '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    return ''.join(replacements.get(c, c) for c in text)


def latex_text(text):
    parts = re.split(r'(\$\$[\s\S]*?\$\$|(?<!\$)\$(?!\$)[^$\n]+\$)', text)
    out = []
    for part in parts:
        if part.startswith('$$'):
            # No arbitrary TeX commands are needed outside math. Reject file/shell primitives in math too.
            out.append('\\[' + part[2:-2] + '\\]')
        elif part.startswith('$'):
            out.append(part)
        else:
            out.append(escape_tex(part).replace('\n\n', '\n\\par\n').replace('\n- ', '\n\\par '))
    result = ''.join(out)
    if re.search(r'\\(?:input|include|write|openout|read|catcode|csname|def|newcommand|usepackage|special)\b', result):
        raise ValueError('公式含不应出现的 TeX 文件/执行命令')
    return result


def to_tex(md, settings=None):
    settings = settings or {}
    if settings.get('paper', 'A4') != 'A4' or settings.get('orientation', 'portrait') != 'portrait' or settings.get('layout', 'questions_then_solutions') != 'questions_then_solutions':
        raise ValueError('当前模板支持 A4 纵向、题目解析分区；其他版式须先修改模板再预览')
    redo_space = settings.get('redo_space_mm', 50)
    if not isinstance(redo_space, (int, float)) or not 0 <= redo_space <= 180:
        raise ValueError('重做留白必须为 0 到 180 毫米')
    title = md.splitlines()[0].lstrip('# ').strip()
    questions = []
    for match in re.finditer(r'^## 题目 (Q-[a-f0-9]+)\n([\s\S]*?)(?=^## |\Z)', md, re.M):
        sections = dict(re.findall(r'^### ([^\n]+)\n([\s\S]*?)(?=^### |\Z)', match[2], re.M))
        if not all(k in sections for k in FIELDS):
            raise ValueError('Markdown 题目结构不完整')
        questions.append((match[1], sections))
    if not questions:
        raise ValueError('无可排版的题目')
    tex = r'''\documentclass[UTF8,fontset=none,zihao=-4]{ctexart}
\usepackage[a4paper,margin=22mm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\setCJKmainfont{Microsoft YaHei}
\setCJKsansfont{Microsoft YaHei}
\setCJKmonofont{Microsoft YaHei}
\usepackage{fancyhdr}
\pagestyle{fancy}\fancyhf{}\fancyfoot[C]{\thepage}
\setlength{\headheight}{15pt}
\setlength{\parindent}{0pt}\setlength{\parskip}{5pt}
\ctexset{paragraph/beforeskip=7pt}
\allowdisplaybreaks[1]
\begin{document}
'''
    tex += '\\begin{center}\\LARGE ' + escape_tex(title) + '\\end{center}\n'
    if '测试验证样本' in md:
        tex += '\\begin{center}测试验证样本（未正式归档）\\end{center}\n'
    tex += '\\section*{题目区}\n'
    for i, (qid, fields) in enumerate(questions, 1):
        if i > 1:
            tex += '\\clearpage\n'
        tex += f'\\subsection*{{题目 {i}（{qid}）}}\n' + latex_text(fields['原题'].strip())
        tex += '\n\\par\\vspace{6mm}重做区域：\\par\\vspace{50mm}\\hrule\n'
    tex += '\\clearpage\\section*{解析区}\n'
    for i, (qid, fields) in enumerate(questions, 1):
        if i > 1:
            tex += '\\clearpage\n'
        tex += f'\\subsection*{{题目 {i}（{qid}）}}\n'
        for k in FIELDS[1:]:
            tex += '\\paragraph{' + k + '}\n' + latex_text(fields[k].strip()) + '\n'
            if k == '解题思路' and fields.get('示意图'):
                figures = figure_files(fields['示意图'])
                if len(figures) != 1:
                    raise ValueError('每道题的示意图字段须包含一张图片')
                png = figures[0]
                vector = str(Path(png).with_suffix('.pdf')).replace('\\', '/')
                caption = re.search(r'!\[([^\]\n]*)\]', fields['示意图'])[1]
                options = '[width=.85\\linewidth,height=50mm,keepaspectratio]'
                tex += '\\begin{center}\\IfFileExists{' + vector + '}{\\includegraphics' + options + '{' + vector + '}}{\\includegraphics' + options + '{' + png + '}}\\par\\small ' + escape_tex(caption) + '\\end{center}\n'
    summary = md.split('\n## 本小节知识总结\n', 1)[1]
    tex += '\\paragraph{本小节知识总结}\n' + latex_text(summary.strip())
    return (tex + '\n\\end{document}\n').replace('\\vspace{50mm}', f'\\vspace{{{redo_space}mm}}')


def compile_pdf(tex_path, compiler):
    bundled = Path(__file__).resolve().parents[1] / 'tools' / 'tectonic.exe'
    if compiler == 'tectonic' and bundled.is_file():
        compiler = str(bundled)
    compiler = str(Path(compiler).resolve()) if Path(compiler).exists() else shutil.which(compiler)
    if not compiler:
        raise RuntimeError('找不到 LaTeX 编译器')
    tex_path = Path(tex_path).resolve()
    if 'tectonic' in Path(compiler).name.lower():
        cmd = [compiler, '--untrusted', '--keep-logs', '--outdir', str(tex_path.parent), str(tex_path)]
    else:
        cmd = [compiler, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', '-output-directory=' + str(tex_path.parent), str(tex_path)]
    result = subprocess.run(cmd, cwd=tex_path.parent, capture_output=True, timeout=360)
    (tex_path.parent / '编译日志.txt').write_bytes(result.stdout + result.stderr)
    pdf = tex_path.with_suffix('.pdf')
    if result.returncode or not pdf.exists() or pdf.stat().st_size < 1000:
        raise RuntimeError('LaTeX 编译失败，原库未提交；见草稿目录编译日志')
    from pypdf import PdfReader
    reader = PdfReader(str(pdf))
    if not reader.pages:
        raise RuntimeError('PDF 无页面')
    return pdf


def archive(stage, confirmed=False, compiler='tectonic'):
    stage = Path(stage).resolve()
    r = read_json(stage / 'receipt.json')
    target = Path(r['target'])
    library = Path(r['library'])
    if not target.resolve().is_relative_to(library.resolve()):
        raise ValueError('目标越界')
    if r['test_only'] and '测试验证' not in library.parts:
        raise ValueError('测试库路径不正确')
    if not confirmed and not r['test_only']:
        raise PermissionError('正式归档必须收到用户对预览的明确确认')
    if hashes(target) != r['base']:
        raise RuntimeError('原库在预览后已改变，须重新合并预览')
    if digest(library / '排版设置.json') != r.get('layout_hash'):
        raise RuntimeError('排版设置在预览后改变，须重新准备')
    if digest(stage / '预览.md') != r['preview_hash'] or digest(stage / '复习记录候选.json') != r['state_hash']:
        raise RuntimeError('草稿被修改，须重新 prepare')
    for name, expected in r.get('assets', {}).items():
        if not re.fullmatch(r'assets/[A-Za-z0-9_-]+\.(?:png|jpg|pdf)', name):
            raise ValueError('附件路径不正确')
        if digest(stage / name) != expected or digest(target / name) != r['assets_base'][name]:
            raise RuntimeError('示意图附件在预览后改变，须重新 prepare')
    md = (stage / '预览.md').read_text(encoding='utf-8')
    tex = stage / '错题分析.tex'
    settings = read_json(library / '排版设置.json') if (library / '排版设置.json').exists() else {}
    tex.write_text(to_tex(md, settings), encoding='utf-8')
    pdf = compile_pdf(tex, compiler)
    if hashes(target) != r['base'] or any(digest(target/name) != value for name,value in r.get('assets_base', {}).items()):
        raise RuntimeError('编译期间原库改变，拒绝覆盖')
    target.mkdir(parents=True, exist_ok=True)
    backup = target / '.backups' / r['batch_id']
    if any(r['base'].values()):
        backup.mkdir(parents=True, exist_ok=False)
    candidates = dict(zip(FILES, (stage / '预览.md', pdf, tex, stage / '复习记录候选.json')))
    candidates.update({name: stage / name for name in r.get('assets', {})})
    before = dict(r['base'], **r.get('assets_base', {}))
    for name in candidates:
        if (target / name).exists():
            (backup / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / name, backup / name)
    try:
        for name, src in candidates.items():
            pending = target / (name + '.pending')
            pending.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, pending)
            os.replace(pending, target / name)
    except Exception:
        for name in candidates:
            if (backup / name).exists():
                shutil.copy2(backup / name, target / name)
            elif before[name] is None:
                (target / name).unlink(missing_ok=True)
            (target / (name + '.pending')).unlink(missing_ok=True)
        raise
    return dict(target=str(target), questions=len(read_json(target / '复习记录.json')['questions']), pdf_sha256=digest(target / '错题分析.pdf'))


def review(section, qid, when, level, prompt, answer, hints, evidence, event):
    when = date.fromisoformat(when)
    if level not in INTERVALS or hints < 0 or not all(s.strip() for s in (prompt, answer, evidence, event)):
        raise ValueError('复习等级、提示次数或证据不完整')
    path = Path(section) / '复习记录.json'
    state = read_json(path)
    q = next((q for q in state['questions'] if q['id'] == qid), None)
    if q is None:
        raise ValueError('不存在该题 ID')
    if any(h['event_id'] == event for h in q['history']):
        raise ValueError('复习事件重复')
    if q['last_review'] and when < date.fromisoformat(q['last_review']):
        raise ValueError('复习日期早于已有记录')
    if level in ('L3', 'L4') and hints:
        raise ValueError('使用提示不能评为独立完成')
    if level == 'L4' and not any(h['level'] in ('L3', 'L4') and h['hints'] == 0 for h in q['history']):
        raise ValueError('L4 需要先有独立完成记录')
    q['history'].append(dict(event_id=event, date=str(when), level=level, prompt=prompt, answer=answer,
                             hints=hints, evidence=evidence, simulated=bool(state.get('test_only'))))
    q.update(mastery=level, review_count=len(q['history']), last_review=str(when),
             next_review=str(when + timedelta(days=INTERVALS[level])))
    pending = path.with_suffix('.json.pending')
    write_json(pending, state)
    os.replace(pending, path)
    return q


def due(library, when):
    date.fromisoformat(when)
    result = []
    for path in Path(library).glob('*/*/*/复习记录.json'):
        for q in read_json(path)['questions']:
            if q['next_review'] is None or q['next_review'] <= when:
                result.append(dict(section=str(path.parent), id=q['id'], mastery=q['mastery'], next_review=q['next_review']))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest='command', required=True)
    a = subs.add_parser('prepare'); a.add_argument('batch'); a.add_argument('--library', required=True); a.add_argument('--stage', required=True); a.add_argument('--test-only', action='store_true')
    a = subs.add_parser('archive'); a.add_argument('stage'); a.add_argument('--confirmed', action='store_true'); a.add_argument('--compiler', default='tectonic')
    a = subs.add_parser('due'); a.add_argument('--library', required=True); a.add_argument('--date', required=True)
    a = subs.add_parser('review'); a.add_argument('section')
    for k in ('question', 'date', 'level', 'prompt', 'answer', 'evidence', 'event'): a.add_argument('--' + k, required=True)
    a.add_argument('--hints', type=int, default=0)
    v = p.parse_args()
    if v.command == 'prepare': result = prepare(v.batch, v.library, v.stage, v.test_only)
    elif v.command == 'archive': result = archive(v.stage, v.confirmed, v.compiler)
    elif v.command == 'due': result = due(v.library, v.date)
    else: result = review(v.section, v.question, v.date, v.level, v.prompt, v.answer, v.hints, v.evidence, v.event)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
