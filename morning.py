"""
Morning greeting window for your personal assistant.

Opens a small window that greets you and tells you what to do today,
then lets you keep chatting. install_autostart.py makes it open by
itself every time you log in to your Mac or Windows laptop.
It also puts an icon in the menu bar (Mac) or system tray (Windows), and
closing the window then just hides it. See tray.py.

Run it by hand:  python morning.py
"""

import os
import platform
import subprocess
import threading
import time
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import filedialog, scrolledtext

import assistant as core
import tray

GREETING_PROMPT = (
    "It's {now}. I just opened my laptop. Greet me in one short, warm line "
    "(use my name if you know it). Then check my tasks and tell me what I need to do today: "
    "anything overdue, things due today, and anything due in the next 3 days that's worth starting. "
    "Suggest an order to do them in. Keep it under 120 words."
)


def time_greeting():
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def local_summary(data, name=""):
    """A greeting built without the AI, used when there's no internet or no API key."""
    today = date.today().isoformat()
    soon_limit = (date.today() + timedelta(days=3)).isoformat()
    open_tasks = [t for t in data["tasks"] if not t["done"]]
    overdue = [t for t in open_tasks if t.get("due") and t["due"] < today]
    due_today = [t for t in open_tasks if t.get("due") == today]
    soon = [t for t in open_tasks if t.get("due") and today < t["due"] <= soon_limit]

    lines = [f"{time_greeting()}{', ' + name if name else ''}! Here's your day."]
    for title, group in (("Overdue", overdue), ("Due today", due_today), ("Coming up", soon)):
        if group:
            lines.append(f"\n{title}:")
            lines += [f"- {t['title']} ({t['area']}" + (f", due {t['due']})" if title == "Coming up" else ")")
                      for t in group]
    if len(lines) == 1:
        lines.append("Nothing due today. Tell me what's on your plate and I'll keep track of it.")
    return "\n".join(lines)


def speak(text):
    """Read text out loud using the computer's built-in voice."""
    try:
        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["say", text])
        elif system == "Windows":
            env = dict(os.environ, ASSISTANT_SAY=text)
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command",
                 "Add-Type -AssemblyName System.Speech; "
                 "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak($env:ASSISTANT_SAY)"],
                env=env, creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
    except OSError:
        pass  # voice is a nice-to-have; never crash over it


class AssistantWindow:
    def __init__(self, root):
        self.root = root
        self.config = core.load_config()
        self.data = core.load_data()
        self.history = []
        self.client = core.make_client()

        root.title("Your Assistant")
        root.geometry("520x600")
        root.minsize(380, 400)

        header = tk.Frame(root, padx=14, pady=10)
        header.pack(fill="x")
        tk.Label(header, text=date.today().strftime("%A, %B %d"),
                 font=("Helvetica", 18, "bold")).pack(anchor="w")
        self.status = tk.Label(header, text="Getting your day ready…", fg="gray")
        self.status.pack(anchor="w")

        self.chat = scrolledtext.ScrolledText(root, wrap="word", font=("Helvetica", 13),
                                              padx=12, pady=10, state="disabled", relief="flat")
        self.chat.tag_configure("you", foreground="#1a5fb4", font=("Helvetica", 13, "bold"))
        self.chat.tag_configure("ai", foreground="#26a269", font=("Helvetica", 13, "bold"))
        self.chat.pack(fill="both", expand=True, padx=8)

        bottom = tk.Frame(root, padx=8, pady=8)
        bottom.pack(fill="x")
        self.entry = tk.Entry(bottom, font=("Helvetica", 13))
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self.send())
        self.button = tk.Button(bottom, text="Send", command=self.send)
        self.button.pack(side="left", padx=(6, 0))
        tk.Button(bottom, text="Code with Claude", command=self.code_with_claude).pack(side="left", padx=(6, 0))
        self.set_busy(True)

        # Pop to the front once, then behave like a normal window.
        root.lift()
        root.attributes("-topmost", True)
        root.after(1500, lambda: root.attributes("-topmost", False))

        threading.Thread(target=self.greet_worker, daemon=True).start()

    # ---------- display helpers (must run on the UI thread)
    def add_message(self, who, text):
        self.chat.configure(state="normal")
        tag = "you" if who == "You" else "ai"
        self.chat.insert("end", f"{who}\n", tag)
        self.chat.insert("end", text.strip() + "\n\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def set_busy(self, busy, status=""):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.entry.configure(state=state)
        self.button.configure(state=state)
        self.status.configure(text=status)
        if not busy:
            self.entry.focus_set()

    def from_thread(self, fn, *args):
        self.root.after(0, lambda: fn(*args))

    # ---------- greeting
    def greet_worker(self):
        """Runs on a background thread. Whatever happens, it ends by showing a greeting and
        switching the input back on, so the window can't get stuck on "Getting your day ready…"."""
        name = self.config.get("name", "").strip()
        try:
            self.greet(name)
        except Exception as e:
            try:
                text = local_summary(self.data, name)
            except Exception:
                text = "Couldn't read your saved tasks."
            self.from_thread(self.finish_greeting, text,
                             f"Something went wrong ({type(e).__name__}), showing saved tasks.")

    def greet(self, name):
        if self.client is None:
            text = local_summary(self.data, name)
            note = "No API key in config.json, showing your saved tasks only."
            self.from_thread(self.finish_greeting, text, note)
            return

        prompt = GREETING_PROMPT.format(now=datetime.now().strftime("%A %I:%M %p"))
        # Right after login, Wi-Fi may not be connected yet, so retry for ~1 minute.
        for attempt in range(7):
            try:
                text = core.ask(self.client, self.data, self.history, prompt, raise_errors=True)
                self.from_thread(self.finish_greeting, text, "")
                return
            except core.anthropic.APIConnectionError:
                self.from_thread(self.status.configure, {"text": "Waiting for internet…"})
                time.sleep(10)
            except (core.anthropic.APIError, core.ReplyError) as e:
                self.from_thread(self.finish_greeting, local_summary(self.data, name),
                                 f"AI unavailable ({type(e).__name__}), showing saved tasks.")
                return
        self.from_thread(self.finish_greeting, local_summary(self.data, name),
                         "Offline, showing your saved tasks.")

    def finish_greeting(self, text, note):
        self.add_message("Assistant", text)
        self.set_busy(False, note)
        if self.config.get("speak"):
            speak(text)

    # ---------- chatting
    def send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.submit(text)

    def submit(self, text):
        """Show what you sent and handle it. Also used by the icon's "Today's brief"."""
        self.add_message("You", text)
        kind, content = core.handle_input(text, self.data)
        if kind == "local":
            self.add_message("Assistant", content)
            return
        if self.client is None:
            self.add_message("Assistant", "Add your API key to config.json to chat. "
                             "Commands like /tasks and /code still work.")
            return
        self.set_busy(True, "Thinking…")

        def worker():
            reply = "(Sorry, something went wrong.)"
            try:
                reply = core.ask(self.client, self.data, self.history, content)
            finally:  # always show a reply and switch the input back on, even if something breaks
                self.from_thread(self.add_message, "Assistant", reply)
                self.from_thread(self.set_busy, False, "")

        threading.Thread(target=worker, daemon=True).start()


    # ---------- coding with Claude
    def code_with_claude(self):
        folder = filedialog.askdirectory(title="Choose the project folder to code in",
                                         initialdir=self.data.get("project") or os.path.expanduser("~"))
        if folder:  # empty if the user pressed Cancel
            self.add_message("Assistant", core.open_code(self.data, folder))

    # ---------- menu bar / tray icon (see tray.py)
    def show(self):
        """Bring the window back and to the front."""
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def hide(self):
        """With the icon running, the close button only hides the window."""
        self.root.withdraw()

    def brief(self):
        self.show()
        if not self.busy:  # if it's already working on something, just show the window
            self.submit("/brief")

    def show_and_code(self):
        self.show()
        self.code_with_claude()


def main():
    root = tk.Tk()
    window = AssistantWindow(root)
    icon = tray.start(window)
    root.mainloop()
    tray.stop(icon)


if __name__ == "__main__":
    main()
