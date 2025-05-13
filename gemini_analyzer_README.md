# Gemini Image Analyzer

This Python script enables you to upload images of multiple-choice questions to Google Gemini and receive detailed analysis, including:
- The question from the image
- The correct answer with explanation
- Why each incorrect answer is wrong

The analysis is formatted and saved as a Word document in the same location as the original image.

## Prerequisites

- Python 3.6 or higher
- A Google Gemini API key (default key is provided in the script)

## Installation

1. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install required packages:
   ```bash
   pip install -r requirements_gemini.txt
   pip install google-generativeai
   ```

## Usage

Run the script:
```bash
python gemini_image_analyzer.py
```

### First-time setup

The script comes with a default Google Gemini API key. If you want to use your own key, you can enter it when prompted.

### Processing a single image

1. Click "Process Single Image"
2. Select an image file with a multiple-choice question
3. The script will upload the image to Google Gemini and receive the analysis
4. A preview window will show the results
5. Click "Save to Word Document" to save the analysis as a Word document

The Word document will be saved with the same name as your image file, with "_analysis" appended.

### Batch Processing

For processing multiple images at once, use the batch processor:

```bash
python gemini_batch_processor.py
```

This allows you to:
1. Select a folder of images
2. Process them all at once
3. Monitor progress with a progress bar
4. Save Word documents for each analysis

## Features

- User-friendly interface
- Preview of analysis before saving
- Remembers last folder location
- Batch processing capability
- Formatted Word document output

## Notes

- The script includes mock response functionality for testing without an active API connection
- The Google Gemini API has usage limits; consult Google's documentation for details 