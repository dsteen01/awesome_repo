"""
analysis/ — Statistical summaries and sensitivity analysis.

The local TableOne copy lives at <project_root>/tableone/.  We add it to
sys.path here once so that every submodule can simply ``from tableone import
TableOne`` without repeating the path manipulation.

Public surface
--------------
    from analysis.summary import CreateCoverPageTable
    from analysis.cutby   import CreateCutBy
"""

from __future__ import annotations

import sys
from pathlib import Path

_TABLEONE_PATH = str(Path(__file__).resolve().parent.parent / 'tableone')
# Always insert at position 0: TCA/tableone/ must come before TCA/ in sys.path
# so that "import tableone" resolves to TCA/tableone/tableone/ (the actual package)
# rather than TCA/tableone/__init__.py (the repo wrapper).
if sys.path[0] != _TABLEONE_PATH:
    sys.path.insert(0, _TABLEONE_PATH)
