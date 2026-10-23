import json
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import wave

scripts = Path(__file__).parent.resolve()
sys.path.insert(0, str(scripts))
root = Path.cwd().resolve() / 'work' / 'video_tmp'
root.mkdir(parents=True, exist_ok=True)
import transcribe
import finalize


class ScriptChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=root)
        self.workspace = Path(self.folder.name).resolve()
        assert self.workspace.parent == root
        self.task = self.workspace / 'work' / 'video_tmp' / 'test-task'
        self.task.mkdir(parents=True)
        self.source = self.workspace / 'original.wav'
        with wave.open(str(self.source), 'wb') as f:
            f.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            f.writeframes(b'\x01\x00' * 65 * 16000)

    def tearDown(self):
        assert self.workspace.parent == root
        self.folder.cleanup()

    def fake(self):
        class Model:
            def __init__(self, *args, **kwargs):
                assert kwargs['local_files_only'] is True
            def transcribe(self, audio, **kwargs):
                assert audio.dtype.name == 'float32' and audio.ndim == 1
                part = SimpleNamespace(start=0.1, end=min(len(audio)/16000, 3),
                                       text='测试内容', avg_logprob=-0.2, no_speech_prob=0.01)
                return iter([part]), SimpleNamespace(language='zh')
        return Model

    def report(self):
        self.note = self.workspace / 'note.md'
        self.evidence = self.workspace / 'note.evidence.json'
        self.note.write_text('测试笔记 https://example.com/video', encoding='utf-8')
        report = {'source': 'https://example.com/video', 'duration_seconds': 65,
                  'material': {'kind': 'asr', 'completed': True},
                  'chapters': [{'start': 0, 'end': 65, 'reviewed': True,
                                'evidence': [{'time': 1, 'excerpt': '测试内容'}]}],
                  'key_details': [], 'review': {'passed': True, 'unresolved_gaps': []}}
        self.evidence.write_text(json.dumps(report), encoding='utf-8')
        return report

    def complete(self):
        with patch('faster_whisper.WhisperModel', self.fake()):
            return transcribe.run(self.source, self.task, 'medium')

    def test_pilot_resumes_without_repeating_first_minute(self):
        original = self.source.read_bytes()
        with patch('faster_whisper.WhisperModel', self.fake()):
            pilot = transcribe.run(self.source, self.task, 'medium', pilot=True)
            self.assertFalse(pilot['completed'])
            self.assertEqual(pilot['processed_seconds'], 60)
            done = transcribe.run(self.source, self.task, 'medium')
        self.assertTrue(done['completed'])
        self.assertEqual(len(done['segments']), 2)
        self.assertGreaterEqual(done['segments'][1]['start'], 60)
        self.assertEqual(self.source.read_bytes(), original)
        with patch('faster_whisper.WhisperModel', side_effect=AssertionError('should not load')):
            transcribe.run(self.source, self.task, 'medium')

    def test_model_change_rejected(self):
        self.complete()
        with self.assertRaises(ValueError):
            transcribe.run(self.source, self.task, 'small')

    def test_failed_chunk_keeps_previous_checkpoint(self):
        with patch('faster_whisper.WhisperModel', self.fake()):
            transcribe.run(self.source, self.task, 'medium', pilot=True)
        class Failed(self.fake()):
            def transcribe(self, *args, **kwargs):
                raise RuntimeError('interrupted chunk')
        with patch('faster_whisper.WhisperModel', Failed), self.assertRaises(RuntimeError):
            transcribe.run(self.source, self.task, 'medium')
        state = json.loads((self.task / 'transcript.json').read_text(encoding='utf-8'))
        self.assertEqual(state['completed_chunks'], 1)
        self.assertFalse(state['completed'])

    def test_partial_transcript_and_unresolved_gaps_block_cleanup(self):
        with patch('faster_whisper.WhisperModel', self.fake()):
            transcribe.run(self.source, self.task, 'medium', pilot=True)
        report = self.report()
        with self.assertRaises(ValueError):
            finalize.validate(self.workspace, self.task, self.note, self.evidence)
        self.complete()
        report['review']['unresolved_gaps'] = ['a formula was not read']
        self.evidence.write_text(json.dumps(report), encoding='utf-8')
        with self.assertRaises(ValueError):
            finalize.validate(self.workspace, self.task, self.note, self.evidence)
        self.assertTrue(self.task.exists())

    def test_missing_and_temporary_attachments_rejected(self):
        self.complete()
        self.report()
        self.note.write_text('https://example.com/video\n![x](missing.png)', encoding='utf-8')
        with self.assertRaises(FileNotFoundError):
            finalize.validate(self.workspace, self.task, self.note, self.evidence)
        image = self.task / 'temporary.png'
        image.write_bytes(b'png')
        self.note.write_text('https://example.com/video\n![x](' + str(image) + ')', encoding='utf-8')
        with self.assertRaises(ValueError):
            finalize.validate(self.workspace, self.task, self.note, self.evidence)

    def test_cleanup_only_deletes_selected_task(self):
        self.complete()
        self.report()
        other = self.task.parent / 'other-task'
        other.mkdir()
        args = ['finalize.py', '--workspace', str(self.workspace), '--task-dir', str(self.task),
                '--note', str(self.note), '--evidence', str(self.evidence), '--clean']
        with patch.object(sys, 'argv', args):
            self.assertEqual(finalize.main(), 0)
        self.assertFalse(self.task.exists())
        self.assertTrue(other.exists() and self.source.exists() and self.note.exists() and self.evidence.exists())

    def test_outside_directory_rejected(self):
        self.complete()
        self.report()
        with self.assertRaises(ValueError):
            finalize.validate(self.workspace, self.workspace, self.note, self.evidence)

    def test_windows_junction_rejected_without_touching_target(self):
        self.complete()
        self.report()
        other = self.workspace / 'keep'
        other.mkdir()
        (other / 'marker.txt').write_text('keep', encoding='utf-8')
        junction = self.task / 'linked'
        command = "New-Item -ItemType Junction -Path '{}' -Target '{}' | Out-Null".format(junction, other)
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True)
        if result.returncode:
            self.skipTest('Junction creation unavailable')
        try:
            with self.assertRaises(ValueError):
                finalize.validate(self.workspace, self.task, self.note, self.evidence)
            self.assertEqual((other / 'marker.txt').read_text(encoding='utf-8'), 'keep')
        finally:
            junction.rmdir()

    def test_evidence_image_must_be_durable_even_without_attachment_list(self):
        self.complete()
        report = self.report()
        temporary = self.task / 'evidence.png'
        temporary.write_bytes(b'png')
        report['key_details'] = [{'verified': True, 'evidence': {'image': str(temporary)}}]
        self.evidence.write_text(json.dumps(report), encoding='utf-8')
        with self.assertRaises(ValueError):
            finalize.validate(self.workspace, self.task, self.note, self.evidence)


unittest.main(verbosity=2)

