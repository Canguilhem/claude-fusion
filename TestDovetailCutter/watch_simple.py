#!/usr/bin/env python3
"""
Simple File Watcher for Fusion 360 Add-In Development
(No external dependencies required)

This script watches for changes to TestDovetailCutter.py using only
Python standard library.

Usage:
    python3 watch_simple.py
"""

import time
import sys
from pathlib import Path


def get_file_mtime(file_path):
    """Get file modification time"""
    try:
        return file_path.stat().st_mtime
    except:
        return 0


def main():
    script_dir = Path(__file__).parent
    addin_file = script_dir / "TestDovetailCutter.py"
    
    if not addin_file.exists():
        print(f"ERROR: {addin_file} not found!")
        sys.exit(1)
    
    print("="*60)
    print("👀 Watching for changes to TestDovetailCutter.py")
    print(f"📁 Watching: {addin_file}")
    print("="*60)
    print("\n💡 TIP: Keep this terminal open while editing.")
    print("   When you save changes, reload instructions will appear.\n")
    print("Press Ctrl+C to stop watching.\n")
    
    last_mtime = get_file_mtime(addin_file)
    
    try:
        while True:
            time.sleep(0.5)  # Check every 0.5 seconds
            
            current_mtime = get_file_mtime(addin_file)
            
            if current_mtime > last_mtime:
                last_mtime = current_mtime
                
                print("\n" + "="*60)
                print("⚠️  FILE CHANGED: TestDovetailCutter.py")
                print("="*60)
                print("\n📋 TO RELOAD IN FUSION 360:")
                print("   1. Go to: Tools → Add-Ins → Add-Ins")
                print("   2. Find 'TestDovetailCutter' in the list")
                print("   3. Click 'Stop' (if running)")
                print("   4. Click 'Run' to reload")
                print("\n   OR use keyboard shortcut:")
                print("   - Mac: Cmd+Shift+A")
                print("   - Windows: Ctrl+Shift+A")
                print("\n" + "="*60 + "\n")
                
    except KeyboardInterrupt:
        print("\n\n👋 Stopped watching. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
