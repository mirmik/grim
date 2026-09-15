"""Run E2E against a disposable book, never modify the user's demo."""
from pathlib import Path
import shutil
import sys
import tempfile
import uvicorn
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.app import BASE, create_app
from fake_agent_model import completion
with tempfile.TemporaryDirectory(prefix='grim-e2e-') as directory:
    root = Path(directory) / 'book'
    shutil.copytree(BASE / 'demo', root)
    uvicorn.run(create_app(root, Path(directory) / 'library', agent_completion=completion), host='127.0.0.1', port=8001, timeout_graceful_shutdown=1)
