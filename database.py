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
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
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
        cursor.execute('INSERT INTO teachers (username, password_hash) VALUES (?, ?)', ('admin', default_hash))
    
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
        SELECT quiz_id, title, question_count, created_at,
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
