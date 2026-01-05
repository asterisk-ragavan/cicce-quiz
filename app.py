"""
Quiz Application - Main Flask Application
==========================================
Optimized for Python 3.13+ and Windows 10+

Features:
- Full SQLite database for quizzes, questions, and results
- Auto-import JSON quiz files on startup
- Per-question analytics tracking
- Password hashing for teacher accounts
- Type hints throughout
"""

from flask import Flask, render_template, jsonify, request, session, redirect, url_for, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
import random
import json
import os
import sys
import sqlite3
import hashlib
from datetime import datetime
from flask_session import Session
from typing import Any

# Type aliases for better readability
QuestionDict = dict[str, Any]
StudentData = dict[str, str]
ResultData = dict[str, Any]

# Path Configuration - Handle both normal and frozen (exe) states
if getattr(sys, 'frozen', False):
    BUNDLE_DIR: str = sys._MEIPASS
    EXE_DIR: str = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR: str = os.path.dirname(os.path.abspath(__file__))

# Initialize Flask app
app = Flask(__name__,
            template_folder=os.path.join(BUNDLE_DIR, 'templates'),
            static_folder=os.path.join(BUNDLE_DIR, 'static'))
app.secret_key = 'your_secret_key_change_in_production'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(EXE_DIR, 'flask_session')
Session(app)

# Path configuration
QUESTIONS_FOLDER: str = os.path.join(EXE_DIR, 'questions')
DATA_DIR: str = os.path.join(EXE_DIR, 'data')
TEACHERS_FILE: str = os.path.join(BUNDLE_DIR, 'data', 'teachers.json')
DATABASE_FILE: str = os.path.join(DATA_DIR, 'quiz_app.db')

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(QUESTIONS_FOLDER, exist_ok=True)

# ============ DATABASE FUNCTIONS ============

def get_db_connection() -> sqlite3.Connection:
    """Get a database connection with row factory"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database() -> None:
    """Initialize SQLite database with all required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Quizzes table - metadata about each quiz
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
    
    # Quiz questions table - individual questions
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
    
    # Quiz results table - student submissions
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
    
    # Permissions table - which batches can see answers
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id TEXT NOT NULL,
            batch TEXT NOT NULL,
            UNIQUE(quiz_id, batch),
            FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id) ON DELETE CASCADE
        )
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_questions_quiz ON quiz_questions(quiz_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_results_quiz ON quiz_results(quiz_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_results_batch ON quiz_results(batch)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_results_timestamp ON quiz_results(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_permissions_quiz ON quiz_permissions(quiz_id)')
    
    conn.commit()
    conn.close()


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
    
    # Check if quiz exists
    cursor.execute('SELECT id, file_hash FROM quizzes WHERE quiz_id = ?', (quiz_id,))
    existing = cursor.fetchone()
    
    if existing:
        # Check if file was modified
        if existing['file_hash'] == file_hash:
            conn.close()
            return quiz_id, 0  # No changes
        
        # File modified - update quiz and questions
        cursor.execute('''
            UPDATE quizzes SET file_hash = ?, question_count = ?, updated_at = CURRENT_TIMESTAMP, is_active = 1
            WHERE quiz_id = ?
        ''', (file_hash, len(questions), quiz_id))
        
        # Delete old questions (keep analytics? for now, delete)
        cursor.execute('DELETE FROM quiz_questions WHERE quiz_id = ?', (quiz_id,))
    else:
        # New quiz
        cursor.execute('''
            INSERT INTO quizzes (quiz_id, title, file_path, file_hash, question_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (quiz_id, title, file_path, file_hash, len(questions)))
    
    # Insert questions
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
    
    # Get all JSON files in folder
    json_files = {f.replace('.json', '').replace(' ', '_').lower(): os.path.join(QUESTIONS_FOLDER, f)
                  for f in os.listdir(QUESTIONS_FOLDER) if f.endswith('.json')}
    
    # Import/update each JSON file
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
    
    # Deactivate quizzes whose JSON files were removed
    cursor.execute('SELECT quiz_id FROM quizzes WHERE is_active = 1')
    active_quizzes = [row['quiz_id'] for row in cursor.fetchall()]
    
    for quiz_id in active_quizzes:
        if quiz_id not in json_files:
            cursor.execute('UPDATE quizzes SET is_active = 0 WHERE quiz_id = ?', (quiz_id,))
            results['deactivated'].append(quiz_id)
    
    conn.commit()
    conn.close()
    
    return results


# Initialize database and sync quizzes on startup
init_database()
sync_results = sync_quizzes_from_folder()
if any(sync_results.values()):
    print(f"Quiz sync: {sync_results}")

# ============ HELPER FUNCTIONS ============

def load_teachers() -> dict[str, str]:
    """Load teacher credentials from JSON file"""
    if os.path.exists(TEACHERS_FILE):
        with open(TEACHERS_FILE, 'r', encoding='utf8') as f:
            return json.load(f)
    return {}


def verify_teacher_password(username: str, password: str) -> bool:
    """Verify teacher password with hash support"""
    teachers = load_teachers()
    if username not in teachers:
        return False
    stored_password = teachers[username]
    if stored_password.startswith(('pbkdf2:', 'scrypt:')):
        return check_password_hash(stored_password, password)
    return stored_password == password


def hash_password(password: str) -> str:
    """Generate a secure password hash"""
    return generate_password_hash(password, method='pbkdf2:sha256')


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
        
        # Update question analytics
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
    
    # Add permissions data
    for quiz in summary:
        cursor.execute('SELECT batch_name FROM quiz_permissions WHERE quiz_id = ?', (quiz['quiz_id'],))
        quiz['allowed_batches'] = [row['batch_name'] for row in cursor.fetchall()]
    
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


def load_student_result(result_id: int) -> ResultData | None:
    """Load a specific student result"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM quiz_results WHERE id = ?', (result_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        "student_info": {
            "first_name": row['first_name'],
            "last_name": row['last_name'],
            "batch": row['batch']
        },
        "quiz_meta": {
            "quiz_id": row['quiz_id'],
            "timestamp": row['timestamp'],
            "total_score": row['score'],
            "max_score": row['max_score']
        },
        "attempt_details": json.loads(row['attempt_details'])
    }


def delete_quiz(quiz_id: str, delete_results: bool = False) -> bool:
    """Delete or deactivate a quiz"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if delete_results:
        # Full delete - cascade will remove questions, results, permissions
        cursor.execute('DELETE FROM quizzes WHERE quiz_id = ?', (quiz_id,))
    else:
        # Just deactivate (archive)
        cursor.execute('UPDATE quizzes SET is_active = 0 WHERE quiz_id = ?', (quiz_id,))
    
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    
    # Also delete JSON file if it exists
    if delete_results:
        for f in os.listdir(QUESTIONS_FOLDER):
            if f.endswith('.json') and f.replace('.json', '').replace(' ', '_').lower() == quiz_id:
                os.remove(os.path.join(QUESTIONS_FOLDER, f))
                break
    
    return affected > 0


def initialize_session(questions: list[QuestionDict]) -> None:
    """Initialize session variables for a new quiz"""
    session['score'] = 0
    session['wrong_attempts'] = 0
    session['current_question'] = 0
    session['is_correct'] = {}
    session['user_answers'] = {}
    session['questions'] = questions
    session['attempts'] = {}
    session['result_saved'] = False
    session.modified = True


# ============ STUDENT ROUTES ============

@app.route('/')
def index() -> str:
    """Home page - List all available quizzes"""
    quizzes = get_active_quizzes()
    return render_template('index.html', quizzes=quizzes)


@app.route('/student-details')
def student_details() -> str | Response:
    """Page to collect student information before quiz"""
    quiz_id = request.args.get('quiz', '')
    if not quiz_id:
        flash('Please select a quiz first.', 'warning')
        return redirect(url_for('index'))
    
    quiz_info = get_quiz_info(quiz_id)
    if not quiz_info:
        flash('Quiz not found.', 'danger')
        return redirect(url_for('index'))
    
    return render_template('student_details.html', quiz_id=quiz_id, quiz_name=quiz_info['title'])


@app.route('/set-student-details', methods=['POST'])
def set_student_details() -> Response:
    """Save student details and start quiz"""
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    batch = request.form.get('batch', '').strip()
    quiz_id = request.form.get('quiz_id', '').strip()
    
    if not all([first_name, last_name, batch, quiz_id]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('student_details', quiz=quiz_id))
    
    quiz_info = get_quiz_info(quiz_id)
    if not quiz_info or not quiz_info['is_active']:
        flash('Quiz not available.', 'danger')
        return redirect(url_for('index'))
    
    session['student_data'] = {
        'first_name': first_name,
        'last_name': last_name,
        'batch': batch
    }
    session['current_quiz_id'] = quiz_id
    session['current_quiz_title'] = quiz_info['title']
    
    questions = get_quiz_questions(quiz_id, shuffle=True)
    initialize_session(questions)
    
    return redirect(url_for('quiz'))


@app.route('/clear-student')
def clear_student() -> Response:
    """Clear student session"""
    session.pop('student_data', None)
    flash('Session cleared.', 'info')
    return redirect(url_for('index'))


@app.route('/load_questions', methods=['POST'])
def load_questions() -> Response:
    """Load questions for a quiz (AJAX)"""
    quiz_id = request.json.get('quiz_id', '')
    
    if not session.get('student_data'):
        return jsonify({'redirect': url_for('student_details', quiz=quiz_id)})
    
    quiz_info = get_quiz_info(quiz_id)
    if not quiz_info or not quiz_info['is_active']:
        return jsonify({'error': 'Quiz not available'})
    
    session['current_quiz_id'] = quiz_id
    session['current_quiz_title'] = quiz_info['title']
    
    questions = get_quiz_questions(quiz_id, shuffle=True)
    initialize_session(questions)
    
    return jsonify('success')


@app.route('/quiz', methods=['GET'])
def quiz() -> str | Response:
    """Quiz page"""
    if 'current_question' not in session:
        return redirect(url_for('index'))
    
    if not session.get('student_data'):
        flash('Please enter your details first.', 'warning')
        return redirect(url_for('index'))
    
    if session['current_question'] >= len(session['questions']):
        return redirect(url_for('result'))
    
    current_question = session['questions'][session['current_question']]
    options = current_question['options'].copy()
    random.shuffle(options)
    
    quiz_id = session.get('current_quiz_id', '')
    student_batch = session['student_data'].get('batch', '')
    show_answers = check_answer_permission(quiz_id, student_batch)
    
    return render_template('quiz.html',
                         quiz_title=session.get('current_quiz_title', ''),
                         question=current_question,
                         options=options,
                         score=session['score'],
                         wrong_attempts=session['wrong_attempts'],
                         question_index=session['current_question'],
                         total_questions=len(session['questions']),
                         show_answers=show_answers)


@app.route('/check_answer', methods=['POST'])
def check_answer() -> Response:
    """Check answer"""
    selected_options = request.json.get('selected_options', [])
    question_index = session['current_question']
    current_question = session['questions'][question_index]
    correct_answer = current_question['answer']
    
    selected_options = [opt.strip() for opt in selected_options]
    correct_answer = [opt.strip() for opt in correct_answer]
    
    is_correct = set(selected_options) == set(correct_answer)
    
    if question_index not in session['attempts']:
        session['attempts'][question_index] = True
        session['user_answers'][question_index] = selected_options
        session['is_correct'][question_index] = is_correct
        
        if is_correct:
            session['score'] += 1
        else:
            session['wrong_attempts'] += 1
        
        session.modified = True
    
    return jsonify({'result': 'correct' if is_correct else 'incorrect', 'score': session['score']})


@app.route('/next', methods=['POST'])
def next_question() -> Response:
    """Next question"""
    session['current_question'] += 1
    session.modified = True
    return jsonify({'status': 'next'})


@app.route('/previous', methods=['POST'])
def previous_question() -> Response:
    """Previous question"""
    if session['current_question'] > 0:
        session['current_question'] -= 1
    session.modified = True
    return jsonify({'status': 'previous'})


@app.route('/get_answer', methods=['GET'])
def get_answer() -> Response:
    """Get correct answer"""
    quiz_id = session.get('current_quiz_id', '')
    student_batch = session.get('student_data', {}).get('batch', '')
    
    if not check_answer_permission(quiz_id, student_batch):
        return jsonify(correct_answers=[], error='Permission denied')
    
    question_index = session['current_question']
    current_question = session['questions'][question_index]
    return jsonify(correct_answers=current_question['answer'])


@app.route('/result')
def result() -> str | Response:
    """Show results"""
    if 'questions' not in session:
        return redirect(url_for('index'))
    
    quiz_id = session.get('current_quiz_id', '')
    is_teacher = session.get('is_teacher', False)
    student_batch = session.get('student_data', {}).get('batch', '')
    
    show_answers = is_teacher or check_answer_permission(quiz_id, student_batch)
    
    # Save result
    if not session.get('result_saved') and not is_teacher and session.get('student_data'):
        try:
            save_student_result(
                student_data=session['student_data'],
                quiz_id=quiz_id,
                score=session['score'],
                max_score=len(session['questions']),
                questions=session['questions'],
                user_answers=session['user_answers'],
                is_correct=session['is_correct']
            )
            session['result_saved'] = True
            session.modified = True
        except Exception as e:
            print(f"Error saving result: {e}")
    
    return render_template(
        'result.html',
        score=session['score'],
        total_questions=len(session['questions']),
        wrong_attempts=session['wrong_attempts'],
        user_answers=session['user_answers'],
        is_correct=session['is_correct'],
        show_answers=show_answers,
        student_data=session.get('student_data', {})
    )


# ============ TEACHER ROUTES ============

@app.route('/teacher/login', methods=['GET', 'POST'])
def teacher_login() -> str | Response:
    """Teacher login"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if verify_teacher_password(username, password):
            session['is_teacher'] = True
            session['teacher_username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('teacher_dashboard'))
        else:
            flash('Invalid credentials.', 'danger')
    
    return render_template('teacher_login.html')


@app.route('/teacher/logout')
def teacher_logout() -> Response:
    """Teacher logout"""
    session.pop('is_teacher', None)
    session.pop('teacher_username', None)
    flash('Logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/teacher/dashboard')
def teacher_dashboard() -> str | Response:
    """Teacher dashboard"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    summary = get_quiz_results_summary()
    return render_template('teacher_dashboard.html', summary=summary)


@app.route('/teacher/quiz/<quiz_id>')
def teacher_quiz_results(quiz_id: str) -> str | Response:
    """View quiz submissions"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    quiz_info = get_quiz_info(quiz_id)
    submissions = get_quiz_submissions(quiz_id)
    analytics = get_question_analytics(quiz_id)
    permissions = get_quiz_permissions(quiz_id)
    
    return render_template('teacher_quiz_results.html', 
                          quiz_id=quiz_id,
                          quiz_name=quiz_info['title'] if quiz_info else quiz_id,
                          is_active=quiz_info['is_active'] if quiz_info else True,
                          submissions=submissions,
                          analytics=analytics,
                          permissions=permissions)


@app.route('/teacher/result/<int:result_id>')
def teacher_view_result(result_id: int) -> str | Response:
    """View student result"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    result_data = load_student_result(result_id)
    if not result_data:
        flash('Result not found.', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    return render_template('teacher_view_result.html',
                          result=result_data,
                          result_id=result_id,
                          show_answers=True)


@app.route('/teacher/quiz/<quiz_id>/permissions', methods=['POST'])
def teacher_update_permissions(quiz_id: str) -> Response:
    """Update quiz permissions"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    batches_str = request.form.get('batches', '').strip()
    batches = [b.strip() for b in batches_str.split(',') if b.strip()]
    set_quiz_permissions(quiz_id, batches)
    
    flash('Permissions updated.', 'success')
    return redirect(url_for('teacher_quiz_results', quiz_id=quiz_id))


@app.route('/teacher/quiz/<quiz_id>/toggle', methods=['POST'])
def teacher_toggle_quiz(quiz_id: str) -> Response:
    """Toggle quiz active status"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_active FROM quizzes WHERE quiz_id = ?', (quiz_id,))
    row = cursor.fetchone()
    
    if row:
        new_status = not row['is_active']
        cursor.execute('UPDATE quizzes SET is_active = ? WHERE quiz_id = ?', (new_status, quiz_id))
        conn.commit()
        
        status_text = 'activated' if new_status else 'archived'
        flash(f'Quiz "{quiz_id}" has been {status_text}.', 'success')
    else:
        flash('Quiz not found.', 'danger')
    
    conn.close()
    return redirect(url_for('teacher_quiz_results', quiz_id=quiz_id))


@app.route('/teacher/quiz/<quiz_id>/delete', methods=['POST'])
def teacher_delete_quiz(quiz_id: str) -> Response:
    """Delete quiz"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    delete_results = request.form.get('delete_results') == 'true'
    
    if delete_quiz(quiz_id, delete_results):
        if delete_results:
            flash(f'Quiz "{quiz_id}" and all results deleted.', 'success')
        else:
            flash(f'Quiz "{quiz_id}" archived (results kept).', 'success')
    else:
        flash('Quiz not found.', 'danger')
    
    return redirect(url_for('teacher_dashboard'))


@app.route('/teacher/delete-result/<int:result_id>', methods=['POST'])
def teacher_delete_result(result_id: int) -> Response:
    """Delete result"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT quiz_id FROM quiz_results WHERE id = ?', (result_id,))
    row = cursor.fetchone()
    quiz_id = row['quiz_id'] if row else None
    
    cursor.execute('DELETE FROM quiz_results WHERE id = ?', (result_id,))
    conn.commit()
    conn.close()
    
    flash('Result deleted.', 'success')
    
    if quiz_id:
        return redirect(url_for('teacher_quiz_results', quiz_id=quiz_id))
    return redirect(url_for('teacher_dashboard'))


@app.route('/teacher/sync', methods=['GET', 'POST'])
def teacher_sync_quizzes() -> Response:
    """Manually sync quizzes from folder"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    results = sync_quizzes_from_folder()
    
    messages = []
    if results['imported']:
        messages.append(f"Imported: {', '.join(results['imported'])}")
    if results['updated']:
        messages.append(f"Updated: {', '.join(results['updated'])}")
    if results['deactivated']:
        messages.append(f"Deactivated: {', '.join(results['deactivated'])}")
    
    if messages:
        flash(' | '.join(messages), 'success')
    else:
        flash('All quizzes are up to date.', 'info')
    
    return redirect(url_for('teacher_dashboard'))


@app.route('/teacher/settings', methods=['GET', 'POST'])
def teacher_settings() -> str | Response:
    """Teacher settings"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    if request.method == 'POST':
        # Save permissions for each quiz
        quizzes = get_quiz_results_summary()
        for quiz in quizzes:
            batches_str = request.form.get(f'batches_{quiz["quiz_id"]}', '').strip()
            batches = [b.strip() for b in batches_str.split(',') if b.strip()]
            set_quiz_permissions(quiz['quiz_id'], batches)
        
        flash('Permissions saved successfully.', 'success')
        return redirect(url_for('teacher_settings'))
    
    quizzes = get_quiz_results_summary()
    return render_template('teacher_settings.html', quizzes=quizzes)


if __name__ == '__main__':
    app.run(debug=True)
