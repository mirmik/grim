"""Copy the opening through the excess explanation for a quick editorial review."""
import json
from pathlib import Path
import subprocess

out=Path(__file__).resolve().parent/'output-voxcpm-scenes'
timeline=json.loads((out/'timeline.json').read_text())
end=next(s['start'] for s in timeline if s['id']=='area')
video=out/'opening-review.mp4'
subprocess.run(['ffmpeg','-v','error','-y','-i',str(out/'spherical-geometry-ru.mp4'),
                '-t',str(end),'-c','copy','-movflags','+faststart',str(video)],check=True)
subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True)
print(video)
