#!/bin/bash

# Set crop region dimensions for the counter (update these if needed)
crop_width=170
crop_height=50

# Set the top-left offset of the counter region.
# Replace these with your measured values.
x_offset=2800  # e.g., measured x offset
y_offset=50  # e.g., measured y offset

# Loop over all PNG files in the current directory
for file in *.png; do
  # Crop the region containing the counter and save it to a temporary file
  magick "$file" -crop ${crop_width}x${crop_height}+${x_offset}+${y_offset} cropped.png
  
  # Run Tesseract OCR on the cropped area
  counter_text=$(tesseract cropped.png stdout 2>/dev/null)
  
  # Extract the first group of digits (assumed to be the counter value)
  counter=$(echo "$counter_text" | grep -Eo '[0-9]+' | head -n1)
  
  if [ -n "$counter" ]; then
    # Create a directory named after the counter if it doesn't already exist
    mkdir -p "$counter"
    # Build new filename with _<counter> suffix before extension
    base_name="${file%.*}"
    ext="${file##*.}"
    new_name="${base_name}_${counter}.${ext}"
    # Move and rename the original image into the corresponding directory
    mv "$file" "$counter/$new_name"
    echo "Moved $file to $counter/$new_name"
  else
    echo "Counter not found in $file"
  fi
done

# Clean up the temporary cropped image
rm -f cropped.png