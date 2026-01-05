"""
Build Script for Quiz Application - Windows 7 Compatible
=========================================================

REQUIREMENTS FOR WINDOWS 7 COMPATIBILITY:
1. Python 3.8.x (the last version supporting Windows 7)
   Download: https://www.python.org/downloads/release/python-3819/
   
2. Install required packages:
   pip install -r requirements.txt

3. Run this script OR use: pyinstaller --clean quiz_app.spec

This script will:
- Check Python version compatibility
- Install dependencies if needed
- Build the executable
"""

import subprocess
import sys
import os

def check_python_version():
    """Check if Python version is compatible with Windows 7"""
    version = sys.version_info
    print(f"Python Version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major != 3:
        print("ERROR: Python 3 is required!")
        return False
    
    if version.minor > 8:
        print("")
        print("=" * 60)
        print("  WARNING: Python 3.9+ does NOT support Windows 7!")
        print("=" * 60)
        print("")
        print("  For Windows 7 compatibility, you need Python 3.8.x")
        print("  Download from: https://www.python.org/downloads/release/python-3819/")
        print("")
        print("  The built executable will NOT run on Windows 7!")
        print("=" * 60)
        print("")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            return False
    else:
        print("✓ Python version is compatible with Windows 7")
    
    return True

def install_requirements():
    """Install required packages"""
    print("\nInstalling requirements...")
    requirements_file = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    
    if os.path.exists(requirements_file):
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', requirements_file])
        print("✓ Requirements installed")
    else:
        print("WARNING: requirements.txt not found, installing packages manually...")
        packages = [
            'Flask==2.0.3',
            'Flask-Session==0.4.0',
            'Werkzeug==2.0.3',
            'cachelib==0.6.0',
            'pyinstaller==5.13.2'
        ]
        for pkg in packages:
            subprocess.run([sys.executable, '-m', 'pip', 'install', pkg])

def build_executable():
    """Build the executable using PyInstaller"""
    print("\nBuilding executable...")
    spec_file = os.path.join(os.path.dirname(__file__), 'quiz_app.spec')
    
    if os.path.exists(spec_file):
        result = subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', spec_file])
        if result.returncode == 0:
            print("")
            print("=" * 60)
            print("  BUILD SUCCESSFUL!")
            print("=" * 60)
            print("  Executable location: dist/QuizApp.exe")
            print("")
            print("  To run on Windows 7:")
            print("  1. Copy QuizApp.exe to the target machine")
            print("  2. The questions/ folder will be created on first run")
            print("  3. Add your quiz JSON files to the questions/ folder")
            print("=" * 60)
        else:
            print("ERROR: Build failed!")
            return False
    else:
        print("ERROR: quiz_app.spec not found!")
        return False
    
    return True

def main():
    print("=" * 60)
    print("  Quiz Application Builder - Windows 7 Compatible")
    print("=" * 60)
    print("")
    
    # Change to script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Install requirements
    install_requirements()
    
    # Build executable
    if not build_executable():
        sys.exit(1)

if __name__ == '__main__':
    main()
