"""Exercise real speech recognition and save timings without transcript payloads."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from solscribe.diagnostics import speech_smoke

if __name__ == '__main__':
    print(json.dumps(speech_smoke(sys.argv[1], 'speech-source-metrics.json', '.smoke-models'), indent=2))
