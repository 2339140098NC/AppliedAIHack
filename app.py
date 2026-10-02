"""Vercel entrypoint. The package itself lives in caseboard/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "caseboard"))

from caseboard.main import app as app
