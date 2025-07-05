import sqlite3
import hashlib
import os
from datetime import datetime
from typing import List, Optional, Dict, Tuple

class OCRDatabase:
    def update_llm_results(self, question_id: int, answer: str, justification: str, explanations: str, references=None) -> bool:
        """Update a question with LLM answer, justification, explanations, and up to 3 source references."""
        try:
            if references is None:
                references = [{}, {}, {}]
            # Ensure 3 references
            while len(references) < 3:
                references.append({'filename':'','section':'','page':''})
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE questions
                    SET llm_answer = ?, llm_justification = ?, llm_explanations = ?,
                        src1_filename = ?, src1_section = ?, src1_page = ?,
                        src2_filename = ?, src2_section = ?, src2_page = ?,
                        src3_filename = ?, src3_section = ?, src3_page = ?,
                        last_seen_date = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (
                    answer, justification, explanations,
                    references[0].get('filename',''), references[0].get('section',''), references[0].get('page',''),
                    references[1].get('filename',''), references[1].get('section',''), references[1].get('page',''),
                    references[2].get('filename',''), references[2].get('section',''), references[2].get('page',''),
                    question_id
                ))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            print(f"Database error updating LLM results: {e}")
            return False


    def has_llm_results(self, question_id: int) -> bool:
        """Return True if all LLM results are present and non-empty for this question."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT llm_answer, llm_justification, llm_explanations FROM questions WHERE id = ?
                ''', (question_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                # Consider both None and empty string as 'not available'
                return all((v is not None and str(v).strip() != "") for v in row)
        except sqlite3.Error as e:
            print(f"Database error checking LLM results: {e}")
            return False

    def get_question_by_id(self, question_id: int) -> dict:
        """Fetch all fields for a question by its ID, including up to 3 source references."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM questions WHERE id = ?', (question_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                d = dict(row)
                # Collect references in a list for convenience
                d['llm_references'] = [
                    {'filename': d.get('src1_filename',''), 'section': d.get('src1_section',''), 'page': d.get('src1_page','')},
                    {'filename': d.get('src2_filename',''), 'section': d.get('src2_section',''), 'page': d.get('src2_page','')},
                    {'filename': d.get('src3_filename',''), 'section': d.get('src3_section',''), 'page': d.get('src3_page','')}
                ]
                return d
        except sqlite3.Error as e:
            print(f"Database error in get_question_by_id: {e}")
            return None


    def get_questions_missing_llm_results(self) -> list:
        """Return all questions missing any LLM results (answer, justification, or explanations)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM questions WHERE llm_answer IS NULL OR llm_justification IS NULL OR llm_explanations IS NULL
                ''')
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Database error getting missing LLM results: {e}")
            return []

    def __init__(self, db_path: str = "ocr_results.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Initialize the database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create the questions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_text TEXT NOT NULL,
                    question_hash TEXT NOT NULL UNIQUE,
                    first_seen_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    llm_answer TEXT,
                    llm_justification TEXT,
                    llm_explanations TEXT,
                    src1_filename TEXT,
                    src1_section TEXT,
                    src1_page TEXT,
                    src2_filename TEXT,
                    src2_section TEXT,
                    src2_page TEXT,
                    src3_filename TEXT,
                    src3_section TEXT,
                    src3_page TEXT
                )
            ''')
            # Add columns if missing (migration)
            columns = [row[1] for row in cursor.execute('PRAGMA table_info(questions)')]
            for col in [
                'src1_filename','src1_section','src1_page',
                'src2_filename','src2_section','src2_page',
                'src3_filename','src3_section','src3_page']:
                if col not in columns:
                    cursor.execute(f"ALTER TABLE questions ADD COLUMN {col} TEXT")
            
            # Create the options table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS options (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id INTEGER,
                    option_letter TEXT NOT NULL,
                    option_text TEXT NOT NULL,
                    FOREIGN KEY (question_id) REFERENCES questions(id),
                    UNIQUE(question_id, option_letter)
                )
            ''')
            
            # Create the source_files table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS source_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id INTEGER,
                    filename TEXT NOT NULL,
                    filename_hash TEXT NOT NULL,
                    processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (question_id) REFERENCES questions(id),
                    UNIQUE(question_id, filename),
                    UNIQUE(filename_hash)
                )
            ''')
            
            conn.commit()

    def compute_question_hash(self, question_text: str) -> str:
        """Compute a stable hash of the question text."""
        # Normalize the text by removing extra whitespace and converting to lowercase
        normalized_text = " ".join(question_text.lower().split())
        return hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
        
    def compute_filename_hash(self, filename: str) -> str:
        """Compute a hash of the filename."""
        # Use just the basename to avoid path differences
        basename = os.path.basename(filename)
        return hashlib.sha256(basename.encode('utf-8')).hexdigest()

    def store_question(self, question_text: str, options: List[str], source_file: str) -> bool:
        """Store a question with its options and source file information."""
        question_hash = self.compute_question_hash(question_text)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Try to insert or update the question
                cursor.execute('''
                    INSERT INTO questions (question_text, question_hash)
                    VALUES (?, ?)
                    ON CONFLICT(question_hash) DO UPDATE SET
                    last_seen_date = CURRENT_TIMESTAMP
                    RETURNING id
                ''', (question_text, question_hash))
                
                result = cursor.fetchone()
                if not result:
                    # If RETURNING isn't supported (older SQLite versions), get the id separately
                    cursor.execute('SELECT id FROM questions WHERE question_hash = ?', (question_hash,))
                    result = cursor.fetchone()
                
                question_id = result[0]
                
                # Store the options
                for i, option_text in enumerate(options):
                    option_letter = chr(65 + i)  # A, B, C, D
                    cursor.execute('''
                        INSERT OR REPLACE INTO options (question_id, option_letter, option_text)
                        VALUES (?, ?, ?)
                    ''', (question_id, option_letter, option_text))
                
                # Store the source file information with hash
                filename_hash = self.compute_filename_hash(source_file)
                cursor.execute('''
                    INSERT OR IGNORE INTO source_files (question_id, filename, filename_hash)
                    VALUES (?, ?, ?)
                ''', (question_id, source_file, filename_hash))
                
                return True
                
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return False

    def get_question_by_hash(self, question_hash: str) -> Optional[dict]:
        """Retrieve a question and its options by hash."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get question details
                cursor.execute('''
                    SELECT id, question_text, first_seen_date, last_seen_date
                    FROM questions
                    WHERE question_hash = ?
                ''', (question_hash,))
                
                question_row = cursor.fetchone()
                if not question_row:
                    return None
                
                # Get options
                cursor.execute('''
                    SELECT option_letter, option_text
                    FROM options
                    WHERE question_id = ?
                    ORDER BY option_letter
                ''', (question_row[0],))
                
                options = {row[0]: row[1] for row in cursor.fetchall()}
                
                # Get source files
                cursor.execute('''
                    SELECT filename, processed_date
                    FROM source_files
                    WHERE question_id = ?
                    ORDER BY processed_date DESC
                ''', (question_row[0],))
                
                sources = [(row[0], row[1]) for row in cursor.fetchall()]
                
                return {
                    'question_text': question_row[1],
                    'first_seen': question_row[2],
                    'last_seen': question_row[3],
                    'options': options,
                    'sources': sources
                }
                
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return None
            
    def is_file_processed(self, filename: str) -> bool:
        """Check if a file has already been processed."""
        filename_hash = self.compute_filename_hash(filename)
        basename = os.path.basename(filename)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Only consider a file processed if it exists in source_files with a valid question_id
                cursor.execute('''
                    SELECT COUNT(*) FROM source_files sf
                    JOIN questions q ON sf.question_id = q.id
                    WHERE sf.filename_hash = ?
                ''', (filename_hash,))
                
                count = cursor.fetchone()[0]
                return count > 0
                
        except sqlite3.Error as e:
            print(f"Database error checking file: {e}")
            return False
            
    def get_all_questions(self) -> List[Dict]:
        """Get all questions in the database, including up to 3 source references."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row  # This enables column access by name
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT q.id, q.question_text, q.question_hash, 
                           q.first_seen_date, q.last_seen_date, 
                           q.llm_answer, q.llm_justification, q.llm_explanations,
                           q.src1_filename, q.src1_section, q.src1_page,
                           q.src2_filename, q.src2_section, q.src2_page,
                           q.src3_filename, q.src3_section, q.src3_page,
                           COUNT(DISTINCT sf.filename) as file_count
                    FROM questions q
                    LEFT JOIN source_files sf ON q.id = sf.question_id
                    GROUP BY q.id
                    ORDER BY q.last_seen_date DESC
                ''')
                
                questions = []
                for row in cursor.fetchall():
                    d = dict(row)
                    d['llm_references'] = [
                        {'filename': d.get('src1_filename',''), 'section': d.get('src1_section',''), 'page': d.get('src1_page','')},
                        {'filename': d.get('src2_filename',''), 'section': d.get('src2_section',''), 'page': d.get('src2_page','')},
                        {'filename': d.get('src3_filename',''), 'section': d.get('src3_section',''), 'page': d.get('src3_page','')}
                    ]
                    questions.append(d)
                
                return questions
                
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return []
            
    def get_options_for_question(self, question_id: int) -> List[Dict]:
        """Get all options for a specific question."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT option_letter, option_text
                    FROM options
                    WHERE question_id = ?
                    ORDER BY option_letter
                ''', (question_id,))
                
                options = []
                for row in cursor.fetchall():
                    options.append({
                        'letter': row['option_letter'],
                        'text': row['option_text']
                    })
                    
                return options
                
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return []
            
    def get_files_for_question(self, question_id: int) -> List[Dict]:
        """Get all source files for a specific question."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT id, filename, processed_date
                    FROM source_files
                    WHERE question_id = ?
                    ORDER BY processed_date DESC
                ''', (question_id,))
                
                files = []
                for row in cursor.fetchall():
                    files.append({
                        'id': row['id'],
                        'filename': row['filename'],
                        'processed_date': row['processed_date']
                    })
                    
                return files
                
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return []
            
    def mark_file_unprocessed(self, filename: str) -> bool:
        """Explicitly mark a file as unprocessed by removing all database entries for it."""
        filename_hash = self.compute_filename_hash(filename)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Find any source_file entries with this filename_hash
                cursor.execute('DELETE FROM source_files WHERE filename_hash = ?', (filename_hash,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            print(f"Database error marking file unprocessed: {e}")
            return False
            
    def update_question_and_options(self, question_id: int, new_question_text: str, new_options: list) -> bool:
        """Update question text and its options."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Update question text
                cursor.execute('''
                    UPDATE questions SET question_text = ?, last_seen_date = CURRENT_TIMESTAMP WHERE id = ?
                ''', (new_question_text, question_id))
                # Update or insert options
                for i, option_text in enumerate(new_options):
                    option_letter = chr(65 + i)  # A, B, C, D
                    cursor.execute('''
                        UPDATE options SET option_text = ? WHERE question_id = ? AND option_letter = ?
                    ''', (option_text, question_id, option_letter))
                    if cursor.rowcount == 0:
                        cursor.execute('''
                            INSERT INTO options (question_id, option_letter, option_text)
                            VALUES (?, ?, ?)
                        ''', (question_id, option_letter, option_text))
                conn.commit()
                return True
        except sqlite3.Error as e:
            print(f"Database error updating question/options: {e}")
            return False
    def delete_question(self, question_id: int) -> bool:
        """Delete a question and all its related data."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Enable foreign keys to ensure cascading deletes work properly
                conn.execute('PRAGMA foreign_keys = ON')
                cursor = conn.cursor()
                
                # Get the filenames associated with this question before deleting
                cursor.execute('SELECT filename FROM source_files WHERE question_id = ?', (question_id,))
                filenames = [row[0] for row in cursor.fetchall()]
                
                # Delete related options and source files first (due to foreign key constraints)
                cursor.execute('DELETE FROM options WHERE question_id = ?', (question_id,))
                cursor.execute('DELETE FROM source_files WHERE question_id = ?', (question_id,))
                
                # Then delete the question
                cursor.execute('DELETE FROM questions WHERE id = ?', (question_id,))
                
                # Commit changes explicitly
                conn.commit()
                
                # Mark all associated files as unprocessed to ensure they can be reprocessed
                for filename in filenames:
                    self.mark_file_unprocessed(filename)
                    
                return True
                
        except sqlite3.Error as e:
            print(f"Database error deleting question: {e}")
            return False
