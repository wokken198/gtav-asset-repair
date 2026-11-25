"""Process-wide switches that every writer checks.

The GUI owns the persistence (``load_config`` / ``save_config`` in :mod:`gui`), so this
module only holds the live values.  Keeping them here lets ``lite`` / ``ped`` / ``rpf``
consult the switch without importing the GUI, and lets the CLI expose the same flags.
"""

KEEP_BAK = True


def keep_bak() -> bool:
    """True when writers should keep ``<name>.bak`` before overwriting."""
    return KEEP_BAK


def set_keep_bak(on: bool) -> None:
    global KEEP_BAK
    KEEP_BAK = bool(on)
