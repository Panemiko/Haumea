#!/usr/bin/env python3
import sys

def run_pyside_viewer(image_path: str, title: str):
    """A helper PySide6 image viewer that opens on the second monitor if available and fits aspect ratio."""
    try:
        from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import Qt
    except ImportError:
        sys.exit(1)
        
    app = QApplication([])
    window = QMainWindow()
    window.setWindowTitle(f"Screenshot: {title}")
    
    pixmap = QPixmap(image_path)
    if pixmap.isNull():
        sys.exit(1)
        
    label = QLabel()
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    screens = app.screens()
    if len(screens) > 1:
        second_screen = screens[1]
        screen_geo = second_screen.geometry()
        scaled_pixmap = pixmap.scaled(
            screen_geo.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        label.setPixmap(scaled_pixmap)
        window.setCentralWidget(label)
        window.setGeometry(screen_geo)
        window.showMaximized()
    else:
        first_screen = screens[0]
        screen_geo = first_screen.geometry()
        target_size = screen_geo.size() * 0.9
        scaled_pixmap = pixmap.scaled(
            target_size.toSize(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        label.setPixmap(scaled_pixmap)
        window.setCentralWidget(label)
        window.resize(target_size.toSize())
        qr = window.frameGeometry()
        cp = first_screen.availableGeometry().center()
        qr.moveCenter(cp)
        window.move(qr.topLeft())
        window.show()
        
    sys.exit(app.exec())

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        run_pyside_viewer(sys.argv[1], sys.argv[2])
    else:
        sys.exit(1)
