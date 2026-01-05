"""
Build Script for Quiz Application - Windows 10+ Optimized
==========================================================

REQUIREMENTS:
1. Python 3.13+ (recommended for best performance)
   Download: https://www.python.org/downloads/
   
2. Install required packages:
   pip install -r requirements.txt

3. Run this script OR use: pyinstaller --clean quiz_app.spec

This script will:
- Check Python version compatibility
- Install dependencies if needed
- Build the executable with optimizations
"""

import subprocess
import sys
import os

def check_python_version() -> bool:
    """Check if Python version is compatible (3.10+ recommended)"""
    version = sys.version_info
    print(f"Python Version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major != 3:
        print("ERROR: Python 3 is required!")
        return False
    
    if version.minor < 10:
        print("")
        print("=" * 60)
        print("  WARNING: Python 3.10+ is recommended for best performance!")
        print("=" * 60)
        print("")
        print("  Your version will work, but consider upgrading for:")
        print("  - Better error messages")
        print("  - Pattern matching support")
        print("  - Performance improvements")
        print("")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            return False
    
    if version.minor >= 13:
        print("✓ Python 3.13+ detected - Excellent! Best performance available.")
    elif version.minor >= 11:
        print("✓ Python 3.11+ detected - Great performance!")
    else:
        print("✓ Python version is compatible")
    
    return True

def install_requirements() -> None:
    """Install required packages"""
    print("\nInstalling requirements...")
    requirements_file = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    
    if os.path.exists(requirements_file):
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', requirements_file])
        print("✓ Requirements installed")
    else:
        print("WARNING: requirements.txt not found, installing packages manually...")
        packages = [
            'Flask>=3.0.0',
            'Flask-Session>=0.8.0',
            'Werkzeug>=3.0.0',
            'cachelib>=0.12.0',
            'pyinstaller>=6.0.0'
        ]
        for pkg in packages:
            subprocess.run([sys.executable, '-m', 'pip', 'install', pkg])

def build_executable() -> bool:
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
            print("  Deployment instructions:")
            print("  1. Copy QuizApp.exe to the target Windows 10+ machine")
            print("  2. The questions/ folder will be created on first run")
            print("  3. Add your quiz JSON files to the questions/ folder")
            print("  4. Results are stored in data/results/ folder")
            print("")
            print("  Built with Python 3.13+ optimizations!")
            print("=" * 60)
        else:
            print("ERROR: Build failed!")
            return False
    else:
        print("ERROR: quiz_app.spec not found!")
        return False
    
    return True

def main() -> None:
    print("=" * 60)
    print("  Quiz Application Builder - Windows 10+ Optimized")
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
