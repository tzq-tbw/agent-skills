"""Check durable evidence and outputs before optionally removing one task directory."""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import unquote, urlsplit


def reparse(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def evidence_images(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'image' and isinstance(item, str):
                yield item
            else:
                yield from evidence_images(item)
    elif isinstance(value, list):
        for item in value:
            yield from evidence_images(item)


def validate(workspace, task, note, evidence):
    workspace = Path(workspace).resolve(strict=True)
    expected_parent = workspace / 'work' / 'video_tmp'
    raw_task = Path(task).absolute()
    if raw_task.parent != expected_parent or reparse(raw_task):
        raise ValueError('Task must be a direct non-linked child of workspace/work/video_tmp')
    for parent in raw_task.parents:
        if parent == workspace:
            break
        if reparse(parent):
            raise ValueError('Linked temporary parent is not allowed')
    task = raw_task.resolve(strict=True)
    for child in task.rglob('*'):
        if reparse(child):
            raise ValueError('Task contains a symlink or Windows reparse point')
    note = Path(note).resolve(strict=True)
    evidence = Path(evidence).resolve(strict=True)
    if note.is_relative_to(task) or evidence.is_relative_to(task):
        raise ValueError('Note and evidence must survive task cleanup')
    text = note.read_text(encoding='utf-8-sig')
    report = json.loads(evidence.read_text(encoding='utf-8-sig'))
    if not text.strip() or not report['source'] or report['source'] not in text:
        raise ValueError('Empty note or missing source reference')
    if urlsplit(report['source']).scheme not in {'http', 'https'}:
        original = Path(report['source']).resolve(strict=True)
        if original.is_relative_to(task):
            raise ValueError('A user-provided original cannot be inside the cleanup directory')
    duration = float(report['duration_seconds'])
    if not math.isfinite(duration) or duration <= 0 or report['material']['completed'] is not True:
        raise ValueError('Primary material is incomplete')
    if report['material']['kind'] not in {'subtitles', 'asr', 'burned-subtitles', 'visual'}:
        raise ValueError('Unknown primary material kind')
    if report['material']['kind'] == 'asr':
        transcript = json.loads((task / 'transcript.json').read_text(encoding='utf-8'))
        if (transcript['completed'] is not True or transcript['mode'] != 'complete'
                or abs(transcript['duration_seconds'] - duration) > 2
                or abs(transcript['processed_seconds'] - transcript['duration_seconds']) > 0.01):
            raise ValueError('ASR pilot/partial/mismatched transcript cannot pass')
    if report['review']['passed'] is not True or report['review']['unresolved_gaps']:
        raise ValueError('Content review has unresolved gaps')
    previous_end = 0.0
    for chapter in report['chapters']:
        start, end = float(chapter['start']), float(chapter['end'])
        if (not math.isfinite(start) or not math.isfinite(end)
                or abs(start - previous_end) > 2 or end <= start or end > duration + 2
                or chapter['reviewed'] is not True or not chapter['evidence']):
            raise ValueError('Chapter coverage or evidence is incomplete')
        previous_end = end
    if not report['chapters'] or abs(previous_end - duration) > 2:
        raise ValueError('Chapters do not cover the selected material')
    for detail in report['key_details']:
        if detail['verified'] is not True or not detail['evidence']:
            raise ValueError('A key detail is not verified')
    assets = []
    for match in re.finditer(r'!\[[^\]]*\]\(([^\n)]+)\)', text):
        target = match.group(1).strip().strip('<>')
        if urlsplit(target).scheme in {'http', 'https', 'data'}:
            continue
        asset = (note.parent / unquote(target)).resolve(strict=True)
        if asset.is_relative_to(task) or not asset.is_file() or asset.stat().st_size == 0:
            raise ValueError('Image is missing, empty, or still temporary')
        assets.append(asset)
    for target in set(report.get('attachments', [])) | set(evidence_images(report)):
        asset = (evidence.parent / target).resolve(strict=True)
        if asset.is_relative_to(task) or not asset.is_file() or asset.stat().st_size == 0:
            raise ValueError('Evidence attachment is not durable')
    return task, len(assets)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['workspace', 'task-dir', 'note', 'evidence']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--clean', action='store_true', help='Delete only after every check passes')
    args = parser.parse_args()
    try:
        task, assets = validate(args.workspace, args.task_dir, args.note, args.evidence)
        print(f'Artifacts verified; {assets} local note images. Semantic review is the agent\'s responsibility.')
        if args.clean:
            shutil.rmtree(task)
            if task.exists():
                raise RuntimeError('Task still exists after cleanup')
            print(f'Cleaned: {task}')
    except Exception as error:
        print(f'{type(error).__name__}: {error}; no successful cleanup reported', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
