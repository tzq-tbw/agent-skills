import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import workflow as w


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd() / 'work' / 'unit-tests'
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.txt'
        self.source.write_text('source', encoding='utf-8')
        self.lib = self.root / '正式库'
        self.stage = self.root / 'stage'
        self.batch = dict(subject='高等数学', chapter='二重积分', section='计算二重积分', summary='总结',
                          questions=[dict(statement='计算 $I=1$。', knowledge='知识', approach='思路', solution='解答',
                                          errors='实际错因待确认', method='方法', sources=[dict(path=str(self.source))])])
        self.batch_path = self.root / 'batch.json'

    def prepare(self):
        w.write_json(self.batch_path, self.batch)
        return w.prepare(self.batch_path, self.lib, self.stage)

    def fake_compile(self, path, compiler):
        pdf = path.with_suffix('.pdf')
        pdf.write_bytes(b'%PDF-test')
        return pdf

    def commit(self):
        with patch.object(w, 'compile_pdf', self.fake_compile):
            return w.archive(self.stage, confirmed=True)

    def test_preview_and_confirmation(self):
        self.prepare()
        self.assertFalse(self.lib.exists())
        with self.assertRaises(PermissionError): w.archive(self.stage)
        self.assertFalse(self.lib.exists())

    def test_incremental_preserves_history_and_old_text(self):
        r = self.prepare(); self.commit(); target = Path(r['target'])
        state = w.read_json(target / '复习记录.json'); qid = state['questions'][0]['id']
        w.review(target, qid, '2026-10-15', 'L2', '问题', '回答', 1, '完成关键步骤', 'e1')
        previous = w.read_json(target / '复习记录.json')['questions'][0]
        old_block = (target / '错题分析.md').read_text(encoding='utf-8').split('\n## 本小节知识总结\n')[0]
        self.batch['questions'][0]['statement'] = '第二道新题'
        self.prepare(); self.commit()
        after = w.read_json(target / '复习记录.json')['questions']
        self.assertEqual(after[0], previous)
        self.assertNotEqual(after[1]['id'], qid)
        self.assertTrue((target / '错题分析.md').read_text(encoding='utf-8').startswith(old_block))
        self.assertEqual(after[1]['mastery'], 'unreviewed')

    def test_compile_failure_keeps_library(self):
        r = self.prepare(); self.commit(); target = Path(r['target']); before = w.hashes(target)
        self.batch['questions'][0]['statement'] = '新增题'
        self.prepare()
        with patch.object(w, 'compile_pdf', side_effect=RuntimeError('compiler failed')):
            with self.assertRaises(RuntimeError): w.archive(self.stage, True)
        self.assertEqual(w.hashes(target), before)

    def test_write_failure_rolls_back(self):
        r = self.prepare(); self.commit(); target = Path(r['target']); before = w.hashes(target)
        self.batch['questions'][0]['statement'] = '新增题'; self.prepare()
        original_replace = w.os.replace
        def failing_replace(src, dst):
            if str(dst).endswith('错题分析.pdf'): raise OSError('simulated disk error')
            return original_replace(src, dst)
        with patch.object(w, 'compile_pdf', self.fake_compile), patch.object(w.os, 'replace', failing_replace):
            with self.assertRaises(OSError): w.archive(self.stage, True)
        self.assertEqual(w.hashes(target), before)

    def test_stale_preview_refuses_overwrite(self):
        r = self.prepare(); self.commit(); target = Path(r['target'])
        self.batch['questions'][0]['statement'] = '新增题'; self.prepare()
        qid = w.read_json(target / '复习记录.json')['questions'][0]['id']
        w.review(target, qid, '2026-10-15', 'L2', '问题', '回答', 1, '证据', 'e1')
        with self.assertRaises(RuntimeError): w.archive(self.stage, True)

    def test_duplicates_and_path_escape(self):
        self.prepare(); self.commit()
        with self.assertRaises(ValueError): self.prepare()
        self.batch['chapter'] = '../outside'
        with self.assertRaises(ValueError): self.prepare()

    def test_draft_tampering(self):
        self.prepare()
        (self.stage / '预览.md').write_text('changed', encoding='utf-8')
        with self.assertRaises(RuntimeError): w.archive(self.stage, True)

    def test_review_isolated_and_scheduled(self):
        r = self.prepare(); self.commit(); target = Path(r['target'])
        before = {k: w.digest(target/k) for k in w.FILES[:-1]}
        qid = w.read_json(target / '复习记录.json')['questions'][0]['id']
        with self.assertRaises(ValueError): w.review(target, qid, '2026-10-15', 'L4', '问题', '回答', 0, '证据', 'e0')
        result = w.review(target, qid, '2026-10-15', 'L3', '问题', '回答', 0, '独立完成', 'e1')
        self.assertEqual(result['next_review'], '2026-10-29')
        with self.assertRaises(ValueError): w.review(target, qid, '2026-10-15', 'L3', '问题', '回答', 0, '证据', 'e1')
        self.assertFalse(w.due(self.lib, '2026-10-28'))
        self.assertEqual(len(w.due(self.lib, '2026-10-29')), 1)
        self.assertEqual(before, {k: w.digest(target/k) for k in w.FILES[:-1]})

    def test_markdown_math_to_latex(self):
        self.prepare(); md = (self.stage / '预览.md').read_text(encoding='utf-8')
        tex = w.to_tex(md)
        self.assertIn('$I=1$', tex)
        self.assertIn('题目区', tex); self.assertIn('解析区', tex)
        with self.assertRaises(ValueError): w.latex_text(r'$\input{file}$')

    def test_simulation_never_in_regular_library(self):
        w.write_json(self.batch_path, self.batch)
        with self.assertRaises(ValueError): w.prepare(self.batch_path, self.lib, self.stage, True)

    def attach_diagram(self):
        image = self.root / 'figure.png'
        image.write_bytes(b'fake PNG for file-transaction tests')
        image.with_suffix('.pdf').write_bytes(b'fake vector PDF for file-transaction tests')
        self.batch['questions'][0]['diagram'] = dict(path=str(image), caption='区域示意图')

    def test_figure_archive_and_incremental_preservation(self):
        self.attach_diagram(); r = self.prepare(); self.commit(); target = Path(r['target'])
        original = {str(p.relative_to(target)): w.digest(p) for p in (target/'assets').iterdir()}
        self.assertEqual(len(original), 2)
        md = (target/'错题分析.md').read_text(encoding='utf-8')
        self.assertIn('includegraphics', w.to_tex(md))
        self.assertIn('IfFileExists', w.to_tex(md))
        self.batch['questions'][0].pop('diagram')
        self.batch['questions'][0]['statement'] = '新增无图题'
        self.prepare(); self.commit()
        self.assertEqual(original, {str(p.relative_to(target)): w.digest(p) for p in (target/'assets').iterdir()})

    def test_figure_tampering_rejected(self):
        self.attach_diagram(); self.prepare()
        image = next((self.stage/'assets').glob('*.png')); image.write_bytes(b'changed')
        with self.assertRaises(RuntimeError): self.commit()
        self.assertFalse(self.lib.exists())

    def test_removed_vector_does_not_leave_stale_stage_asset(self):
        self.attach_diagram(); self.prepare()
        (self.root/'figure.pdf').unlink()
        self.prepare()
        self.assertFalse(list((self.stage/'assets').glob('*.pdf')))
        self.assertTrue(list((self.stage/'assets').glob('*.png')))

    def test_figure_write_failure_rolls_back(self):
        r = self.prepare(); self.commit(); target = Path(r['target']); before = w.hashes(target)
        self.batch['questions'][0]['statement'] = '新增有图题'
        self.attach_diagram(); self.prepare()
        original_replace = w.os.replace
        def failing_replace(src, dst):
            if str(dst).endswith('-figure.pdf'): raise OSError('simulated attachment write failure')
            return original_replace(src, dst)
        with patch.object(w, 'compile_pdf', self.fake_compile), patch.object(w.os, 'replace', failing_replace):
            with self.assertRaises(OSError): w.archive(self.stage, True)
        self.assertEqual(w.hashes(target), before)
        self.assertEqual(list((target/'assets').iterdir()), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
