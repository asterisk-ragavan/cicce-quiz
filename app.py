from flask import Flask, render_template, jsonify, request, session, redirect, url_for, flash
import random
import json
import os
import sys
from datetime import datetime
from flask_session import Session

# Path Configuration - Handle both normal and frozen (exe) states
if getattr(sys, 'frozen', False):
    # Running as compiled executable (single file)
    # BUNDLE_DIR = where bundled files are extracted (templates, static, teachers.json)
    BUNDLE_DIR = sys._MEIPASS
    # EXE_DIR = where the exe is located (for questions, results, permissions)
    EXE_DIR = os.path.dirname(sys.executable)
else:
    # Running as script - everything in same folder
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = os.path.dirname(os.path.abspath(__file__))

# Initialize Flask app with BUNDLED templates and static files
app = Flask(__name__,
            template_folder=os.path.join(BUNDLE_DIR, 'templates'),
            static_folder=os.path.join(BUNDLE_DIR, 'static'))
app.secret_key = 'your_secret_key'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(EXE_DIR, 'flask_session')
Session(app)

# Path configuration:
# - BUNDLED (inside exe): templates, static, teachers.json
# - EXTERNAL (next to exe): questions folder, data/results, data/permissions.json
QUESTIONS_FOLDER = os.path.join(EXE_DIR, 'questions')  # External - can add new quizzes
DATA_DIR = os.path.join(EXE_DIR, 'data')  # External - for writable data
TEACHERS_FILE = os.path.join(BUNDLE_DIR, 'data', 'teachers.json')  # Bundled (read-only)
PERMISSIONS_FILE = os.path.join(DATA_DIR, 'permissions.json')  # External (writable)
RESULTS_DIR = os.path.join(DATA_DIR, 'results')  # External (writable)

# Ensure data directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

quiz_title = ''

# ============ HELPER FUNCTIONS ============

def initialize_session(questions):
    """Initialize session variables for a new quiz"""
    session['score'] = 0
    session['wrong_attempts'] = 0
    session['current_question'] = 0
    session['is_correct'] = {}
    session['user_answers'] = {}
    session['questions'] = random.sample(questions, len(questions))
    session['attempts'] = {}
    session['result_saved'] = False
    session.modified = True

def load_teachers():
    """Load teacher credentials from JSON file"""
    if os.path.exists(TEACHERS_FILE):
        with open(TEACHERS_FILE, 'r', encoding='utf8') as f:
            return json.load(f)
    return {}

def load_permissions():
    """Load permissions from JSON file"""
    if os.path.exists(PERMISSIONS_FILE):
        with open(PERMISSIONS_FILE, 'r', encoding='utf8') as f:
            return json.load(f)
    return {}

def save_permissions(permissions):
    """Save permissions to JSON file"""
    with open(PERMISSIONS_FILE, 'w', encoding='utf8') as f:
        json.dump(permissions, f, indent=2)

def check_answer_permission(quiz_file, batch):
    """Check if a batch is allowed to see answers for a quiz"""
    permissions = load_permissions()
    allowed_batches = permissions.get(quiz_file, [])
    return batch in allowed_batches

def save_student_result(student_data, quiz_id, quiz_file, score, max_score, questions, user_answers, is_correct):
    """Save student result to a JSON file"""
    # Create quiz-specific results folder
    quiz_results_dir = os.path.join(RESULTS_DIR, quiz_id)
    os.makedirs(quiz_results_dir, exist_ok=True)
    
    # Generate timestamp
    timestamp = datetime.now()
    timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    timestamp_file = timestamp.strftime("%Y%m%d_%H%M%S")
    
    # Build attempt details
    attempt_details = []
    for idx, question in enumerate(questions):
        # Handle both string and integer keys
        user_selected = user_answers.get(idx, user_answers.get(str(idx), []))
        correct = is_correct.get(idx, is_correct.get(str(idx), False))
        
        # Ensure user_selected is a list
        if not isinstance(user_selected, list):
            user_selected = [user_selected] if user_selected else []
        
        attempt_details.append({
            "question_text": question['question'],
            "options": question['options'],
            "correct_option": question['answer'],
            "selected_option": user_selected,
            "is_correct": correct
        })
    
    # Build result object
    result_data = {
        "student_info": {
            "first_name": student_data['first_name'],
            "last_name": student_data['last_name'],
            "batch": student_data['batch']
        },
        "quiz_meta": {
            "quiz_id": quiz_id,
            "quiz_file": quiz_file,
            "timestamp": timestamp_str,
            "total_score": score,
            "max_score": max_score
        },
        "attempt_details": attempt_details
    }
    
    # Generate filename
    safe_fname = f"{student_data['batch']}_{student_data['first_name']}_{student_data['last_name']}_{timestamp_file}.json"
    safe_fname = "".join(c if c.isalnum() or c in ['_', '-', '.'] else '_' for c in safe_fname)
    
    file_path = os.path.join(quiz_results_dir, safe_fname)
    
    with open(file_path, 'w', encoding='utf8') as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    
    return file_path

def get_quiz_results_summary():
    """Get summary of all quiz results"""
    summary = []
    if os.path.exists(RESULTS_DIR):
        for quiz_folder in os.listdir(RESULTS_DIR):
            quiz_path = os.path.join(RESULTS_DIR, quiz_folder)
            if os.path.isdir(quiz_path):
                result_files = [f for f in os.listdir(quiz_path) if f.endswith('.json')]
                summary.append({
                    'quiz_id': quiz_folder,
                    'submission_count': len(result_files)
                })
    return summary

def get_quiz_submissions(quiz_id):
    """Get all submissions for a specific quiz"""
    submissions = []
    quiz_path = os.path.join(RESULTS_DIR, quiz_id)
    
    if os.path.exists(quiz_path):
        for filename in os.listdir(quiz_path):
            if filename.endswith('.json'):
                file_path = os.path.join(quiz_path, filename)
                with open(file_path, 'r', encoding='utf8') as f:
                    data = json.load(f)
                    submissions.append({
                        'filename': filename,
                        'first_name': data['student_info']['first_name'],
                        'last_name': data['student_info']['last_name'],
                        'batch': data['student_info']['batch'],
                        'score': data['quiz_meta']['total_score'],
                        'max_score': data['quiz_meta']['max_score'],
                        'timestamp': data['quiz_meta']['timestamp']
                    })
    
    # Sort by timestamp descending
    submissions.sort(key=lambda x: x['timestamp'], reverse=True)
    return submissions

def load_student_result(quiz_id, filename):
    """Load a specific student result file"""
    file_path = os.path.join(RESULTS_DIR, quiz_id, filename)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf8') as f:
            return json.load(f)
    return None

# ============ STUDENT ROUTES ============

@app.route('/')
def index():
    """Home page - List all available quizzes"""
    question_files = [f.replace('.json', '') for f in os.listdir(QUESTIONS_FOLDER) if f.endswith('.json')]
    return render_template('index.html', question_files=question_files)

@app.route('/student-details')
def student_details():
    """Page to collect student information before quiz"""
    quiz_file = request.args.get('quiz', '')
    if not quiz_file:
        flash('Please select a quiz first.', 'warning')
        return redirect(url_for('index'))
    return render_template('student_details.html', quiz_file=quiz_file)

@app.route('/set-student-details', methods=['POST'])
def set_student_details():
    """Save student details to session and start quiz"""
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    batch = request.form.get('batch', '').strip()
    quiz_file = request.form.get('quiz_file', '').strip()
    
    if not all([first_name, last_name, batch, quiz_file]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('student_details', quiz=quiz_file))
    
    # Store student data in session
    session['student_data'] = {
        'first_name': first_name,
        'last_name': last_name,
        'batch': batch
    }
    session.modified = True
    
    # Load quiz questions
    global quiz_title
    quiz_title = quiz_file
    session['current_quiz_file'] = quiz_file + '.json'
    session['current_quiz_id'] = quiz_file.replace(' ', '_').lower()
    
    file_path = os.path.join(QUESTIONS_FOLDER, quiz_file + '.json')
    
    if not os.path.exists(file_path):
        flash('Quiz file not found.', 'danger')
        return redirect(url_for('index'))
    
    with open(file_path, 'r', encoding='utf8') as f:
        questions = json.load(f)
    
    initialize_session(questions)
    
    return redirect(url_for('quiz'))

@app.route('/clear-student')
def clear_student():
    """Clear student session data"""
    session.pop('student_data', None)
    flash('Session cleared.', 'info')
    return redirect(url_for('index'))

@app.route('/load_questions', methods=['POST'])
def load_questions():
    """Load questions for a quiz (AJAX endpoint)"""
    selected_file = request.json['file_name'] + '.json'
    global quiz_title
    quiz_title = request.json['file_name']
    
    # Check if student data exists
    if not session.get('student_data'):
        return jsonify({'redirect': url_for('student_details', quiz=request.json['file_name'])})
    
    session['current_quiz_file'] = selected_file
    session['current_quiz_id'] = request.json['file_name'].replace(' ', '_').lower()
    
    file_path = os.path.join(QUESTIONS_FOLDER, selected_file)
    
    with open(file_path, 'r', encoding='utf8') as f:
        questions = json.load(f)
    
    initialize_session(questions)
    
    return jsonify('success')

@app.route('/quiz', methods=['GET'])
def quiz():
    """Quiz page - Display current question"""
    if 'current_question' not in session:
        return redirect(url_for('index'))
    
    if not session.get('student_data'):
        flash('Please enter your details first.', 'warning')
        return redirect(url_for('index'))
    
    if session['current_question'] >= len(session['questions']):
        return redirect(url_for('result'))
    
    current_question = session['questions'][session['current_question']]
    random.shuffle(current_question['options'])
    
    # Check if student can view answers during quiz
    show_answers_during_quiz = False
    if session.get('student_data'):
        student_batch = session['student_data'].get('batch', '')
        quiz_file = session.get('current_quiz_file', '')
        show_answers_during_quiz = check_answer_permission(quiz_file, student_batch)
    
    return render_template('quiz.html',
                         quiz_title=quiz_title,
                         question=current_question,
                         score=session['score'],
                         wrong_attempts=session['wrong_attempts'],
                         question_index=session['current_question'],
                         total_questions=len(session['questions']),
                         show_answers=show_answers_during_quiz)

@app.route('/check_answer', methods=['POST'])
def check_answer():
    """Check if submitted answer is correct"""
    selected_options = request.json.get('selected_options')
    question_index = session['current_question']
    current_question = session['questions'][question_index]
    correct_answer = current_question['answer']

    selected_options = [option.strip() for option in selected_options]
    correct_answer = [option.strip() for option in correct_answer]
    
    if set(selected_options) == set(correct_answer):
        if question_index not in session['attempts']:
            session['score'] += 1
            session['user_answers'][question_index] = selected_options
            session['attempts'][question_index] = True
            session['is_correct'][question_index] = True
            session.modified = True
        return jsonify({'result': 'correct', 'score': session['score']})
    else:
        if question_index not in session['attempts']:
            session['wrong_attempts'] += 1
            session['attempts'][question_index] = True
        session['is_correct'][question_index] = False
        session['user_answers'][question_index] = selected_options
        session.modified = True
        return jsonify({'result': 'incorrect', 'score': session['score']})

@app.route('/next', methods=['POST'])
def next_question():
    """Move to next question"""
    session['current_question'] += 1
    session.modified = True
    return jsonify({'status': 'next'})

@app.route('/previous', methods=['POST'])
def previous_question():
    """Move to previous question"""
    if session['current_question'] > 0:
        session['current_question'] -= 1
    session.modified = True
    return jsonify({'status': 'previous'})

@app.route('/get_answer', methods=['GET'])
def get_answer():
    """Get correct answer for current question"""
    # Check permission before revealing answer
    if session.get('student_data'):
        student_batch = session['student_data'].get('batch', '')
        quiz_file = session.get('current_quiz_file', '')
        if not check_answer_permission(quiz_file, student_batch):
            return jsonify(correct_answers=[], error='You do not have permission to view answers')
    
    question_index = session['current_question']
    current_question = session['questions'][question_index]
    correct_answer = current_question['answer']
    return jsonify(correct_answers=correct_answer)

@app.route('/result')
def result():
    """Show quiz results"""
    if 'questions' not in session:
        return redirect(url_for('index'))
    
    # Check permissions for showing answers
    show_answers = True
    is_teacher = session.get('is_teacher', False)
    
    student_batch = ''
    quiz_file = session.get('current_quiz_file', '')
    
    print(f"DEBUG: student_data = {session.get('student_data')}")
    print(f"DEBUG: result_saved = {session.get('result_saved')}")
    print(f"DEBUG: is_teacher = {is_teacher}")
    print(f"DEBUG: quiz_file = {quiz_file}")
    print(f"DEBUG: current_quiz_id = {session.get('current_quiz_id')}")
    
    if session.get('student_data'):
        student_batch = session['student_data'].get('batch', '')
        
        if not is_teacher:
            show_answers = check_answer_permission(quiz_file, student_batch)
        
        # Save result to file (only for students, not teachers reviewing)
        if not session.get('result_saved') and not is_teacher:
            try:
                print(f"DEBUG: Attempting to save result...")
                save_student_result(
                    student_data=session['student_data'],
                    quiz_id=session.get('current_quiz_id', 'unknown'),
                    quiz_file=quiz_file,
                    score=session['score'],
                    max_score=len(session['questions']),
                    questions=session['questions'],
                    user_answers=session['user_answers'],
                    is_correct=session['is_correct']
                )
                session['result_saved'] = True
                session.modified = True
                print(f"DEBUG: Result saved successfully!")
            except Exception as e:
                print(f"Error saving result: {e}")
                import traceback
                traceback.print_exc()
    else:
        print("DEBUG: No student_data in session!")
    
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
def teacher_login():
    """Teacher login page"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        teachers = load_teachers()
        
        if username in teachers and teachers[username] == password:
            session['is_teacher'] = True
            session['teacher_username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('teacher_dashboard'))
        else:
            flash('Invalid credentials.', 'danger')
    
    return render_template('teacher_login.html')

@app.route('/teacher/logout')
def teacher_logout():
    """Teacher logout"""
    session.pop('is_teacher', None)
    session.pop('teacher_username', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))

@app.route('/teacher/dashboard')
def teacher_dashboard():
    """Teacher dashboard - shows quiz result summary"""
    if not session.get('is_teacher'):
        flash('Please login as teacher.', 'warning')
        return redirect(url_for('teacher_login'))
    
    summary = get_quiz_results_summary()
    return render_template('teacher_dashboard.html', summary=summary)

@app.route('/teacher/quiz/<quiz_id>')
def teacher_quiz_results(quiz_id):
    """View all submissions for a specific quiz"""
    if not session.get('is_teacher'):
        flash('Please login as teacher.', 'warning')
        return redirect(url_for('teacher_login'))
    
    submissions = get_quiz_submissions(quiz_id)
    return render_template('teacher_quiz_results.html', quiz_id=quiz_id, submissions=submissions)

@app.route('/teacher/result/<quiz_id>/<filename>')
def teacher_view_result(quiz_id, filename):
    """View a specific student's result (teacher view)"""
    if not session.get('is_teacher'):
        flash('Please login as teacher.', 'warning')
        return redirect(url_for('teacher_login'))
    
    result_data = load_student_result(quiz_id, filename)
    
    if not result_data:
        flash('Result not found.', 'danger')
        return redirect(url_for('teacher_quiz_results', quiz_id=quiz_id))
    
    return render_template('teacher_view_result.html',
                         result=result_data,
                         quiz_id=quiz_id,
                         filename=filename,
                         show_answers=True)

@app.route('/teacher/settings', methods=['GET', 'POST'])
def teacher_settings():
    """Teacher settings page - manage permissions"""
    if not session.get('is_teacher'):
        flash('Please login as teacher.', 'warning')
        return redirect(url_for('teacher_login'))
    
    if request.method == 'POST':
        permissions = {}
        quiz_files = [f for f in os.listdir(QUESTIONS_FOLDER) if f.endswith('.json')]
        
        for quiz_file in quiz_files:
            batches_str = request.form.get(f'batches_{quiz_file}', '').strip()
            if batches_str:
                batches = [b.strip() for b in batches_str.split(',') if b.strip()]
            else:
                batches = []
            permissions[quiz_file] = batches
        
        save_permissions(permissions)
        flash('Permissions updated successfully!', 'success')
    
    # Load current permissions and quiz files
    permissions = load_permissions()
    quiz_files = [f for f in os.listdir(QUESTIONS_FOLDER) if f.endswith('.json')]
    
    return render_template('teacher_settings.html',
                         permissions=permissions,
                         quiz_files=quiz_files)

@app.route('/teacher/delete-result/<quiz_id>/<filename>', methods=['POST'])
def teacher_delete_result(quiz_id, filename):
    """Delete a specific student result"""
    if not session.get('is_teacher'):
        flash('Please login as teacher.', 'warning')
        return redirect(url_for('teacher_login'))
    
    file_path = os.path.join(RESULTS_DIR, quiz_id, filename)
    
    if os.path.exists(file_path):
        os.remove(file_path)
        flash('Result deleted successfully.', 'success')
    else:
        flash('Result not found.', 'danger')
    
    return redirect(url_for('teacher_quiz_results', quiz_id=quiz_id))

if __name__ == '__main__':
    app.run(debug=True)