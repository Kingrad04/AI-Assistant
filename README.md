# Personal AI Assistant

A terminal assistant for everyday life at home, at school and at work. It manages your to-do list, remembers facts about you between sessions, and plans your day.

## Setup

1. Install Python 3.9 or newer.
2. Install the library:
   ```
   pip install anthropic
   ```
3. Get an API key at https://console.anthropic.com and set it:
   - Mac/Linux: `export ANTHROPIC_API_KEY="sk-ant-..."`
   - Windows (cmd): `set ANTHROPIC_API_KEY=sk-ant-...`
4. Run:
   ```
   python assistant.py
   ```

## Morning greeting window (opens when you log in)

`morning.py` opens a small window that greets you, tells you what to do today, and lets you keep chatting.

1. Put this folder somewhere simple, like `~/assistant` on a Mac or `C:\Users\you\assistant` on Windows. On a Mac, avoid Desktop, Documents and Downloads, because macOS can block apps started at login from reading those folders.
2. Fill in `config.json`:
   ```json
   { "api_key": "sk-ant-...", "name": "Sam", "speak": true }
   ```
   `speak: true` reads the greeting out loud. Apps started at login can't see your terminal's variables, which is why the key goes in this file. Keep the file private.
3. Try it once: `python morning.py`
4. Make it open at every login: `python install_autostart.py`
   To turn it off: `python install_autostart.py --uninstall`
   With the menu bar / tray icon (below), closing the greeting window keeps the assistant in your menu bar or tray. Choose **Quit** from the icon's menu to close it completely.

**Notes**
- **Windows:** the python.org installer includes everything you need.
- **Mac with Homebrew Python:** also run `brew install python-tk`.
- **Right after login, Wi-Fi may not be connected yet.** The window waits about a minute for internet. If it's still offline, it shows your saved tasks without the AI.
- **If the window doesn't appear on Mac,** look in `morning_error.log` in this folder.

## Menu bar / tray icon

The window can also live in your Mac's menu bar (top right) or your Windows system tray (bottom right, next to the clock).

Run `python morning.py` as usual and a chat-bubble icon appears.

- **Click the icon** to open the assistant. **Right-click it** for a menu with **Today's brief**, **Code with Claude…** and **Quit**.
- **Closing the window only hides it.** Choose **Quit** from the icon's menu to close it completely.
- **It needs Tk 9,** the window toolkit that comes with Python. To check: `python -c "import tkinter; print(tkinter.TkVersion)"`.
  - **Older Tk on Windows:** run `pip install pystray Pillow` and the icon works too.
  - **Older Tk on a Mac:** there's no icon, and the window works as before.
- **On a Mac,** run `pip install pyobjc-framework-Cocoa` to also hide the Python icon from the Dock, so the assistant lives only in the menu bar.

## Coding with Claude

For coding, the assistant hands you off to **Claude Code**, Claude's coding tool. It signs in with your claude.ai account and can read your project, find and fix bugs, write new code and run it.

**One-time setup:**
1. Install Claude Code:
   - Mac: `curl -fsSL https://claude.ai/install.sh | bash`
   - Windows (PowerShell): `irm https://claude.ai/install.ps1 | iex`
2. Open a new terminal, run `claude`, and sign in with your claude.ai account. A paid Claude plan is needed.

**Then, from your assistant:**
- Click **Code with Claude** in the window and pick your project folder, or
- Type `/code C:\path\to\project` (or `/code ~/projects/myapp`). Plain `/code` reopens the last folder you used.

A terminal opens with Claude ready in that folder. Ask it things like:
- "find and fix the bug that crashes login when the email is empty"
- "review app.py for bugs"
- "write tests for utils.py and run them"
- "build a script that renames my photos by date"

If Claude Code isn't installed yet, `/code` opens claude.ai/code in your browser instead.

## Try saying

- "I have a biology exam next Thursday and a group project due the 30th"
- "I need to buy groceries and do laundry this weekend"
- "Remember that I have work Mon–Fri 9 to 5 and classes Tue/Thu evenings"
- "What should I do today?" (or type `/brief`)
- "I finished the laundry"
- "Break the group project into steps"

Your tasks and facts are saved in `assistant_data.json` next to the script.

## How it works

1. You type a message.
2. The script sends it to Claude with a list of **tools** (add_task, list_tasks, remember, …).
3. Claude decides whether to answer directly or to call a tool. The script runs the tool and sends the result back to Claude, repeating until Claude gives a final answer.
4. Each time, the system prompt includes today's date and everything it remembers about you.

## Ideas for next steps

- **Google Calendar:** add a `get_events` tool using the Google Calendar API, so the brief includes your meetings and classes.
- **Gmail / Outlook:** a tool that pulls unread emails so it can tell you what needs a reply.
- **Morning brief:** run a script that calls `ask(...)` with the brief prompt every morning (cron, Windows Task Scheduler or GitHub Actions) and sends the result to you by email or Telegram.
- **Telegram or Discord bot:** replace the `input()` loop with a bot, so you can talk to the assistant from your phone.
- **Reminders:** store a remind-at time on tasks and have a background job notify you.
- **Better storage:** switch from JSON to SQLite once you have lots of tasks.
- **Voice:** add speech-to-text and text-to-speech for a hands-free assistant.
