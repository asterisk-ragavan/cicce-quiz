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
import random
import os
import sys
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
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(EXE_DIR, 'flask_session')
Session(app)

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
    initialize_session(questions)
    
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
    initialize_session(questions)
    
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
    
    if session['current_question'] >= len(session['questions']):
        return redirect(url_for('result'))
    
    current_question = session['questions'][session['current_question']]
    options = current_question['options'].copy()
    random.shuffle(options)
    
    quiz_id = session.get('current_quiz_id', '')
    student_batch = session['student_data'].get('batch', '')
    show_answers = db.check_answer_permission(quiz_id, student_batch)
    
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
def teacher_login() -> str | Response:
    """Teacher login"""
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


if __name__ == '__main__':
    app.run(debug=True)
