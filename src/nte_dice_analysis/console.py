import sys


def configure_stdout() -> None:
    reconfigure = getattr(sys.stdout, 'reconfigure', None)
    if reconfigure is None:
        return

    try:
        reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError, ValueError):
        return
