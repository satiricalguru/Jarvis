"""
tools.py — JARVIS system-action layer.

Supports:
  • Opening websites / URLs
  • Launching macOS applications
  • Creating files and folders on the Desktop / any path
  • Deleting files and folders
  • Writing content into files
  • Reading files
  • Taking screenshots
  • Listing directory contents
  • Getting system info (battery, CPU, memory)
  • Running safe shell commands (allowlisted)

All actions are parsed from natural-language messages sent to /chat.
Returns a human-readable status string (or None if no action matched).
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

DESKTOP = Path.home() / "Desktop"

_LAST_REFERENCED_FILE: Path | None = None


def _update_last_referenced_file(target: Path) -> None:
    global _LAST_REFERENCED_FILE
    _LAST_REFERENCED_FILE = target


def _run(cmd: list[str], timeout: int = 10) -> str:
    """Run a subprocess and return stdout or stderr."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return (result.stdout or result.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return "Command timed out."
    except Exception as exc:
        return f"Error: {exc}"


def _expand(path_str: str) -> Path:
    """Expand ~, $HOME, and make absolute. Defaults to Desktop if bare name."""
    p = Path(os.path.expandvars(path_str)).expanduser()
    if not p.is_absolute():
        p = DESKTOP / p
    return p


def _is_safe_to_delete(path: Path) -> bool:
    """Ensure path is within safe directories (Desktop, Documents, Downloads) and not protected."""
    try:
        resolved = path.resolve()
    except Exception:
        return False

    home = Path.home().resolve()
    desktop = (home / "Desktop").resolve()
    documents = (home / "Documents").resolve()
    downloads = (home / "Downloads").resolve()

    # Never allow deleting root, home directory, or top-level user directories
    if resolved in (Path("/"), home, desktop, documents, downloads):
        return False

    # Must be strictly within Desktop, Documents, or Downloads
    is_in_safe_area = any(
        resolved.is_relative_to(safe_dir)
        for safe_dir in (desktop, documents, downloads)
    )
    if not is_in_safe_area:
        return False

    # Block protected paths (e.g. current project or dotfiles)
    base_dir = Path(__file__).resolve().parent.parent.parent.resolve()
    if resolved == base_dir or resolved.is_relative_to(base_dir):
        return False

    if any(part.startswith(".") for part in resolved.parts):
        return False

    return True


def _trash_item(target: Path) -> bool:
    """Use macOS AppleScript / Finder to move item to Trash safely (recoverable)."""
    try:
        script = f'tell application "Finder" to delete POSIX file "{target}"'
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
        return res.returncode == 0
    except Exception:
        return False



# ──────────────────────────────────────────────
# 1. Open website / URL
# ──────────────────────────────────────────────

_OPEN_URL_PAT = re.compile(
    r"\b(?:open|launch|go to|navigate to|browse to)\s+"
    r"(https?://[^\s]+|[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s]*)?|youtube|google|github|gmail|reddit|twitter|x\.com|instagram|linkedin|stackoverflow|chatgpt)",
    re.IGNORECASE,
)

_SHORTHAND: dict[str, str] = {
    "youtube":      "youtube.com",
    "google":       "google.com",
    "github":       "github.com",
    "gmail":        "mail.google.com",
    "reddit":       "reddit.com",
    "twitter":      "twitter.com",
    "x.com":        "x.com",
    "instagram":    "instagram.com",
    "linkedin":     "linkedin.com",
    "stackoverflow":"stackoverflow.com",
    "chatgpt":      "chatgpt.com",
}


def try_open_website(message: str) -> str | None:
    m = _OPEN_URL_PAT.search(message)
    if not m:
        return None
    site = m.group(1).lower().strip()
    site = _SHORTHAND.get(site, site)
    url  = site if site.startswith("http") else f"https://{site}"
    webbrowser.open(url)
    return f"Opening {url}, Sir."


# ──────────────────────────────────────────────
# 2. Open macOS application
# ──────────────────────────────────────────────

_APP_ALIASES: dict[str, str] = {
    "finder":       "Finder",
    "safari":       "Safari",
    "chrome":       "Google Chrome",
    "firefox":      "Firefox",
    "terminal":     "Terminal",
    "iterm":        "iTerm",
    "iterm2":       "iTerm",
    "vscode":       "Visual Studio Code",
    "vs code":      "Visual Studio Code",
    "code":         "Visual Studio Code",
    "cursor":       "Cursor",
    "xcode":        "Xcode",
    "slack":        "Slack",
    "discord":      "Discord",
    "spotify":      "Spotify",
    "music":        "Music",
    "messages":     "Messages",
    "mail":         "Mail",
    "calendar":     "Calendar",
    "notes":        "Notes",
    "reminders":    "Reminders",
    "calculator":   "Calculator",
    "preview":      "Preview",
    "photos":       "Photos",
    "maps":         "Maps",
    "weather":      "Weather",
    "clock":        "Clock",
    "system preferences": "System Preferences",
    "system settings":    "System Settings",
    "activity monitor":   "Activity Monitor",
    "activity":     "Activity Monitor",
    "disk utility": "Disk Utility",
    "quicktime":    "QuickTime Player",
    "vlc":          "VLC",
    "zoom":         "zoom.us",
    "facetime":     "FaceTime",
    "whatsapp":     "WhatsApp",
    "telegram":     "Telegram",
    "notion":       "Notion",
    "obsidian":     "Obsidian",
    "figma":        "Figma",
    "postman":      "Postman",
    "docker":       "Docker",
    "warp":         "Warp",
    "arc":          "Arc",
    "bear":         "Bear",
    "1password":    "1Password",
}

_OPEN_APP_PAT = re.compile(
    r"\b(?:open|launch|start|run|fire up)\s+(?:the\s+)?(?:app\s+)?([a-z0-9 ]+?)(?:\s+app)?\s*$",
    re.IGNORECASE,
)


def try_open_app(message: str) -> str | None:
    m = _OPEN_APP_PAT.search(message.strip())
    if not m:
        return None
    raw = m.group(1).strip().lower()

    # If the target is a known website shorthand or looks like a URL/domain,
    # skip try_open_app so it can fall through to try_open_website.
    if raw in _SHORTHAND or "." in raw or raw.startswith("http"):
        return None

    has_explicit_app_keyword = bool(re.search(r"\b(?:app|application)\b", message, re.IGNORECASE))

    app = _APP_ALIASES.get(raw)
    if not app:
        # Try partial match only for explicit app aliases
        for key, val in _APP_ALIASES.items():
            if raw == key or (len(raw) >= 4 and raw in key):
                app = val
                break

    if not app:
        # Only attempt title-casing if the user explicitly said "app" or "application"
        if has_explicit_app_keyword:
            app = raw.title()
        else:
            return None

    result = _run(["open", "-a", app])
    if result and "Unable to find" in result:
        # If open command failed because the app wasn't found,
        # but the message matches a URL pattern, let it fall through.
        if _OPEN_URL_PAT.search(message):
            return None
        return f"Could not find app '{app}', Sir."
    return f"Launching {app}, Sir."


# ──────────────────────────────────────────────
# 3. Create file
# ──────────────────────────────────────────────

_FOLDER_INTENT_PAT = re.compile(
    r"\b(?:create|make|mkdir|new)\s+(?:a\s+|new\s+|another\s+)?(?:folder|directory|dir)\b",
    re.IGNORECASE
)

def try_create_file(message: str) -> str | None:
    low = message.lower()
    if not any(v in low for v in ["create", "make", "touch", "new"]):
        return None
    
    # If the user explicitly wants to create a folder, let try_create_folder handle it.
    if _FOLDER_INTENT_PAT.search(message):
        return None
        
    filename = None
    # 1. Look for "called <name>", "named <name>", "named as <name>"
    name_match = re.search(r"\b(?:called|named|named as)\s+[\"']?([a-z0-9_.-]+)[\"']?", low)
    if name_match:
        filename = name_match.group(1).strip()
    else:
        # 2. Look for name after "file" or "document" or "script"
        file_match = re.search(r"\b(?:file|document|script)\s+[\"']?([a-z0-9_.-]+)[\"']?", low)
        if file_match:
            filename = file_match.group(1).strip()
        else:
            # 3. Look for a dotted name in the message
            dotted_match = re.search(r"\b([a-z0-9_-]+\.[a-z0-9]+)\b", low)
            if dotted_match:
                filename = dotted_match.group(1).strip()

    if not filename:
        return None

    # Determine extension if not present
    if "." not in filename:
        ext_match = re.search(r"\b(\.[a-z0-9]+|[a-z0-9+]+)\s+(?:file|document|script)\b", low)
        ext = None
        if ext_match:
            raw_ext = ext_match.group(1).strip().lower()
            if raw_ext.startswith("."):
                ext = raw_ext
            else:
                ext_map = {
                    "text": ".txt",
                    "txt": ".txt",
                    "python": ".py",
                    "py": ".py",
                    "js": ".js",
                    "javascript": ".js",
                    "ts": ".ts",
                    "typescript": ".ts",
                    "html": ".html",
                    "css": ".css",
                    "json": ".json",
                    "md": ".md",
                    "markdown": ".md",
                    "cpp": ".cpp",
                    "c": ".c",
                    "go": ".go",
                    "rs": ".rs",
                    "rust": ".rs",
                }
                ext = ext_map.get(raw_ext)
        if ext:
            filename = f"{filename}{ext}"
        else:
            filename = f"{filename}.txt"

    target_dir = DESKTOP
    if "desktop" in low:
        target_dir = DESKTOP
    elif "document" in low:
        target_dir = Path.home() / "Documents"
    elif "download" in low:
        target_dir = Path.home() / "Downloads"
    
    # Custom path check (e.g. "in /tmp/foo" or "in folder Projects")
    loc_match = re.search(r"\b(?:in|on|at|into)\s+(?:the\s+)?(?:folder\s+|directory\s+)?[\"']?([a-z0-9_/.~$-]+)[\"']?", low)
    if loc_match:
        loc_str = loc_match.group(1).strip().lower()
        if loc_str not in ["desktop", "documents", "downloads", "home"]:
            p = Path(os.path.expandvars(loc_str)).expanduser()
            if not p.is_absolute():
                target_dir = DESKTOP / p
            else:
                target_dir = p

    target = target_dir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(exist_ok=True)
    _update_last_referenced_file(target)
    return f"Created file '{target}', Sir."


# ──────────────────────────────────────────────
# 4. Create folder / directory
# ──────────────────────────────────────────────

def try_create_folder(message: str) -> str | None:
    low = message.lower()
    if not any(v in low for v in ["create", "make", "mkdir", "new"]):
        return None
        
    if not _FOLDER_INTENT_PAT.search(message) and "mkdir" not in low:
        return None

    dirname = None
    name_match = re.search(r"\b(?:called|named|named as)\s+[\"']?([a-z0-9_.-]+)[\"']?", low)
    if name_match:
        dirname = name_match.group(1).strip()
    else:
        dir_match = re.search(r"\b(?:folder|directory|dir)\s+[\"']?([a-z0-9_.-]+)[\"']?", low)
        if dir_match:
            dirname = dir_match.group(1).strip()
        else:
            mkdir_match = re.search(r"\bmkdir\s+[\"']?([a-z0-9_.-]+)[\"']?", low)
            if mkdir_match:
                dirname = mkdir_match.group(1).strip()

    if not dirname:
        return None

    target_dir = DESKTOP
    if "desktop" in low:
        target_dir = DESKTOP
    elif "document" in low:
        target_dir = Path.home() / "Documents"
    elif "download" in low:
        target_dir = Path.home() / "Downloads"

    loc_match = re.search(r"\b(?:in|on|at|into)\s+(?:the\s+)?(?:folder\s+|directory\s+)?[\"']?([a-z0-9_/.~$-]+)[\"']?", low)
    if loc_match:
        loc_str = loc_match.group(1).strip().lower()
        if loc_str not in ["desktop", "documents", "downloads", "home"]:
            if loc_str != dirname:
                p = Path(os.path.expandvars(loc_str)).expanduser()
                if not p.is_absolute():
                    target_dir = DESKTOP / p
                else:
                    target_dir = p

    target = target_dir / dirname
    target.mkdir(parents=True, exist_ok=True)
    return f"Created folder '{target}', Sir."


# ──────────────────────────────────────────────
# 5. Delete file or folder
# ──────────────────────────────────────────────

_DELETE_PAT = re.compile(
    r"\b(?:delete|remove|trash|rm)\s+(?:the\s+)?(?:file\s+|folder\s+)?[\"']?([^\s\"']+)[\"']?",
    re.IGNORECASE,
)

_QUESTION_PAT = re.compile(
    r"\b(?:how\s+(?:to|can|do|does)|why\s+(?:to|should|would)|can\s+you\s+explain|what\s+happens\s+if|should\s+i)\b",
    re.IGNORECASE,
)


def try_delete(message: str) -> str | None:
    if _QUESTION_PAT.search(message):
        return None

    m = _DELETE_PAT.search(message)
    if not m:
        return None
    name = m.group(1).strip()
    if name.lower() in ("files", "everything", "all", "something", "bugs", "errors", "data", "history"):
        return None

    target = _expand(name)
    if not target.exists():
        return f"'{target}' does not exist, Sir."

    if not _is_safe_to_delete(target):
        return f"Permission denied: '{target}' is protected and cannot be deleted, Sir."

    global _LAST_REFERENCED_FILE
    if _LAST_REFERENCED_FILE == target:
        _LAST_REFERENCED_FILE = None

    if _trash_item(target):
        return f"Moved '{target}' to Trash, Sir."

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return f"Deleted '{target}', Sir."



# ──────────────────────────────────────────────
# 6. Write content to file
# ──────────────────────────────────────────────

_WRITE_PAT = re.compile(
    r"\b(?:write|append|add)\s+[\"'](.+?)[\"']\s+(?:to|into)\s+(?:the\s+)?(?:file\s+)?[\"']?([^\s\"']+)[\"']?",
    re.IGNORECASE,
)


def resolve_filename(name: str) -> Path | None:
    """Resolve a user-provided file name or reference to a Path."""
    if not name:
        return None
    name = name.strip()
    low = name.lower()
    
    # Handle "that file", "the file", "it"
    if low in ("that file", "the file", "it"):
        global _LAST_REFERENCED_FILE
        if _LAST_REFERENCED_FILE and _LAST_REFERENCED_FILE.exists():
            return _LAST_REFERENCED_FILE
        # Fallback to the most recently modified file on the Desktop
        try:
            files = [p for p in DESKTOP.iterdir() if p.is_file() and not p.name.startswith(".")]
            if files:
                return max(files, key=lambda p: p.stat().st_mtime)
        except Exception:
            pass
        return None
        
    # Check absolute path
    p = Path(os.path.expandvars(name)).expanduser()
    if p.is_absolute():
        if p.exists():
            return p
        p_txt = p.with_suffix(p.suffix + ".txt") if p.suffix else p.with_suffix(".txt")
        if p_txt.exists():
            return p_txt
        return p

    # Otherwise, check under DESKTOP first
    p_desktop = DESKTOP / name
    if p_desktop.exists():
        return p_desktop
    p_desktop_txt = p_desktop.with_suffix(".txt")
    if p_desktop_txt.exists():
        return p_desktop_txt

    # Check under other common folders: Documents, Downloads
    for folder in [Path.home() / "Documents", Path.home() / "Downloads"]:
        p_f = folder / name
        if p_f.exists():
            return p_f
        p_f_txt = p_f.with_suffix(".txt")
        if p_f_txt.exists():
            return p_f_txt
            
    # If not exists anywhere but it has an extension, return it relative to Desktop
    if "." in name:
        return DESKTOP / name
        
    # If it is a single word, check if it matches the stem of the _LAST_REFERENCED_FILE
    if _LAST_REFERENCED_FILE and _LAST_REFERENCED_FILE.stem.lower() == low:
        return _LAST_REFERENCED_FILE
        
    # Check if there is any file on Desktop matching this stem
    try:
        for item in DESKTOP.iterdir():
            if item.is_file() and item.stem.lower() == low:
                return item
    except Exception:
        pass
        
    # Default fallback
    return DESKTOP / f"{name}.txt"


def _execute_write(target: Path, content: str, append: bool) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with target.open(mode, encoding="utf-8") as f:
        f.write(content + "\n")
    _update_last_referenced_file(target)
    action = "Appended to" if mode == "a" else "Wrote to"
    return f"{action} '{target}', Sir."


def _should_generate_content(content: str) -> bool:
    content_stripped = content.strip()
    if (content_stripped.startswith('"') and content_stripped.endswith('"')) or \
       (content_stripped.startswith("'") and content_stripped.endswith("'")):
        return False
        
    words = content_stripped.lower().split()
    if len(words) < 3:
        return False
        
    keywords = {
        "summary", "essay", "poem", "script", "description", "article", "report", 
        "list of", "write-up", "analysis", "overview", "review", "story", "generate",
        "detail", "detailed", "explanation", "paragraph", "code", "guide", "tutorial"
    }
    
    content_lower = content_stripped.lower()
    if any(k in content_lower for k in keywords):
        return True
        
    return False


async def _generate_content_via_llm(
    prompt: str,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    try:
        from app.brain import resolve_chat, GENERATE_SYSTEM_PROMPT
        reply, _ = await resolve_chat(
            message=prompt,
            provider=provider,
            model=model,
            system_prompt=GENERATE_SYSTEM_PROMPT
        )
        return reply.strip()
    except Exception as e:
        print(f"[JARVIS] LLM content generation failed: {e}")
        return prompt


async def try_write_file(
    message: str,
    provider: str | None = None,
    model: str | None = None,
) -> str | None:
    # 1. Try quoted regex first
    m = _WRITE_PAT.search(message)
    if m:
        content = m.group(1).strip()
        filename = m.group(2).strip()
        target = resolve_filename(filename) or _expand(filename)
        return _execute_write(target, content, "append" in message.lower())

    # 2. Try quotes-free patterns
    low = message.lower()
    
    verb = None
    for v in ["write", "append", "add"]:
        if re.search(r"\b" + re.escape(v) + r"\b", low):
            verb = v
            break
    if not verb:
        return None
        
    # Pattern A: in/on/to/into <file_ref> write/append/add <content>
    m_prep = re.search(
        r"\b(?:in|on|to|into)\s+(that\s+file|the\s+file|it|[a-z0-9_.-]+)\s+\b(?:write|append|add)\s+(.+)",
        message,
        re.IGNORECASE
    )
    if m_prep:
        file_ref = m_prep.group(1).strip()
        content = m_prep.group(2).strip()
        target = resolve_filename(file_ref)
        if target:
            if _should_generate_content(content):
                content = await _generate_content_via_llm(content, provider, model)
            return _execute_write(target, content, verb == "append" or "append" in low)

    # Pattern B: write/append/add in/to/into <file_ref> <content>
    m_verb_first = re.search(
        r"\b(?:write|append|add)\s+(?:in|to|into)\s+(that\s+file|the\s+file|it|[a-z0-9_.-]+)\s+(.+)",
        message,
        re.IGNORECASE
    )
    if m_verb_first:
        file_ref = m_verb_first.group(1).strip()
        content = m_verb_first.group(2).strip()
        target = resolve_filename(file_ref)
        if target:
            if _should_generate_content(content):
                content = await _generate_content_via_llm(content, provider, model)
            return _execute_write(target, content, verb == "append" or "append" in low)

    # Pattern C: write/append/add <content> in/to/into <file_ref>
    m_content_first = re.search(
        r"\b(?:write|append|add)\s+(.+?)\s+(?:in|to|into)\s+(that\s+file|the\s+file|it|[a-z0-9_.-]+)\s*$",
        message,
        re.IGNORECASE
    )
    if m_content_first:
        content = m_content_first.group(1).strip()
        file_ref = m_content_first.group(2).strip()
        
        is_valid_ref = False
        if file_ref.lower() in ("that file", "the file", "it"):
            is_valid_ref = True
        elif "." in file_ref:
            is_valid_ref = True
        else:
            target = resolve_filename(file_ref)
            if target and target.exists():
                is_valid_ref = True
                
        if is_valid_ref:
            target = resolve_filename(file_ref)
            if target:
                if _should_generate_content(content):
                    content = await _generate_content_via_llm(content, provider, model)
                return _execute_write(target, content, verb == "append" or "append" in low)

    return None


# ──────────────────────────────────────────────
# 7. Read file
# ──────────────────────────────────────────────

_READ_PAT = re.compile(
    r"\b(?:read|show|display|cat|open)\s+(?:the\s+)?(?:file\s+|contents? of\s+)?[\"']?([^\s\"']+\.[a-z]+)[\"']?",
    re.IGNORECASE,
)


def try_read_file(message: str) -> str | None:
    # 1. Try pattern match with extension/quotes first
    m = _READ_PAT.search(message)
    filename = None
    if m:
        filename = m.group(1).strip()
    else:
        # 2. Try quotes-free/pronoun pattern
        m_pronoun = re.search(
            r"\b(?:read|show|display|cat|open)\s+(?:the\s+)?(?:file\s+|contents? of\s+)?(that\s+file|the\s+file|it|[a-z0-9_.-]+)\b",
            message,
            re.IGNORECASE
        )
        if m_pronoun:
            filename = m_pronoun.group(1).strip()

    if not filename:
        return None

    target = resolve_filename(filename) or _expand(filename)
    if not target.exists():
        if filename.lower() in ("that file", "the file", "it"):
            return None
        return f"File '{target}' not found, Sir."

    _update_last_referenced_file(target)
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
        preview = text[:800]
        return f"Contents of '{target.name}':\n{preview}" + ("…" if len(text) > 800 else "")
    except Exception as exc:
        return f"Could not read '{target}': {exc}"


# ──────────────────────────────────────────────
# 8. List directory
# ──────────────────────────────────────────────

_LIST_PAT = re.compile(
    r"\b(?:list|ls|show|what(?:'s| is) in)\s+(?:the\s+)?(?:files? in\s+|contents? of\s+)?(?:the\s+)?([^\s?!.]+)",
    re.IGNORECASE,
)


def try_list_dir(message: str) -> str | None:
    low = message.lower()
    if not any(k in low for k in ("list", "ls ", "what's in", "what is in", "show files", "show me")):
        return None
    m = _LIST_PAT.search(message)
    folder = "desktop"
    if m:
        folder = m.group(1).strip().lower()

    if folder in ("desktop", "my desktop"):
        target = DESKTOP
    elif folder in ("home", "~"):
        target = Path.home()
    elif folder in ("downloads",):
        target = Path.home() / "Downloads"
    elif folder in ("documents",):
        target = Path.home() / "Documents"
    else:
        target = _expand(folder)

    if not target.is_dir():
        return None  # Not a list request we understand

    items = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    lines = []
    for item in items[:30]:
        icon = "📁" if item.is_dir() else "📄"
        lines.append(f"{icon} {item.name}")
    result = "\n".join(lines)
    if len(items) > 30:
        result += f"\n…and {len(items)-30} more items."
    return f"Contents of {target}:\n{result}"


# ──────────────────────────────────────────────
# 9. Screenshot
# ──────────────────────────────────────────────

_SCREENSHOT_PAT = re.compile(
    r"\b(?:(?:take|capture|grab)\s+(?:a\s+)?(?:screen ?shot|screen)|screen ?shot)\b",
    re.IGNORECASE,
)


def try_screenshot(message: str) -> str | None:
    if not _SCREENSHOT_PAT.search(message):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = DESKTOP / f"jarvis_screenshot_{ts}.png"
    _run(["screencapture", "-x", str(out)])
    if out.exists():
        return f"Screenshot saved to Desktop as '{out.name}', Sir."
    return "Screenshot failed, Sir."


# ──────────────────────────────────────────────
# 10. System info (battery, memory, CPU)
# ──────────────────────────────────────────────

_SYSINFO_PAT = re.compile(
    r"\b(?:check|show|get|display|what(?:'s| is)(?: the)?|status of(?: the)?)\s+(?:the\s+)?(?:battery|memory|ram|cpu|processor|disk|storage|system(?: info| status)?)\b|\b(?:system info|system status)\b",
    re.IGNORECASE,
)


def try_system_info(message: str) -> str | None:
    if not _SYSINFO_PAT.search(message):
        return None
    low = message.lower()
    parts: list[str] = []
    is_general = "system info" in low or "system status" in low

    if is_general or any(k in low for k in ("battery",)):
        out = _run(["pmset", "-g", "batt"])
        pct_m = re.search(r"(\d+)%;", out)
        pct = pct_m.group(1) + "%" if pct_m else "unknown"
        parts.append(f"Battery: {pct}")

    if is_general or any(k in low for k in ("memory", "ram")):
        out = _run(["vm_stat"])
        free_m = re.search(r"Pages free:\s+(\d+)", out)
        if free_m:
            free_pages = int(free_m.group(1))
            free_mb = (free_pages * 4096) / (1024 ** 2)
            parts.append(f"Free memory: {free_mb:.0f} MB")

    if is_general or any(k in low for k in ("cpu", "processor")):
        out = _run(["top", "-l", "1", "-s", "0", "-n", "0"])
        cpu_m = re.search(r"CPU usage:\s+(.+)", out)
        if cpu_m:
            parts.append(f"CPU: {cpu_m.group(1)}")

    if is_general or any(k in low for k in ("disk", "storage")):
        out = _run(["df", "-h", "/"])
        lines = out.splitlines()
        if len(lines) >= 2:
            parts.append(f"Disk: {lines[1]}")

    return "\n".join(parts) if parts else None


# ──────────────────────────────────────────────
# Master dispatcher
# ──────────────────────────────────────────────

async def dispatch_action(
    message: str,
    provider: str | None = None,
    model: str | None = None,
) -> str | None:
    """
    Try every action handler in priority order.
    Returns the first non-None status string, or None if nothing matched.
    """
    res = await asyncio.to_thread(try_open_app, message)
    if res is not None:
        return res

    res = await asyncio.to_thread(try_open_website, message)
    if res is not None:
        return res

    res = await asyncio.to_thread(try_create_file, message)
    if res is not None:
        return res

    res = await asyncio.to_thread(try_create_folder, message)
    if res is not None:
        return res

    res = await asyncio.to_thread(try_delete, message)
    if res is not None:
        return res

    res = await try_write_file(message, provider, model)
    if res is not None:
        return res

    res = await asyncio.to_thread(try_read_file, message)
    if res is not None:
        return res

    res = await asyncio.to_thread(try_list_dir, message)
    if res is not None:
        return res

    res = await asyncio.to_thread(try_screenshot, message)
    if res is not None:
        return res

    res = await asyncio.to_thread(try_system_info, message)
    if res is not None:
        return res

    return None

