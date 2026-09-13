"""Validate the actual encoded artifact, timing, and analytical geometry."""
import json
import argparse
from pathlib import Path
import subprocess
import soundfile as sf
from geometry import validate

OUT=Path(__file__).resolve().parent/'output-voxcpm-scenes'
parser=argparse.ArgumentParser()
parser.add_argument('--output-dir',type=Path,default=OUT)
OUT=parser.parse_args().output_dir.resolve()
video=OUT/'spherical-geometry-ru.mp4'
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,width,height,r_frame_rate,sample_rate,channels,duration','-of','json',str(video)]))
v=next(s for s in probe['streams'] if s['codec_name']=='h264')
a=next(s for s in probe['streams'] if s['codec_name']=='aac')
assert (v['width'],v['height'],v['r_frame_rate'])==(1920,1080,'30/1')
assert a['sample_rate']=='48000'
assert abs(float(v['duration'])-float(a['duration']))<=1/30
timeline=json.loads((OUT/'timeline.json').read_text())
scene_audio=any('audio_start' in s for s in timeline)
narration,narration_rate=sf.read(OUT/'narration.wav',dtype='float32')
for i,s in enumerate(timeline):
    if i:assert abs(timeline[i-1]['end']-s['start'])<1e-8
    if 'audio_start' in s:
        original,original_rate=sf.read(OUT/s['cues'][0]['file'],dtype='float32')
        assert original_rate==narration_rate
        offset=round(s['audio_start']*narration_rate)
        assert (narration[offset:offset+len(original)]==original).all()
        assert abs(s['cues'][0]['audio_start'])<1e-8
        for prev,cur in zip(s['cues'],s['cues'][1:]):
            assert prev['file']==cur['file']
            assert abs(prev['audio_end']-cur['audio_start'])<1e-8
            assert abs(prev['end']-cur['start'])<1e-8
        last=s['cues'][-1]
        assert abs(last['audio_end']-sf.info(OUT/last['file']).duration)<1/24000
    for c in s['cues']:
        assert s['start']<=c['start']<c['end']<=s['end']
        audio=sf.info(OUT/c['file'])
        audio_start=c.get('audio_start',0)
        audio_end=c.get('audio_end',audio.duration)
        assert 0<=audio_start<audio_end<=audio.duration+1/audio.samplerate
        assert abs((audio_end-audio_start)-(c['end']-c['start']))<1/audio.samplerate
        source,source_rate=sf.read(OUT/c['file'],dtype='float32')
        assert source_rate==narration_rate
        left,right=round(audio_start*source_rate),round(audio_end*source_rate)
        offset=round(c['start']*source_rate)
        assert (narration[offset:offset+right-left]==source[left:right]).all()
        if 'audio_start' in c:
            assert abs(c['start']-(s['audio_start']+audio_start))<1/audio.samplerate
assert abs(sf.info(OUT/'narration.wav').duration-timeline[-1]['end'])<1/24000
subprocess.run(['ffmpeg','-v','error','-xerror','-err_detect','explode','-i',str(video),'-f','null','-'],check=True)
result={'media':probe,'geometry':validate(),'full_decode':'passed','cue_audio_durations':'passed','speech_assessment':'Local ASR in speech-check.json; word stress and prosody are not verified by ASR.'}
result['source_audio_assembly']='Every cue matches its source WAV sample-for-sample before final MP4 loudness normalization'
if scene_audio:result['continuous_scene_audio']='Sample-for-sample match with each whole source scene WAV'
(OUT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
