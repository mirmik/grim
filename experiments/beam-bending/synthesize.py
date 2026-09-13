"""Local XTTS narration, one cached audio file per sentence for precise cue timing."""
import hashlib
import json
import os
import re
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
os.environ.setdefault("NUMBA_CACHE_DIR", str(OUT/"numba-cache"))

def main():
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio
    original_load = torch.load
    torch.load = lambda *a, **kw: original_load(*a, **{**kw,"weights_only":False})
    def load_audio(path, **kw):
        data,sr=sf.read(path,dtype="float32",always_2d=True)
        return torch.from_numpy(data.T),sr
    torchaudio.load=load_audio
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    model_dir=Path.home()/".local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2"
    reference=Path.home()/"project/for-tts-xtts/reference.wav"
    OUT.mkdir(exist_ok=True)
    config=XttsConfig()
    config.load_json(str(model_dir/"config.json"))
    model=Xtts.init_from_config(config)
    model.load_checkpoint(config,checkpoint_dir=str(model_dir),use_deepspeed=False)
    model.to("cuda" if torch.cuda.is_available() else "cpu")
    print("Device:",next(model.parameters()).device,flush=True)
    cond,speaker=model.get_conditioning_latents(audio_path=[str(reference)])
    voice_hash=hashlib.sha256(reference.read_bytes()).hexdigest()
    script=json.loads((ROOT/"script.json").read_text())
    rate=24000
    clips,timeline=[],[]
    samples=0
    def silence(seconds):
        nonlocal samples
        data=np.zeros(round(seconds*rate),dtype=np.float32)
        clips.append(data)
        samples+=len(data)
    for i,scene in enumerate(script):
        entry={**scene,"start":samples/rate,"cues":[]}
        silence(.35)
        utterances=[sentence for paragraph in scene['speech'] for sentence in re.split(r'(?<=[.!?])\s+',paragraph)]
        for j,text in enumerate(utterances):
            seed=180+i*10+j
            spec={"text":text,"reference":voice_hash,"model_dir":str(model_dir),"seed":seed,"temperature":.60,"speed":1.0}
            path=OUT/f"{i:02d}-{scene['id']}-{j}.wav"
            meta=path.with_suffix(".json")
            started=time.monotonic()
            if path.exists() and meta.exists() and json.loads(meta.read_text()) == spec:
                audio,sr=sf.read(path,dtype="float32")
                assert sr==rate
            else:
                torch.manual_seed(seed)
                with torch.inference_mode():
                    result=model.inference(text=text,language="ru",gpt_cond_latent=cond,speaker_embedding=speaker,temperature=.60,speed=1.0,enable_text_splitting=True)
                audio=np.asarray(result["wav"],dtype=np.float32).squeeze()
                assert audio.ndim==1 and len(audio)>rate and np.isfinite(audio).all()
                indices=np.flatnonzero(abs(audio)>.006)
                if len(indices): audio=audio[max(0,indices[0]-1800):min(len(audio),indices[-1]+2400)]
                audio[:240]*=np.linspace(0,1,240)
                audio[-240:]*=np.linspace(1,0,240)
                sf.write(path,audio,rate,subtype="PCM_16")
                meta.write_text(json.dumps(spec,ensure_ascii=False,indent=2))
                print(f"{path.name}: {len(audio)/rate:.1f}s speech in {time.monotonic()-started:.1f}s",flush=True)
            start=samples/rate
            clips.append(audio)
            samples+=len(audio)
            entry["cues"].append({"start":start,"end":samples/rate,"text":text,"file":path.name})
            silence(.20 if j<len(utterances)-1 else .8)
        entry["end"]=samples/rate
        timeline.append(entry)
    silence(1)
    timeline[-1]["end"]=samples/rate
    sf.write(OUT/"narration.wav",np.concatenate(clips),rate,subtype="PCM_16")
    (OUT/"timeline.json").write_text(json.dumps(timeline,ensure_ascii=False,indent=2))
    print(f"Total: {samples/rate:.2f}s",flush=True)

if __name__ == "__main__": main()
