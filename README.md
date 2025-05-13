# Image Processor

This script processes a folder of images by:
1. Cropping them according to a user-defined rectangle
2. Extracting page numbers from a specified region
3. Saving the processed images in a new 'DATA' subfolder

## Prerequisites

- Python 3.6 or higher
- Tesseract OCR must be installed on your system:
  - For macOS: `brew install tesseract`
  - For Ubuntu/Debian: `sudo apt-get install tesseract-ocr`
  - For Windows: Download installer from https://github.com/UB-Mannheim/tesseract/wiki

## Installation

1. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the script:
   ```bash
   python image_processor.py
   ```

2. When prompted, select the folder containing your images.

3. The script will open the oldest image in the folder and ask you to:
   - Draw a rectangle for the cropping area (this will be applied to all images)
   - Draw a rectangle around the page number area

4. Press 'c' or Enter to confirm each rectangle selection.

5. The script will process all images and save them in a new 'DATA' subfolder with the format:
   `original_filename_p[page_number].extension`

## Notes

- Supported image formats: PNG, JPG, JPEG, TIFF, BMP
- If a page number cannot be extracted, "unknown" will be used in the filename
- Original files are not modified; processed files are saved in the DATA subfolder 