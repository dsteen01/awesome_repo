"""
delivery - report output and distribution.

Public API::

    from delivery import send_report, EmailConfig
"""


def __getattr__(name):
    """Lazy-import so that ``python -m delivery.email`` does not trigger a
    circular-import RuntimeWarning from the package __init__ pre-loading
    the submodule before Python sets it up as __main__."""
    if name in ('EmailConfig', 'send_report'):
        from . import email as _email
        return getattr(_email, name)
    raise AttributeError(f"module 'delivery' has no attribute {name!r}")


__all__ = ['EmailConfig', 'send_report']
