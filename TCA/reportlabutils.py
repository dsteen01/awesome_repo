"""
reportlabutils.py — Backward-compatibility shim.

All classes and functions have moved to the ``report/`` subpackage.
This file re-exports them from their canonical locations so that any
code that still does ``from reportlabutils import ...`` continues to
work during the transition.

New code should import directly from the subpackages::

    from report.templates  import MyDocTemplate, PageNumCanvas
    from report.components import df2table, fig2image
    from report.builder    import createMultiPage
"""

# Re-export everything the old module exposed at its top level.
from report.templates  import MyDocTemplate, PageNumCanvas   # noqa: F401
from report.components import df2table, fig2image            # noqa: F401
from report.builder    import createMultiPage                # noqa: F401

# Also expose the third-party names that old wildcard importers relied on.
from reportlab.lib import colors                             # noqa: F401
