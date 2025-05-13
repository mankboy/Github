import os
import sys
import tempfile
from datetime import datetime
from PIL import Image, ImageTk, ImageGrab
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import json
import time
from screeninfo import get_monitors
import pyautogui
import subprocess

# Configuration file path
CONFIG_FILE = os.path.expanduser("~/pdf_processor_config.json")

# At the top of the file, after PIL imports
try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.ANTIALIAS

def load_config():
    """Load configuration from file"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {str(e)}")
    return {
        "last_output_dir": os.path.expanduser("~")
    }

def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {str(e)}")

def process_screenshot(screenshot, watermark_coords=None, fill_color=None):
    """
    Process a screenshot to remove watermarks.
    
    Args:
        screenshot: PIL Image object of the screenshot
        watermark_coords: Tuple of (x1, y1, x2, y2) defining watermark region to remove
        fill_color: RGB tuple for the fill color (default: white)
    """
    if watermark_coords:
        x1, y1, x2, y2 = [int(round(v)) for v in watermark_coords]
        width = int(round(x2 - x1))
        height = int(round(y2 - y1))
        # Create a rectangle with the specified fill color
        draw = Image.new('RGB', (width, height), color=fill_color or (255, 255, 255))
        screenshot.paste(draw, (x1, y1))
    
    return screenshot

class WatermarkSelector:
    def __init__(self, parent):
        self.parent = parent
        self.screens = self.get_screens()
        self.screenshot = None
        
        # Create window
        self.window = tk.Toplevel(parent)
        self.window.title("Select Watermark Region")
        self.window.geometry("900x700")
        
        # Instructions
        tk.Label(self.window, 
                text="1. Open your PDF in Adobe Reader\n"
                     "2. Position the window so the watermark is visible\n"
                     "3. Select the screen to capture OR load a screenshot file\n"
                     "4. Click 'Capture Screenshot' or 'Load Screenshot from File'\n"
                     "5. Select the watermark region\n"
                     "\nNote: Screens to the left or above your main display may have negative coordinates. This is normal.\n"
                     "If live capture fails, use the 'Load Screenshot from File' option.",
                justify=tk.LEFT).pack(pady=10)
        
        # Screen selection
        screen_frame = tk.Frame(self.window)
        screen_frame.pack(pady=5)
        tk.Label(screen_frame, text="Select Screen:").pack(side=tk.LEFT)
        self.screen_var = tk.StringVar()
        self.screen_combo = ttk.Combobox(screen_frame, textvariable=self.screen_var, state="readonly")
        self.screen_combo.pack(side=tk.LEFT, padx=5)
        
        # Capture and load buttons
        btn_frame = tk.Frame(self.window)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Capture Screenshot", command=self.capture_screenshot).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Load Screenshot from File", command=self.load_screenshot_from_file).pack(side=tk.LEFT, padx=5)
        
        # Create canvas for image display
        self.canvas_frame = tk.Frame(self.window)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
        # Create canvas with scrollbars
        self.canvas = tk.Canvas(self.canvas_frame)
        self.scrollbar_y = tk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL)
        self.scrollbar_x = tk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL)
        
        # Configure scrollbars
        self.scrollbar_y.config(command=self.canvas.yview)
        self.scrollbar_x.config(command=self.canvas.xview)
        self.canvas.config(yscrollcommand=self.scrollbar_y.set, xscrollcommand=self.scrollbar_x.set)
        
        # Pack scrollbars and canvas
        self.scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
        # Selection variables
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.selection_coords = None
        
        # Buttons
        button_frame = tk.Frame(self.window)
        button_frame.pack(pady=10)
        
        tk.Button(button_frame, text="Confirm Selection", 
                 command=self.confirm_selection).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", 
                 command=self.window.destroy).pack(side=tk.LEFT, padx=5)
        
        # Initialize screen list
        self.update_screen_list()

    def get_screens(self):
        """Get actual screens using screeninfo"""
        try:
            monitors = get_monitors()
            return monitors
        except Exception as e:
            messagebox.showerror("Error", f"Could not detect screens: {str(e)}")
            return []

    def update_screen_list(self):
        """Update the list of available screens with resolution and position"""
        try:
            screens = []
            for i, m in enumerate(self.screens):
                screens.append(f"Screen {i+1}: {m.width}x{m.height} at ({m.x},{m.y})")
            # Defensive: Only set values if the list is not empty and contains only strings
            screen_values = [str(s) for s in screens if s]
            if screen_values:
                self.screen_combo['values'] = screen_values
                self.screen_combo.set(screen_values[0])
                self.screen_combo.config(state="readonly")
            else:
                self.screen_combo['values'] = []
                self.screen_combo.set('')
                self.screen_combo.config(state="disabled")
        except Exception as e:
            print(f"Error getting screen list: {str(e)}")

    def capture_screenshot(self):
        """Capture the selected screen after a short delay"""
        self.window.iconify()  # Minimize the window
        time.sleep(2)  # Give user time to switch to Adobe Reader
        try:
            idx = self.screen_combo.current()
            if idx < 0 or idx >= len(self.screens):
                raise Exception("No screen selected")
            m = self.screens[idx]
            # Capture the selected screen
            self.screenshot = ImageGrab.grab(bbox=(m.x, m.y, m.x + m.width, m.y + m.height))
            # Convert to PhotoImage and display
            self.photo = ImageTk.PhotoImage(self.screenshot)
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
            self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))
            # Bind mouse events
            self.canvas.bind("<ButtonPress-1>", self.on_press)
            self.canvas.bind("<B1-Motion>", self.on_drag)
            self.canvas.bind("<ButtonRelease-1>", self.on_release)
        except Exception as e:
            messagebox.showerror("Error", f"Error capturing screenshot: {str(e)}")
        finally:
            self.window.deiconify()  # Restore the window
    
    def on_press(self, event):
        """Handle mouse press event"""
        # Get canvas coordinates
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
        
        # Create rectangle if it doesn't exist
        if not self.rect:
            self.rect = self.canvas.create_rectangle(
                self.start_x, self.start_y, self.start_x, self.start_y,
                outline='red', width=2
            )
    
    def on_drag(self, event):
        """Handle mouse drag event"""
        # Update rectangle coordinates
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)
    
    def on_release(self, event):
        """Handle mouse release event"""
        # Get final coordinates
        end_x = self.canvas.canvasx(event.x)
        end_y = self.canvas.canvasy(event.y)
        
        # Store selection coordinates
        self.selection_coords = (
            min(self.start_x, end_x),
            min(self.start_y, end_y),
            max(self.start_x, end_x),
            max(self.start_y, end_y)
        )
    
    def get_color_at_point(self, x, y):
        """Get RGB color at specified point in the image"""
        try:
            # Convert coordinates to image coordinates
            img_x = int(x)
            img_y = int(y)
            
            # Ensure coordinates are within image bounds
            if 0 <= img_x < self.screenshot.width and 0 <= img_y < self.screenshot.height:
                return self.screenshot.getpixel((img_x, img_y))
        except Exception as e:
            print(f"Error getting color: {str(e)}")
        return (255, 255, 255)  # Default to white if error
    
    def confirm_selection(self):
        """Confirm the selection and get the fill color, then offer batch capture."""
        if not self.selection_coords:
            messagebox.showerror("Error", "Please select a region first")
            return
        # Get the point 200 pixels to the left of the lower left corner
        x1, y1, x2, y2 = self.selection_coords
        color_x = max(0, x1 - 200)  # Ensure we don't go off the left edge
        color_y = y2  # Use the bottom y-coordinate
        fill_color = self.get_color_at_point(color_x, color_y)
        processed_image = process_screenshot(self.screenshot, self.selection_coords, fill_color)
        self.result = {
            'image': processed_image,
            'coords': self.selection_coords,
            'fill_color': fill_color
        }
        # Save the first processed image
        self.save_batch_image(processed_image, 1)
        # Ask for number of pages
        num_pages = self.ask_num_pages()
        if num_pages:
            self.batch_capture(num_pages, self.selection_coords, fill_color)
        if self.window.winfo_exists():
            self.window.destroy()

    def ask_num_pages(self):
        """Prompt user for number of pages to process in batch."""
        from tkinter.simpledialog import askinteger
        return askinteger("Batch Capture", "How many pages in total (including the first)?", minvalue=1)

    def batch_capture(self, num_pages, coords, fill_color):
        """Automate screenshot, watermark removal, and saving for multiple pages."""
        print(f"Starting batch capture of {num_pages} pages")
        print(f"Output folder: {self.parent.output_var.get() if hasattr(self.parent, 'output_var') else os.path.expanduser('~')}")
        
        for i in range(2, num_pages + 1):
            print(f"Processing page {i}")
            try:
                # Ensure window is active
                time.sleep(0.5)  # Small delay before keypress
                pyautogui.press('pagedown')
                time.sleep(1.5)  # Increased delay to ensure page loads
                
                # Capture screenshot with error checking
                try:
                    screenshot = pyautogui.screenshot()
                    print(f"Screenshot captured: {screenshot.size}")
                except Exception as e:
                    print(f"Error capturing screenshot: {str(e)}")
                    continue
                
                # Process screenshot
                try:
                    processed = process_screenshot(screenshot, coords, fill_color)
                    print(f"Image processed: {processed.size}")
                except Exception as e:
                    print(f"Error processing image: {str(e)}")
                    continue
                
                # Save the image
                self.save_batch_image(processed, i)
                print(f"Completed page {i}")
                
            except Exception as e:
                print(f"Error in batch capture loop: {str(e)}")

    def save_batch_image(self, image, idx):
        """Save processed image with incrementing filename."""
        try:
            # Get output folder with fallback
            output_folder = self.parent.output_var.get() if hasattr(self.parent, 'output_var') else os.path.expanduser("~")
            print(f"Attempting to save to folder: {output_folder}")
            
            # Ensure output directory exists
            os.makedirs(output_folder, exist_ok=True)
            
            # Create filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(output_folder, f"processed_page_{idx:03d}_{timestamp}.png")
            print(f"Full output path: {output_path}")
            
            # Verify image is valid
            if not image or not hasattr(image, 'save'):
                raise ValueError("Invalid image object")
            
            # Save the image
            image.save(output_path)
            print(f"Successfully saved image to: {output_path}")
            
            # Verify file exists after saving
            if os.path.exists(output_path):
                print(f"File exists after save: {output_path}")
            else:
                raise FileNotFoundError(f"File not found after save: {output_path}")
                
        except Exception as e:
            print(f"Error saving image: {str(e)}")
            raise  # Re-raise the exception to be caught by the caller

    def load_screenshot_from_file(self):
        filetypes = [("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.tiff"), ("All files", "*.*")]
        filename = filedialog.askopenfilename(title="Select Screenshot Image", filetypes=filetypes)
        if not filename:
            return  # User cancelled, do not proceed
        try:
            img = Image.open(filename)
            self.screenshot = img.copy()
            # Enable region selection on the loaded image
            self.canvas.create_image(0, 0, anchor=tk.NW, image=ImageTk.PhotoImage(self.screenshot))
            self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))
            self.canvas.bind("<ButtonPress-1>", self.on_press)
            self.canvas.bind("<B1-Motion>", self.on_drag)
            self.canvas.bind("<ButtonRelease-1>", self.on_release)
        except Exception as e:
            print(f"Could not load image: {str(e)}")

class ScreenshotProcessorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Watermark Remover")
        self.root.geometry("600x400")
        
        # Load configuration
        self.config = load_config()
        
        # Create main frame
        main_frame = tk.Frame(root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Instructions
        tk.Label(main_frame, 
                text="1. Open your PDF in Adobe Reader\n"
                     "2. Position the window so the watermark is visible\n"
                     "3. Select the watermark region in the next window",
                justify=tk.LEFT).pack(pady=10)
        
        # Output folder selection
        output_frame = tk.Frame(main_frame)
        output_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(output_frame, text="Save Processed Image To:").pack(side=tk.LEFT)
        self.output_var = tk.StringVar()
        tk.Entry(output_frame, textvariable=self.output_var, width=50).pack(side=tk.LEFT, padx=5)
        tk.Button(output_frame, text="Browse", 
                 command=self.browse_output).pack(side=tk.LEFT)
        
        # Status label
        self.status_var = tk.StringVar()
        tk.Label(main_frame, textvariable=self.status_var).pack(pady=10)
        
        # Watermark selection variables
        self.watermark_coords = None
        self.fill_color = None
        self.processed_image = None
        
        # Restore last used paths
        self.restore_last_paths()
        
        # Start watermark selection automatically
        self.start_watermark_selection()
    
    def restore_last_paths(self):
        """Restore last used file paths from config"""
        if "last_output_dir" in self.config:
            self.output_var.set(self.config["last_output_dir"])
    
    def browse_output(self):
        """Browse for output folder"""
        folder = filedialog.askdirectory(
            initialdir=self.config.get("last_output_dir", os.path.expanduser("~")),
            title="Select output folder"
        )
        if folder:
            self.output_var.set(folder)
            self.config["last_output_dir"] = folder
            save_config(self.config)
    
    def start_watermark_selection(self):
        """Start watermark selection process"""
        # Create watermark selector
        selector = WatermarkSelector(self.root)
        self.root.wait_window(selector.window)
        
        # Get selection results
        if hasattr(selector, 'result'):
            self.processed_image = selector.result['image']
            self.watermark_coords = selector.result['coords']
            self.fill_color = selector.result['fill_color']
            
            # Save the processed image
            self.save_processed_image()
    
    def save_processed_image(self):
        """Save the processed image"""
        if not self.processed_image:
            return
        
        if not self.output_var.get():
            messagebox.showerror("Error", "Please select an output folder")
            return
        
        try:
            # Create output filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(self.output_var.get(), f"processed_{timestamp}.png")
            
            # Save the image
            self.processed_image.save(output_path)
            
            # Show success message
            messagebox.showinfo("Success", 
                              f"Processed image saved to:\n{output_path}")
            
            # Update status
            self.status_var.set("Processing complete!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error saving image: {str(e)}")
            self.status_var.set("Error saving image")

class PDFCaptureGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Page Capture")
        self.root.geometry("400x200")
        
        # Create main frame
        main_frame = tk.Frame(root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Instructions
        tk.Label(main_frame, 
                text="1. Select your PDF file\n"
                     "2. The script will:\n"
                     "   - Open it in Adobe Reader\n"
                     "   - Capture each page\n"
                     "   - Save images in the same folder",
                justify=tk.LEFT).pack(pady=10)
        
        # Select PDF button
        tk.Button(main_frame, text="Select PDF File", 
                 command=self.start_capture).pack(pady=10)
        
        # Status label
        self.status_var = tk.StringVar()
        tk.Label(main_frame, textvariable=self.status_var).pack(pady=10)

    def start_capture(self):
        """Start the PDF capture process"""
        # Get PDF file
        pdf_path = filedialog.askopenfilename(
            title="Select PDF File",
            filetypes=[("PDF files", "*.pdf")]
        )
        
        if not pdf_path:
            return
            
        # Get output directory (same as PDF)
        output_dir = os.path.dirname(pdf_path)
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        
        try:
            # Open PDF in Adobe Reader
            self.status_var.set("Opening PDF in Adobe Reader...")
            subprocess.Popen(['open', '/Applications/Adobe Acrobat DC/Adobe Acrobat.app', pdf_path])
            
            # Wait for Adobe Reader to open and allow user to bring it to the foreground
            self.status_var.set("Waiting 30 seconds for Adobe Reader to open. Please bring it to the front and make it fullscreen if needed.")
            time.sleep(30)
            
            # Go to first page
            pyautogui.hotkey('command', '1')  # Go to first page
            time.sleep(1)
            # Please manually enter fullscreen in Adobe Reader before capture begins.
            
            page_num = 1
            while True:
                # Capture full screen
                self.status_var.set(f"Capturing page {page_num}...")
                screenshot = ImageGrab.grab()
                
                # Save with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = os.path.join(output_dir, f"{pdf_name}_page_{page_num:03d}_{timestamp}.png")
                screenshot.save(output_path)
                print(f"Saved: {output_path}")
                
                # Try to go to next page
                pyautogui.press('pagedown')
                time.sleep(2)  # Wait for page to load
                
                # Check if we're still on the same page
                new_screenshot = ImageGrab.grab()
                if new_screenshot.tobytes() == screenshot.tobytes():
                    # If screenshots are identical, we've reached the end
                    break
                    
                page_num += 1
            
            self.status_var.set(f"Completed! Captured {page_num} pages.")
            messagebox.showinfo("Success", f"Successfully captured {page_num} pages!")
            
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")

def main():
    root = tk.Tk()
    app = PDFCaptureGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()