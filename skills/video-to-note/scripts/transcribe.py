"""Local transcription with FFmpeg normalization and one-minute checkpoints."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import wave

import numpy as np


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def run(source, task, model_name, language=None, pilot=False, download=False):
    source = Path(source).resolve(strict=True)
    task = Path(task).resolve()
    task.mkdir(parents=True, exist_ok=True)
    checkpoint = task / 'transcript.json'
    normalized = task / 'normalized.wav'
    if source == normalized:
        raise ValueError('Input must not be the generated normalized.wav')
    digest = hashlib.sha256()
    with source.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    config = {'source_sha256': digest.hexdigest(), 'model': model_name, 'language': language}
    previous = json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else None
    if not previous and normalized.exists():
        raise ValueError('Untracked normalized.wav exists; use a new task directory')
    if previous and previous['config'] != config:
        raise ValueError('Source/model/language changed; use a new task directory')
    ffmpeg = shutil.which('ffmpeg')
    ffprobe = shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise RuntimeError('FFmpeg and FFprobe must be available on PATH')
    probe = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'json', str(source)], check=True, capture_output=True, text=True)
    source_duration = float(json.loads(probe.stdout)['format']['duration'])
    if not previous or not normalized.exists():
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
                        '-map', '0:a:0', '-vn', '-ar', '16000', '-ac', '1',
                        '-c:a', 'pcm_s16le', str(normalized)], check=True)
    with wave.open(str(normalized), 'rb') as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
            raise ValueError('Normalized audio is not 16 kHz mono PCM16')
        duration = audio.getnframes() / 16000
        if duration <= 0 or abs(duration - source_duration) > 2:
            raise ValueError('Audio duration does not match input; inspect the streams')
        chunks = math.ceil(duration / 60)
        state = previous or {'config': config, 'source': str(source), 'duration_seconds': duration,
                             'source_duration_seconds': source_duration, 'processed_seconds': 0,
                             'completed_chunks': 0, 'completed': False, 'mode': 'prepared',
                             'segments': [], 'empty_chunks': []}
        if abs(state['duration_seconds'] - duration) > 0.01:
            raise ValueError('Checkpoint audio duration changed')
        done = state['completed_chunks']
        if not isinstance(done, int) or not 0 <= done <= chunks:
            raise ValueError('Invalid checkpoint position')
        if abs(state['processed_seconds'] - min(done * 60, duration)) > 0.01:
            raise ValueError('Checkpoint progress is inconsistent')
        if state['completed']:
            print(f'Already complete: {checkpoint}', flush=True)
            return state
        save(checkpoint, state)
        limit = min(chunks, 1) if pilot else chunks
        if done < limit:
            from faster_whisper import WhisperModel
            print(f'Loading {model_name}; downloads allowed: {download}', flush=True)
            model = WhisperModel(model_name, device='cpu', compute_type='int8',
                                 local_files_only=not download)
            for index in range(done, limit):
                # shortcut: minute boundaries can split sentences; recheck boundary audio for exact quotations.
                start = index * 60
                audio.setpos(start * 16000)
                samples = np.frombuffer(audio.readframes(60 * 16000), dtype=np.int16)
                samples = samples.astype(np.float32) / 32768.0
                # Arrays bypass PyAV's incompatible av.open(metadata_errors=...) interface.
                segments, info = model.transcribe(samples, language=language, beam_size=1, vad_filter=True)
                parts = []
                for segment in segments:
                    text = segment.text.strip()
                    if not text:
                        continue
                    low_confidence = segment.avg_logprob < -1 or segment.no_speech_prob > 0.6
                    parts.append({'start': round(start + segment.start, 2),
                                  'end': round(start + segment.end, 2), 'text': text,
                                  'avg_logprob': segment.avg_logprob,
                                  'no_speech_prob': segment.no_speech_prob,
                                  'needs_review': low_confidence})
                if not parts:
                    state['empty_chunks'].append(index)
                state['segments'].extend(parts)
                state['detected_language'] = info.language
                state['completed_chunks'] = index + 1
                state['processed_seconds'] = min((index + 1) * 60, duration)
                state['mode'] = 'pilot' if pilot else 'partial'
                save(checkpoint, state)
                print(f'{state["processed_seconds"]:.1f}/{duration:.1f}s; checkpoint saved', flush=True)
        if not pilot and state['completed_chunks'] == chunks:
            if not state['segments']:
                raise RuntimeError('No speech recognized; inspect audio before choosing another route')
            state['completed'] = True
            state['mode'] = 'complete'
        elif pilot:
            state['mode'] = 'pilot'
        save(checkpoint, state)
        print(f'{state["mode"]}: {checkpoint}', flush=True)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='Local audio or video; original is never modified')
    parser.add_argument('--task-dir', required=True)
    parser.add_argument('--model', required=True, help='Prefer a cached model or local model directory')
    parser.add_argument('--language', help='Omit for automatic language detection')
    parser.add_argument('--pilot', action='store_true', help='Process first minute; never marks complete')
    parser.add_argument('--download-model', action='store_true', help='Allow an uncached model download')
    args = parser.parse_args()
    try:
        run(args.source, args.task_dir, args.model, args.language, args.pilot, args.download_model)
    except KeyboardInterrupt:
        print('Interrupted; completed minutes remain in transcript.json', file=sys.stderr)
        return 130
    except Exception as error:
        print(f'{type(error).__name__}: {error}; retain task directory', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
