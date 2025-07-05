import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from PIL import Image, ImageOps # Added ImageOps for potential padding
import pytesseract
from datetime import datetime
import subprocess
import re
from db_operations import OCRDatabase # Added for database operations
import textwrap
import sys
import functools
# --- Import AnythingLLM document fetcher for RAG enforcement ---
from getfilelist import fetch_documents, BASE_URL, API_KEY

# --- Configuration (User might need to set this) ---
# Example: pytesseract.pytesseract.tesseract_cmd = r'/opt/homebrew/bin/tesseract'

CONFIG_FILE = os.path.expanduser("~/.lmstudio_ocr_config.json")

def save_config(config_data):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f)
    except Exception as e:
        print(f"Warning: Could not save configuration: {str(e)}")

def load_config():
    """Load configuration from JSON file"""
    default_config = {"last_folder": os.path.expanduser("~")}
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        # Ensure 'last_folder' key exists, provide default if not
        if 'last_folder' not in config or not config['last_folder']:
            config['last_folder'] = os.path.expanduser("~")
        return config
    except (FileNotFoundError, json.JSONDecodeError):
        return default_config

import requests
import time
import threading
from TextRedirector import TextRedirector

class OCRApp:
    def query_lms_batch_with_tab_switch(self):
        """Switch to Logging tab, then run the batch query in a background thread (ensures UI updates instantly)."""
        self.notebook.select(self.logging_tab)
        self.master.update_idletasks()
        t = threading.Thread(target=self.query_lms_batch_worker)
        t.daemon = True
        t.start()

    def query_lms_batch(self):
        # Deprecated: all logic now in query_lms_batch_worker (threaded)
        pass

    def query_lms_batch_worker(self):
        import traceback
        import sys
        # Redirect stdout/stderr in this thread to the Logging tab
        sys.stdout = self.stdout_redirector
        sys.stderr = self.stderr_redirector
        def safe_gui_call(func, *args, **kwargs):
            self.master.after(0, lambda: func(*args, **kwargs))

        print(f"[DEBUG] sys.stdout in worker: {type(sys.stdout)} {repr(sys.stdout)}", flush=True)
        safe_gui_call(self.query_lms_button.config, state=tk.DISABLED)
        selection = self.questions_listbox.curselection()
        if not selection:
            safe_gui_call(messagebox.showinfo, "Query LMS", "Please select one or more questions to query.")
            safe_gui_call(self.query_lms_button.config, state=tk.NORMAL)
            return
        selected_indices = list(selection)
        questions = [self.question_data[i] for i in selected_indices if 0 <= i < len(self.question_data)]
        print(f"[BATCH] Query LMS batch started at {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        print(f"[BATCH] Selected indices: {selected_indices}", flush=True)
        print(f"[BATCH] Selected question IDs: {[q['id'] for q in questions]}", flush=True)
        if not questions:
            safe_gui_call(messagebox.showinfo, "Query LMS", "No valid questions selected.")
            safe_gui_call(self.query_lms_button.config, state=tk.NORMAL)
            return
        safe_gui_call(self.log_status, f"Querying LMS for {len(questions)} selected question(s)...")
        # --- Limit queries to available RAG documents ---
        try:
            documents = fetch_documents(BASE_URL, API_KEY)
            available_doc_ids = [doc.get('id') for doc in documents if doc.get('id')]
            print(f"[RAG] Limiting queries to available document IDs: {available_doc_ids}", flush=True)
        except Exception as e:
            print(f"[RAG] Failed to fetch available RAG documents: {e}", flush=True)
            available_doc_ids = []

        for idx, q in enumerate(questions, 1):
            qid = q['id']
            qtext = q['question_text']
            print(f"[API] ({idx}/{len(questions)}) Starting LLM query for question id={qid}", flush=True)
            if self.db.has_llm_results(qid):
                print(f"[API] ({idx}/{len(questions)}) Skipping question id={qid} (already has LLM results)", flush=True)
                safe_gui_call(self.log_status, f"[{idx}/{len(questions)}] Skipping question id={qid} (already has LLM results)")
                continue
            options = self.db.get_options_for_question(qid)
            if not options:
                print(f"[API] ({idx}/{len(questions)}) Skipping question id={qid} (no options found)", flush=True)
                safe_gui_call(self.log_status, f"[{idx}/{len(questions)}] Skipping question id={qid} (no options found)")
                continue
            prompt = self._build_llm_prompt(qtext, options)
            print(f"[PROMPT] Prompt for question id={qid} (idx={idx}):\n{prompt}", flush=True)
            payload = {
                "model": "gemma-3-12b-instruct",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "document_ids": available_doc_ids
            }
            print(f"[HTTP] Sending payload for question id={qid}: {json.dumps(payload, indent=2)}", flush=True)
            try:
                start_time = time.time()
                headers = {"Authorization": "Bearer P5G5T5W-8914F8J-M9B40WZ-SH08PNA"}
                resp = requests.post(
                    url = "http://127.0.0.1:8000/v1/openai/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=60
                )
                elapsed = time.time() - start_time
                print(f"[HTTP] Response status: {resp.status_code} in {elapsed:.2f}s", flush=True)
                resp.raise_for_status()
                print(f"[HTTP] Raw response text: {resp.text}", flush=True)
                try:
                    data = resp.json()
                    print(f"[HTTP] Decoded JSON: {json.dumps(data, indent=2)}", flush=True)
                    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                    if not content:
                        print(f"[API] ({idx}/{len(questions)}) LLM response missing content.", flush=True)
                        safe_gui_call(self.log_status, f"[{idx}/{len(questions)}] LLM response missing content.")
                    else:
                        print(f"[API] ({idx}/{len(questions)}) LLM response content: {content}", flush=True)
                        try:
                            answer, justification, explanations, references = self._parse_llm_response(data)
                            print(f"[DB] Updating DB for question id={qid}", flush=True)
                            self.db.update_llm_results(qid, answer, justification, explanations, references)
                            self.question_data[idx-1]['llm_answer'] = answer
                            self.question_data[idx-1]['llm_justification'] = justification
                            self.question_data[idx-1]['llm_explanations'] = explanations
                            for i, ref in enumerate(references):
                                self.question_data[idx-1][f'src{i+1}_filename'] = ref.get('filename', '')
                                self.question_data[idx-1][f'src{i+1}_section'] = ref.get('section', '')
                                self.question_data[idx-1][f'src{i+1}_page'] = ref.get('page', '')
                            self.question_data[idx-1]['llm_references'] = references
                            safe_gui_call(self.log_status, f"[{idx}/{len(questions)}] LLM results stored for question id={qid}")
                        except Exception as e:
                            print(f"[API] ({idx}/{len(questions)}) FAILED to parse LLM response for question id={qid}: {e}\n{traceback.format_exc()}", flush=True)
                            safe_gui_call(self.log_status, f"[{idx}/{len(questions)}] LLM response parsing failed for id={qid}: {e}")
                except Exception as json_e:
                    print(f"[API] ({idx}/{len(questions)}) JSON decode or response parse error: {json_e}", flush=True)
                    print(f"[API] ({idx}/{len(questions)}) Raw response text for debugging: {resp.text}", flush=True)
                    safe_gui_call(self.log_status, f"[{idx}/{len(questions)}] JSON decode or response parse error: {json_e}")
            except Exception as e:
                print(f"[API] ({idx}/{len(questions)}) FAILED for question id={qid}: {e}", flush=True)
                safe_gui_call(self.log_status, f"[{idx}/{len(questions)}] FAILED for question id={qid}: {e}")
            time.sleep(1)
        safe_gui_call(messagebox.showinfo, "Query LMS", f"LLM processing complete. {len(questions)} question(s) processed.")
        print(f"[BATCH] Query LMS batch finished at {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        safe_gui_call(self.query_lms_button.config, state=tk.NORMAL)
        safe_gui_call(self.refresh_questions_list)
        # Reload question_data and refresh details pane so UI shows latest LLM results
        self.question_data = self.db.get_all_questions()
        selection = self.questions_listbox.curselection()
        if selection:
            safe_gui_call(self.on_question_select, None)

    def _build_llm_prompt(self, question_text, options):
        prompt = f"Given the following multiple choice question, provide the correct answer, a detailed justification for the correct answer, and an explanation for why each incorrect option is incorrect.\n\nQuestion: {question_text}\n"
        for opt in options:
            prompt += f"{opt['letter']}: {opt['text']}\n"
        prompt += (
            "\nFormat your response as:\n"
            "Answer: <letter>\n"
            "Justification: <text>\n"
            "Explanations:\nA: <reason>\nB: <reason>\nC: <reason>\nD: <reason>\n"
            "Source References (up to 3):\n"
            "1. Document Name: <name>; Section: <section>; Page: <number>\n"
            "2. Document Name: <name>; Section: <section>; Page: <number>\n"
            "3. Document Name: <name>; Section: <section>; Page: <number>\n"
        )
        return prompt

    def _parse_llm_response(self, response_json):
        # Try to extract answer, justification, explanations from LLM response
        content = response_json.get('choices', [{}])[0].get('message', {}).get('content', '')
        print("\n=== FULL LLM RESPONSE CONTENT ===\n" + content + "\n===============================\n")
        answer, justification, explanations = '', '', ''
        import re
        answer_match = re.search(r'Answer:\s*([A-D])', content)
        if answer_match:
            answer = answer_match.group(1)
        justification_match = re.search(r'Justification:(.*?)(?:Explanations:|A:|B:|C:|D:|$)', content, re.DOTALL)
        if justification_match:
            justification = justification_match.group(1).strip()
        explanations_match = re.search(r'Explanations:(.*?)(?:Source References:|$)', content, re.DOTALL)
        if explanations_match:
            explanations = explanations_match.group(1).strip()
        # Extract up to 3 source references
        references = []
        ref_pattern = re.compile(r'(?:^|\n)\s*\d+\. Document Name:\s*(.*?);\s*Section:\s*(.*?);\s*Page:\s*(.*?)(?:\n|$)', re.MULTILINE)
        for match in ref_pattern.finditer(content):
            doc_name, section, page = match.group(1).strip(), match.group(2).strip(), match.group(3).strip()
            references.append({'filename': doc_name, 'section': section, 'page': page})
        while len(references) < 3:
            references.append({'filename': '', 'section': '', 'page': ''})
        return answer, justification, explanations, references

    def on_question_select(self, event):
        selection = self.questions_listbox.curselection()
        if not selection:
            return
        # Show details for the first selected question
        index = selection[0]
        if index < 0 or index >= len(self.question_data):
            return
        question = self.question_data[index]
        question_id = question['id']
        # Get current question text and options
        current_question_text = question['question_text']
        current_options = self.db.get_options_for_question(question_id)
        # Display question text and options
        self.question_text_var.set(current_question_text)
        self.options_text.delete(1.0, tk.END)
        for opt in current_options:
            self.options_text.insert(tk.END, f"{opt['letter']}: {opt['text']}\n")
        # Display LLM results if present
        if 'llm_answer' in question:
            self.llm_answer_var.set(question['llm_answer'])
            self.llm_justification_text.delete(1.0, tk.END)
            self.llm_justification_text.insert(tk.END, question['llm_justification'])
            self.llm_explanations_text.delete(1.0, tk.END)
            self.llm_explanations_text.insert(tk.END, question['llm_explanations'])

        # --- Prepare details_text content ---
        self.details_text.delete(1.0, tk.END)
        # (Insert any other details you want at the top here)
        # ...

        # Insert LLM answer, justification, explanations first
        self.details_text.insert(tk.END, f"Answer: {question.get('llm_answer', '')}\n")
        self.details_text.insert(tk.END, f"Justification: {question.get('llm_justification', '')}\n")
        self.details_text.insert(tk.END, f"Explanations:\n{question.get('llm_explanations', '')}\n")

        # Now insert source references block
        references = question.get('llm_references')
        if not references:
            # Fallback to legacy fields if needed
            references = []
            for i in range(1, 4):
                src_filename = question.get(f'src{i}_filename', '')
                src_section = question.get(f'src{i}_section', '')
                src_page = question.get(f'src{i}_page', '')
                if src_filename or src_section or src_page:
                    references.append({'filename': src_filename, 'section': src_section, 'page': src_page})
        # Filter references to only those mentioning 'sacomm'
        sacomm_refs = [
            ref for ref in references
            if any('sacomm' in (str(ref.get(field, '')).lower()) for field in ['filename', 'section', 'page'])
        ]
        if sacomm_refs:
            self.details_text.insert(tk.END, "\nSource References (sacomm workspace):\n")
            for idx, ref in enumerate(sacomm_refs, 1):
                self.details_text.insert(
                    tk.END,
                    f"  {idx}. Document Name: {ref['filename']}\n     Section: {ref['section']}\n     Page: {ref['page']}\n"
                )
        else:
            self.details_text.insert(tk.END, "\nNo sacomm workspace references found.\n")

        # Insert source file links and other details (existing logic for hyperlinks etc.)
        # (Assume this code follows here, unchanged)


    def delete_llm_info(self):
        """Clear LLM answer, justification, explanations, and source references for all selected questions."""
        selection = self.questions_listbox.curselection()
        if not selection:
            messagebox.showinfo("Delete LLM Info", "Please select one or more questions to clear LLM info.")
            return
        for index in selection:
            if index < 0 or index >= len(self.question_data):
                continue
            question = self.question_data[index]
            question_id = question['id']
            # Clear in database
            self.db.update_llm_results(
                question_id,
                answer='',
                justification='',
                explanations='',
                references=[{'filename':'','section':'','page':''} for _ in range(3)]
            )
            # Clear in local data
            question['llm_answer'] = ''
            question['llm_justification'] = ''
            question['llm_explanations'] = ''
            question['llm_references'] = [
                {'filename': '', 'section': '', 'page': ''},
                {'filename': '', 'section': '', 'page': ''},
                {'filename': '', 'section': '', 'page': ''}
            ]
            for i in range(1, 4):
                question[f'src{i}_filename'] = ''
                question[f'src{i}_section'] = ''
                question[f'src{i}_page'] = ''
        # Refresh details for the first selected question
        self.on_question_select(None)
        messagebox.showinfo("Delete LLM Info", "LLM info cleared for all selected questions.")

    def preview_file(self, filepath):
        """Open the given file with the system's default application, searching input folder if needed."""
        # Try as absolute or relative path first
        if not os.path.isfile(filepath):
            # Try to find in the last used input folder
            input_folder = self.input_folder_path.get()
            candidate = os.path.join(input_folder, filepath)
            if os.path.isfile(candidate):
                filepath = candidate
            else:
                messagebox.showerror("File Not Found", f"The file {filepath} does not exist.")
                return
        try:
            if sys.platform.startswith('darwin'):
                subprocess.call(('open', filepath))
            elif os.name == 'nt':
                os.startfile(filepath)
            elif os.name == 'posix':
                subprocess.call(('xdg-open', filepath))
            else:
                messagebox.showerror("Error", f"Don't know how to open files on this platform: {sys.platform}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file:\n{filepath}\n\n{e}")
    def _maximize_window(self):
        print("Maximizing window...")  # Debug
        try:
            print("Trying attributes('-zoomed', True)")
            self.master.attributes('-zoomed', True)
        except Exception as e:
            print(f"attributes('-zoomed', True) failed: {e}")
            try:
                print("Trying wm_attributes('-zoomed', True)")
                self.master.wm_attributes('-zoomed', True)
            except Exception as e2:
                print(f"wm_attributes('-zoomed', True) failed: {e2}")
                try:
                    print("Trying state('zoomed')")
                    self.master.state('zoomed')
                except Exception as e3:
                    print(f"state('zoomed') failed: {e3}")

    def _on_tab_changed(self, event):
        tab = event.widget.tab(event.widget.select(), "text")
        print(f"TAB CHANGED: {tab}")  # Debug
        print(f"self.master type: {type(self.master)} repr: {repr(self.master)}")  # Debug
        print(f"notebook tabs: {self.notebook.tabs()}")  # Debug
        print(f"selected tab index: {self.notebook.index(self.notebook.select())}")  # Debug
        if tab == 'Database Records':
            self._maximize_window()
            self.refresh_questions_list()

    def _select_first_question(self):
        if self.questions_listbox.size() > 0:
            self.questions_listbox.selection_clear(0, tk.END)
            self.questions_listbox.selection_set(0)
            self.questions_listbox.activate(0)
            # Generate the <<ListboxSelect>> event so the detail window updates
            self.questions_listbox.event_generate('<<ListboxSelect>>')

    def __init__(self, master):
        self.master = master
        master.title("LMStudio OCR Processor")
        master.geometry("800x600")

        # Initialize database
        self.db = OCRDatabase()
        
        # Create main frame with padding
        self.main_frame = ttk.Frame(master, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create tabs
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        self.ocr_tab = ttk.Frame(self.notebook)
        self.db_tab = ttk.Frame(self.notebook)
        self.logging_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.ocr_tab, text='OCR Processing')
        self.notebook.add(self.db_tab, text='Database Records')
        self.notebook.add(self.logging_tab, text='Logging')
        
        # Create folder selection widgets in OCR tab
        self.input_folder_path = tk.StringVar()
        self.create_folder_selection_widgets()
        
        # Create the log text widget
        self.create_log_widget()
        # Redirect stdout/stderr to the Logging tab for all threads
        self.stdout_redirector = TextRedirector(self.log_text, "stdout")
        self.stderr_redirector = TextRedirector(self.log_text, "stderr")
        sys.stdout = self.stdout_redirector
        sys.stderr = self.stderr_redirector

        
        # Create the start button
        self.create_start_button()
        
        # Create database viewer
        self.create_db_viewer()
        
        # Load last used folder
        config = load_config()
        self.input_folder_path.set(config.get("last_folder", os.path.expanduser("~"))) # Use .get for safety

    def refresh_questions_list(self):
        self.questions_listbox.delete(0, tk.END)
        self.question_data = self.db.get_all_questions()
        for i, question in enumerate(self.question_data):
            display_text = textwrap.shorten(question['question_text'], width=80, placeholder="...")
            self.questions_listbox.insert(tk.END, f"{i+1}. {display_text}")
        # Always auto-select first question after refresh
        if self.questions_listbox.size() > 0:
            self.questions_listbox.selection_clear(0, tk.END)
            self.questions_listbox.selection_set(0)
            self.questions_listbox.activate(0)
            self.questions_listbox.event_generate('<<ListboxSelect>>')


    def edit_selected_question(self):
        selection = self.questions_listbox.curselection()
        if not selection:
            messagebox.showinfo("Information", "Please select a question to edit.")
            return
        index = selection[0]
        if index < 0 or index >= len(self.question_data):
            return
        question = self.question_data[index]
        question_id = question['id']
        # Get current question text and options
        current_question_text = question['question_text']
        current_options = self.db.get_options_for_question(question_id)
        # Create popup window
        edit_win = tk.Toplevel(self.master)
        edit_win.title("Edit Question and Options")
        edit_win.transient(self.master)
        edit_win.grab_set()
        tk.Label(edit_win, text="Question Text:").pack(anchor="w", padx=10, pady=(10, 0))
        q_text_var = tk.Text(edit_win, width=60, height=4)
        q_text_var.pack(fill=tk.X, padx=10)
        q_text_var.insert(tk.END, current_question_text)
        option_vars = []
        option_labels = ['A', 'B', 'C', 'D']
        filled_options = [opt['text'] for opt in current_options[:4]]
        filled_options += [''] * (4 - len(filled_options))
        for i in range(4):
            tk.Label(edit_win, text=f"Option {option_labels[i]}:").pack(anchor="w", padx=10, pady=(10 if i==0 else 5, 0))
            opt_var = tk.Entry(edit_win, width=60)
            opt_var.pack(fill=tk.X, padx=10)
            opt_var.insert(0, filled_options[i])
            option_vars.append(opt_var)

        def save_edits():
            new_qtext = q_text_var.get("1.0", tk.END).strip()
            new_opts = [v.get().strip() for v in option_vars]
            if not new_qtext or any(not o for o in new_opts):
                messagebox.showerror("Error", "Question and all options must be filled.", parent=edit_win)
                return
            success = self.db.update_question_and_options(question_id, new_qtext, new_opts)
            if success:
                messagebox.showinfo("Success", "Question and options updated.", parent=edit_win)
                edit_win.destroy()
                self.refresh_questions_list()
                # Optionally, reselect the edited item
                self.questions_listbox.selection_clear(0, tk.END)
                self.questions_listbox.selection_set(index)
                self.questions_listbox.activate(index)
                self.on_question_select(None)
            else:
                messagebox.showerror("Error", "Failed to update the question.", parent=edit_win)
        btn_frame = tk.Frame(edit_win)
        btn_frame.pack(fill=tk.X, pady=10)
        tk.Button(btn_frame, text="Save", command=save_edits).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Cancel", command=edit_win.destroy).pack(side=tk.LEFT, padx=10)

        # Initialize database
        self.db = OCRDatabase()
        
        # Create main frame with padding
        self.main_frame = ttk.Frame(master, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create tabs
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        self.ocr_tab = ttk.Frame(self.notebook)
        self.db_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.ocr_tab, text='OCR Processing')
        self.notebook.add(self.db_tab, text='Database Records')
        
        # Create folder selection widgets in OCR tab
        self.input_folder_path = tk.StringVar()
        self.create_folder_selection_widgets()
        
        # Create the log text widget
        self.create_log_widget()
        
        # Create the start button
        self.create_start_button()
        
        # Create database viewer
        self.create_db_viewer()
        
        # Load last used folder
        config = load_config()
        self.input_folder_path.set(config.get("last_folder", os.path.expanduser("~"))) # Use .get for safety

    def log_status(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END) # Scroll to the end
        self.master.update_idletasks() # Ensure GUI updates

    def create_folder_selection_widgets(self):
        folder_frame = ttk.Frame(self.ocr_tab, padding="5")
        folder_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(folder_frame, text="Input Folder:").pack(side=tk.LEFT, padx=5, pady=5)
        self.folder_entry = ttk.Entry(folder_frame, textvariable=self.input_folder_path, width=60)
        self.folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        browse_button = ttk.Button(folder_frame, text="Browse...", command=self.browse_input_folder)
        browse_button.pack(side=tk.LEFT, padx=5, pady=5)

    def create_log_widget(self):
        log_frame = ttk.LabelFrame(self.logging_tab, text="Terminal Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, width=70, height=15, state=tk.NORMAL)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text['yscrollcommand'] = log_scrollbar.set

    def create_start_button(self):
        start_button = ttk.Button(self.ocr_tab, text="Start OCR Process", command=self.start_ocr_processing)
        start_button.pack(fill=tk.X, padx=10, pady=10)

    def browse_input_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.input_folder_path.set(folder_selected)
            self.log_status(f"Input folder selected: {folder_selected}")
            config = load_config()
            config["last_folder"] = folder_selected
            save_config(config)

    def preprocess_image_for_ocr(self, image_path):
        img = Image.open(image_path)
        # Convert to grayscale
        gray_img = img.convert('L')
        # Optional: Add padding
        # padded_img = ImageOps.expand(gray_img, border=20, fill='white')
        # Optional: Binarization (simple threshold)
        # threshold_img = padded_img.point(lambda p: p > 180 and 255)
        # return threshold_img
        return gray_img # For now, just grayscale

    def extract_text_from_image(self, image_path):
        try:
            self.log_status(f"Processing: {os.path.basename(image_path)}")
            preprocessed_img = self.preprocess_image_for_ocr(image_path)
            # Using PSM 6 for assuming a single uniform block of text.
            # PSM 3 (auto) or PSM 11 (sparse text) might also be good depending on image variability.
            custom_config = r'--oem 3 --psm 6 -c preserve_interword_spaces=1'
            text = pytesseract.image_to_string(preprocessed_img, config=custom_config)
            return text
        except Exception as e:
            self.log_status(f"Error processing {os.path.basename(image_path)}: {e}")
            return ""

    def parse_ocr_text(self, raw_text, image_filename):
        lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
        if not lines:
            return f"--- Source Image: {image_filename} ---\nNo text found.\n\n"
            
        # Debug: Print exact raw lines
        print(f"\nDEBUG RAW LINES for {image_filename}:")
        for i, line in enumerate(lines):
            print(f"Line {i}: '{line}'")

        # Step 1: Find and assemble the complete question text
        question_text = ""
        question_index = 0
        options_start_index = 1

        # Patterns for question identification
        question_prefix_pattern = re.compile(r"^\s*(?:[{(]\s*)?Question\s*\d*:(.*)$", re.IGNORECASE)
        implicit_question_pattern = re.compile(r"^(Which|What|How|Why|When|Where|Is|Are|If|Using|Initially|A router|An LSP).*\??$", re.IGNORECASE)
        
        # More permissive option patterns
        option_start_pattern = re.compile(r"^(?:Option\s+[A-D]:|[O0QC©o]\s+)[A-Za-z0-9]|^[O\(\)\[\]\*•◦○⦿⬤□■]*\s*0x[0-9a-fA-F]+$|^\d+\s*Gbps$")
        hex_value_pattern = re.compile(r".*0x[0-9a-fA-F]+.*")
        number_with_units_pattern = re.compile(r"^\d+\s*Gbps$")

        # Find the start of the question
        for i, line in enumerate(lines):
            prefix_match = question_prefix_pattern.match(line)
            if prefix_match:
                rest_of_line = prefix_match.group(1).strip()
                if rest_of_line:  
                    question_text = rest_of_line
                    options_start_index = i + 1
                elif i + 1 < len(lines):  
                    next_line = lines[i + 1].strip()
                    next_line = re.sub(r"^Option\s+A:\s*", "", next_line, flags=re.IGNORECASE)
                    question_text = next_line
                    options_start_index = i + 2
                question_index = i
                break
            elif implicit_question_pattern.match(line):
                question_text = line
                question_index = i
                options_start_index = i + 1
                break

        # If no explicit question found, use first line
        if not question_text and lines:
            question_text = lines[0]
            options_start_index = 1

        # Continue assembling multi-line question until we hit an option
        while options_start_index < len(lines):
            line = lines[options_start_index].strip()
            if option_start_pattern.match(line) or "Option A:" in line:
                break
            question_text += " " + line
            options_start_index += 1

        # Step 2: Process options (maximum 4: A, B, C, D)
        current_option = ""
        options = []
        
        for line in lines[options_start_index:]:
            if "beta share feedback" in line.lower():
                continue

            # Clean the line while preserving hex numbers and numbers with units
            stripped_line = line.strip()
            hex_match = re.search(r'(0x[0-9a-fA-F]+)', stripped_line)
            gbps_match = re.search(r'(\d+\s*Gbps)', stripped_line)
            
            if hex_match:
                # Extract just the hex value
                cleaned_line = hex_match.group(1)
                print(f"DEBUG: Found hex value: {cleaned_line} in '{stripped_line}'")
            elif gbps_match:
                # Extract just the Gbps value
                cleaned_line = gbps_match.group(1)
                print(f"DEBUG: Found Gbps value: {cleaned_line} in '{stripped_line}'")
            else:
                # Remove radio buttons, option markers, and copyright symbols
                cleaned_line = re.sub(r"^[O0QC©o○□⦿⬤•◦\(\)]\s*|^[O0QC©o](?=[A-Z])|^Option\s+[A-Z]:\s*|\s*©\s*$", "", 
                                    stripped_line, flags=re.IGNORECASE).strip()

            # Skip if this matches the question text
            if cleaned_line.lower() == question_text.lower():
                continue

            # If this looks like a new option, hex number, or number with units
            is_valid_option = (option_start_pattern.match(line) or 
                             hex_value_pattern.search(line.strip()) or 
                             re.match(r'^\d+\s*Gbps$', line.strip()) or
                             # Radio button with any text
                             re.match(r'[○⦿⬤•◦\(\)O]\s*\w+', line.strip()))
            
            print(f"DEBUG: Line '{line.strip()}' valid option? {is_valid_option}")
            if is_valid_option or len(options) == 0:
                if current_option:  # Save previous option if it exists
                    options.append(current_option)
                    if len(options) >= 4:  # Maximum 4 options
                        break
                current_option = cleaned_line
            else:  # This is a continuation of the current option
                current_option += " " + cleaned_line

        # Add the last option if it exists
        if current_option and len(current_option) > 3 and len(options) < 4:
            options.append(current_option)

        # Store in database
        try:
            question_hash = self.db.store_question(question_text.strip(), options[:4], image_filename)
            # Just store to DB, don't log every hash to reduce log clutter
        except Exception as e:
            print(f"Database error: {e}")  # Print to console but don't disturb UI workflow

        # Format output
        formatted_text = f"--- Source Image: {image_filename} ---\n{question_text.strip()}\n"
        for i, opt in enumerate(options[:4]):  # Limit to 4 options
            formatted_text += f"Option {chr(65+i)}: {opt}\n"
        formatted_text += "\n"

        return formatted_text

    def create_db_viewer(self):
        # Create frames for the database tab
        questions_frame = ttk.LabelFrame(self.db_tab, text="Questions", padding="5")
        questions_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        questions_frame.columnconfigure(0, weight=1)
        questions_frame.rowconfigure(0, weight=1)
        
        details_frame = ttk.LabelFrame(self.db_tab, text="Details", padding="5")
        details_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        details_frame.columnconfigure(0, weight=1)
        details_frame.rowconfigure(0, weight=1)
        
        # Adjust column weights
        self.db_tab.columnconfigure(0, weight=1)
        self.db_tab.columnconfigure(1, weight=1)
        self.db_tab.rowconfigure(0, weight=1)
        
        # Questions list
        self.questions_listbox = tk.Listbox(questions_frame, width=50, height=20, selectmode=tk.EXTENDED)
        self.questions_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        questions_scrollbar = ttk.Scrollbar(questions_frame, orient=tk.VERTICAL, command=self.questions_listbox.yview)
        questions_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.questions_listbox['yscrollcommand'] = questions_scrollbar.set
        self.questions_listbox.bind('<<ListboxSelect>>', self.on_question_select)
        
        # Question details text area
        self.details_text = scrolledtext.ScrolledText(details_frame, wrap=tk.WORD, width=50, height=15)
        self.details_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # self.details_text.config(state=tk.DISABLED)  # Leave NORMAL so hyperlinks work
        
        # Buttons frame
        buttons_frame = ttk.Frame(details_frame, padding="5")
        buttons_frame.pack(side=tk.LEFT, fill=tk.X, padx=5, pady=5)
        
        refresh_button = ttk.Button(buttons_frame, text="Refresh List", command=self.refresh_questions_list)
        refresh_button.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        delete_button = ttk.Button(buttons_frame, text="Delete Selected", command=self.delete_selected_question)
        delete_button.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # Edit button
        edit_button = ttk.Button(buttons_frame, text="Edit Selected", command=self.edit_selected_question)
        edit_button.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # Delete LLM Info button
        clear_llm_button = ttk.Button(buttons_frame, text="Delete LLM Info", command=self.delete_llm_info)
        clear_llm_button.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        # Query LMS button
        query_lms_button = ttk.Button(buttons_frame, text="Query LMS", command=self.query_lms_batch_with_tab_switch)
        query_lms_button.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        self.query_lms_button = query_lms_button

        # Load questions initially
        self.refresh_questions_list()
    

    
    def on_question_select(self, event):
        
        selection = self.questions_listbox.curselection()
        if not selection:
            return
            
        index = selection[0]
        # Fetch the latest question data from the database
        qid = self.question_data[index]['id']
        question = self.db.get_question_by_id(qid) if hasattr(self.db, 'get_question_by_id') else self.question_data[index]
        options = self.db.get_options_for_question(qid)
        files = self.db.get_files_for_question(qid)
        
        
        # Update details text
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete(1.0, tk.END)

        # Format and insert question details
        self.details_text.insert(tk.END, f"Question ID: {question['id']}\n")
        self.details_text.insert(tk.END, f"First seen: {question.get('first_seen', 'N/A')}\n")
        self.details_text.insert(tk.END, f"Last seen: {question.get('last_seen', 'N/A')}\n")
        self.details_text.insert(tk.END, f"Associated files: {question.get('file_count', 'N/A')}\n\n")
        
        self.details_text.insert(tk.END, f"Question Text:\n{question['question_text']}\n\n")
        self.details_text.insert(tk.END, "Options:\n")
        for option in options:
            self.details_text.insert(tk.END, f"  {option['letter']}: {option['text']}\n")
        # Show LLM answer and justification if available
        llm_answer = question.get('llm_answer')
        llm_justification = question.get('llm_justification')
        # Show LLM source references if present
        for i in range(1, 4):
            src_filename = question.get(f'src{i}_filename', '')
            src_section = question.get(f'src{i}_section', '')
            src_page = question.get(f'src{i}_page', '')
            if src_filename or src_section or src_page:
                self.details_text.insert(tk.END, f"\nSource Reference {i}:\n  Document Name: {src_filename}\n  Section: {src_section}\n  Page: {src_page}\n")
        if llm_answer:
            self.details_text.insert(tk.END, f"\nLLM Answer: {llm_answer}\n")
        else:
            self.details_text.insert(tk.END, "\nLLM Answer: (not available)\n")
        if llm_justification:
            self.details_text.insert(tk.END, f"Justification: {llm_justification}\n")
        else:
            self.details_text.insert(tk.END, "Justification: (not available)\n")

        self.details_text.insert(tk.END, "\nSource Files:\n")
        import functools
        for i, file in enumerate(files):
            filename = file.get('filename')
            display_name = os.path.basename(filename) if filename else '(unknown file)'
            processed_date = file.get('processed_date', '(unknown date)')
            # Try to get document name, section, page number if present
            doc_name = file.get('document_name', display_name)
            section = file.get('section', '(section N/A)')
            page = file.get('page_number', '(page N/A)')
            self.details_text.insert(tk.END, "  ")
            self.details_text.mark_set(tk.INSERT, tk.END)
            start_index = self.details_text.index(tk.INSERT)
            self.details_text.insert(tk.INSERT, doc_name)
            end_index = self.details_text.index(tk.INSERT)
            tag_name = f"filelink_{i}"
            self.details_text.tag_add(tag_name, start_index, end_index)
            self.details_text.tag_config(tag_name, foreground="#FF00FF", underline=1, font=("Arial", 12, "bold"))
            self.details_text.tag_bind(tag_name, '<Button-1>', functools.partial(self._on_filelink_click, filename=filename))
            self.details_text.tag_bind(tag_name, '<Enter>', lambda e, t=tag_name: self.details_text.config(cursor="hand2"))
            self.details_text.tag_bind(tag_name, '<Leave>', lambda e, t=tag_name: self.details_text.config(cursor=""))
            self.details_text.insert(tk.END, f" | Section: {section} | Page: {page} | Processed: {processed_date}\n")
        # Keep widget NORMAL and block editing, so hyperlinks work
        self.details_text.config(state=tk.NORMAL)
        self.details_text.bind("<Key>", lambda e: "break")
        self.details_text.bind("<Button-3>", lambda e: "break")
    
    def _on_filelink_click(self, event, filename):
        print(f"DEBUG: File link clicked for {filename}")
        self.preview_file(filename)

    def delete_selected_question(self):
        selection = self.questions_listbox.curselection()
        if not selection:
            messagebox.showinfo("Information", "Please select a question to delete.")
            return

        index = selection[0]
        if index < 0 or index >= len(self.question_data):
            return

        question = self.question_data[index]
        # Confirm deletion
        if messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete this question and all related data?\n\n{question['question_text']}"):
            success = self.db.delete_question(question['id'])
            if success:
                # Clear the question from our local data immediately
                del self.question_data[index]
                self.questions_listbox.delete(index)
                self.details_text.config(state=tk.NORMAL)
                self.details_text.delete(1.0, tk.END)
                self.details_text.config(state=tk.NORMAL)
                # Prevent user from editing the details_text widget
                self.details_text.bind("<Key>", lambda e: "break")
                self.details_text.bind("<Button-3>", lambda e: "break")
            else:
                messagebox.showerror("Error", "Failed to delete the question.")

    def start_ocr_processing(self):
        input_dir = self.input_folder_path.get()
        if not input_dir or not os.path.isdir(input_dir):
            messagebox.showerror("Error", "Please select a valid input folder.")
            return

        # Save the last used folder for next time
        config = load_config()
        config["last_folder"] = input_dir
        
        save_config(config)

        # Find image files
        image_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif'))])
        if not image_files:
            self.log_status("No image files found in the selected folder.")
            messagebox.showinfo("Info", "No image files found in the selected folder.")
            return

        # Log status
        self.log_status(f"Found {len(image_files)} image files in {input_dir}")
        
        # Generate timestamped filename in the input directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"Results_{timestamp}.txt"
        output_file_path = os.path.join(input_dir, output_filename)
        self.log_status(f"Output will be saved to: {output_file_path}")

        self.log_status("Starting OCR process...")
        all_formatted_text = ""  # Initialize an empty string for accumulating results
        skipped_count = 0  # Track skipped files for status
        processed_count = 0  # Track processed files for status
        
        # Process each image file
        for image_file in image_files:
            full_image_path = os.path.join(input_dir, image_file)
            
            # Skip already processed files
            if self.db.is_file_processed(full_image_path):
                self.log_status(f"Skipping already processed file: {image_file}")
                skipped_count += 1
                continue
                
            self.log_status(f"Processing {image_file}...")
            
            # Extract text from image
            raw_text = self.extract_text_from_image(full_image_path)
            if raw_text:
                parsed_text = self.parse_ocr_text(raw_text, image_file)
                all_formatted_text += parsed_text
                processed_count += 1
            else:
                self.log_status(f"Warning: No text extracted from {image_file}")
        
        self.log_status(f"Processing complete. Processed {processed_count} new files, skipped {skipped_count} already processed files.")
        
        # Only save file if we processed any new files
        if processed_count > 0:
            try:
                with open(output_file_path, 'w', encoding='utf-8') as f:
                    f.write(all_formatted_text)
                self.log_status(f"Successfully saved output to {output_file_path}")
                
                # Open the file with the default text editor
                try:
                    if os.name == 'nt':  # Windows
                        os.startfile(output_file_path)
                    elif os.name == 'posix':  # macOS, Linux
                        if os.path.exists('/usr/bin/open'):
                            subprocess.call(('open', output_file_path))
                        else:
                            subprocess.call(('xdg-open', output_file_path))
                    self.log_status("Opened output file in default editor.")
                except Exception as e:
                    self.log_status(f"Could not open file automatically: {e}")
            except Exception as e:
                self.log_status(f"Error saving output: {e}")
                messagebox.showerror("Error", f"Error saving output: {e}")
        else:
            self.log_status("No new files were processed. No output file was created.")
            
        # Refresh the database tab
        self.refresh_questions_list()

def main():
    root = tk.Tk()
    root.title("LMStudio OCR Processor")
    app = OCRApp(root)

    # --- Maximize window on start (cross-platform) ---
    import platform
    root.update_idletasks()
    try:
        if platform.system() == "Windows":
            root.state('zoomed')
        elif platform.system() == "Darwin":  # macOS
            # Maximize to screen size (not true "fullscreen")
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            root.geometry(f"{screen_width}x{screen_height}+0+0")
            # Uncomment the next line for true fullscreen (Mission Control style)
            # root.wm_attributes('-fullscreen', True)
        else:  # Linux or other
            root.state('zoomed')
    except Exception as e:
        print(f"Window maximization not supported: {e}")
    root.lift()
    root.focus_force()
    # --- End maximize ---

    root.mainloop()

if __name__ == "__main__":
    main()
