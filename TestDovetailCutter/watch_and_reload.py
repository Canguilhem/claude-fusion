#!/usr/bin/env python3
"""
File Watcher for Fusion 360 Add-In Development

This script watches for changes to TestDovetailCutter.py and provides
instructions for reloading the add-in in Fusion 360.

Usage:
    python3 watch_and_reload.py

If watchdog is not installed, use watch_simple.py instead (no dependencies).
"""

import time
import sys
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    print("⚠️  watchdog not installed. Falling back to simple polling method...")
    print("💡 For better performance, install watchdog: pip install --break-system-packages watchdog")
    print("   Or use watch_simple.py which doesn't require watchdog\n")


class AddInFileHandler(FileSystemEventHandler):
    """Handler for file change events"""
    
    def __init__(self, file_path):
        self.file_path = file_path
        self.last_modified = file_path.stat().st_mtime
        
    def on_modified(self, event):
        if event.src_path == str(self.file_path):
            # Check if file was actually modified (not just accessed)
            current_mtime = self.file_path.stat().st_mtime
            if current_mtime != self.last_modified:
                self.last_modified = current_mtime
                self.on_file_changed()
    
    def on_file_changed(self):
        """Called when the add-in file is modified"""
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


def watch_simple(addin_file):
    """Simple polling-based watcher (no external dependencies)"""
    print("="*60)
    print("👀 Watching for changes to TestDovetailCutter.py (simple mode)")
    print(f"📁 Watching: {addin_file}")
    print("="*60)
    print("\n💡 TIP: Keep this terminal open while editing.")
    print("   When you save changes, reload instructions will appear.\n")
    print("Press Ctrl+C to stop watching.\n")
    
    def get_mtime():
        try:
            return addin_file.stat().st_mtime
        except:
            return 0
    
    last_mtime = get_mtime()
    
    try:
        while True:
            time.sleep(0.5)  # Check every 0.5 seconds
            current_mtime = get_mtime()
            
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


def main():
    script_dir = Path(__file__).parent
    addin_file = script_dir / "TestDovetailCutter.py"
    
    if not addin_file.exists():
        print(f"ERROR: {addin_file} not found!")
        sys.exit(1)
    
    if not HAS_WATCHDOG:
        watch_simple(addin_file)
        return
    
    # Use watchdog if available
    print("="*60)
    print("👀 Watching for changes to TestDovetailCutter.py")
    print(f"📁 Watching: {addin_file}")
    print("="*60)
    print("\n💡 TIP: Keep this terminal open while editing.")
    print("   When you save changes, reload instructions will appear.\n")
    print("Press Ctrl+C to stop watching.\n")
    
    event_handler = AddInFileHandler(addin_file)
    observer = Observer()
    observer.schedule(event_handler, path=str(script_dir), recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n\n👋 Stopped watching. Goodbye!")
    
    observer.join()


if __name__ == "__main__":
    main()
