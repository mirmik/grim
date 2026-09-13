"""Reuse the tested whole-scene VoxCPM2 pipeline and the same cloned voice."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('beam_voxcpm', ROOT.parent / 'beam-bending/synthesize_voxcpm.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ROOT = ROOT
if '--chunking' not in sys.argv:
    sys.argv.extend(['--chunking', 'scene'])
if __name__ == '__main__':
    module.main()
