"""
Menu bar icon (Mac) / system tray icon (Windows) for the assistant window.

Click the icon to open the assistant. Right-click it for a menu:
Open assistant, Today's brief, Code with Claude…, Quit.
Closing the window only hides it; the icon stays, so the assistant is always one click away.

It uses the icon support built into Tk 9 (the window toolkit that comes with Python),
so there's nothing extra to install. To check your version:
    python3 -c "import tkinter; print(tkinter.TkVersion)"
With an older Tk it uses pystray instead on Windows and Linux (pip install pystray Pillow).
On a Mac with an older Tk there's no icon, and the window works as before. (pystray can't be
used there: on a Mac it crashes when it shares a program with a tkinter window.)
"""

import base64
import io
import platform
import tkinter as tk

try:
    import pystray
    from PIL import Image
except ImportError:
    pystray = None

ON_MAC = platform.system() == "Darwin"

# An 18x18 chat bubble (PNG). The menu bar on a Mac shows it in black or white to match the theme.
ICON_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAABIAAAASCAYAAABWzo5XAAACsElEQVR42p2UT2hdRRTGf+fMzLv9k2J3mlAC3RlpFy5c"
    "N+BO8MVSUhD6aNxU3Il24UJ5qbiUFu3KXeIDhQSlTZq1hUIEly11pQtRU1tblfx57917Z+a4uHmhtP7tBwPDnJlvzjnf"
    "NyOM0O0qTCtMZ/4Lrl9XpqczF+Sh/WbCk6LbVQDBTBCx8c7SpPin3oJ83FIC+VtyE/Wg/vs42L5877OTtzATAZPJ19aO"
    "RvM3tDg4YakC/i1BQzRgcbgtsXzxp09f/saDWEwr77sDYxOp//vQEIdgu+mq0fTg4TmGCP2s+w6N5Vh9CHbCAyD6fK77"
    "BrQ0FIoomGGpRn3RnI0l6gKIgGUsDszqgQFTk2+sHdYmVckYIr4luR6uW9WfyfVgQZzfsrgzZ3FnTpzfyvVgoYkN18UV"
    "mCEIOVde/Kh/YKBexMrzG7321+Ovrqwn6+/80ptZBHimc/UFiTK/8Xn7/kRn5Vc0rJMHe4oLwMTZa7fEtY4BZrG6asIH"
    "AqdwxRyp7gDgQo9ULhh8Ica7ElqvWIpg+Z56P7VLtPqt+GLK6ipLKNRSjbgA9og3RRnFLA5NNIileB8rnvW7KjwQ8dmo"
    "ktUlCGp1mZuSxUaSI2JgajFnEFAHKW4eOFxvN660fAkXVJwPe0YUFMQQtBmigGtkw4mo09aYM8kffXf5pVLpdvXn3syX"
    "afjb64j+CM4wM8AkFPoXZjSQbOrvpp0H791ZbH9M17S5fXbJsXw6PX1m9ZhzchORrH6/S1X/HfHuSi5Lp0WRAChLKA4R"
    "0ubdHxZP/jEqv+nRc7eN2SUXijDMMSYNB30ebr59p9e++I8vZXbJsSwJwO8tLp9OsXMt+H1jPldb5zd67Yuc+yQwfi7B"
    "/CMM83ABG5E89hUcmVs7Pt5ZfROAE195nhy7inVN/+/JPwHvfk4/udEEbwAAAABJRU5ErkJggg=="
)


def start(window):
    """Show the icon, and make the window's close button hide the window instead of quitting.
    Returns "tk" or a pystray icon (pass it to stop() when the window is gone), or None."""
    root = window.root
    if _tk_has_systray(root):
        icon = _start_tk_icon(window)
    elif not ON_MAC and pystray is not None:
        icon = _start_pystray_icon(window)
    else:
        if ON_MAC:
            print("Tip: the menu bar icon needs Tk 9 or newer (see tray.py).")
        else:
            print("Tip: run  pip install pystray Pillow  to keep the assistant in your system tray.")
        return None
    root.protocol("WM_DELETE_WINDOW", window.hide)
    return icon


def stop(icon):
    """Remove the icon when the app quits."""
    if icon is None or icon == "tk":
        return  # Tk's icon goes away with the window (or by Quit, below)
    try:
        icon.stop()  # pystray: ends the icon's thread, so the program can exit
    except Exception:
        pass  # the app is closing anyway


def quit_app(root):
    """Quit from the icon's menu: remove the icon, then close the window for good."""
    try:
        root.tk.call("tk", "systray", "destroy")
    except tk.TclError:
        pass  # no Tk icon (pystray, or none at all)
    root.destroy()


# ---------------------------------------------------------------- Tk 9's built-in icon
def _tk_has_systray(root):
    try:
        root.tk.call("tk", "systray", "exists")
        return True
    except tk.TclError:  # "unknown or ambiguous subcommand": this Tk is older than 9
        return False


def _start_tk_icon(window):
    root = window.root
    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="Open assistant", command=window.show)
    menu.add_command(label="Today's brief", command=window.brief)
    menu.add_command(label="Code with Claude…", command=window.show_and_code)
    menu.add_separator()
    menu.add_command(label="Quit", command=lambda: quit_app(root))

    def show_menu():
        try:
            menu.tk_popup(root.winfo_pointerx(), root.winfo_pointery())
        finally:
            menu.grab_release()

    image = tk.PhotoImage(master=root, data=ICON_PNG)
    window.tray_image = image  # keep a reference, or Python throws the picture away
    root.tk.call("tk", "systray", "create", "-image", image, "-text", "Your Assistant",
                 "-button1", root.register(window.show), "-button3", root.register(show_menu))
    if ON_MAC:
        _hide_dock_icon()
    return "tk"


def _hide_dock_icon():
    """Mac: no Python icon in the Dock; the assistant lives in the menu bar instead.
    Needs pyobjc-framework-Cocoa (pip install pyobjc-framework-Cocoa); skipped without it."""
    try:
        import AppKit
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(
            AppKit.NSApplicationActivationPolicyAccessory)
    except Exception:
        pass  # not essential: the Dock icon just stays


# ---------------------------------------------------------------- pystray (older Tk, Windows/Linux)
def _start_pystray_icon(window):
    root = window.root

    def later(action):
        # Clicks arrive on the icon's own thread; hand them to the window's thread.
        return lambda icon, item: root.after(0, action)

    menu = pystray.Menu(
        pystray.MenuItem("Open assistant", later(window.show), default=True),  # default = left-click
        pystray.MenuItem("Today's brief", later(window.brief)),
        pystray.MenuItem("Code with Claude…", later(window.show_and_code)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", later(lambda: quit_app(root))),
    )
    image = Image.open(io.BytesIO(base64.b64decode(ICON_PNG)))
    icon = pystray.Icon("assistant", image, "Your Assistant", menu)
    icon.run_detached()  # runs the icon on its own thread
    return icon
