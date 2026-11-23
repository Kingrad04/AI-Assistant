"""
Connects your assistant to Claude for coding.

open_claude(folder) opens Claude Code (Claude's coding tool, which signs in with
your claude.ai account) in a new terminal window inside your project folder.
Claude Code can then read your code, find and fix bugs, write new code and run it.

If Claude Code isn't installed, it opens claude.ai/code in your browser instead
and tells you how to install it.
"""

import os
import platform
import shlex
import shutil
import subprocess
import webbrowser
from pathlib import Path

CLAUDE_WEB = "https://claude.ai/code"
INSTALL_HELP = {
    "Darwin": "curl -fsSL https://claude.ai/install.sh | bash",
    "Windows": "irm https://claude.ai/install.ps1 | iex      (in PowerShell)",
    "Linux": "curl -fsSL https://claude.ai/install.sh | bash",
}


def as_path(folder):
    return Path(folder).expanduser().resolve()


def is_folder(folder):
    return as_path(folder).is_dir()


def find_claude():
    """Full path to the claude command, or None if Claude Code isn't installed.

    Apps started at login (like the morning window) get a short PATH that usually leaves out
    the folders Claude Code installs into, so we also look in those folders directly."""
    found = shutil.which("claude")
    if found:
        return found
    for path in (Path.home() / ".local" / "bin" / "claude",  # the official installer
                 Path("/opt/homebrew/bin/claude"),            # Homebrew on Apple Silicon Macs
                 Path("/usr/local/bin/claude")):              # Homebrew on Intel Macs, npm
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def claude_installed():
    return find_claude() is not None


def _open_terminal(folder, claude="claude"):
    system = platform.system()
    if system == "Darwin":
        # Use the full path, in case the new Terminal window can't find claude on its PATH either.
        command = f"cd {shlex.quote(str(folder))} && {shlex.quote(claude)}"
        applescript_text = command.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(["osascript",
                        "-e", f'tell application "Terminal" to do script "{applescript_text}"',
                        "-e", 'tell application "Terminal" to activate'], check=True)
    elif system == "Windows":
        # Opens a new console window titled "Claude Code" in the folder and starts claude.
        subprocess.Popen(["cmd", "/c", "start", "Claude Code", "cmd", "/k", "claude"],
                         cwd=str(folder), creationflags=0x08000000)
    else:
        for term in ("x-terminal-emulator", "gnome-terminal", "konsole"):
            if shutil.which(term):
                subprocess.Popen([term, "-e", claude], cwd=str(folder))
                return
        raise OSError("couldn't find a terminal app")


def open_claude(folder=None):
    """Open Claude Code in `folder`. Returns a message to show the user."""
    if folder is None:
        folder = Path.home()
    folder = as_path(folder)
    if not folder.is_dir():
        return f"That folder doesn't exist: {folder}"

    claude = find_claude()
    if claude is None:
        webbrowser.open(CLAUDE_WEB)
        cmd = INSTALL_HELP.get(platform.system(), INSTALL_HELP["Linux"])
        return ("Claude Code isn't installed yet, so I opened claude.ai/code in your browser.\n"
                f"To code with Claude on your own files, install it once with:\n  {cmd}\n"
                "Then open a new terminal, run: claude  and sign in with your claude.ai account.")
    try:
        _open_terminal(folder, claude)
    except (OSError, subprocess.CalledProcessError) as e:
        return f"Couldn't open a terminal ({e}). Open one yourself and run:\n  cd \"{folder}\"\n  claude"
    return (f"Opened Claude Code in {folder}.\n"
            "Tell it what you need, e.g. \"find the bug in login.py\", \"write tests for utils\", "
            "or \"build a script that renames my photos by date\".")
