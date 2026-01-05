"""
Database Module - Quiz Application
===================================
All database interactions for the quiz app.
Handles SQLite operations for quizzes, questions, results, permissions, and teachers.
"""

import sqlite3
import json
import os
import hashlib
from typing import Any
from werkzeug.security import generate_password_hash, check_password_hash

# Type aliases
QuestionDict = dict[str, Any]
StudentData = dict[str, str]
ResultData = dict[str, Any]

# Module-level variables (set by init_db)
DATABASE_FILE: str = ""
QUESTIONS_FOLDER: str = ""


def init_db(database_file: str, questions_folder: str) -> None:
    """Initialize module with paths"""
    global DATABASE_FILE, QUESTIONS_FOLDER
    DATABASE_FILE = database_file
    QUESTIONS_FOLDER = questions_folder


def get_db_connection() -> sqlite3.Connection:
    """Get a database connection with row factory"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ============ INITIALIZATION ============

def init_database() -> None:
    """Initialize SQLite database with all required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Quizzes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            file_path TEXT,
            file_hash TEXT,
            question_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            time_limit_minutes INTEGER DEFAULT 0,
            partial_credit INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Quiz questions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id TEXT NOT NULL,
            question_index INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            options TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            times_shown INTEGER DEFAULT 0,
            times_correct INTEGER DEFAULT 0,
            times_wrong INTEGER DEFAULT 0,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id) ON DELETE CASCADE
        )
    ''')
    
    # Quiz results table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            batch TEXT NOT NULL,
            score INTEGER NOT NULL,
            max_score INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            attempt_details TEXT NOT NULL,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id) ON DELETE CASCADE
        )
    ''')
    
    # Permissions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id TEXT NOT NULL,
            batch TEXT NOT NULL,
            UNIQUE(quiz_id, batch),
            FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id) ON DELETE CASCADE
        )
    ''')
    
    # Teachers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Batches table for batch management
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Quiz progress table for resume feature
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            batch TEXT NOT NULL,
            current_question INTEGER DEFAULT 0,
            score INTEGER DEFAULT 0,
            wrong_attempts INTEGER DEFAULT 0,
            user_answers TEXT DEFAULT '{}',
            is_correct TEXT DEFAULT '{}',
            flagged_questions TEXT DEFAULT '[]',
            partial_scores TEXT DEFAULT '{}',
            quiz_start_time REAL,
            quiz_end_time REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(quiz_id, first_name, last_name, batch)
        )
    ''')
    
    # Add is_admin column to teachers if it doesn't exist
    try:
        cursor.execute('ALTER TABLE teachers ADD COLUMN is_admin INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_questions_quiz ON quiz_questions(quiz_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_results_quiz ON quiz_results(quiz_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_results_batch ON quiz_results(batch)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_results_timestamp ON quiz_results(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_permissions_quiz ON quiz_permissions(quiz_id)')
    
    # Create default admin user if no teachers exist
    cursor.execute('SELECT COUNT(*) FROM teachers')
    if cursor.fetchone()[0] == 0:
        default_hash = generate_password_hash('password', method='pbkdf2:sha256')
        cursor.execute('INSERT INTO teachers (username, password_hash, is_admin) VALUES (?, ?, 1)', ('admin', default_hash))
    else:
        # Make sure the admin user has is_admin = 1
        cursor.execute('UPDATE teachers SET is_admin = 1 WHERE username = ?', ('admin',))
    
    conn.commit()
    conn.close()


# ============ QUIZ IMPORT/SYNC ============

def get_file_hash(file_path: str) -> str:
    """Calculate MD5 hash of a file to detect changes"""
    with open(file_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def import_quiz_from_json(file_path: str) -> tuple[str, int]:
    """Import a quiz from JSON file into the database"""
    with open(file_path, 'r', encoding='utf8') as f:
        questions = json.load(f)
    
    filename = os.path.basename(file_path)
    quiz_id = filename.replace('.json', '').replace(' ', '_').lower()
    title = filename.replace('.json', '')
    file_hash = get_file_hash(file_path)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, file_hash FROM quizzes WHERE quiz_id = ?', (quiz_id,))
    existing = cursor.fetchone()
    
    if existing:
        if existing['file_hash'] == file_hash:
            conn.close()
            return quiz_id, 0  # No changes
        
        cursor.execute('''
            UPDATE quizzes SET file_hash = ?, question_count = ?, updated_at = CURRENT_TIMESTAMP, is_active = 1
            WHERE quiz_id = ?
        ''', (file_hash, len(questions), quiz_id))
        cursor.execute('DELETE FROM quiz_questions WHERE quiz_id = ?', (quiz_id,))
    else:
        cursor.execute('''
            INSERT INTO quizzes (quiz_id, title, file_path, file_hash, question_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (quiz_id, title, file_path, file_hash, len(questions)))
    
    for idx, q in enumerate(questions):
        cursor.execute('''
            INSERT INTO quiz_questions (quiz_id, question_index, question_text, options, correct_answer)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            quiz_id,
            idx,
            q['question'],
            json.dumps(q['options'], ensure_ascii=False),
            json.dumps(q['answer'], ensure_ascii=False)
        ))
    
    conn.commit()
    conn.close()
    
    return quiz_id, len(questions)


def sync_quizzes_from_folder() -> dict[str, Any]:
    """Scan questions folder and sync with database"""
    results = {'imported': [], 'updated': [], 'deactivated': []}
    
    if not os.path.exists(QUESTIONS_FOLDER):
        return results
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    json_files = {f.replace('.json', '').replace(' ', '_').lower(): os.path.join(QUESTIONS_FOLDER, f)
                  for f in os.listdir(QUESTIONS_FOLDER) if f.endswith('.json')}
    
    for quiz_id, file_path in json_files.items():
        try:
            cursor.execute('SELECT id FROM quizzes WHERE quiz_id = ?', (quiz_id,))
            existed = cursor.fetchone() is not None
            
            imported_id, count = import_quiz_from_json(file_path)
            
            if count > 0:
                if existed:
                    results['updated'].append(f"{imported_id} ({count} questions)")
                else:
                    results['imported'].append(f"{imported_id} ({count} questions)")
        except Exception as e:
            print(f"Error importing {file_path}: {e}")
    
    cursor.execute('SELECT quiz_id FROM quizzes WHERE is_active = 1')
    active_quizzes = [row['quiz_id'] for row in cursor.fetchall()]
    
    for quiz_id in active_quizzes:
        if quiz_id not in json_files:
            cursor.execute('UPDATE quizzes SET is_active = 0 WHERE quiz_id = ?', (quiz_id,))
            results['deactivated'].append(quiz_id)
    
    conn.commit()
    conn.close()
    
    return results


# ============ TEACHER AUTH ============

def verify_teacher_password(username: str, password: str) -> bool:
    """Verify teacher password from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT password_hash FROM teachers WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return False
    
    return check_password_hash(row['password_hash'], password)


def update_teacher_password(username: str, new_password: str) -> bool:
    """Update teacher password in database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
    cursor.execute('UPDATE teachers SET password_hash = ? WHERE username = ?', (password_hash, username))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


# ============ QUIZ QUERIES ============

def get_active_quizzes() -> list[dict[str, Any]]:
    """Get all active quizzes from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT quiz_id, title, question_count, time_limit_minutes, partial_credit, created_at,
               (SELECT COUNT(*) FROM quiz_results WHERE quiz_results.quiz_id = quizzes.quiz_id) as submission_count
        FROM quizzes 
        WHERE is_active = 1 
        ORDER BY title
    ''')
    quizzes = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return quizzes


def get_quiz_questions(quiz_id: str, shuffle: bool = True) -> list[QuestionDict]:
    """Get all questions for a quiz"""
    import random
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, question_text, options, correct_answer 
        FROM quiz_questions 
        WHERE quiz_id = ? 
        ORDER BY question_index
    ''', (quiz_id,))
    rows = cursor.fetchall()
    conn.close()
    
    questions = []
    for row in rows:
        questions.append({
            'db_id': row['id'],
            'question': row['question_text'],
            'options': json.loads(row['options']),
            'answer': json.loads(row['correct_answer'])
        })
    
    if shuffle:
        random.shuffle(questions)
    
    return questions


def get_quiz_info(quiz_id: str) -> dict[str, Any] | None:
    """Get quiz metadata"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM quizzes WHERE quiz_id = ?', (quiz_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ============ PERMISSIONS ============

def check_answer_permission(quiz_id: str, batch: str) -> bool:
    """Check if a batch is allowed to see answers for a quiz"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM quiz_permissions WHERE quiz_id = ? AND batch = ?', (quiz_id, batch))
    result = cursor.fetchone() is not None
    conn.close()
    return result


def get_quiz_permissions(quiz_id: str) -> list[str]:
    """Get all batches allowed to see answers for a quiz"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT batch FROM quiz_permissions WHERE quiz_id = ?', (quiz_id,))
    batches = [row['batch'] for row in cursor.fetchall()]
    conn.close()
    return batches


def set_quiz_permissions(quiz_id: str, batches: list[str]) -> None:
    """Set which batches can see answers for a quiz"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM quiz_permissions WHERE quiz_id = ?', (quiz_id,))
    for batch in batches:
        if batch.strip():
            cursor.execute('INSERT OR IGNORE INTO quiz_permissions (quiz_id, batch) VALUES (?, ?)', 
                          (quiz_id, batch.strip()))
    conn.commit()
    conn.close()


# ============ ANALYTICS ============

def update_question_analytics(question_db_id: int, is_correct: bool) -> None:
    """Update analytics for a question"""
    conn = get_db_connection()
    cursor = conn.cursor()
    if is_correct:
        cursor.execute('''
            UPDATE quiz_questions 
            SET times_shown = times_shown + 1, times_correct = times_correct + 1 
            WHERE id = ?
        ''', (question_db_id,))
    else:
        cursor.execute('''
            UPDATE quiz_questions 
            SET times_shown = times_shown + 1, times_wrong = times_wrong + 1 
            WHERE id = ?
        ''', (question_db_id,))
    conn.commit()
    conn.close()


def get_question_analytics(quiz_id: str) -> list[dict[str, Any]]:
    """Get analytics for all questions in a quiz"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT question_index, question_text, times_shown, times_correct, times_wrong,
               CASE WHEN times_shown > 0 
                    THEN ROUND(CAST(times_correct AS FLOAT) / times_shown * 100, 1)
                    ELSE 0 END as success_rate
        FROM quiz_questions
        WHERE quiz_id = ?
        ORDER BY question_index
    ''', (quiz_id,))
    analytics = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return analytics


# ============ RESULTS ============

def save_student_result(
    student_data: StudentData,
    quiz_id: str,
    score: int,
    max_score: int,
    questions: list[QuestionDict],
    user_answers: dict[int | str, list[str]],
    is_correct: dict[int | str, bool]
) -> int:
    """Save student result to database"""
    attempt_details: list[dict[str, Any]] = []
    
    for idx, question in enumerate(questions):
        user_selected = user_answers.get(idx, user_answers.get(str(idx), []))
        correct = is_correct.get(idx, is_correct.get(str(idx), False))
        
        if not isinstance(user_selected, list):
            user_selected = [user_selected] if user_selected else []
        
        attempt_details.append({
            "question_id": question.get('db_id'),
            "question_text": question['question'],
            "options": question['options'],
            "correct_option": question['answer'],
            "selected_option": user_selected,
            "is_correct": correct
        })
        
        if question.get('db_id'):
            update_question_analytics(question['db_id'], correct)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO quiz_results (quiz_id, first_name, last_name, batch, score, max_score, attempt_details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        quiz_id,
        student_data['first_name'],
        student_data['last_name'],
        student_data['batch'],
        score,
        max_score,
        json.dumps(attempt_details, ensure_ascii=False)
    ))
    result_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return result_id


def get_quiz_results_summary() -> list[dict[str, Any]]:
    """Get summary of all quiz results"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT q.quiz_id, q.title as quiz_name, q.is_active, q.question_count,
               COUNT(r.id) as submission_count,
               AVG(CAST(r.score AS FLOAT) / r.max_score * 100) as avg_score
        FROM quizzes q
        LEFT JOIN quiz_results r ON q.quiz_id = r.quiz_id
        GROUP BY q.quiz_id
        ORDER BY q.title
    ''')
    summary = [dict(row) for row in cursor.fetchall()]
    
    for quiz in summary:
        cursor.execute('SELECT batch FROM quiz_permissions WHERE quiz_id = ?', (quiz['quiz_id'],))
        quiz['allowed_batches'] = [row['batch'] for row in cursor.fetchall()]
    
    conn.close()
    return summary


def get_quiz_submissions(quiz_id: str) -> list[dict[str, Any]]:
    """Get all submissions for a specific quiz"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id as result_id, first_name, last_name, batch, score, max_score, timestamp
        FROM quiz_results
        WHERE quiz_id = ?
        ORDER BY timestamp DESC
    ''', (quiz_id,))
    submissions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return submissions


def load_student_result(result_id: int) -> ResultData | None:
    """Load a specific student result"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, q.title as quiz_name 
        FROM quiz_results r 
        LEFT JOIN quizzes q ON r.quiz_id = q.quiz_id 
        WHERE r.id = ?
    ''', (result_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        "result_id": row['id'],
        "quiz_id": row['quiz_id'],
        "quiz_name": row['quiz_name'] or row['quiz_id'],
        "first_name": row['first_name'],
        "last_name": row['last_name'],
        "batch": row['batch'],
        "score": row['score'],
        "max_score": row['max_score'],
        "submitted_at": row['timestamp'],
        "attempt_details": json.loads(row['attempt_details'])
    }


def delete_result(result_id: int) -> str | None:
    """Delete a specific result, returns quiz_id"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT quiz_id FROM quiz_results WHERE id = ?', (result_id,))
    row = cursor.fetchone()
    quiz_id = row['quiz_id'] if row else None
    
    cursor.execute('DELETE FROM quiz_results WHERE id = ?', (result_id,))
    conn.commit()
    conn.close()
    
    return quiz_id


# ============ QUIZ MANAGEMENT ============

def delete_quiz(quiz_id: str, delete_results: bool = False) -> bool:
    """Delete or deactivate a quiz"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if delete_results:
        cursor.execute('DELETE FROM quizzes WHERE quiz_id = ?', (quiz_id,))
    else:
        cursor.execute('UPDATE quizzes SET is_active = 0 WHERE quiz_id = ?', (quiz_id,))
    
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    
    if delete_results and QUESTIONS_FOLDER:
        for f in os.listdir(QUESTIONS_FOLDER):
            if f.endswith('.json') and f.replace('.json', '').replace(' ', '_').lower() == quiz_id:
                os.remove(os.path.join(QUESTIONS_FOLDER, f))
                break
    
    return affected > 0


def toggle_quiz_active(quiz_id: str) -> bool | None:
    """Toggle quiz active status, returns new status"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_active FROM quizzes WHERE quiz_id = ?', (quiz_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return None
    
    new_status = not row['is_active']
    cursor.execute('UPDATE quizzes SET is_active = ? WHERE quiz_id = ?', (new_status, quiz_id))
    conn.commit()
    conn.close()
    
    return new_status


def update_quiz_settings(quiz_id: str, time_limit_minutes: int, partial_credit: bool) -> bool:
    """Update quiz settings (time limit and partial credit)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE quizzes 
        SET time_limit_minutes = ?, partial_credit = ? 
        WHERE quiz_id = ?
    ''', (time_limit_minutes, 1 if partial_credit else 0, quiz_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def calculate_partial_score(selected: list[str], correct: list[str]) -> float:
    """Calculate partial credit for multi-select questions.
    
    Scoring formula:
    - Each correct selection: +1 point
    - Each incorrect selection: -1 point (penalty for wrong selections)
    - Minimum score: 0 (no negative total)
    - Normalized to 0-1 range based on number of correct answers
    """
    if not correct:
        return 0.0
    
    selected_set = set(opt.strip() for opt in selected)
    correct_set = set(opt.strip() for opt in correct)
    
    # For single-answer questions, use binary scoring
    if len(correct_set) == 1:
        return 1.0 if selected_set == correct_set else 0.0
    
    # Multi-select partial credit calculation
    correct_selections = len(selected_set & correct_set)  # Correct answers selected
    incorrect_selections = len(selected_set - correct_set)  # Wrong answers selected
    
    # Raw score: correct picks minus incorrect picks
    raw_score = correct_selections - incorrect_selections
    
    # Normalize: divide by total correct answers, minimum 0
    normalized_score = max(0, raw_score) / len(correct_set)
    
    return round(normalized_score, 2)


# ============ TEACHER MANAGEMENT ============

def get_all_teachers() -> list[dict[str, Any]]:
    """Get all teachers"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, is_admin, created_at
        FROM teachers
        ORDER BY created_at DESC
    ''')
    teachers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return teachers


def create_teacher(username: str, password: str, is_admin: bool = False) -> tuple[bool, str]:
    """Create a new teacher account"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if username exists
    cursor.execute('SELECT id FROM teachers WHERE username = ?', (username,))
    if cursor.fetchone():
        conn.close()
        return False, "Username already exists"
    
    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    cursor.execute('''
        INSERT INTO teachers (username, password_hash, is_admin)
        VALUES (?, ?, ?)
    ''', (username, password_hash, 1 if is_admin else 0))
    
    conn.commit()
    conn.close()
    return True, "Teacher created successfully"


def delete_teacher(teacher_id: int) -> tuple[bool, str]:
    """Delete a teacher (cannot delete admin)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT username, is_admin FROM teachers WHERE id = ?', (teacher_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return False, "Teacher not found"
    
    if row['username'] == 'admin':
        conn.close()
        return False, "Cannot delete the admin account"
    
    cursor.execute('DELETE FROM teachers WHERE id = ?', (teacher_id,))
    conn.commit()
    conn.close()
    return True, "Teacher deleted successfully"


def get_teacher_info(username: str) -> dict[str, Any] | None:
    """Get teacher info by username"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, is_admin, created_at FROM teachers WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ============ BATCH MANAGEMENT ============

def get_all_batches() -> list[dict[str, Any]]:
    """Get all batches"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.id, b.name, b.description, b.is_active, b.created_at,
               (SELECT COUNT(*) FROM quiz_results WHERE batch = b.name) as student_count
        FROM batches b
        ORDER BY b.name
    ''')
    batches = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return batches


def create_batch(name: str, description: str = '') -> tuple[bool, str]:
    """Create a new batch"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO batches (name, description)
            VALUES (?, ?)
        ''', (name.strip(), description.strip()))
        conn.commit()
        conn.close()
        return True, "Batch created successfully"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Batch name already exists"


def update_batch(batch_id: int, name: str, description: str, is_active: bool) -> tuple[bool, str]:
    """Update a batch"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get old name for updating results
    cursor.execute('SELECT name FROM batches WHERE id = ?', (batch_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "Batch not found"
    
    old_name = row['name']
    
    try:
        cursor.execute('''
            UPDATE batches 
            SET name = ?, description = ?, is_active = ?
            WHERE id = ?
        ''', (name.strip(), description.strip(), 1 if is_active else 0, batch_id))
        
        # Update quiz_results with new batch name
        if old_name != name.strip():
            cursor.execute('UPDATE quiz_results SET batch = ? WHERE batch = ?', (name.strip(), old_name))
            cursor.execute('UPDATE quiz_permissions SET batch = ? WHERE batch = ?', (name.strip(), old_name))
        
        conn.commit()
        conn.close()
        return True, "Batch updated successfully"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Batch name already exists"


def delete_batch(batch_id: int) -> tuple[bool, str]:
    """Delete a batch"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name FROM batches WHERE id = ?', (batch_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "Batch not found"
    
    cursor.execute('DELETE FROM batches WHERE id = ?', (batch_id,))
    conn.commit()
    conn.close()
    return True, "Batch deleted successfully"


def get_unique_batches_from_results() -> list[str]:
    """Get unique batch names from quiz results"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT batch FROM quiz_results ORDER BY batch')
    batches = [row['batch'] for row in cursor.fetchall()]
    conn.close()
    return batches


# ============ EXPORT FUNCTIONS ============

def get_quiz_results_for_export(quiz_id: str) -> list[dict[str, Any]]:
    """Get all results for a quiz in export-friendly format"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.id, r.first_name, r.last_name, r.batch, r.score, r.max_score, 
               r.timestamp, r.attempt_details,
               ROUND(CAST(r.score AS FLOAT) / r.max_score * 100, 1) as percentage
        FROM quiz_results r
        WHERE r.quiz_id = ?
        ORDER BY r.timestamp DESC
    ''', (quiz_id,))
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_all_results_for_export() -> list[dict[str, Any]]:
    """Get all results for export"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.id, q.title as quiz_name, r.first_name, r.last_name, r.batch, 
               r.score, r.max_score, r.timestamp,
               ROUND(CAST(r.score AS FLOAT) / r.max_score * 100, 1) as percentage
        FROM quiz_results r
        LEFT JOIN quizzes q ON r.quiz_id = q.quiz_id
        ORDER BY r.timestamp DESC
    ''')
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# ============ ANALYTICS ============

def get_dashboard_analytics() -> dict[str, Any]:
    """Get analytics data for the dashboard"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total stats
    cursor.execute('SELECT COUNT(*) as count FROM quiz_results')
    total_submissions = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM quizzes WHERE is_active = 1')
    total_quizzes = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(DISTINCT batch) as count FROM quiz_results')
    total_batches = cursor.fetchone()['count']
    
    cursor.execute('SELECT AVG(CAST(score AS FLOAT) / max_score * 100) as avg FROM quiz_results')
    row = cursor.fetchone()
    overall_avg = round(row['avg'], 1) if row['avg'] else 0
    
    # Submissions by day (last 7 days)
    cursor.execute('''
        SELECT DATE(timestamp) as date, COUNT(*) as count
        FROM quiz_results
        WHERE timestamp >= DATE('now', '-7 days')
        GROUP BY DATE(timestamp)
        ORDER BY date
    ''')
    submissions_by_day = [dict(row) for row in cursor.fetchall()]
    
    # Score distribution
    cursor.execute('''
        SELECT 
            CASE 
                WHEN (CAST(score AS FLOAT) / max_score * 100) >= 90 THEN '90-100%'
                WHEN (CAST(score AS FLOAT) / max_score * 100) >= 80 THEN '80-89%'
                WHEN (CAST(score AS FLOAT) / max_score * 100) >= 70 THEN '70-79%'
                WHEN (CAST(score AS FLOAT) / max_score * 100) >= 60 THEN '60-69%'
                WHEN (CAST(score AS FLOAT) / max_score * 100) >= 50 THEN '50-59%'
                ELSE 'Below 50%'
            END as range,
            COUNT(*) as count
        FROM quiz_results
        GROUP BY range
        ORDER BY range DESC
    ''')
    score_distribution = [dict(row) for row in cursor.fetchall()]
    
    # Performance by quiz
    cursor.execute('''
        SELECT q.title as quiz_name, 
               COUNT(r.id) as submissions,
               ROUND(AVG(CAST(r.score AS FLOAT) / r.max_score * 100), 1) as avg_score
        FROM quizzes q
        LEFT JOIN quiz_results r ON q.quiz_id = r.quiz_id
        WHERE q.is_active = 1
        GROUP BY q.quiz_id
        HAVING submissions > 0
        ORDER BY avg_score DESC
    ''')
    quiz_performance = [dict(row) for row in cursor.fetchall()]
    
    # Performance by batch
    cursor.execute('''
        SELECT batch, 
               COUNT(*) as submissions,
               ROUND(AVG(CAST(score AS FLOAT) / max_score * 100), 1) as avg_score
        FROM quiz_results
        GROUP BY batch
        ORDER BY avg_score DESC
    ''')
    batch_performance = [dict(row) for row in cursor.fetchall()]
    
    # Recent submissions
    cursor.execute('''
        SELECT r.first_name, r.last_name, r.batch, q.title as quiz_name,
               r.score, r.max_score, r.timestamp
        FROM quiz_results r
        LEFT JOIN quizzes q ON r.quiz_id = q.quiz_id
        ORDER BY r.timestamp DESC
        LIMIT 10
    ''')
    recent_submissions = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        'total_submissions': total_submissions,
        'total_quizzes': total_quizzes,
        'total_batches': total_batches,
        'overall_avg': overall_avg,
        'submissions_by_day': submissions_by_day,
        'score_distribution': score_distribution,
        'quiz_performance': quiz_performance,
        'batch_performance': batch_performance,
        'recent_submissions': recent_submissions
    }


# ============ QUIZ PROGRESS (RESUME FEATURE) ============

def save_quiz_progress(
    quiz_id: str,
    student_data: StudentData,
    current_question: int,
    score: int,
    wrong_attempts: int,
    user_answers: dict,
    is_correct: dict,
    flagged_questions: list,
    partial_scores: dict,
    quiz_start_time: float | None,
    quiz_end_time: float | None
) -> bool:
    """Save quiz progress for resume feature"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO quiz_progress (
            quiz_id, first_name, last_name, batch, current_question, score, 
            wrong_attempts, user_answers, is_correct, flagged_questions,
            partial_scores, quiz_start_time, quiz_end_time, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(quiz_id, first_name, last_name, batch) DO UPDATE SET
            current_question = excluded.current_question,
            score = excluded.score,
            wrong_attempts = excluded.wrong_attempts,
            user_answers = excluded.user_answers,
            is_correct = excluded.is_correct,
            flagged_questions = excluded.flagged_questions,
            partial_scores = excluded.partial_scores,
            quiz_start_time = excluded.quiz_start_time,
            quiz_end_time = excluded.quiz_end_time,
            updated_at = CURRENT_TIMESTAMP
    ''', (
        quiz_id,
        student_data['first_name'],
        student_data['last_name'],
        student_data['batch'],
        current_question,
        score,
        wrong_attempts,
        json.dumps(user_answers),
        json.dumps(is_correct),
        json.dumps(flagged_questions),
        json.dumps(partial_scores),
        quiz_start_time,
        quiz_end_time
    ))
    
    conn.commit()
    conn.close()
    return True


def get_quiz_progress(quiz_id: str, student_data: StudentData) -> dict[str, Any] | None:
    """Get saved quiz progress for resume"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM quiz_progress 
        WHERE quiz_id = ? AND first_name = ? AND last_name = ? AND batch = ?
    ''', (quiz_id, student_data['first_name'], student_data['last_name'], student_data['batch']))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'id': row['id'],
            'current_question': row['current_question'],
            'score': row['score'],
            'wrong_attempts': row['wrong_attempts'],
            'user_answers': json.loads(row['user_answers']),
            'is_correct': json.loads(row['is_correct']),
            'flagged_questions': json.loads(row['flagged_questions']),
            'partial_scores': json.loads(row['partial_scores']),
            'quiz_start_time': row['quiz_start_time'],
            'quiz_end_time': row['quiz_end_time'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at']
        }
    return None


def delete_quiz_progress(quiz_id: str, student_data: StudentData) -> bool:
    """Delete quiz progress after completion"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM quiz_progress 
        WHERE quiz_id = ? AND first_name = ? AND last_name = ? AND batch = ?
    ''', (quiz_id, student_data['first_name'], student_data['last_name'], student_data['batch']))
    
    conn.commit()
    conn.close()
    return True


# ============ SCORE HISTORY ============

def get_student_score_history(first_name: str, last_name: str, batch: str, quiz_id: str = None) -> list[dict[str, Any]]:
    """Get score history for a student"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if quiz_id:
        cursor.execute('''
            SELECT r.id, r.quiz_id, q.title as quiz_name, r.score, r.max_score, 
                   r.timestamp, ROUND(CAST(r.score AS FLOAT) / r.max_score * 100, 1) as percentage
            FROM quiz_results r
            LEFT JOIN quizzes q ON r.quiz_id = q.quiz_id
            WHERE r.first_name = ? AND r.last_name = ? AND r.batch = ? AND r.quiz_id = ?
            ORDER BY r.timestamp DESC
        ''', (first_name, last_name, batch, quiz_id))
    else:
        cursor.execute('''
            SELECT r.id, r.quiz_id, q.title as quiz_name, r.score, r.max_score, 
                   r.timestamp, ROUND(CAST(r.score AS FLOAT) / r.max_score * 100, 1) as percentage
            FROM quiz_results r
            LEFT JOIN quizzes q ON r.quiz_id = q.quiz_id
            WHERE r.first_name = ? AND r.last_name = ? AND r.batch = ?
            ORDER BY r.timestamp DESC
            LIMIT 20
        ''', (first_name, last_name, batch))
    
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return history


def get_student_stats(first_name: str, last_name: str, batch: str) -> dict[str, Any]:
    """Get overall stats for a student"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(*) as total_attempts,
               COUNT(DISTINCT quiz_id) as quizzes_taken,
               ROUND(AVG(CAST(score AS FLOAT) / max_score * 100), 1) as avg_score,
               MAX(CAST(score AS FLOAT) / max_score * 100) as best_score
        FROM quiz_results
        WHERE first_name = ? AND last_name = ? AND batch = ?
    ''', (first_name, last_name, batch))
    
    row = cursor.fetchone()
    conn.close()
    
    return {
        'total_attempts': row['total_attempts'] or 0,
        'quizzes_taken': row['quizzes_taken'] or 0,
        'avg_score': row['avg_score'] or 0,
        'best_score': round(row['best_score'], 1) if row['best_score'] else 0
    }

