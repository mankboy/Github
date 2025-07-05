from PIL import Image, UnidentifiedImageError
import os
import tkinter as tk
from tkinter import messagebox

def is_majority_grey(image_path, grey_threshold=25, majority_percentage=75, white_exclusion_threshold=235, black_exclusion_threshold=20):
    """
    Analyzes an image to determine if it has a majority mid-range grey background,
    while specifically EXCLUDING white and black backgrounds.
    """
    if not os.path.isfile(image_path):
        print(f"  Warning: File does not exist: {image_path}")
        return False
    try:
        with Image.open(image_path) as img:
            img = img.convert('RGB')
            thumbnail = img.resize((150, 150))  # Slightly larger for better color sampling

            pixels = list(thumbnail.getdata())
            total_pixels = len(pixels)
            grey_pixels = 0

            for r, g, b in pixels:
                is_low_saturation = max(r, g, b) - min(r, g, b) < grey_threshold
                is_not_white = max(r, g, b) < white_exclusion_threshold
                is_not_black = min(r, g, b) > black_exclusion_threshold

                if is_low_saturation and is_not_white and is_not_black:
                    grey_pixels += 1

            percentage = (grey_pixels / total_pixels) * 100

            return percentage >= majority_percentage

    except UnidentifiedImageError:
        print(f"  Warning: Cannot identify image file, skipping: {os.path.basename(image_path)}")
        return False
    except Exception as e:
        print(f"  Warning: Could not analyze image {os.path.basename(image_path)}. Error: {e}")
        return False

import json
import subprocess

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'copyfilestodata_config.json')

# Helper to load last folder from config file
def load_last_folder():
    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            return data.get('last_source_folder', '')
    except Exception:
        return ''

# Helper to save last folder to config file
def save_last_folder(folder):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({'last_source_folder': folder}, f)
    except Exception:
        pass

def open_in_finder(path):
    # Open a folder in Finder on macOS
    subprocess.run(['open', path])

def show_main_gui():
    def select_source_folder():
        folder = tk.filedialog.askdirectory(title="Select Source Folder", initialdir=source_var.get() or os.path.expanduser('~'))
        if folder:
            source_var.set(folder)
            save_last_folder(folder)
            log_text.insert(tk.END, f"Selected source folder: {folder}\n")

    def start_processing():
        import shutil
        import glob
        folder = source_var.get()
        if not folder:
            messagebox.showwarning("No Folder Selected", "Please select a source folder first.")
            return
        log_text.insert(tk.END, f"Starting processing for folder: {folder}\n")
        data_folder = os.path.join(folder, 'DATA')
        if not os.path.isdir(data_folder):
            os.makedirs(data_folder, exist_ok=True)
            log_text.insert(tk.END, f"Created DATA folder: {data_folder}\n")

        image_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')
        subfolders = [f for f in os.listdir(folder) if os.path.isdir(os.path.join(folder, f))]
        def subfolder_sort_key(x):
            return (0, int(x)) if x.isdigit() else (1, x.lower())
        copied_count = 0
        for sub in sorted(subfolders, key=subfolder_sort_key):
            sub_path = os.path.join(folder, sub)
            if not os.path.isdir(sub_path):
                continue
            # Find all image files in this subfolder
            images = [f for f in os.listdir(sub_path) if f.lower().endswith(image_exts) and os.path.isfile(os.path.join(sub_path, f))]
            if not images:
                log_text.insert(tk.END, f"  No images found in subfolder '{sub}'.\n")
                continue
            # Sort images by modification time, newest first
            images_sorted = sorted(images, key=lambda f: os.path.getmtime(os.path.join(sub_path, f)), reverse=True)
            chosen_img = None
            for img_file in images_sorted:
                img_path = os.path.join(sub_path, img_file)
                if not is_majority_grey(img_path):
                    chosen_img = img_file
                    break
                else:
                    log_text.insert(tk.END, f"    Skipping grey image: {img_file}\n")
            if not chosen_img:
                log_text.insert(tk.END, f"  No suitable non-grey image found in subfolder '{sub}'.\n")
                continue
            src_img = os.path.join(sub_path, chosen_img)
            name, ext = os.path.splitext(chosen_img)
            suffix = f"_{sub}"
            dest_img = os.path.join(data_folder, f"{name}{suffix}{ext}")
            try:
                shutil.copy2(src_img, dest_img)
                log_text.insert(tk.END, f"  Copied {src_img} -> {dest_img}\n")
                copied_count += 1
            except Exception as e:
                log_text.insert(tk.END, f"  Failed to copy {src_img}: {e}\n")

        log_text.insert(tk.END, f"Processing complete. {copied_count} image(s) copied.\n")
        open_in_finder(data_folder)
        log_text.insert(tk.END, f"Opened DATA folder in Finder: {data_folder}\n")

    root = tk.Tk()
    root.title("Copy Files to Data")

    frm = tk.Frame(root)
    frm.pack(padx=20, pady=20)

    source_var = tk.StringVar(value=load_last_folder())

    btn_select = tk.Button(frm, text="Select Source Folder", command=select_source_folder)
    btn_select.grid(row=0, column=0, sticky="ew")

    lbl_source = tk.Label(frm, textvariable=source_var, width=40, anchor="w")
    lbl_source.grid(row=0, column=1, padx=(10,0))

    btn_start = tk.Button(frm, text="Start Processing", command=start_processing)
    btn_start.grid(row=1, column=0, columnspan=2, pady=(10,0), sticky="ew")

    log_text = tk.Text(root, height=10, width=60)
    log_text.pack(padx=20, pady=(0,20))
    log_text.insert(tk.END, "Ready.\n")
    log_text.config(state="normal")

    root.mainloop()


if __name__ == "__main__":
    import tkinter.filedialog  # Needed for filedialog
    show_main_gui()