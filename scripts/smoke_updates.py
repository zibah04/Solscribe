"""Verify a real public update through the same HTTPS client as the desktop."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from solscribe.update_diagnostics import update_smoke

if __name__ == '__main__':
    print(json.dumps(update_smoke('update-source-metrics.json'), indent=2))
