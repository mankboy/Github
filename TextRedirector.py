import tkinter as tk

class TextRedirector:
    def __init__(self, text_widget, tag):
        self.text_widget = text_widget
        self.tag = tag

    def write(self, str_):
        from datetime import datetime
        # Add timestamp to each line
        lines = str_.splitlines(True)  # Keep line endings
        timestamped = "".join([
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {line}" if line.strip() else line
            for line in lines
        ])
        def append():
            self.text_widget.insert(tk.END, timestamped, self.tag)
            self.text_widget.see(tk.END)
        try:
            self.text_widget.after(0, append)
        except RuntimeError:
            pass  # Widget might be destroyed during shutdown

    def flush(self):
        pass
