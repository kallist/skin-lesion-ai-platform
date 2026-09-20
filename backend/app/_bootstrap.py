"""Import-path bootstrap.

The backend imports the ``ml`` package (preprocessing contract, predictor) which
lives at the project root, one level above ``backend/``.  Rather than requiring
callers to set ``PYTHONPATH``, this module makes the project root importable as
soon as the application package is imported, so the documented command

    cd backend && python -m uvicorn app.main:app

works from a clean checkout.
"""

from __future__ import annotations

import sys
from pathlib import Path

# backend/app/_bootstrap.py -> backend/app -> backend -> project root
BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


def ensure_project_root_on_path() -> Path:
    """Prepend the project root to ``sys.path`` if it is not importable yet."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return PROJECT_ROOT


ensure_project_root_on_path()
