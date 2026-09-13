"""Map sentence captions onto uninterrupted scene audio using local ASR anchors.

Exact word matches supply timestamps; unmatched words are interpolated. This is
approximate caption alignment, not a phonetic forced aligner. Audio is untouched.
"""
from difflib import SequenceMatcher
import argparse
import json
from pathlib import Path
import re
import numpy as np
import soundfile as sf

OUT = Path(__file__).resolve().parent / 'output-qwen-scenes'


def tokens(text):
    return re.findall(r'[а-яa-z0-9]+', text.lower().replace('ё', 'е'))


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=OUT)
    OUT = parser.parse_args().output_dir.resolve()
    timeline = json.loads((OUT / 'timeline.json').read_text())
    recognized = {r['file']: r for r in json.loads((OUT / 'speech-check.json').read_text())}
    report = []
    for scene in timeline:
        first = scene['cues'][0]
        file = first['file']
        start = scene.get('audio_start', first['start'])
        scene['audio_start'] = start
        duration = sf.info(OUT / file).duration
        sentences = [s for p in scene['speech'] for s in re.split(r'(?<=[.!?])\s+', p)]
        sentence_tokens = [tokens(s) for s in sentences]
        expected = [w for s in sentence_tokens for w in s]
        actual, times = [], []
        for word in recognized[file]['words']:
            for token in tokens(word['word']):
                actual.append(token)
                times.append(word['start'])
        matches = SequenceMatcher(None, expected, actual, autojunk=False).get_matching_blocks()
        anchors = [(m.a + j, times[m.b + j]) for m in matches for j in range(m.size)]
        coverage = len(anchors) / len(expected)
        assert coverage >= .5, (file, coverage, 'Review transcript before alignment')
        xs = [i for i, t in anchors] + [len(expected)]
        ys = [t for i, t in anchors] + [duration]
        indices = np.cumsum([len(s) for s in sentence_tokens])[:-1]
        boundaries = [0.] + [float(np.interp(i, xs, ys)) for i in indices] + [duration]
        assert all(b > a for a, b in zip(boundaries, boundaries[1:])), file
        scene['cues'] = [dict(text=text, file=file, start=start+a, end=start+b,
                              audio_start=a, audio_end=b)
                         for text, a, b in zip(sentences, boundaries, boundaries[1:])]
        report.append(dict(file=file, matched_word_fraction=coverage,
                           sentence_boundaries=boundaries, audio_unchanged=True))
        print(f'{file}: {len(sentences)} captions, {coverage:.0%} word anchors', flush=True)
    (OUT / 'timeline.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=2))
    (OUT / 'alignment-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
