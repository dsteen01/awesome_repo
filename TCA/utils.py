"""
utils.py — Backward-compatibility shim.

All functions have moved to the structured subpackages.  This file re-exports
them from their canonical locations so that any code that still does
``from utils import ...`` continues to work during the transition.

New code should import directly from the subpackages::

    from data.filters    import CreateOutlierFrame
    from analysis.summary import CreateCoverPageTable
    from analysis.cutby   import CreateCutBy
    from viz.histograms   import CreateFeatureHistograms
    from viz.timeseries   import CreateFeatureTS
"""

from data.filters    import CreateOutlierFrame          # noqa: F401
from data.transforms import resolve_time_grouping as _resolve_time_grouping  # noqa: F401
from analysis.summary import CreateCoverPageTable       # noqa: F401
from analysis.cutby   import CreateCutBy                # noqa: F401
from viz.histograms   import CreateFeatureHistograms    # noqa: F401
from viz.timeseries   import CreateFeatureTS            # noqa: F401
