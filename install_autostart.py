"""
Make the morning assistant open automatically when you log in.

  python install_autostart.py              turn it on
  python install_autostart.py --uninstall  turn it off

Run this with the same Python you use for the assistant (the one where
you ran "pip install anthropic").
"""

import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "morning.py"
LABEL = "com.personal.assistant"


# ---------------------------------------------------------------- macOS
def mac_plist_path():
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def mac_install():
    protected = [Path.home() / d for d in ("Desktop", "Documents", "Downloads")]
    if any(p in HERE.parents or p == HERE for p in protected):
        print("Warning: macOS may block apps started at login from reading Desktop, "
              "Documents or Downloads.\nIf the window doesn't appear, move this folder "
              f"to your home folder (e.g. {Path.home() / 'assistant'}) and run this again.\n")
    path = mac_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, str(SCRIPT)],
        "WorkingDirectory": str(HERE),
        "RunAtLoad": True,
        "StandardErrorPath": str(HERE / "morning_error.log"),
    }
    with open(path, "wb") as f:
        plistlib.dump(plist, f)
    print(f"Installed: {path}\nThe assistant will open the next time you log in.")


def mac_uninstall():
    path = mac_plist_path()
    if path.exists():
        subprocess.run(["launchctl", "unload", str(path)], stderr=subprocess.DEVNULL)
        path.unlink()
        print("Removed. The assistant won't open at login any more.")
    else:
        print("It wasn't installed.")


# ---------------------------------------------------------------- Windows
def win_shortcut_path():
    startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / "Personal Assistant.lnk"


def win_install():
    # pythonw.exe runs the app without a black console window.
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    lnk = win_shortcut_path()
    env = dict(os.environ, LNK=str(lnk), TARGET=str(pythonw),
               ARGS=f'"{SCRIPT}"', WORKDIR=str(HERE))
    ps = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); "
          "$s.TargetPath = $env:TARGET; $s.Arguments = $env:ARGS; "
          "$s.WorkingDirectory = $env:WORKDIR; $s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True)
    print(f"Installed: {lnk}\nThe assistant will open the next time you sign in.")


def win_uninstall():
    lnk = win_shortcut_path()
    if lnk.exists():
        lnk.unlink()
        print("Removed. The assistant won't open at sign-in any more.")
    else:
        print("It wasn't installed.")


# ---------------------------------------------------------------- main
def main():
    system = platform.system()
    uninstall = "--uninstall" in sys.argv
    if system == "Darwin":
        mac_uninstall() if uninstall else mac_install()
    elif system == "Windows":
        win_uninstall() if uninstall else win_install()
    else:
        sys.exit("Only macOS and Windows are supported by this installer.")


if __name__ == "__main__":
    main()
