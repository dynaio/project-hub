"""Fade-in, toast, and theme-crossfade helpers."""
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QTimer, QPoint,
)
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect, QLabel, QWidget,
)


def fade_in(widget: QWidget, duration: int = 220, delay: int = 0):
    """Fade a widget from 0 to 1 opacity, then remove the effect."""
    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _done():
        try:
            widget.setGraphicsEffect(None)
        except RuntimeError:
            pass
    anim.finished.connect(_done)
    widget._fade_anim = anim
    if delay > 0:
        QTimer.singleShot(delay, anim.start)
    else:
        anim.start()
    return anim


def fade_out(widget: QWidget, duration: int = 180, on_done=None):
    eff = widget.graphicsEffect()
    if eff is None:
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InCubic)
    if on_done:
        anim.finished.connect(on_done)
    widget._fade_out_anim = anim
    anim.start()
    return anim


# ------------------------------------------------------------- toast
_TOAST = {"widget": None}


def show_toast(parent: QWidget, text: str, error: bool = False, duration: int = 2800):
    """Show a single ephemeral toast at the bottom-center of `parent`."""
    old = _TOAST.get("widget")
    if old is not None:
        try:
            old.deleteLater()
        except RuntimeError:
            pass

    toast = QLabel(text, parent)
    toast.setObjectName("ToastError" if error else "Toast")
    toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
    toast.setFixedHeight(42)
    toast.setMinimumWidth(260)
    toast.adjustSize()

    w = max(260, toast.width() + 48)
    toast.setFixedWidth(w)
    x = max(16, (parent.width() - w) // 2)
    y_target = parent.height() - 90
    toast.move(x, y_target + 18)
    toast.show()
    toast.raise_()

    eff = QGraphicsOpacityEffect(toast)
    toast.setGraphicsEffect(eff)

    a1 = QPropertyAnimation(eff, b"opacity", toast)
    a1.setDuration(200)
    a1.setStartValue(0.0)
    a1.setEndValue(1.0)
    a1.setEasingCurve(QEasingCurve.Type.OutCubic)

    a2 = QPropertyAnimation(toast, b"pos", toast)
    a2.setDuration(220)
    a2.setStartValue(QPoint(x, y_target + 18))
    a2.setEndValue(QPoint(x, y_target))
    a2.setEasingCurve(QEasingCurve.Type.OutCubic)

    toast._a1, toast._a2 = a1, a2
    a1.start()
    a2.start()

    def _dismiss():
        eff2 = toast.graphicsEffect()
        if eff2 is None:
            toast.deleteLater()
            return
        a3 = QPropertyAnimation(eff2, b"opacity", toast)
        a3.setDuration(220)
        a3.setStartValue(1.0)
        a3.setEndValue(0.0)
        a3.setEasingCurve(QEasingCurve.Type.InCubic)
        a3.finished.connect(toast.deleteLater)
        toast._a3 = a3
        a3.start()

    QTimer.singleShot(duration, _dismiss)
    _TOAST["widget"] = toast
    return toast


# ------------------------------------------------------------- theme fade
def crossfade_theme(window: QWidget, apply_fn):
    """Snapshot the window, apply the new theme, fade the snapshot out."""
    try:
        pix = window.grab()
    except RuntimeError:
        apply_fn()
        return

    overlay = QLabel(window)
    overlay.setPixmap(pix)
    overlay.setGeometry(0, 0, window.width(), window.height())
    overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    overlay.show()
    overlay.raise_()

    apply_fn()

    eff = QGraphicsOpacityEffect(overlay)
    overlay.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", overlay)
    anim.setDuration(240)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(overlay.deleteLater)
    window._theme_anim = anim
    anim.start()
    return anim
