import os
import glob
from PIL import Image, ImageDraw, ImageOps
import cv2 # For OpenCV
import numpy as np # For OpenCV

# --- Configuration for Cropping with OpenCV ---
# Threshold for cv2.threshold to create a binary mask.
# Pixels with grayscale value > CV2_CROP_THRESHOLD become 255 (white), others 0 (black).
# Adjust this so the main slide content becomes a clear white blob.
CV2_CROP_THRESHOLD = 50  # Grayscale value (0-255)
# Minimum fraction of the total image area that the largest contour must occupy
# to be considered valid. Prevents using tiny noise as the main content.
MIN_CONTOUR_AREA_FRACTION = 0.05 # e.g., 5% of total image area

# --- Fallback PIL Cropping Configuration (if OpenCV contour finding fails) ---
# This is the CROP_CONTENT_THRESHOLD used in the previous PIL-only versions.
# It's used if the OpenCV largest contour method doesn't find a suitable contour.
PIL_FALLBACK_CROP_THRESHOLD = 20 # Grayscale value (0-255)

# --- Configuration for Fixed Redaction (relative to CROPPED content) ---
REDACTION_BAR_WIDTH_FROM_RIGHT_PX = 98
REDACTION_BAR_TOP_MARGIN_PX = 200
REDACTION_BAR_BOTTOM_MARGIN_PX = 260

# --- Configuration for Color Sampling (relative to REDACTION BAR on CROPPED content) ---
SAMPLE_OFFSET_X_INSIDE_BAR_PX = 5
SAMPLE_OFFSET_Y_INSIDE_BAR_PX = 5
SAMPLE_SQUARE_SIZE_PX = 5

# --- Troubleshooting ---
TROUBLESHOOT_FILL_COLOR = None # Set to None to use picked color, or "color_name" for fixed color


def get_average_color_from_region(image_pil, x1, y1, x2, y2):
    """
    Calculates the average RGB color from a specified rectangular region of a PIL image.
    Returns a tuple (R, G, B) or None if the region is invalid or empty.
    """
    if x1 >= x2 or y1 >= y2:
        print(f"    Warning: Sample region is invalid or empty ({x1},{y1} to {x2},{y2}). Cannot pick color.")
        return None
    # Ensure the image for sampling is in RGB mode
    if image_pil.mode != 'RGB':
        image_pil_rgb = image_pil.convert('RGB')
    else:
        image_pil_rgb = image_pil

    pixels = image_pil_rgb.load()
    r_total, g_total, b_total = 0, 0, 0
    count = 0

    for x in range(int(x1), int(x2)):
        for y in range(int(y1), int(y2)):
            # Ensure coordinates are within the image bounds
            if 0 <= x < image_pil_rgb.width and 0 <= y < image_pil_rgb.height:
                try:
                    r, g, b = pixels[x, y]
                    r_total += r
                    g_total += g
                    b_total += b
                    count += 1
                except IndexError: # Should be caught by bounds check, but as a safeguard
                    print(f"    Warning: Pixel ({x},{y}) out of bounds during sampling.")
                    continue
            else:
                # This case should ideally not be reached if actual_sample_... are clipped correctly
                pass
    
    if count == 0:
        print(f"    Warning: No pixels sampled from region ({x1},{y1} to {x2},{y2}) (possibly all out of bounds or zero size). Cannot pick color.")
        return None
        
    avg_r = round(r_total / count)
    avg_g = round(g_total / count)
    avg_b = round(b_total / count)
    return (avg_r, avg_g, avg_b)


def apply_adaptive_redaction(image_path, output_path, debug_folder):
    try:
        img_pil_full = Image.open(image_path).convert("RGB")
        W_full, H_full = img_pil_full.size
        print(f"  Original full image size (W, H): ({W_full}, {H_full})")

        # 1. Auto-crop using OpenCV to find largest content area
        img_cv_full = np.array(img_pil_full) # Convert PIL to OpenCV format (RGB)
        img_cv_gray = cv2.cvtColor(img_cv_full, cv2.COLOR_RGB2GRAY)

        # Apply binary threshold
        print(f"    Using CV2_CROP_THRESHOLD: {CV2_CROP_THRESHOLD}")
        _, thresh_cv = cv2.threshold(img_cv_gray, CV2_CROP_THRESHOLD, 255, cv2.THRESH_BINARY)

        if debug_folder:
            cv_mask_debug_filename = f"DEBUG_CV_MASK_{os.path.basename(image_path)}"
            cv_mask_debug_path = os.path.join(debug_folder, cv_mask_debug_filename)
            cv2.imwrite(cv_mask_debug_path, thresh_cv)
            print(f"    Saved OpenCV threshold mask to: {cv_mask_debug_path}")

        contours, _ = cv2.findContours(thresh_cv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        img_cropped_pil = None
        bbox_used = None

        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            contour_area = cv2.contourArea(largest_contour)
            min_required_area = W_full * H_full * MIN_CONTOUR_AREA_FRACTION
            
            print(f"    Largest contour area: {contour_area:.2f}, Min required area: {min_required_area:.2f}")

            if contour_area > min_required_area:
                x, y, w, h = cv2.boundingRect(largest_contour)
                # Ensure bounding box is within image dimensions (should be, but good practice)
                x = max(0, x)
                y = max(0, y)
                w = min(w, W_full - x)
                h = min(h, H_full - y)
                
                bbox_used = (x, y, x + w, y + h) # (left, top, right_exclusive, bottom_exclusive)
                img_cropped_pil = img_pil_full.crop(bbox_used)
                print(f"    Cropped to largest contour bbox: {bbox_used}")
            else:
                print(f"    Warning: Largest contour area ({contour_area:.2f}) is less than min required ({min_required_area:.2f}).")
        
        if img_cropped_pil is None: # If OpenCV method failed or contour too small, fallback to PIL
            print(f"    Attempting fallback to PIL's getbbox with PIL_FALLBACK_CROP_THRESHOLD: {PIL_FALLBACK_CROP_THRESHOLD}")
            content_mask_pil = img_pil_full.convert('L').point(lambda p: 255 if p > PIL_FALLBACK_CROP_THRESHOLD else 0)
            content_mask_for_bbox_pil = content_mask_pil.convert('1')
            
            if debug_folder: # Save PIL mask if used
                pil_mask_debug_filename = f"DEBUG_PIL_FALLBACK_MASK_{os.path.basename(image_path)}"
                pil_mask_debug_path = os.path.join(debug_folder, pil_mask_debug_filename)
                content_mask_pil.convert("RGB").save(pil_mask_debug_path)
                print(f"    Saved PIL fallback mask to: {pil_mask_debug_path}")

            bbox_pil = content_mask_for_bbox_pil.getbbox()
            if bbox_pil:
                img_cropped_pil = img_pil_full.crop(bbox_pil)
                bbox_used = bbox_pil
                print(f"    Fallback PIL getbbox used: {bbox_used}")
            else:
                print(f"    Warning: Fallback PIL getbbox also failed. Using full image.")
                img_cropped_pil = img_pil_full
                bbox_used = (0, 0, W_full, H_full)
        
        W_content, H_content = img_cropped_pil.size
        print(f"  Content area size after crop (W_content, H_content): ({W_content}, {H_content})")

        if debug_folder:
            cropped_debug_filename = f"DEBUG_CROPPED_BEFORE_REDACTION_{os.path.basename(image_path)}"
            cropped_debug_path = os.path.join(debug_folder, cropped_debug_filename)
            img_cropped_pil.save(cropped_debug_path)
            print(f"    Saved cropped (pre-redaction) image to: {cropped_debug_path}")

        if W_content == 0 or H_content == 0:
            print(f"  Skipping redaction for {os.path.basename(image_path)}: Content area is empty after crop.")
            return False

        # 2. Define redaction bar (relative to CROPPED content)
        bar_x1 = W_content - REDACTION_BAR_WIDTH_FROM_RIGHT_PX
        bar_y1 = REDACTION_BAR_TOP_MARGIN_PX
        bar_x2 = W_content
        bar_y2 = H_content - REDACTION_BAR_BOTTOM_MARGIN_PX

        rect_to_fill = (
            max(0, bar_x1), max(0, bar_y1),
            min(W_content, bar_x2), min(H_content, bar_y2),
        )
        print(f"  Calculated redaction bar on content (L, T, R, B): {rect_to_fill}")

        if not (rect_to_fill[0] < rect_to_fill[2] and rect_to_fill[1] < rect_to_fill[3]):
            print(f"  Skipping redaction: Redaction bar on content is invalid. Check REDACTION_..._PX values relative to content size.")
            return False
        
        # 3. Define sample region (relative to redaction bar ON CROPPED image)
        sample_region_tl_x = rect_to_fill[0] + SAMPLE_OFFSET_X_INSIDE_BAR_PX
        sample_region_tl_y = rect_to_fill[1] + SAMPLE_OFFSET_Y_INSIDE_BAR_PX
        sample_region_br_x = sample_region_tl_x + SAMPLE_SQUARE_SIZE_PX
        sample_region_br_y = sample_region_tl_y + SAMPLE_SQUARE_SIZE_PX

        # Clip sample region to be within the actual cropped image
        actual_sample_x1 = max(0, min(sample_region_tl_x, W_content -1))
        actual_sample_y1 = max(0, min(sample_region_tl_y, H_content -1))
        actual_sample_x2 = min(W_content, max(sample_region_br_x, actual_sample_x1 + 1))
        actual_sample_y2 = min(H_content, max(sample_region_br_y, actual_sample_y1 + 1))
        
        print(f"    Nominal sample region TL (rel to bar): ({SAMPLE_OFFSET_X_INSIDE_BAR_PX},{SAMPLE_OFFSET_Y_INSIDE_BAR_PX})")
        print(f"    Actual clipped sample region on content (abs coords): ({actual_sample_x1},{actual_sample_y1} to {actual_sample_x2},{actual_sample_y2})")

        # 4. Get average color (from CROPPED image) or use troubleshoot color
        fill_color_to_use = TROUBLESHOOT_FILL_COLOR 

        if TROUBLESHOOT_FILL_COLOR:
            print(f"    TROUBLESHOOTING: Using fixed fill color: {fill_color_to_use}")
        else: 
            picked_color = get_average_color_from_region(img_cropped_pil, 
                                                       actual_sample_x1, actual_sample_y1,
                                                       actual_sample_x2, actual_sample_y2)
            if picked_color is None:
                print(f"  Failed to pick background color. Defaulting to black.")
                fill_color_to_use = "black"
            else:
                fill_color_to_use = picked_color
                print(f"    Picked fill color (R,G,B): {fill_color_to_use}")

        # 5. Draw redaction on CROPPED image
        draw = ImageDraw.Draw(img_cropped_pil)
        draw.rectangle(rect_to_fill, fill=fill_color_to_use)
        
        img_cropped_pil.save(output_path)
        print(f"  Saved cropped & redacted image to: {output_path}")
        return True

    except FileNotFoundError:
        print(f"Error: Image file not found at {image_path}")
        return False
    except Exception as e:
        print(f"  An unexpected error occurred while processing {os.path.basename(image_path)}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_folder = os.path.join(script_dir, "input_images")
    output_folder = os.path.join(script_dir, "redacted_images")
    debug_folder = os.path.join(script_dir, "debug_images")

    for folder in [input_folder, output_folder, debug_folder]:
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"Created folder: {os.path.abspath(folder)}")
    
    if not os.listdir(input_folder) and input_folder == os.path.join(script_dir, "input_images"):
         print(f"Input folder {os.path.abspath(input_folder)} is empty. Please place images there.")
         return

    image_patterns = ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"]
    image_files = []
    for pattern in image_patterns:
        image_files.extend(glob.glob(os.path.join(input_folder, pattern)))
    image_files = sorted(list(set(image_files)))

    if not image_files:
        print(f"No images found in {os.path.abspath(input_folder)}")
        return

    print(f"Found {len(image_files)} image(s) to process in {os.path.abspath(input_folder)}.")
    processed_count = 0
    redaction_applied_count = 0

    for image_file in image_files:
        print(f"\nProcessing: {os.path.basename(image_file)}")
        base_name = os.path.basename(image_file)
        name, ext = os.path.splitext(base_name)
        output_file_name = f"{name}_redacted{ext}"
        output_file_path = os.path.join(output_folder, output_file_name)

        if apply_adaptive_redaction(image_file, output_file_path, debug_folder):
            redaction_applied_count +=1
        processed_count +=1

    print(f"\n--- Summary ---")
    print(f"Total images processed: {processed_count}")
    print(f"Images with redaction applied and saved: {redaction_applied_count}")
    print(f"Redacted images are in: {os.path.abspath(output_folder)}")
    print(f"Debug images (if any) are in: {os.path.abspath(debug_folder)}")

if __name__ == "__main__":
    main()