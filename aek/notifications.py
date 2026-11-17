"""Reminder alert engine + in-app notification centre."""
from datetime import datetime, timedelta

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class ReminderEngine(QObject):
    due = pyqtSignal(dict)     # one fired reminder

    def __init__(self, db, settings, parent=None):
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self._timer = QTimer(self)
        self._timer.setInterval(60 * 1000)   # check every minute
        self._timer.timeout.connect(self.tick)
        self._seen = set()

    def start(self):
        self._timer.start()
        QTimer.singleShot(2000, self.tick)   # first check shortly after launch

    def stop(self):
        self._timer.stop()

    def tick(self):
        if not self.settings.get("notifications_enabled", True):
            return
        now = datetime.now().isoformat(timespec="seconds")
        try:
            rows = self.db.reminders_due(now)
        except Exception:
            return
        for r in rows:
            key = (r["id"], r.get("snoozed_until") or "")
            if key in self._seen:
                continue
            self._seen.add(key)
            # mark as notified to avoid re-firing on restart
            try:
                self.db.reminder_update(r["id"], notified=1)
            except Exception:
                pass
            self.due.emit(r)

    def snooze(self, rid, days=1):
        until = (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")
        self.db.reminder_update(rid, snoozed_until=until, notified=0)
        # clear from seen so it can fire again
        self._seen = {k for k in self._seen if k[0] != rid}

    def dismiss(self, rid):
        self.db.reminder_update(rid, completed_at=datetime.now().isoformat(timespec="seconds"))
