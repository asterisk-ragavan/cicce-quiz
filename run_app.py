"""
Launcher script for the Quiz Application
=========================================
Optimized for Python 3.13+ and Windows 10+

This script is used for creating the executable
Features system tray icon for easy browser access
"""
import os
import sys
import socket
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

# System tray imports
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

# Singleton lock configuration
SINGLETON_PORT = 59123  # Port used for singleton detection
SINGLETON_SOCKET = None


def is_already_running() -> bool:
    """
    Check if another instance is already running.
    Uses a socket bound to a specific port as a lock mechanism.
    """
    global SINGLETON_SOCKET
    try:
        SINGLETON_SOCKET = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        SINGLETON_SOCKET.bind(('127.0.0.1', SINGLETON_PORT))
        SINGLETON_SOCKET.listen(1)
        return False  # No other instance running, we got the lock
    except socket.error:
        return True  # Another instance has the port bound


def signal_existing_instance() -> None:
    """
    Signal the existing instance to open browser by connecting to it.
    """
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(('127.0.0.1', SINGLETON_PORT))
        client.send(b'OPEN_BROWSER')
        client.close()
    except socket.error:
        pass


def listen_for_new_instances() -> None:
    """
    Listen for signals from new instances trying to launch.
    When detected, open the browser.
    """
    global SINGLETON_SOCKET
    if SINGLETON_SOCKET is None:
        return
    
    while True:
        try:
            conn, addr = SINGLETON_SOCKET.accept()
            data = conn.recv(1024)
            if data == b'OPEN_BROWSER':
                webbrowser.open('http://127.0.0.1:5000')
            conn.close()
        except Exception:
            break


# Handle PyInstaller bundled app paths
if getattr(sys, 'frozen', False):
    # Running as compiled executable (single file)
    EXE_DIR: str = os.path.dirname(sys.executable)
    BUNDLE_DIR: str = sys._MEIPASS
else:
    # Running as script
    EXE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR: str = os.path.dirname(os.path.abspath(__file__))

# Change to the exe directory
os.chdir(EXE_DIR)

# Create necessary directories next to the exe
data_dir: str = os.path.join(EXE_DIR, 'data')
questions_dir: str = os.path.join(EXE_DIR, 'questions')

os.makedirs(data_dir, exist_ok=True)
os.makedirs(questions_dir, exist_ok=True)

# Note: Database (quiz_app.db) is created automatically by app.py on startup
# All data (quizzes, results, permissions, teachers) stored in SQLite database

# Copy sample questions if questions folder is empty
if not os.listdir(questions_dir):
    bundled_questions: str = os.path.join(BUNDLE_DIR, 'questions')
    if os.path.exists(bundled_questions):
        for f in os.listdir(bundled_questions):
            src: str = os.path.join(bundled_questions, f)
            dst: str = os.path.join(questions_dir, f)
            if os.path.isfile(src):
                shutil.copy(src, dst)

def open_browser() -> None:
    """Open browser after a short delay"""
    time.sleep(1.5)
    webbrowser.open('http://127.0.0.1:5000')


def create_tray_icon() -> Image.Image:
    """Create a simple icon for the system tray"""
    # Check if custom icon exists
    icon_path = os.path.join(EXE_DIR, 'icon.ico')
    if os.path.exists(icon_path):
        try:
            return Image.open(icon_path)
        except Exception:
            pass
    
    # Also check in bundle directory
    if getattr(sys, 'frozen', False):
        bundled_icon = os.path.join(BUNDLE_DIR, 'icon.ico')
        if os.path.exists(bundled_icon):
            try:
                return Image.open(bundled_icon)
            except Exception:
                pass
    
    # Create a simple colored icon
    size = 64
    image = Image.new('RGB', (size, size), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    # Draw a "Q" for Quiz
    draw.rectangle([4, 4, size-4, size-4], fill=(0, 102, 204), outline=(0, 51, 153))
    draw.ellipse([12, 12, size-12, size-12], fill=(255, 255, 255))
    draw.ellipse([20, 20, size-20, size-20], fill=(0, 102, 204))
    # Add a small tail for the Q
    draw.polygon([(size-20, size-25), (size-10, size-10), (size-25, size-20)], fill=(255, 255, 255))
    
    return image


def on_open_browser(icon, item) -> None:
    """Open browser when menu item is clicked"""
    webbrowser.open('http://127.0.0.1:5000')


def on_quit(icon, item) -> None:
    """Quit the application"""
    icon.stop()
    os._exit(0)


def setup_tray_icon() -> None:
    """Setup and run the system tray icon"""
    if not TRAY_AVAILABLE:
        return
    
    icon_image = create_tray_icon()
    
    menu = pystray.Menu(
        pystray.MenuItem('Open Quiz App', on_open_browser, default=True),
        pystray.MenuItem('Quit', on_quit)
    )
    
    icon = pystray.Icon('QuizApp', icon_image, 'Quiz Application', menu)
    icon.run()


def run_flask_server() -> None:
    """Run the Flask server in a thread"""
    from app import app
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False, threaded=True)

if __name__ == '__main__':
    # Check if another instance is already running
    if is_already_running():
        print("Quiz Application is already running!")
        print("Opening browser to existing instance...")
        signal_existing_instance()
        # Also open browser directly in case signal fails
        webbrowser.open('http://127.0.0.1:5000')
        sys.exit(0)
    
    # Import the Flask app
    from app import app
    
    print("=" * 50)
    print("  Quiz Application - Windows 10+ Optimized")
    print("=" * 50)
    print(f"\n  Starting server at: http://127.0.0.1:5000")
    print(f"  Questions folder: {questions_dir}")
    print(f"  Database: {os.path.join(data_dir, 'quiz_app.db')}")
    print("\n  Press Ctrl+C to stop the server")
    print("=" * 50)
    
    # Start listener for new instance signals
    listener_thread = threading.Thread(target=listen_for_new_instances, daemon=True)
    listener_thread.start()
    
    # Open browser automatically
    threading.Thread(target=open_browser, daemon=True).start()
    
    if TRAY_AVAILABLE:
        # Run Flask server in background thread
        flask_thread = threading.Thread(target=run_flask_server, daemon=True)
        flask_thread.start()
        
        # Run system tray icon in main thread (required for Windows)
        setup_tray_icon()
    else:
        # Run Flask app directly without tray icon
        app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
