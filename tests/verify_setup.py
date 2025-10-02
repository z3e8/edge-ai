#!/usr/bin/env python3
"""verify setup is complete and all components work"""

import sys
import os

def check_dependencies():
    """check that all required deps are installed"""
    print("checking dependencies...")
    required = ['flask', 'tensorflow', 'PIL', 'numpy', 'requests']
    
    for module in required:
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except ImportError:
            print(f"  ✗ {module} - not installed")
            return False
    
    return True

def check_structure():
    """check that all expected files exist"""
    print("\nchecking project structure...")
    files = [
        'src/app.py',
        'src/model.py',
        'src/preprocessing.py',
        'src/logging_config.py',
        'tests/test_basic.py',
        'tests/load_test.py',
        'tests/demo.py',
        'requirements.txt',
        'README.md',
        'edge-ai.service'
    ]
    
    all_exist = True
    for f in files:
        exists = os.path.exists(f)
        status = "✓" if exists else "✗"
        print(f"  {status} {f}")
        if not exists:
            all_exist = False
    
    return all_exist

def main():
    print("=" * 60)
    print("  Edge AI Platform - Setup Verification")
    print("=" * 60 + "\n")
    
    deps_ok = check_dependencies()
    struct_ok = check_structure()
    
    print("\n" + "=" * 60)
    if deps_ok and struct_ok:
        print("✓ Setup verification passed!")
        print("\nNext steps:")
        print("  1. Start service: python3 src/app.py")
        print("  2. Run tests: python3 tests/test_basic.py")
        print("  3. Run demo: python3 tests/demo.py")
    else:
        print("✗ Setup verification failed")
        print("\nPlease install dependencies: pip install -r requirements.txt")
        sys.exit(1)
    
    print("=" * 60)

if __name__ == '__main__':
    main()

