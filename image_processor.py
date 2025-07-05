import os
import cv2
import numpy as np
from datetime import datetime
import pytesseract
from tkinter import filedialog, Tk, messagebox
import tkinter as tk
import json
import platform

# Global variables for rectangle selection
drawing = False
ix, iy = -1, -1
rect_coords = []
current_image = None
window_name = "Image Selector"
original_screen_size = None

# Configuration file to store last used folder
CONFIG_FILE = os.path.expanduser("~/.image_processor_config.json")

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except Exception as e:
        print(f"Warning: Could not save configuration: {str(e)}")

def load_config():
    default_config = {
        "last_folder": os.path.expanduser("~")
    }
    
    if not os.path.exists(CONFIG_FILE):
        return default_config
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"Warning: Could not load configuration: {str(e)}")
        return default_config

def draw_rectangle(event, x, y, flags, param):
    global ix, iy, drawing, rect_coords, current_image, original_image
    
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        ix, iy = x, y
        print(f"Started drawing at ({x}, {y})")
    
    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            # Draw on a copy of the original to prevent accumulation
            img_copy = original_image.copy()
            cv2.rectangle(img_copy, (ix, iy), (x, y), (0, 255, 0), 2)
            
            # Show dimensions
            w, h = abs(x - ix), abs(y - iy)
            text = f"{w}x{h}"
            cv2.putText(img_copy, text, (x+10, y+20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            current_image = img_copy
            cv2.imshow(window_name, current_image)
    
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        if abs(x - ix) > 10 and abs(y - iy) > 10:  # Ensure minimum size
            # Save final rectangle
            x1, y1 = min(ix, x), min(iy, y)
            x2, y2 = max(ix, x), max(iy, y)
            rect_coords = [x1, y1, x2-x1, y2-y1]  # x, y, w, h
            
            # Draw final rectangle
            cv2.rectangle(current_image, (ix, iy), (x, y), (0, 255, 0), 2)
            cv2.imshow(window_name, current_image)
            print(f"Rectangle selected: {rect_coords}")
        else:
            print("Rectangle too small! Please try again.")
            rect_coords = []

def get_rectangle(image, title):
    global rect_coords, current_image, original_image, window_name
    
    # Reset global variables
    rect_coords = []
    window_name = title
    
    # Make a copy of the image
    current_image = image.copy()
    original_image = image.copy()
    
    # Get screen dimensions
    screen_w, screen_h = 1920, 1080  # Default values
    
    # Try to get actual screen resolution for proper sizing
    try:
        root = Tk()
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        root.destroy()
    except:
        pass
    
    # Create window with optimal size based on screen and image
    height, width = image.shape[:2]
    scale = min(0.9 * screen_w / width, 0.9 * screen_h / height)
    display_width = int(width * scale)
    display_height = int(height * scale)
    
    print("\nInstructions:")
    print("1. Click and drag to draw a rectangle")
    print("2. Release mouse button to finish drawing")
    print("3. Press 'c' or Enter to confirm the selection")
    print("4. Press 'r' to reset if you make a mistake")
    print("5. Press 'q' to quit without selecting\n")
    
    # Create a resizable window at near-maximum size
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, display_width, display_height)
    
    # On macOS, we'll use a different approach to maximize
    if platform.system() == "Darwin":  # macOS
        cv2.setWindowProperty(window_name, cv2.WND_PROP_ASPECT_RATIO, cv2.WINDOW_KEEPRATIO)
        cv2.moveWindow(window_name, 0, 0)
    else:
        # On Windows/Linux try to use fullscreen
        try:
            cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        except:
            pass  # Fallback to resizable window if fullscreen fails

    cv2.setMouseCallback(window_name, draw_rectangle)
    cv2.imshow(window_name, current_image)
    
    # Ensure window is brought to front and activated
    cv2.waitKey(1)

    # Attempt to bring the window to the front after it's definitely drawn
    try:
        cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)
        cv2.waitKey(1) # Allow time for property to apply
        cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 0)
        print("Attempted to bring window to front.") # Debug message
    except Exception as e:
        print(f"Note: Could not set window property for bringing to front: {e}")
    
    while True:
        cv2.imshow(window_name, current_image)
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('c') or key == 13:  # 'c' or Enter
            if rect_coords:
                cv2.destroyAllWindows()
                break
            else:
                print("No rectangle selected! Please draw a rectangle first.")
        elif key == ord('r'):  # 'r' to reset
            current_image = original_image.copy()
            rect_coords = []
            cv2.imshow(window_name, current_image)
            print("Reset selection. Please try again.")
        elif key == ord('q') or key == 27:  # 'q' or Esc to quit
            cv2.destroyAllWindows()
            rect_coords = []
            break
    
    return rect_coords

def get_folder_path():
    # Load last used folder from config
    config = load_config()
    initial_dir = config.get("last_folder", os.path.expanduser("~"))
    
    # Make sure the initial directory exists
    if not os.path.exists(initial_dir):
        initial_dir = os.path.expanduser("~")
    
    root = Tk()
    root.withdraw()  # Hide the main window
    
    # Open dialog at the last used location
    folder_path = filedialog.askdirectory(title="Select folder containing images", 
                                       initialdir=initial_dir)
    
    if folder_path:
        # Save selected folder to config
        config["last_folder"] = folder_path
        save_config(config)
        
        # Show confirmation message
        root.deiconify()
        msg = f"Selected folder: {folder_path}\nClick OK to continue."
        messagebox.showinfo("Folder Selected", msg)
        root.withdraw()
    
    return folder_path

def get_oldest_image(folder_path):
    image_files = []
    for file in os.listdir(folder_path):
        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
            full_path = os.path.join(folder_path, file)
            creation_time = os.path.getctime(full_path)
            image_files.append((creation_time, full_path))
    
    if not image_files:
        raise Exception("No image files found in the selected folder")
    
    oldest_image = min(image_files, key=lambda x: x[0])[1]
    return oldest_image

def extract_page_number(image, rect):
    if not rect or len(rect) != 4:
        return "unknown"
        
    x, y, w, h = rect
    
    # Make sure coordinates are within bounds
    h_img, w_img = image.shape[:2]
    x = max(0, min(x, w_img-1))
    y = max(0, min(y, h_img-1))
    w = min(w, w_img-x)
    h = min(h, h_img-y)
    
    # Extract ROI
    try:
        roi = image[y:y+h, x:x+w]
        
        # Convert to grayscale if not already
        if len(roi.shape) == 3:
            roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            
        # Apply threshold to make text clearer
        _, roi = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Save ROI for debugging
        cv2.imwrite("page_number_roi.png", roi)
        
        # Extract text using Tesseract
        text = pytesseract.image_to_string(roi, config='--psm 6 -c tessedit_char_whitelist=0123456789')
        
        # Clean up the text and extract numbers
        numbers = ''.join(filter(str.isdigit, text))
        return numbers if numbers else "unknown"
    except Exception as e:
        print(f"Error extracting page number: {str(e)}")
        return "unknown"

def main():
    # Get folder path from user
    folder_path = get_folder_path()
    if not folder_path:
        print("No folder selected. Exiting...")
        return

    # Get the oldest image
    try:
        oldest_image_path = get_oldest_image(folder_path)
        print(f"\nOpening oldest image: {oldest_image_path}")
        image = cv2.imread(oldest_image_path)
        if image is None:
            print(f"Error loading image: {oldest_image_path}")
            return
    except Exception as e:
        print(f"Error: {str(e)}")
        return

    # Create output directory
    output_dir = os.path.join(folder_path, "DATA")
    os.makedirs(output_dir, exist_ok=True)

    # Get crop rectangle
    print("\n=== Step 1: Select Cropping Region ===")
    crop_rect = get_rectangle(image, "Select Crop Region")
    if not crop_rect:
        print("No crop region selected. Exiting...")
        return

    # Get page number rectangle
    print("\n=== Step 2: Select Page Number Region ===")
    page_rect = get_rectangle(image, "Select Page Number Region")
    if not page_rect:
        print("No page number region selected. Exiting...")
        return

    print("\n=== Processing Images ===")
    # Process all images in the folder
    processed_count = 0
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
            input_path = os.path.join(folder_path, filename)
            img = cv2.imread(input_path)
            if img is None:
                print(f"Error loading image: {filename}")
                continue

            try:
                # Extract page number
                page_number = extract_page_number(img, page_rect)
                
                # Crop image
                x, y, w, h = crop_rect
                
                # Ensure crop coordinates are within image bounds
                h_img, w_img = img.shape[:2]
                x = max(0, min(x, w_img-1))
                y = max(0, min(y, h_img-1))
                w = min(w, w_img-x)
                h = min(h, h_img-y)
                
                cropped_img = img[y:y+h, x:x+w]
                
                # Create new filename
                base_name, ext = os.path.splitext(filename)
                new_filename = f"{base_name}_p{page_number}{ext}"
                output_path = os.path.join(output_dir, new_filename)
                
                # Save the cropped image
                cv2.imwrite(output_path, cropped_img)
                print(f"Processed: {filename} -> {new_filename}")
                processed_count += 1
            except Exception as e:
                print(f"Error processing {filename}: {str(e)}")

    print("\nProcessing complete!")
    print(f"Processed {processed_count} images")
    print(f"Processed images have been saved to: {output_dir}")

if __name__ == "__main__":
    main() 