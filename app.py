"""
Quiz Application - Main Flask Application
==========================================
Optimized for Python 3.13+ and Windows 10+

Features:
- Full SQLite database for quizzes, questions, and results
- Auto-import JSON quiz files on startup
- Per-question analytics tracking
- Password hashing for teacher accounts
- CSRF protection with Flask-WTF
- Rate limiting for login attempts
- Session timeout for security
- Type hints throughout
"""

from flask import Flask, render_template, jsonify, request, session, redirect, url_for, flash, Response, make_response
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import random
import os
import sys
import csv
import io
from datetime import timedelta
from flask_session import Session
from typing import Any

# Import database functions
import database as db

# Type aliases for better readability
QuestionDict = dict[str, Any]

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

# Session configuration
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(EXE_DIR, 'flask_session')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)  # Session timeout
app.config['SESSION_PERMANENT'] = True
Session(app)

# CSRF Protection
csrf = CSRFProtect(app)

# Rate Limiting (for login protection)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Path configuration
QUESTIONS_FOLDER: str = os.path.join(EXE_DIR, 'questions')
DATA_DIR: str = os.path.join(EXE_DIR, 'data')
DATABASE_FILE: str = os.path.join(DATA_DIR, 'quiz_app.db')

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(QUESTIONS_FOLDER, exist_ok=True)

# Initialize database module with paths
db.init_db(DATABASE_FILE, QUESTIONS_FOLDER)

# Initialize database and sync quizzes on startup
db.init_database()
sync_results = db.sync_quizzes_from_folder()
if sync_results['imported']:
    print(f"Imported quizzes: {', '.join(sync_results['imported'])}")
if sync_results['updated']:
    print(f"Updated quizzes: {', '.join(sync_results['updated'])}")


# ============ SESSION HELPERS ============

def initialize_session(questions: list[QuestionDict], time_limit_minutes: int = 0, partial_credit: bool = True) -> None:
    """Initialize session variables for a new quiz"""
    session['score'] = 0
    session['partial_score'] = 0.0  # For partial credit tracking
    session['wrong_attempts'] = 0
    session['current_question'] = 0
    session['is_correct'] = {}
    session['user_answers'] = {}
    session['questions'] = questions
    session['attempts'] = {}
    session['result_saved'] = False
    session['review_mode'] = False  # For review before submit
    session['quiz_submitted'] = False  # Track if quiz is submitted
    
    # Timer settings
    session['time_limit_minutes'] = time_limit_minutes
    session['partial_credit_enabled'] = partial_credit
    if time_limit_minutes > 0:
        import time
        session['quiz_start_time'] = time.time()
        session['quiz_end_time'] = session['quiz_start_time'] + (time_limit_minutes * 60)
    else:
        session['quiz_start_time'] = None
        session['quiz_end_time'] = None
    
    session.modified = True


@app.before_request
def check_session_timeout() -> Response | None:
    """Check for session timeout and refresh session"""
    session.permanent = True
    # Refresh session on each request to extend timeout
    session.modified = True
    return None


# ============ STUDENT ROUTES ============

@app.route('/')
def index() -> str:
    """Home page - List all available quizzes"""
    quizzes = db.get_active_quizzes()
    return render_template('index.html', quizzes=quizzes)


@app.route('/student-details')
def student_details() -> str | Response:
    """Page to collect student information before quiz"""
    quiz_id = request.args.get('quiz', '')
    if not quiz_id:
        flash('Please select a quiz first.', 'warning')
        return redirect(url_for('index'))
    
    quiz_info = db.get_quiz_info(quiz_id)
    if not quiz_info:
        flash('Quiz not found.', 'danger')
        return redirect(url_for('index'))
    
    # Pass existing student data if available
    student_data = session.get('student_data')
    return render_template('student_details.html', 
                          quiz_id=quiz_id, 
                          quiz_name=quiz_info['title'],
                          quiz_info=quiz_info,
                          student_data=student_data)


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
    
    quiz_info = db.get_quiz_info(quiz_id)
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
    
    questions = db.get_quiz_questions(quiz_id, shuffle=True)
    time_limit = quiz_info.get('time_limit_minutes', 0) or 0
    partial_credit = quiz_info.get('partial_credit', 1) == 1
    initialize_session(questions, time_limit, partial_credit)
    
    return redirect(url_for('quiz'))


@app.route('/clear-student')
def clear_student() -> Response:
    """Clear student session"""
    session.pop('student_data', None)
    flash('Session cleared.', 'info')
    return redirect(url_for('index'))


@app.route('/clear-student-redirect')
def clear_student_and_redirect() -> Response:
    """Clear student session and redirect back to student details"""
    quiz_id = request.args.get('quiz', '')
    session.pop('student_data', None)
    session.pop('current_quiz_id', None)
    session.pop('current_quiz_title', None)
    if quiz_id:
        return redirect(url_for('student_details', quiz=quiz_id))
    return redirect(url_for('index'))


@app.route('/start-quiz-session', methods=['POST'])
def start_quiz_with_session() -> Response:
    """Start quiz using existing session student data"""
    quiz_id = request.form.get('quiz_id', '').strip()
    
    if not session.get('student_data'):
        flash('Please enter your details first.', 'warning')
        return redirect(url_for('student_details', quiz=quiz_id))
    
    quiz_info = db.get_quiz_info(quiz_id)
    if not quiz_info or not quiz_info['is_active']:
        flash('Quiz not available.', 'danger')
        return redirect(url_for('index'))
    
    session['current_quiz_id'] = quiz_id
    session['current_quiz_title'] = quiz_info['title']
    
    questions = db.get_quiz_questions(quiz_id, shuffle=True)
    time_limit = quiz_info.get('time_limit_minutes', 0) or 0
    partial_credit = quiz_info.get('partial_credit', 1) == 1
    initialize_session(questions, time_limit, partial_credit)
    
    return redirect(url_for('quiz'))


@app.route('/load_questions', methods=['POST'])
def load_questions() -> Response:
    """Load questions for a quiz (AJAX) - always redirect to student details for confirmation"""
    quiz_id = request.json.get('quiz_id', '')
    
    # Always redirect to student details page for identity confirmation
    return jsonify({'redirect': url_for('student_details', quiz=quiz_id)})


@app.route('/quiz', methods=['GET'])
def quiz() -> str | Response:
    """Quiz page"""
    if 'current_question' not in session:
        return redirect(url_for('index'))
    
    if not session.get('student_data'):
        flash('Please enter your details first.', 'warning')
        return redirect(url_for('index'))
    
    # Check if quiz is submitted
    if session.get('quiz_submitted'):
        return redirect(url_for('result'))
    
    # Check if time has expired
    import time
    if session.get('quiz_end_time') and time.time() > session['quiz_end_time']:
        # Auto-submit if time expired
        return redirect(url_for('submit_quiz'))
    
    # Check if in review mode or reached end of questions
    if session.get('review_mode') or session['current_question'] >= len(session['questions']):
        return redirect(url_for('review_quiz'))
    
    current_question = session['questions'][session['current_question']]
    options = current_question['options'].copy()
    random.shuffle(options)
    
    quiz_id = session.get('current_quiz_id', '')
    student_batch = session['student_data'].get('batch', '')
    show_answers = db.check_answer_permission(quiz_id, student_batch)
    
    # Calculate remaining time
    remaining_seconds = None
    if session.get('quiz_end_time'):
        remaining_seconds = max(0, int(session['quiz_end_time'] - time.time()))
    
    return render_template('quiz.html',
                         quiz_title=session.get('current_quiz_title', ''),
                         question=current_question,
                         options=options,
                         score=session['score'],
                         wrong_attempts=session['wrong_attempts'],
                         question_index=session['current_question'],
                         total_questions=len(session['questions']),
                         show_answers=show_answers,
                         time_limit_minutes=session.get('time_limit_minutes', 0),
                         remaining_seconds=remaining_seconds,
                         partial_credit_enabled=session.get('partial_credit_enabled', True),
                         user_answers=session.get('user_answers', {}),
                         is_correct=session.get('is_correct', {}))


@app.route('/check_answer', methods=['POST'])
def check_answer() -> Response:
    """Check answer with partial credit support"""
    selected_options = request.json.get('selected_options', [])
    question_index = session['current_question']
    current_question = session['questions'][question_index]
    correct_answer = current_question['answer']
    
    selected_options = [opt.strip() for opt in selected_options]
    correct_answer = [opt.strip() for opt in correct_answer]
    
    is_correct = set(selected_options) == set(correct_answer)
    
    # Calculate partial credit score for multi-select questions
    partial_credit_enabled = session.get('partial_credit_enabled', True)
    partial_score = 0.0
    
    if partial_credit_enabled and len(correct_answer) > 1:
        # Multi-select with partial credit
        partial_score = db.calculate_partial_score(selected_options, correct_answer)
    else:
        # Binary scoring
        partial_score = 1.0 if is_correct else 0.0
    
    if question_index not in session['attempts']:
        session['attempts'][question_index] = True
        session['user_answers'][question_index] = selected_options
        session['is_correct'][question_index] = is_correct
        
        # Track partial scores for multi-select
        if 'partial_scores' not in session:
            session['partial_scores'] = {}
        session['partial_scores'][question_index] = partial_score
        
        if is_correct:
            session['score'] += 1
        else:
            session['wrong_attempts'] += 1
        
        session.modified = True
    
    return jsonify({'result': 'correct' if is_correct else 'incorrect', 'score': session['score']})


@app.route('/next', methods=['POST'])
def next_question() -> Response:
    """Next question - goes to review at the end"""
    session['current_question'] += 1
    session.modified = True
    
    # If we've answered all questions, redirect to review
    if session['current_question'] >= len(session.get('questions', [])):
        return jsonify({'status': 'review', 'redirect': url_for('review_quiz')})
    
    return jsonify({'status': 'next'})


@app.route('/previous', methods=['POST'])
def previous_question() -> Response:
    """Previous question"""
    if session['current_question'] > 0:
        session['current_question'] -= 1
    session.modified = True
    return jsonify({'status': 'previous'})


@app.route('/go_to_question/<int:question_index>', methods=['POST'])
def go_to_question(question_index: int) -> Response:
    """Go to a specific question (for review mode)"""
    if 0 <= question_index < len(session.get('questions', [])):
        session['current_question'] = question_index
        session['review_mode'] = False  # Exit review mode when jumping to a question
        session.modified = True
    return jsonify({'status': 'ok'})


@app.route('/review', methods=['GET'])
def review_quiz() -> str | Response:
    """Review all answers before final submission"""
    if 'questions' not in session:
        return redirect(url_for('index'))
    
    if not session.get('student_data'):
        flash('Please enter your details first.', 'warning')
        return redirect(url_for('index'))
    
    if session.get('quiz_submitted'):
        return redirect(url_for('result'))
    
    # Check if time has expired
    import time
    remaining_seconds = None
    if session.get('quiz_end_time'):
        remaining_seconds = max(0, int(session['quiz_end_time'] - time.time()))
        if remaining_seconds <= 0:
            return redirect(url_for('submit_quiz'))
    
    session['review_mode'] = True
    session.modified = True
    
    # Prepare question summaries
    questions_summary = []
    for idx, question in enumerate(session['questions']):
        user_answer = session.get('user_answers', {}).get(idx, [])
        is_answered = idx in session.get('attempts', {})
        is_correct = session.get('is_correct', {}).get(idx, None)
        partial_score = session.get('partial_scores', {}).get(idx, 0)
        
        questions_summary.append({
            'index': idx,
            'question_text': question['question'][:100] + ('...' if len(question['question']) > 100 else ''),
            'is_answered': is_answered,
            'is_correct': is_correct,
            'user_answer': user_answer,
            'correct_answer': question['answer'],
            'is_multi_select': len(question['answer']) > 1,
            'partial_score': partial_score
        })
    
    answered_count = sum(1 for q in questions_summary if q['is_answered'])
    
    return render_template('review.html',
                         quiz_title=session.get('current_quiz_title', ''),
                         questions_summary=questions_summary,
                         total_questions=len(session['questions']),
                         answered_count=answered_count,
                         score=session['score'],
                         wrong_attempts=session['wrong_attempts'],
                         time_limit_minutes=session.get('time_limit_minutes', 0),
                         remaining_seconds=remaining_seconds,
                         partial_credit_enabled=session.get('partial_credit_enabled', True))


@app.route('/submit_quiz', methods=['GET', 'POST'])
def submit_quiz() -> Response:
    """Final quiz submission"""
    if 'questions' not in session:
        return redirect(url_for('index'))
    
    session['quiz_submitted'] = True
    session['review_mode'] = False
    session.modified = True
    
    return redirect(url_for('result'))


@app.route('/get_remaining_time', methods=['GET'])
def get_remaining_time() -> Response:
    """Get remaining time for the quiz (AJAX endpoint)"""
    import time
    if session.get('quiz_end_time'):
        remaining = max(0, int(session['quiz_end_time'] - time.time()))
        return jsonify({'remaining_seconds': remaining, 'expired': remaining <= 0})
    return jsonify({'remaining_seconds': None, 'expired': False})


@app.route('/get_answer', methods=['GET'])
def get_answer() -> Response:
    """Get correct answer"""
    quiz_id = session.get('current_quiz_id', '')
    student_batch = session.get('student_data', {}).get('batch', '')
    
    if not db.check_answer_permission(quiz_id, student_batch):
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
    
    show_answers = is_teacher or db.check_answer_permission(quiz_id, student_batch)
    
    # Save result
    if not session.get('result_saved') and not is_teacher and session.get('student_data'):
        try:
            db.save_student_result(
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
@limiter.limit("5 per minute", methods=["POST"])  # Rate limit login attempts
def teacher_login() -> str | Response:
    """Teacher login with rate limiting"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if db.verify_teacher_password(username, password):
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
    
    summary = db.get_quiz_results_summary()
    return render_template('teacher_dashboard.html', summary=summary)


@app.route('/teacher/quiz/<quiz_id>')
def teacher_quiz_results(quiz_id: str) -> str | Response:
    """View quiz submissions"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    quiz_info = db.get_quiz_info(quiz_id)
    submissions = db.get_quiz_submissions(quiz_id)
    analytics = db.get_question_analytics(quiz_id)
    permissions = db.get_quiz_permissions(quiz_id)
    
    return render_template('teacher_quiz_results.html', 
                          quiz_id=quiz_id,
                          quiz_name=quiz_info['title'] if quiz_info else quiz_id,
                          is_active=quiz_info['is_active'] if quiz_info else True,
                          time_limit_minutes=quiz_info.get('time_limit_minutes', 0) if quiz_info else 0,
                          partial_credit=quiz_info.get('partial_credit', 1) if quiz_info else 1,
                          submissions=submissions,
                          analytics=analytics,
                          permissions=permissions)


@app.route('/teacher/result/<int:result_id>')
def teacher_view_result(result_id: int) -> str | Response:
    """View student result"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    result_data = db.load_student_result(result_id)
    if not result_data:
        flash('Result not found.', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    return render_template('teacher_view_result.html',
                          result=result_data,
                          result_id=result_id,
                          show_answers=True)


@app.route('/teacher/quiz/<quiz_id>/settings', methods=['POST'])
def teacher_update_quiz_settings(quiz_id: str) -> Response:
    """Update quiz settings (time limit, partial credit)"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    time_limit_minutes = int(request.form.get('time_limit_minutes', 0) or 0)
    partial_credit = request.form.get('partial_credit') == 'on'
    
    db.update_quiz_settings(quiz_id, time_limit_minutes, partial_credit)
    
    flash('Quiz settings updated.', 'success')
    return redirect(url_for('teacher_quiz_results', quiz_id=quiz_id))


@app.route('/teacher/quiz/<quiz_id>/permissions', methods=['POST'])
def teacher_update_permissions(quiz_id: str) -> Response:
    """Update quiz permissions"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    batches_str = request.form.get('batches', '').strip()
    batches = [b.strip() for b in batches_str.split(',') if b.strip()]
    db.set_quiz_permissions(quiz_id, batches)
    
    flash('Permissions updated.', 'success')
    return redirect(url_for('teacher_quiz_results', quiz_id=quiz_id))


@app.route('/teacher/quiz/<quiz_id>/toggle', methods=['POST'])
def teacher_toggle_quiz(quiz_id: str) -> Response:
    """Toggle quiz active status"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    new_status = db.toggle_quiz_active(quiz_id)
    
    if new_status is not None:
        status_text = 'activated' if new_status else 'archived'
        flash(f'Quiz "{quiz_id}" has been {status_text}.', 'success')
    else:
        flash('Quiz not found.', 'danger')
    
    return redirect(url_for('teacher_quiz_results', quiz_id=quiz_id))


@app.route('/teacher/quiz/<quiz_id>/delete', methods=['POST'])
def teacher_delete_quiz(quiz_id: str) -> Response:
    """Delete quiz"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    delete_results = request.form.get('delete_results') == 'true'
    
    if db.delete_quiz(quiz_id, delete_results):
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
    
    quiz_id = db.delete_result(result_id)
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
    
    results = db.sync_quizzes_from_folder()
    
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
        quizzes = db.get_quiz_results_summary()
        for quiz in quizzes:
            batches_str = request.form.get(f'batches_{quiz["quiz_id"]}', '').strip()
            batches = [b.strip() for b in batches_str.split(',') if b.strip()]
            db.set_quiz_permissions(quiz['quiz_id'], batches)
        
        flash('Permissions saved successfully.', 'success')
        return redirect(url_for('teacher_settings'))
    
    quizzes = db.get_quiz_results_summary()
    return render_template('teacher_settings.html', quizzes=quizzes)


@app.route('/teacher/change-password', methods=['GET', 'POST'])
def teacher_change_password() -> str | Response:
    """Change teacher password"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        username = session.get('teacher_username', 'admin')
        
        # Validate current password
        if not db.verify_teacher_password(username, current_password):
            flash('Current password is incorrect.', 'danger')
            return redirect(url_for('teacher_change_password'))
        
        # Validate new password
        if len(new_password) < 6:
            flash('New password must be at least 6 characters.', 'danger')
            return redirect(url_for('teacher_change_password'))
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return redirect(url_for('teacher_change_password'))
        
        # Update password
        if db.update_teacher_password(username, new_password):
            flash('Password changed successfully!', 'success')
            return redirect(url_for('teacher_settings'))
        else:
            flash('Failed to update password.', 'danger')
    
    return render_template('teacher_change_password.html')


# ============ EXPORT ROUTES ============

@app.route('/teacher/export/quiz/<quiz_id>')
def teacher_export_quiz_csv(quiz_id: str) -> Response:
    """Export quiz results to CSV"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    quiz_info = db.get_quiz_info(quiz_id)
    results = db.get_quiz_results_for_export(quiz_id)
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(['ID', 'First Name', 'Last Name', 'Batch', 'Score', 'Max Score', 'Percentage', 'Date/Time'])
    
    # Data rows
    for r in results:
        writer.writerow([
            r['id'], r['first_name'], r['last_name'], r['batch'],
            r['score'], r['max_score'], f"{r['percentage']}%", r['timestamp']
        ])
    
    # Create response
    output.seek(0)
    response = make_response(output.getvalue())
    quiz_name = quiz_info['title'] if quiz_info else quiz_id
    response.headers['Content-Disposition'] = f'attachment; filename={quiz_name}_results.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response


@app.route('/teacher/export/all')
def teacher_export_all_csv() -> Response:
    """Export all results to CSV"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    results = db.get_all_results_for_export()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(['ID', 'Quiz', 'First Name', 'Last Name', 'Batch', 'Score', 'Max Score', 'Percentage', 'Date/Time'])
    
    # Data rows
    for r in results:
        writer.writerow([
            r['id'], r['quiz_name'], r['first_name'], r['last_name'], r['batch'],
            r['score'], r['max_score'], f"{r['percentage']}%", r['timestamp']
        ])
    
    # Create response
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=all_quiz_results.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response


# ============ ANALYTICS ROUTES ============

@app.route('/teacher/analytics')
def teacher_analytics() -> str | Response:
    """Analytics dashboard with charts"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    analytics = db.get_dashboard_analytics()
    return render_template('teacher_analytics.html', analytics=analytics)


@app.route('/api/analytics')
def api_analytics() -> Response:
    """API endpoint for analytics data (for AJAX refresh)"""
    if not session.get('is_teacher'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    analytics = db.get_dashboard_analytics()
    return jsonify(analytics)


# ============ TEACHER MANAGEMENT ROUTES ============

@app.route('/teacher/manage-teachers')
def teacher_manage_teachers() -> str | Response:
    """Manage teacher accounts"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    # Check if current user is admin
    teacher_info = db.get_teacher_info(session.get('teacher_username', ''))
    if not teacher_info or not teacher_info.get('is_admin'):
        flash('Only admins can manage teacher accounts.', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    teachers = db.get_all_teachers()
    return render_template('teacher_manage_teachers.html', teachers=teachers)


@app.route('/teacher/add-teacher', methods=['POST'])
def teacher_add_teacher() -> Response:
    """Add a new teacher account"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    # Check if current user is admin
    teacher_info = db.get_teacher_info(session.get('teacher_username', ''))
    if not teacher_info or not teacher_info.get('is_admin'):
        flash('Only admins can add teacher accounts.', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    is_admin = request.form.get('is_admin') == 'on'
    
    if not username or not password:
        flash('Username and password are required.', 'danger')
        return redirect(url_for('teacher_manage_teachers'))
    
    if len(password) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('teacher_manage_teachers'))
    
    success, message = db.create_teacher(username, password, is_admin)
    flash(message, 'success' if success else 'danger')
    
    return redirect(url_for('teacher_manage_teachers'))


@app.route('/teacher/delete-teacher/<int:teacher_id>', methods=['POST'])
def teacher_delete_teacher(teacher_id: int) -> Response:
    """Delete a teacher account"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    # Check if current user is admin
    teacher_info = db.get_teacher_info(session.get('teacher_username', ''))
    if not teacher_info or not teacher_info.get('is_admin'):
        flash('Only admins can delete teacher accounts.', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    success, message = db.delete_teacher(teacher_id)
    flash(message, 'success' if success else 'danger')
    
    return redirect(url_for('teacher_manage_teachers'))


# ============ BATCH MANAGEMENT ROUTES ============

@app.route('/teacher/manage-batches')
def teacher_manage_batches() -> str | Response:
    """Manage student batches"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    batches = db.get_all_batches()
    unique_batches = db.get_unique_batches_from_results()
    return render_template('teacher_manage_batches.html', batches=batches, unique_batches=unique_batches)


@app.route('/teacher/add-batch', methods=['POST'])
def teacher_add_batch() -> Response:
    """Add a new batch"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    
    if not name:
        flash('Batch name is required.', 'danger')
        return redirect(url_for('teacher_manage_batches'))
    
    success, message = db.create_batch(name, description)
    flash(message, 'success' if success else 'danger')
    
    return redirect(url_for('teacher_manage_batches'))


@app.route('/teacher/update-batch/<int:batch_id>', methods=['POST'])
def teacher_update_batch(batch_id: int) -> Response:
    """Update a batch"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    is_active = request.form.get('is_active') == 'on'
    
    if not name:
        flash('Batch name is required.', 'danger')
        return redirect(url_for('teacher_manage_batches'))
    
    success, message = db.update_batch(batch_id, name, description, is_active)
    flash(message, 'success' if success else 'danger')
    
    return redirect(url_for('teacher_manage_batches'))


@app.route('/teacher/delete-batch/<int:batch_id>', methods=['POST'])
def teacher_delete_batch(batch_id: int) -> Response:
    """Delete a batch"""
    if not session.get('is_teacher'):
        flash('Please login.', 'warning')
        return redirect(url_for('teacher_login'))
    
    success, message = db.delete_batch(batch_id)
    flash(message, 'success' if success else 'danger')
    
    return redirect(url_for('teacher_manage_batches'))


@app.errorhandler(429)
def ratelimit_handler(e):
    """Handle rate limit exceeded"""
    flash('Too many login attempts. Please wait a minute before trying again.', 'danger')
    return redirect(url_for('teacher_login'))


if __name__ == '__main__':
    app.run(debug=True)
