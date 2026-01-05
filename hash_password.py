"""
Password Hash Generator Utility
===============================
Use this script to generate secure password hashes for teachers.json

Usage:
    python hash_password.py <password>
    
Example:
    python hash_password.py mySecurePassword123
    
Then copy the output hash to data/teachers.json
"""

import sys
from werkzeug.security import generate_password_hash, check_password_hash


def generate_hash(password: str) -> str:
    """Generate a secure password hash"""
    return generate_password_hash(password, method='pbkdf2:sha256')


def verify_hash(password: str, password_hash: str) -> bool:
    """Verify a password against its hash"""
    return check_password_hash(password_hash, password)


def main() -> None:
    if len(sys.argv) < 2:
        print("Password Hash Generator")
        print("=" * 40)
        print("\nUsage: python hash_password.py <password>")
        print("\nExample:")
        print("  python hash_password.py mySecurePassword123")
        print("\nThen update data/teachers.json with the hash:")
        print('  {')
        print('    "admin": "<paste_hash_here>"')
        print('  }')
        return
    
    password = sys.argv[1]
    password_hash = generate_hash(password)
    
    print("\n" + "=" * 60)
    print("  Password Hash Generated")
    print("=" * 60)
    print(f"\nOriginal password: {password}")
    print(f"\nHash (copy this to teachers.json):")
    print(f"\n{password_hash}")
    
    # Verify the hash works
    if verify_hash(password, password_hash):
        print("\n✓ Hash verification successful!")
    else:
        print("\n✗ Hash verification failed!")
    
    print("\n" + "=" * 60)
    print("  Example teachers.json:")
    print("=" * 60)
    print('{')
    print(f'  "admin": "{password_hash}"')
    print('}')


if __name__ == '__main__':
    main()
