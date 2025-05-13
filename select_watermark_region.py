import os
import sys
import platform
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QFileDialog, QDesktopWidget, QMessageBox
from PyQt5.QtGui import QPixmap, QPainter, QPen
from PyQt5.QtCore import Qt, QRect

LAST_FILE_PATH = os.path.expanduser("~/.last_watermark_image")

class ImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.start = None
        self.end = None
        self.pixmap_to_draw = None

    def set_draw_rect(self, start, end, pixmap):
        self.start = start
        self.end = end
        self.pixmap_to_draw = pixmap
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.start and self.end and self.pixmap_to_draw:
            painter = QPainter(self)
            painter.setPen(QPen(Qt.red, 2, Qt.SolidLine))
            rect = QRect(self.start, self.end)
            painter.drawRect(rect)

class RegionSelector(QMainWindow):
    def __init__(self, image_path):
        super().__init__()
        self.setWindowTitle("Select Watermark Region")
        # Get the screen size
        desktop = QApplication.primaryScreen().geometry()
        self.setGeometry(0, 0, desktop.width(), desktop.height())
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.move(0, 0)

        self.original_image = QPixmap(image_path)
        self.label = ImageLabel(self)
        self.setCentralWidget(self.label)
        self.start = self.end = None
        self.rect = QRect()
        self.confirmed = False
        self.update_scaled_image()
        self.show()

    def resizeEvent(self, event):
        self.update_scaled_image()

    def update_scaled_image(self):
        window_size = self.size()
        scaled = self.original_image.scaled(window_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label.setPixmap(scaled)
        self.label.pixmap_to_draw = scaled

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start = event.pos()
            self.end = self.start
            self.label.set_draw_rect(self.start, self.end, self.label.pixmap())

    def mouseMoveEvent(self, event):
        if self.start:
            self.end = event.pos()
            self.label.set_draw_rect(self.start, self.end, self.label.pixmap())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.start:
            self.end = event.pos()
            self.label.set_draw_rect(self.start, self.end, self.label.pixmap())
            # Ask for confirmation
            x1, y1 = min(self.start.x(), self.end.x()), min(self.start.y(), self.end.y())
            x2, y2 = max(self.start.x(), self.end.x()), max(self.start.y(), self.end.y())
            reply = QMessageBox.question(self, 'Confirm Region',
                f"Selected region: (x1={x1}, y1={y1}, x2={x2}, y2={y2})\n\nIs this correct?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                print(f"Selected region: (x1={x1}, y1={y1}, x2={x2}, y2={y2})")
                QApplication.quit()
            else:
                # Reset selection
                self.start = self.end = None
                self.label.set_draw_rect(None, None, self.label.pixmap())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Bring window to front on macOS
    if platform.system() == "Darwin":
        try:
            from AppKit import NSApplication, NSApp, NSApplicationActivationPolicyRegular
            NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular)
            NSApp.activateIgnoringOtherApps_(True)
        except Exception:
            pass

    # Load last file path if available
    initial_dir = ""
    if os.path.exists(LAST_FILE_PATH):
        with open(LAST_FILE_PATH, "r") as f:
            last_path = f.read().strip()
            if os.path.exists(last_path):
                initial_dir = os.path.dirname(last_path)

    file_path, _ = QFileDialog.getOpenFileName(
        None, "Select a sample screenshot", initial_dir, "Image Files (*.png *.jpg *.jpeg *.bmp)"
    )
    if file_path:
        # Save last file path
        with open(LAST_FILE_PATH, "w") as f:
            f.write(file_path)
        selector = RegionSelector(file_path)
        sys.exit(app.exec_())
    else:
        print("No file selected.")