from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from ..sleep import SleepTimer


def populate_sleep_menu(menu: QMenu, sleep: SleepTimer):
    menu.clear()
    for m in (15, 30, 45, 60, 90):
        a = QAction("%d minutes" % m, menu)
        a.triggered.connect(lambda _=False, m=m: sleep.start(m))
        menu.addAction(a)
    menu.addAction("End of this track", sleep.start_end_of_track)
    if sleep.active:
        menu.addSeparator()
        menu.addAction("Cancel timer (%s)" % sleep.describe(), sleep.cancel)


def make_sleep_menu(parent, sleep: SleepTimer, title="Sleep timer") -> QMenu:
    m = QMenu(title, parent)
    m.aboutToShow.connect(lambda: populate_sleep_menu(m, sleep))
    populate_sleep_menu(m, sleep)
    return m
