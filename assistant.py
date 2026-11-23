"""
Personal AI Assistant — a starter you can grow.

What it does:
  * Chat with it in your terminal about anything (home, school, work).
  * It manages a to-do list for you (add / list / update / delete tasks).
  * It remembers facts about you ("I have class MWF 9am") between sessions.
  * /brief gives you a plan for today.

Run:
  pip install anthropic
  export ANTHROPIC_API_KEY="your-key"      (Windows: set ANTHROPIC_API_KEY=your-key)
  python assistant.py
"""

import json
import os
import sys
import tempfile
import uuid
from datetime import date, datetime
from pathlib import Path

try:
    import anthropic
except ImportError:
    sys.exit("Missing package. Run:  pip install anthropic")

import claude_link

# ------------------------------------------------------------------ settings
# The assistant sends updates (today's date, your tasks, your facts) as "system" messages in
# the middle of the chat. That needs a model that accepts mid-conversation system messages;
# claude-sonnet-5-5 does.
DEFAULT_MODEL = "claude-sonnet-5-5"
DATA_FILE = Path(__file__).with_name("assistant_data.json")
CONFIG_FILE = Path(__file__).with_name("config.json")
AREAS = ["home", "school", "work", "personal"]
MAX_HISTORY = 60  # once the conversation is longer than this many messages, it starts over


# ------------------------------------------------------------------ storage
def load_data():
    """Load tasks and remembered facts from disk.
    If the file is damaged, it's moved aside (never deleted) and the assistant starts fresh."""
    data = {"tasks": [], "facts": [], "project": None}
    if DATA_FILE.exists():
        try:
            saved = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if not isinstance(saved, dict):
                raise ValueError("not a JSON object")
            data.update(saved)
        except ValueError:  # bad JSON or unreadable text
            backup = _set_aside_damaged_file()
            print(f"Warning: {DATA_FILE.name} was damaged, so it was moved to {backup.name} "
                  "and the assistant started with an empty list. Your old data is still in that file.",
                  file=sys.stderr)
    return data


def _set_aside_damaged_file():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DATA_FILE.with_name(f"{DATA_FILE.stem}.corrupt-{stamp}.json")
    n = 2
    while backup.exists():  # never overwrite an earlier backup
        backup = DATA_FILE.with_name(f"{DATA_FILE.stem}.corrupt-{stamp}-{n}.json")
        n += 1
    DATA_FILE.rename(backup)
    return backup


def save_data(data):
    """Write to a temporary file first, then swap it in. If the app crashes halfway through
    a save, the old file is still there in one piece instead of half-written."""
    fd, tmp = tempfile.mkstemp(dir=DATA_FILE.parent, prefix=DATA_FILE.stem + ".", suffix=".tmp.json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, DATA_FILE)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_config():
    """Settings from config.json (API key, your name, voice on/off)."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("Warning: config.json is not valid JSON; ignoring it.")
    return {}


def make_client():
    """Create the Claude client, or return None if no API key is set anywhere."""
    key = os.environ.get("ANTHROPIC_API_KEY") or load_config().get("api_key", "").strip()
    if not key:
        return None
    return anthropic.Anthropic(api_key=key)


def get_model():
    return os.environ.get("ASSISTANT_MODEL") or load_config().get("model") or DEFAULT_MODEL


def new_id():
    return uuid.uuid4().hex[:6]


# ------------------------------------------------------------------ tools
# These describe to the AI what actions it is allowed to take.
TOOLS = [
    {
        "name": "add_task",
        "description": "Add a task to the user's to-do list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short description of the task"},
                "area": {"type": "string", "enum": AREAS},
                "due": {"type": "string", "description": "Due date as YYYY-MM-DD (optional)"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "notes": {"type": "string", "description": "Extra details (optional)"},
            },
            "required": ["title", "area"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List the user's tasks. Use this before planning a day or answering 'what do I need to do'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "area": {"type": "string", "enum": AREAS, "description": "Only this area (optional)"},
                "include_done": {"type": "boolean", "description": "Also show finished tasks"},
            },
        },
    },
    {
        "name": "update_task",
        "description": "Change a task, e.g. mark it done or move its due date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "done": {"type": "boolean"},
                "title": {"type": "string"},
                "area": {"type": "string", "enum": AREAS},
                "due": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "notes": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "delete_task",
        "description": "Permanently delete a task. Only do this if the user clearly asks.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "remember",
        "description": "Save a lasting fact about the user (schedule, preferences, people, goals) so you know it in future sessions.",
        "input_schema": {
            "type": "object",
            "properties": {"fact": {"type": "string"}},
            "required": ["fact"],
        },
    },
    {
        "name": "forget",
        "description": "Remove a remembered fact by its id.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
]


def find_task(data, task_id):
    return next((t for t in data["tasks"] if t["id"] == task_id), None)


def run_tool(name, args, data):
    """Carry out a tool call from the AI and return the result as text."""
    if name == "add_task":
        task = {
            "id": new_id(),
            "title": args["title"],
            "area": args.get("area", "personal"),
            "due": args.get("due"),
            "priority": args.get("priority", "medium"),
            "notes": args.get("notes", ""),
            "done": False,
            "created": date.today().isoformat(),
        }
        data["tasks"].append(task)
        save_data(data)
        return json.dumps({"added": task})

    if name == "list_tasks":
        tasks = data["tasks"]
        if args.get("area"):
            tasks = [t for t in tasks if t["area"] == args["area"]]
        if not args.get("include_done"):
            tasks = [t for t in tasks if not t["done"]]
        return json.dumps({"tasks": tasks})

    if name == "update_task":
        task = find_task(data, args["id"])
        if not task:
            return json.dumps({"error": f"No task with id {args['id']}"})
        for key in ("done", "title", "area", "due", "priority", "notes"):
            if key in args:
                task[key] = args[key]
        save_data(data)
        return json.dumps({"updated": task})

    if name == "delete_task":
        task = find_task(data, args["id"])
        if not task:
            return json.dumps({"error": f"No task with id {args['id']}"})
        data["tasks"].remove(task)
        save_data(data)
        return json.dumps({"deleted": task["title"]})

    if name == "remember":
        fact = {"id": new_id(), "fact": args["fact"]}
        data["facts"].append(fact)
        save_data(data)
        return json.dumps({"remembered": fact})

    if name == "forget":
        before = len(data["facts"])
        data["facts"] = [f for f in data["facts"] if f["id"] != args["id"]]
        save_data(data)
        return json.dumps({"forgotten": before != len(data["facts"])})

    return json.dumps({"error": f"Unknown tool {name}"})



# ------------------------------------------------------------------ the AI's instructions
# The main instructions stay exactly the same for the whole session. Newer Claude models check
# that the earlier part of a conversation hasn't changed, and reject the request if it has.
# So anything that changes (the date, your tasks, your facts) goes in a new message each turn.
_session_prompt = None


def build_system_prompt():
    """The fixed instructions for this session. Built once, then reused unchanged."""
    global _session_prompt
    if _session_prompt is None:
        _session_prompt = _make_system_prompt()
    return _session_prompt


def state_message(data):
    """A system message with what may have changed since the last turn."""
    today = date.today()
    facts = "\n".join(f"- [{f['id']}] {f['fact']}" for f in data["facts"]) or "- (nothing yet)"
    open_tasks = sum(1 for t in data["tasks"] if not t["done"])
    return {"role": "system", "content": f"""Today is {today.strftime('%A, %B %d, %Y')} ({today.isoformat()}).
The user has {open_tasks} open task(s).

What you know about the user:
{facts}"""}


def _make_system_prompt():
    started = date.today()
    name = load_config().get("name", "").strip()
    who = f"The user's name is {name}.\n" if name else ""
    return f"""You are a friendly, practical personal assistant that helps the user with everyday life:
home (chores, errands, bills), school (classes, assignments, exams) and work (meetings, deadlines, projects).

{who}This conversation started on {started.strftime('%A, %B %d, %Y')}. During the chat you'll get system
messages with today's date, the number of open tasks and what you know about the user.
Always go by the most recent one.

How to behave:
- When the user mentions something they need to do, add it as a task (pick the right area, convert
  words like "Friday" or "tomorrow" into a YYYY-MM-DD date).
- When they share a lasting fact about themselves (schedule, preferences, goals), remember it.
- When asked what to do today or for a plan, check the task list first, then give a short,
  prioritized plan: overdue and due-today items first, high priority next, and suggest time blocks.
- Break big or vague tasks into small next steps.
- Keep answers short and easy to scan. Don't show task ids unless they're useful.
- Ask before deleting anything.

Formatting: plain text, no ** or # markdown. Simple "- " bullet lines are fine.
Put code in fenced blocks (``` ... ```) so it shows in a code font.

If the user wants help with code, help with small questions here, and for real coding work suggest
they type /code <project folder> to open Claude Code, which can read and edit their project."""


# ------------------------------------------------------------------ conversation
class ReplyError(Exception):
    """The AI's reply was cut off or declined, so there's nothing usable to show."""


def ask(client, data, history, user_text, raise_errors=False):
    """Send one user message; let the AI use tools as needed; return its final reply.
    With raise_errors=True, errors are raised instead of returned as text.

    The conversation is only ever added to, never edited. When it gets too long it starts
    over (your tasks and facts are saved on disk and sent again, so nothing important is lost)."""
    if len(history) > MAX_HISTORY:
        history.clear()
    start_len = len(history)
    history.append({"role": "user", "content": user_text})
    history.append(state_message(data))
    try:
        while True:
            response = client.messages.create(
                model=get_model(),
                max_tokens=16000,  # room for the AI's thinking plus its reply
                system=build_system_prompt(),
                tools=TOOLS,
                messages=history,
            )

            # A reply that was cut off or declined can't be continued (a cut-off reply may end in
            # half a tool call), so undo this turn. Anything a tool already saved stays saved.
            if response.stop_reason in ("max_tokens", "refusal"):
                del history[start_len:]
                if response.stop_reason == "max_tokens":
                    message = "(Sorry, that reply got too long and was cut off. Try asking for something smaller.)"
                else:
                    message = "(Sorry, Claude declined to answer that. Try rephrasing your request.)"
                if raise_errors:
                    raise ReplyError(message)
                return message

            history.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return "".join(b.text for b in response.content if b.type == "text")

            results = []
            for block in response.content:
                if block.type == "tool_use":
                    try:
                        output = run_tool(block.name, block.input, data)
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
                    except Exception as e:
                        # Tell the AI the tool failed (so it can tell you or try again) instead of crashing.
                        results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                        "content": f"The tool failed: {type(e).__name__}: {e}"})
            history.append({"role": "user", "content": results})
    except anthropic.APIError as e:
        del history[start_len:]  # undo this turn so the conversation stays valid
        if raise_errors:
            raise
        return f"(Sorry, the AI request failed: {e})"
    except Exception as e:
        del history[start_len:]  # same for anything unexpected, so one bad turn can't break the rest
        if raise_errors:
            raise
        return f"(Sorry, something went wrong: {type(e).__name__}: {e})"


# ------------------------------------------------------------------ commands (shared by terminal and window)
def tasks_text(data):
    open_tasks = [t for t in data["tasks"] if not t["done"]]
    if not open_tasks:
        return "No open tasks."
    order = {"high": 0, "medium": 1, "low": 2}
    open_tasks.sort(key=lambda t: (t["due"] or "9999-99-99", order.get(t["priority"], 1)))
    return "\n".join(f"- [{t['area']}] {t['title']}" + (f" (due {t['due']})" if t["due"] else "")
                     + f", {t['priority']}" for t in open_tasks)


HELP = """Commands:
  /brief           plan for today
  /tasks           show your open tasks
  /facts           show what the assistant remembers about you
  /code [folder]   open Claude Code in a project folder to write, fix and review code
                   (no folder = the last one you used)

Or just type normally."""

BRIEF_PROMPT = ("Give me my brief for today: what's overdue, what's due today and soon, "
                "and a suggested order to do things in, across home, school and work.")


def handle_input(text, data):
    """Decide what to do with what the user typed.
    Returns ("local", message_to_show) or ("ask", prompt_for_the_ai)."""
    if not text.startswith("/"):
        return "ask", text
    cmd, _, arg = text.partition(" ")
    cmd, arg = cmd.lower(), arg.strip().strip('"').strip("'")

    if cmd == "/help":
        return "local", HELP
    if cmd == "/tasks":
        return "local", tasks_text(data)
    if cmd == "/facts":
        return "local", "\n".join("- " + f["fact"] for f in data["facts"]) or "Nothing remembered yet."
    if cmd == "/brief":
        return "ask", BRIEF_PROMPT
    if cmd == "/code":
        return "local", open_code(data, arg or None)
    return "local", f"Unknown command {cmd}. Type /help."


def open_code(data, folder=None):
    """Open Claude Code in a folder and remember it for next time."""
    folder = folder or data.get("project")
    message = claude_link.open_claude(folder)
    if folder and claude_link.is_folder(folder):
        data["project"] = str(claude_link.as_path(folder))
        save_data(data)
    return message


# ------------------------------------------------------------------ terminal app
def main():
    client = make_client()
    if client is None:
        sys.exit("No API key found. Put it in config.json (\"api_key\") or set ANTHROPIC_API_KEY.")
    data = load_data()
    history = []

    print("Personal assistant ready. Type /help for commands, /quit to exit.")
    print()
    while True:
        try:
            user_text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            continue
        if user_text.lower() in ("/quit", "/exit"):
            break

        kind, content = handle_input(user_text, data)
        if kind == "local":
            print(content + "\n")
            continue
        reply = ask(client, data, history, content)
        print(f"\nassistant> {reply}\n")

    print("Bye!")


if __name__ == "__main__":
    main()
