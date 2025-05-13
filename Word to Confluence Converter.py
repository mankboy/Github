import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import os
import re
import tempfile
import shutil
import sys # Import sys for platform check
import configparser # Although simple, let's use configparser for future proofing
import zipfile # For extracting images from docx files
import uuid # For generating unique filenames
import datetime # For timestamping
import pathlib # For path manipulations
import json # For storing file lists
import io # For BytesIO

# Try to import PIL but provide a fallback if not available
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL/Pillow not available. Using basic image extraction.")

__version__ = "0.1.5" # Application version (direct image extraction)
CONFIG_FILE = os.path.expanduser("~/.word_to_confluence_config.ini")

def load_last_directory():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        return config.get('Settings', 'last_directory', fallback=os.path.expanduser("~"))
    return os.path.expanduser("~")

def save_last_directory(dir_path):
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
    if 'Settings' not in config:
        config['Settings'] = {}
    config['Settings']['last_directory'] = dir_path
    try:
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
    except Exception as e:
        print(f"Warning: Could not save last directory: {e}")

def load_recent_files():
    """Load list of recently used files from config"""
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        if 'RecentFiles' in config and 'files' in config['RecentFiles']:
            try:
                # Deserialize the JSON string of file paths
                files_json = config['RecentFiles']['files']
                files_list = json.loads(files_json)
                # Filter to only existing files
                return [f for f in files_list if os.path.exists(f)]
            except Exception as e:
                print(f"Warning: Could not load recent files: {e}")
    return []

def save_recent_files(file_paths):
    """Save list of recently used files to config"""
    if not file_paths:
        return
        
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        
    if 'RecentFiles' not in config:
        config['RecentFiles'] = {}
        
    try:
        # Serialize the file paths as JSON
        config['RecentFiles']['files'] = json.dumps(file_paths)
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
    except Exception as e:
        print(f"Warning: Could not save recent files: {e}")

class WordToConfluenceGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Word to Confluence Converter")
        self.root.geometry("750x320")  # Increased height for recent files display

        # Variables
        self.input_file_display = tk.StringVar(value="No files selected")
        self.selected_files_tuple = ()
        self.output_file_path = None # To store the path of the output file
        self.recent_files = load_recent_files()  # Load recent files

        # GUI Elements
        tk.Label(root, text="Word to Confluence Converter", font=("Arial", 14)).pack(pady=10)

        # Input File Frame
        input_frame = tk.Frame(root)
        input_frame.pack(pady=5)
        tk.Label(input_frame, text="Input Word Document(s) (.docx):").pack(side=tk.LEFT, padx=5)
        tk.Entry(input_frame, textvariable=self.input_file_display, width=40, state='readonly').pack(side=tk.LEFT)
        tk.Button(input_frame, text="Browse", command=self.browse_input).pack(side=tk.LEFT, padx=5)

        # Recent Files Section (new)
        if self.recent_files:
            recent_frame = tk.Frame(root)
            recent_frame.pack(pady=5, fill=tk.X, padx=20)
            tk.Label(recent_frame, text="Recent Files:", font=("Arial", 10, "bold")).pack(anchor=tk.W)
            
            # Create a frame with fixed height for recent files list
            files_frame = tk.Frame(recent_frame)
            files_frame.pack(fill=tk.X, expand=True)
            
            # Display up to 3 most recent files with buttons to use them
            for i, file_path in enumerate(self.recent_files[:3]):
                file_frame = tk.Frame(files_frame)
                file_frame.pack(fill=tk.X, pady=2)
                
                # Truncate long paths for display
                display_path = file_path
                if len(display_path) > 50:
                    display_path = "..." + display_path[-47:]
                
                tk.Label(file_frame, text=display_path, anchor=tk.W).pack(side=tk.LEFT)
                tk.Button(file_frame, text="Use", 
                         command=lambda p=file_path: self.use_recent_file(p)).pack(side=tk.RIGHT)

        # Convert Button
        tk.Button(root, text="Convert", command=self.convert).pack(pady=10)

        # Status Frame
        status_frame = tk.Frame(root)
        status_frame.pack(pady=10, fill=tk.X, padx=20)
        self.status = tk.Label(status_frame, text="Ready", wraplength=450, justify=tk.LEFT)
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.show_file_button = tk.Button(status_frame, text="Show File", command=self.show_output_file, state=tk.DISABLED)
        self.show_file_button.pack(side=tk.RIGHT, padx=5)
        
        # --- Bottom Controls Frame ---
        bottom_frame = tk.Frame(root)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        # Quit Button (aligned left)
        quit_button = tk.Button(bottom_frame, text="Quit", command=root.destroy)
        quit_button.pack(side=tk.LEFT)

        # Version Label (aligned right)
        version_label = tk.Label(bottom_frame, text=f"Version: {__version__}", font=("Arial", 12)) # Increased font size
        version_label.pack(side=tk.RIGHT)

    def use_recent_file(self, file_path):
        """Set a recent file as the current selection"""
        if os.path.exists(file_path):
            self.selected_files_tuple = (file_path,)
            self.input_file_display.set(f"1 file(s) selected")
            self.status.config(text=f"Loaded recent file: {file_path}")
        else:
            self.status.config(text=f"Error: File no longer exists: {file_path}")
            # Remove this file from recent files
            if file_path in self.recent_files:
                self.recent_files.remove(file_path)
                save_recent_files(self.recent_files)

    def browse_input(self):
        # Start browsing from the last used directory
        initial_dir = load_last_directory()
        if not os.path.isdir(initial_dir):
             initial_dir = os.path.expanduser("~") # Fallback if saved dir is invalid
            
        # Allow multiple file selection
        file_paths = filedialog.askopenfilenames(
            title="Select Word Document(s)", # Updated title
            initialdir=initial_dir,
            filetypes=[("Word Documents", "*.docx")]
        )
        if file_paths: # Returns a tuple of paths
            self.selected_files_tuple = file_paths
            # Update display to show file count
            self.input_file_display.set(f"{len(file_paths)} file(s) selected") 
            save_last_directory(os.path.dirname(file_paths[0])) # Save directory of first selected file
            
            # Update recent files list (add these files to the start of the list)
            updated_recent = list(file_paths) + [f for f in self.recent_files if f not in file_paths]
            self.recent_files = updated_recent[:10]  # Keep at most 10 recent files
            save_recent_files(self.recent_files)
        else:
            # If user cancels, clear selection
            self.selected_files_tuple = ()
            self.input_file_display.set("No files selected")

    def convert(self):
        self.status.config(text="Processing...")
        self.show_file_button.config(state=tk.DISABLED) 
        self.output_file_path = None 
        try:
            # Validate input
            input_paths = self.selected_files_tuple
            if not input_paths:
                raise ValueError("Please select one or more .docx files")
            # Check if all are valid docx files and exist
            if not all(path.lower().endswith(".docx") and os.path.exists(path) for path in input_paths):
                 raise ValueError("Please ensure all selected files are valid existing .docx files")
            
            # Save directory of first file
            first_file_dir = os.path.dirname(input_paths[0])
            save_last_directory(first_file_dir) 

            # Create attachments folder for images
            attachments_dir = os.path.join(first_file_dir, "confluenceAttachments")
            os.makedirs(attachments_dir, exist_ok=True)
            self.status.config(text="Created attachments folder at: " + attachments_dir)
            self.root.update_idletasks()

            combined_markup = "" # Accumulate results here
            temp_dirs = [] # Keep track of temporary directories
            current_question_number = 1  # Start question numbering at 1
            
            # Track extracted images for linking
            extracted_images = []

            try:
                # First, directly extract media files from all documents
                for idx, input_path in enumerate(input_paths):
                    input_filename = os.path.basename(input_path)
                    self.status.config(text=f"Extracting media from {input_filename}...")
                    self.root.update_idletasks()
                    
                    # Extract media files directly
                    doc_images = self.extract_direct_media(input_path, attachments_dir)
                    if doc_images:
                        extracted_images.extend(doc_images)
                        self.status.config(text=f"Extracted {len(doc_images)} images from {input_filename}")
                    else:
                        self.status.config(text=f"No images found in {input_filename}")
                    self.root.update_idletasks()
                
                # Now process each document for conversion
                for idx, input_path in enumerate(input_paths):
                    input_filename = os.path.basename(input_path)
                    self.status.config(text=f"Processing file {idx+1}/{len(input_paths)}: {input_filename}")
                    self.root.update_idletasks() # Update GUI

                    # Create a temporary directory for this file
                    temp_dir = tempfile.mkdtemp()
                    temp_dirs.append(temp_dir)
                    temp_input_path = os.path.join(temp_dir, input_filename)
                    shutil.copy2(input_path, temp_input_path)

                    # Step 1: Convert Word to Wiki using Pandoc
                    temp_wiki_path = os.path.join(temp_dir, f"temp_{idx}.wiki")
                    subprocess.run(["pandoc", temp_input_path, "-t", "jira", "-o", temp_wiki_path], check=True)

                    # Step 2: Apply macro formatting - pass and retrieve the current question number
                    # Also pass extracted images for proper linking
                    file_markup, current_question_number = self.apply_expand_macro(
                        temp_wiki_path, 
                        current_question_number,
                        extracted_images
                    )
                    
                    # Append markup (ensure separation between file contents)
                    if combined_markup:
                         combined_markup += "\n\n" # Add separation if not the first file
                    combined_markup += file_markup

                # --- Processing finished, ask for save location --- 
                self.status.config(text="Processing complete. Select output file location.")
                self.root.update_idletasks()
                
                # Suggest a default filename
                first_input_name = os.path.splitext(os.path.basename(input_paths[0]))[0]
                default_output_name = f"wiki_{first_input_name}_combined.wiki"
                
                output_path = filedialog.asksaveasfilename(
                    title="Save Combined Wiki Markup As",
                    initialdir=os.path.dirname(input_paths[0]), # Start in same dir as input
                    initialfile=default_output_name,
                    defaultextension=".wiki",
                    filetypes=[("Wiki Markup", "*.wiki"), ("All Files", "*.*")]
                )

                if not output_path:
                    self.status.config(text="Save cancelled.")
                    return # Exit if user cancels save dialog

                # Write combined markup to the chosen file
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(combined_markup)

                # Create README in attachments folder
                if extracted_images:
                    readme_path = os.path.join(attachments_dir, "README.txt")
                    with open(readme_path, 'w', encoding='utf-8') as readme:
                        readme.write("IMPORTANT: These image files need to be uploaded to Confluence.\n\n")
                        readme.write("After uploading, the image references in the wiki markup will work correctly.\n\n")
                        readme.write("Images extracted from Word documents:\n")
                        for img in extracted_images:
                            readme.write(f"- {img['new_filename']} (from {img['source_doc']})\n")

                self.status.config(text=f"Success! Combined markup saved to {output_path}. Images in {attachments_dir}")
                self.root.bell() 
                self.output_file_path = output_path # Store single output path
                self.show_file_button.config(state=tk.NORMAL)

            except subprocess.CalledProcessError as e:
                # More robust error reporting
                err_msg = f"Pandoc conversion failed. Ensure Pandoc is installed and working correctly. Error: {e}"
                self.status.config(text=f"Error: {err_msg}")
                messagebox.showerror("Pandoc Error", err_msg)
            except FileNotFoundError as e:
                 err_msg = f"File not found during processing. Please check input files. Error: {e}"
                 self.status.config(text=f"Error: {err_msg}")
                 messagebox.showerror("File Error", err_msg)
            except Exception as e:
                # More robust generic error reporting
                err_msg = f"An error occurred during processing: {str(e)}"
                self.status.config(text=f"Error: {err_msg}")
                messagebox.showerror("Error", err_msg)
            finally:
                # Clean up all temporary directories
                for temp_dir in temp_dirs:
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)

        except ValueError as ve:
            # Handle validation errors (e.g., no files selected)
            self.status.config(text=f"Input Error: {str(ve)}")
            messagebox.showwarning("Input Error", str(ve))
        except Exception as e:
            # Handle unexpected errors
            self.status.config(text=f"Unexpected Error: {str(e)}")
            messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}")

    def extract_direct_media(self, docx_path, output_dir):
        """
        Extract ONLY the actual media files from the Word document.
        This direct approach bypasses any text content and focuses only on 
        actual embedded images in the word/media directory.
        """
        extracted_images = []
        try:
            docx_name = os.path.basename(docx_path)
            
            with zipfile.ZipFile(docx_path, 'r') as zip_ref:
                # Get ONLY files from the word/media directory which contains actual embedded images
                media_files = [f for f in zip_ref.namelist() if f.startswith('word/media/')]
                
                # Log what we found
                self.log_debug_info(
                    [f"Found {len(media_files)} media files in {docx_name}",
                     "Media files: " + ", ".join(media_files)], 
                    docx_name)
                
                if not media_files:
                    return []
                
                # Process each media file (these are the actual embedded images)
                for file_path in media_files:
                    try:
                        # Get file data
                        data = zip_ref.read(file_path)
                        file_size = len(data)
                        
                        # Skip files that are too small (likely icons, bullets, etc.)
                        if file_size < 2000:  # 2KB minimum
                            continue
                            
                        # Get file extension (or default to .png)
                        file_ext = os.path.splitext(file_path)[1].lower()
                        if not file_ext or file_ext not in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']:
                            # Try to determine the file type from content
                            if data[:8].startswith(b'\x89PNG\r\n\x1a\n'):
                                file_ext = '.png'
                            elif data[:3] == b'\xff\xd8\xff':
                                file_ext = '.jpg'
                            else:
                                file_ext = '.png'  # Default
                        
                        # Generate unique filename
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        unique_id = str(uuid.uuid4())[:8]
                        new_filename = f"img_{timestamp}_{unique_id}{file_ext}"
                        output_path = os.path.join(output_dir, new_filename)
                        
                        # Save the file
                        with open(output_path, 'wb') as f:
                            f.write(data)
                        
                        # Store information about this image
                        extracted_images.append({
                            'source_path': file_path,
                            'new_filename': new_filename,
                            'output_path': output_path,
                            'source_doc': docx_name,
                            'size': file_size
                        })
                    except Exception as e:
                        print(f"Error extracting {file_path}: {e}")
        
        except Exception as e:
            print(f"Error processing document {docx_path}: {e}")
            
        return extracted_images

    def apply_expand_macro(self, wiki_file_path, start_question_number=1, extracted_images=None):
        """Reads Confluence/Jira wiki markup, formats each question as a multi-line numbered list item (#),
           includes all parts, uses bold for 'Correct Answer', expands answers, and adds rule.
           Returns the formatted markup and the next question number to use."""
        if extracted_images is None:
            extracted_images = []
            
        with open(wiki_file_path, 'r', encoding='utf-8') as file:
            content = file.read()

        # Replace "Unknown Attachment" placeholders with Confluence image macros
        if extracted_images:
            content = self.replace_unknown_attachments(content, extracted_images)

        split_pattern = r'(\n*h1\.\s*(?:\{anchor:.*?\})?\s*Question\s*\d+(?:\s*of\s*\d+)?\s*\n)'
        question_blocks_with_delimiters = [block for block in re.split(split_pattern, content, flags=re.IGNORECASE) if block and block.strip()]

        processed_question_blocks = [] # Store processed multiline strings for each question
        content_before_first_question = ""
        question_number = start_question_number # Use the provided starting number

        if question_blocks_with_delimiters and not re.match(split_pattern.strip('()'), question_blocks_with_delimiters[0], flags=re.IGNORECASE):
            content_before_first_question = question_blocks_with_delimiters.pop(0).strip()

        for block_content in question_blocks_with_delimiters:
            if re.match(split_pattern.strip('()'), block_content, flags=re.IGNORECASE):
                continue
                
            redundant_question_marker = r"^h2\.\s*(?:\{anchor:question(?:-\d+)?\})?\s*Question\s*$\n?"
            current_block_text = re.sub(redundant_question_marker, "", block_content, count=1, flags=re.MULTILINE | re.IGNORECASE).strip()
            
            options_marker_regex = r"(^h2\.\s*(?:\{anchor:options(?:-\d+)?\})?\s*Options\s*$\n?)"
            # Find the start line of the Correct Answer section (might be h2 or bold)
            answer_start_locator_regex = r"^(?:h\d\.|\*)\s*(?:\{anchor:correct-answer(?:-\d+)?\})?\s*(?:\n)?Correct Answer\s*$\n?"
            
            question_text = ""
            options_section = ""
            answer_content = ""

            options_match = re.search(options_marker_regex, current_block_text, re.MULTILINE | re.IGNORECASE)
            answer_start_match = re.search(answer_start_locator_regex, current_block_text, re.MULTILINE | re.IGNORECASE)

            if options_match:
                question_text = current_block_text[:options_match.start()].strip()
                if answer_start_match:
                    options_section = current_block_text[options_match.start():answer_start_match.start()].strip()
                    answer_content = current_block_text[answer_start_match.end():].strip()
                else:
                    options_section = current_block_text[options_match.start():].strip()
            elif answer_start_match:
                 question_text = current_block_text[:answer_start_match.start()].strip()
                 answer_content = current_block_text[answer_start_match.end():].strip()
            else:
                 question_text = current_block_text 

            # --- Build the output with the correct heading format --- 
            output_lines_for_item = []
            
            # Question in h2 format
            output_lines_for_item.append(f"h2. {question_number}. Question")
            if question_text:
                output_lines_for_item.append(question_text)
            
            if options_section:
                # Extremely aggressive filtering to remove all "Options" headers and text
                # First, remove any line that has only the word "Options" on it (with optional whitespace)
                options_section = re.sub(r'(?m)^\s*Options\s*$', '', options_section)
                
                # Then remove any Options headers (any heading level)
                options_section = re.sub(r'(?m)^h\d\.\s*(?:\{anchor:options(?:-\d+)?\})?\s*Options\s*$', '', options_section)
                
                # Process what's left line by line
                options_lines = options_section.splitlines()
                options_content = []
                
                # Skip any lines until we find one that starts with "A."
                found_first_option = False
                for line in options_lines:
                    # If we already found an option or this line looks like an option (A., B., etc.)
                    if found_first_option or re.match(r'^\s*[A-Z]\.\s', line):
                        found_first_option = True
                        options_content.append(line)
                
                # Options in h3 format
                output_lines_for_item.append(f"h3. {question_number}.1. Options")
                if options_content:
                    # Join the filtered options content
                    output_lines_for_item.append("\n".join(options_content))
            
            # Correct Answer in h3 format
            output_lines_for_item.append(f"h3. {question_number}.2. Correct Answer")
            
            # Add the expand macro start
            output_lines_for_item.append("{expand:title=Click here to expand}")
            
            # Add answer content
            if answer_content:
                output_lines_for_item.append(answer_content)
            
            # Add the expand macro end
            output_lines_for_item.append("{expand}")
            
            # Add the horizontal rule
            output_lines_for_item.append("----")
            
            # Join the lines for this question with appropriate spacing
            processed_question_blocks.append("\n\n".join(output_lines_for_item))
            
            # Increment question number for the next question
            question_number += 1

        # --- Combine processed parts --- 
        final_output = ""
        if content_before_first_question:
            final_output += content_before_first_question + "\n\n"
            
        # Join the fully processed blocks for each question
        if processed_question_blocks:
            final_output += "\n\n".join(processed_question_blocks)

        # Return both the formatted content and the next question number to use
        return final_output.strip(), question_number
        
    def replace_unknown_attachments(self, content, extracted_images):
        """
        Replace 'Unknown Attachment' occurrences with Confluence image macros
        """
        if not extracted_images:
            return content
            
        # Find patterns for image placeholders
        placeholder_patterns = [
            r'\?\s*Unknown\s+Attachment',  # Main pattern from screenshot
            r'!\[\]\([^)]*\)',             # Markdown image syntax
            r'<img[^>]*>',                 # HTML image syntax
            r'\{attachment:[^}]*\}',       # Confluence attachment syntax
            r'!\s*$\n^\s*!',               # Jira image syntax (multiline)
            r'!\s*\(image\)',              # Another Jira image pattern
        ]
        
        # Find placeholder positions in content
        placeholders = []
        for pattern in placeholder_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE):
                placeholders.append((match.start(), match.end(), match.group(0)))
        
        # Sort placeholders by position in the content
        placeholders.sort(key=lambda x: x[0])
        
        # If we have placeholders and images, replace them
        if placeholders and extracted_images:
            self.status.config(text=f"Found {len(placeholders)} image placeholders and {len(extracted_images)} extracted images")
            self.root.update_idletasks()
            
            # Create a new content string with replacements
            new_content = ""
            last_pos = 0
            
            # Match each placeholder with an image
            for i, (start, end, placeholder) in enumerate(placeholders):
                if i < len(extracted_images):
                    # Add content up to the placeholder
                    new_content += content[last_pos:start]
                    
                    # Add the image reference
                    image_info = extracted_images[i]
                    image_macro = f"!{image_info['new_filename']}!"
                    new_content += image_macro
                    
                    # Update last position
                    last_pos = end
            
            # Add any remaining content
            new_content += content[last_pos:]
            return new_content
        
        return content

    def show_output_file(self):
        if self.output_file_path and os.path.exists(self.output_file_path):
            output_dir = os.path.dirname(self.output_file_path)
            if sys.platform == "win32":
                try:
                     # Try opening the file first
                     os.startfile(self.output_file_path)
                except Exception:
                     # Fallback to opening directory
                     os.startfile(output_dir)
            elif sys.platform == "darwin":  # macOS
                try:
                    # Use 'open -a TextEdit' to open the specific file with TextEdit
                    subprocess.call(["open", "-a", "TextEdit", self.output_file_path])
                except Exception as e:
                    messagebox.showerror("Error", f"Could not open file with TextEdit: {e}\nOpening containing folder instead.")
                    subprocess.call(["open", output_dir]) # Fallback to opening directory
            else:  # Linux
                try:
                     # Use xdg-open which is standard for opening files/dirs
                    subprocess.call(["xdg-open", self.output_file_path])
                except Exception as e:
                     messagebox.showerror("Error", f"Could not open file: {e}\nOpening containing folder instead.")
                     subprocess.call(["xdg-open", output_dir]) # Fallback to opening directory
        else:
            messagebox.showinfo("Info", "No output file generated or found.")

if __name__ == "__main__":
    root = tk.Tk()
    app = WordToConfluenceGUI(root)
    
    # Start iconified, then de-iconify and raise after a short delay
    root.iconify() # Start minimized
    # Schedule popup after 200ms
    root.after(200, lambda: (root.deiconify(), root.lift(), root.focus_force())) 

    root.mainloop()