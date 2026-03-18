# Quick Reload Guide for Fusion 360 Add-In Development

## Fastest Workflow

### Option 1: Keyboard Shortcut (Fastest)
1. **Edit** your code in your editor
2. **Save** the file (Cmd+S / Ctrl+S)
3. **In Fusion 360**: Press `Cmd+Shift+A` (Mac) or `Ctrl+Shift+A` (Windows)
   - This opens the Add-Ins dialog
4. **Click "Stop"** then **"Run"** to reload

### Option 2: File Watcher Script (Recommended)
1. **Run the watcher** in a terminal:
   ```bash
   cd "/Users/crunch/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/TestDovetailCutter"
   python3 watch_simple.py
   ```
   Or use the advanced version (requires watchdog):
   ```bash
   python3 watch_and_reload.py
   ```
2. **Edit and save** your code - the watcher will notify you
3. **Follow the reload instructions** shown in the terminal

**Note**: `watch_simple.py` uses only Python standard library (no dependencies needed)

### Option 3: Manual Reload
1. **Tools** → **Add-Ins** → **Add-Ins**
2. Find **TestDovetailCutter**
3. Click **Stop** (if running)
4. Click **Run** to reload

## Tips for Faster Development

1. **Keep Add-Ins dialog open**: After opening it once, keep it in the background
2. **Use keyboard shortcuts**: `Cmd+Shift+A` / `Ctrl+Shift+A` is fastest
3. **Test incrementally**: Make small changes and test frequently
4. **Use print() statements**: Check the console output in Fusion 360 for debugging

## Console Output

To see print() output and errors:
- **Mac**: View → Show Text Commands
- **Windows**: View → Show Text Commands
- Or check the **Text Commands** panel at the bottom

## Troubleshooting

**Add-in not reloading?**
- Make sure you clicked "Stop" before "Run"
- Check that the file was actually saved
- Restart Fusion 360 if needed

**Changes not appearing?**
- Verify the file path is correct
- Check for syntax errors (they'll appear in console)
- Make sure you're editing the right file
