"""
Launcher script for the Quiz Application
This script is used for creating the executable
"""
import os
import sys
import webbrowser
import threading
import time
import shutil

# Fix for PyInstaller: Redirect stdout/stderr if they are None
# This prevents AttributeError in click/flask when showing server banner
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# Handle PyInstaller bundled app paths
if getattr(sys, 'frozen', False):
    # Running as compiled executable (single file)
    EXE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = sys._MEIPASS
else:
    # Running as script
    EXE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

# Change to the exe directory
os.chdir(EXE_DIR)

# Create necessary directories next to the exe
data_dir = os.path.join(EXE_DIR, 'data')
results_dir = os.path.join(data_dir, 'results')
questions_dir = os.path.join(EXE_DIR, 'questions')

os.makedirs(data_dir, exist_ok=True)
os.makedirs(results_dir, exist_ok=True)
os.makedirs(questions_dir, exist_ok=True)

# Copy default permissions.json if it doesn't exist
permissions_dest = os.path.join(data_dir, 'permissions.json')
if not os.path.exists(permissions_dest):
    permissions_src = os.path.join(BUNDLE_DIR, 'data', 'permissions.json')
    if os.path.exists(permissions_src):
        shutil.copy(permissions_src, permissions_dest)
    else:
        with open(permissions_dest, 'w') as f:
            f.write('{}')

# Copy sample questions if questions folder is empty
if not os.listdir(questions_dir):
    bundled_questions = os.path.join(BUNDLE_DIR, 'questions')
    if os.path.exists(bundled_questions):
        for f in os.listdir(bundled_questions):
            src = os.path.join(bundled_questions, f)
            dst = os.path.join(questions_dir, f)
            if os.path.isfile(src):
                shutil.copy(src, dst)

def open_browser():
    """Open browser after a short delay"""
    time.sleep(1.5)
    webbrowser.open('http://127.0.0.1:5000')

if __name__ == '__main__':
    # Import the Flask app
    from app import app
    
    print("=" * 50)
    print("  Quiz Application")
    print("=" * 50)
    print(f"\n  Starting server at: http://127.0.0.1:5000")
    print(f"  Questions folder: {questions_dir}")
    print(f"  Results folder: {results_dir}")
    print("\n  Press Ctrl+C to stop the server")
    print("=" * 50)
    
    # Open browser automatically
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Run the Flask app
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
