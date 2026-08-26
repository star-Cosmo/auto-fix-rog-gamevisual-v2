"""Double-click entry point.

The sys.path insert keeps imports working under embeddable Python whose
``python312._pth`` enables isolated mode (script dir not auto-added).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gamevisual_fixer.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
