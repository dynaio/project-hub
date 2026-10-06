#!/usr/bin/env python3
"""aek — personal project hub. Entry point."""
import sys

from PyQt6.QtWidgets import QApplication

from aek.mainwindow import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("aek")
    app.setApplicationDisplayName("aek")
    app.setOrganizationName("aek")

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
