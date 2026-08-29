import json
import os
import shutil
import subprocess
import threading
import time
import zipfile
import tarfile
from pathlib import Path
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

APP_NAME = "Py File Manager"
CONFIG_DIR = Path.home() / ".pyfilemanager_android"
CONFIG_FILE = CONFIG_DIR / "config.json"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT = {
    "mode": "dark",
    "view": "grid",
    "accent": "#5b8cff",
    "favorites": [],
    "tags": {},
    "recents": [],
    "flappy_best": 0,
}


def load_config():
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            out = DEFAULT.copy()
            out.update(data)
            return out
    except Exception:
        pass
    return DEFAULT.copy()


def save_config(c):
    try:
        CONFIG_FILE.write_text(json.dumps(c, indent=2), encoding="utf-8")
    except Exception:
        pass


def human_size(n):
    try:
        v = float(n)
    except Exception:
        return ""
    for u in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024:
            return f"{v:.1f} {u}"
        v /= 1024
    return f"{v:.1f} PB"


def mod_time(p):
    try:
        return datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def is_archive(p):
    return Path(p).suffix.lower() in {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz"}


def file_icon(p):
    if os.path.isdir(p):
        return "📁"
    ext = Path(p).suffix.lower()
    return {
        ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️", ".gif": "🖼️", ".webp": "🖼️",
        ".mp3": "🎵", ".wav": "🎵", ".flac": "🎵", ".m4a": "🎵",
        ".mp4": "🎬", ".mkv": "🎬", ".avi": "🎬", ".mov": "🎬",
        ".zip": "📦", ".tar": "📦", ".gz": "📦", ".tgz": "📦", ".bz2": "📦", ".xz": "📦",
        ".pdf": "📕", ".py": "🐍", ".txt": "📄", ".json": "📋",
    }.get(ext, "📄")


class Card(ButtonBehavior, BoxLayout):
    selected = BooleanProperty(False)
    accent = StringProperty("#5b8cff")
    bg = StringProperty("#202429")
    fg = StringProperty("#f4f6f8")
    sub = StringProperty("#9ba4ad")

    def __init__(self, path, app, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(4), size_hint_y=None, height=dp(160), **kwargs)
        self.path = path
        self.app = app
        self._last_tap = 0
        self._draw()

        icon = Label(text=file_icon(path), font_size=dp(42), size_hint_y=None, height=dp(62))
        name = os.path.basename(path) or path
        if len(name) > 25:
            name = name[:22] + "…"
        self.name_label = Label(text=name, font_size=dp(13), bold=True, color=self._rgba(self.fg), size_hint_y=None, height=dp(24))
        info = "Folder" if os.path.isdir(path) else human_size(os.path.getsize(path)) if os.path.isfile(path) else ""
        self.info_label = Label(text=info, font_size=dp(11), color=self._rgba(self.sub), size_hint_y=None, height=dp(20))
        self.add_widget(icon)
        self.add_widget(self.name_label)
        self.add_widget(self.info_label)
        self.bind(selected=lambda *_: self._draw())

    @staticmethod
    def _rgba(hex_color):
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4)) + (1,)

    def _draw(self):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self._rgba(self.accent if self.selected else self.bg))
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)])
            if self.selected:
                Color(*self._rgba(self.accent))
                Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(14)), width=dp(2.5))
        self.canvas.ask_update()

    def on_release(self):
        now = time.monotonic()
        if now - self._last_tap < 0.32:
            self.app.open_path(self.path)
            self._last_tap = 0
        else:
            self.app.select_path(self.path)
            self._last_tap = now

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and touch.is_mouse_scrolling:
            return False
        if self.collide_point(*touch.pos) and touch.button == "right":
            self.app.context_menu(self.path)
            return True
        return super().on_touch_down(touch)


class ArchivePopup(Popup):
    def __init__(self, app, archive, **kwargs):
        self.app = app
        self.archive = archive
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        scroll = ScrollView()
        self.list_box = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        scroll.add_widget(self.list_box)
        box.add_widget(scroll)
        actions = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        actions.add_widget(Button(text="Extract All", on_release=lambda *_: self.extract_all()))
        actions.add_widget(Button(text="Open Selected", on_release=lambda *_: self.open_selected()))
        actions.add_widget(Button(text="Close", on_release=lambda *_: self.dismiss()))
        box.add_widget(actions)
        self.entries = []
        super().__init__(title=f"Archive • {os.path.basename(archive)}", content=box, size_hint=(0.96, 0.88), **kwargs)
        self.populate()

    def populate(self):
        try:
            with zipfile.ZipFile(self.archive, "r") as z:
                for info in z.infolist():
                    b = Button(text=("📁 " if info.is_dir() else "📄 ") + info.filename, size_hint_y=None, height=dp(42), halign="left")
                    b.bind(on_release=lambda btn, n=info.filename: self.toggle_entry(n, btn))
                    self.list_box.add_widget(b)
                    self.entries.append((info.filename, b))
        except Exception as e:
            self.app.show_message("ZIP error", str(e))

    def toggle_entry(self, name, btn):
        selected = getattr(btn, "_selected", False)
        btn._selected = not selected
        btn.background_color = (0.35, 0.55, 1, 1) if not selected else (1, 1, 1, 1)

    def selected(self):
        return [n for n, b in self.entries if getattr(b, "_selected", False) and not n.endswith("/")]

    def extract_all(self):
        dest = self.app.storage_root / "PyFileManager_Extracted"
        dest.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(self.archive, "r") as z:
                z.extractall(dest)
            self.app.show_message("Complete", f"Extracted to:\n{dest}")
        except Exception as e:
            self.app.show_message("Extraction failed", str(e))

    def open_selected(self):
        names = self.selected()
        if len(names) != 1:
            self.app.show_message("Select one file", "Select exactly one file inside the ZIP.")
            return
        temp_dir = self.app.storage_root / ".pyfm_zip_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(self.archive, "r") as z:
                z.extract(names[0], temp_dir)
            self.dismiss()
            self.app.open_file(str(temp_dir / names[0]))
        except Exception as e:
            self.app.show_message("Open failed", str(e))


class FileManagerAndroid(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.config = load_config()
        self.current_path = None
        self.items = []
        self.selected = set()
        self.sort_key = "name"
        self.sort_reverse = False
        self.storage_root = Path("/storage/emulated/0") if os.path.exists("/storage/emulated/0") else Path.home()
        self.theme()
        self.build_ui()
        self.show_home()

    def theme(self):
        mode = self.config.get("mode", "dark")
        if mode in ("dark", "black"):
            self.bg = "#0f1114" if mode == "black" else "#15181c"
            self.card = "#20252b"
            self.fg = "#f3f6f8"
            self.sub = "#9aa3ad"
            self.hover = "#2a3037"
        else:
            self.bg = "#f4f6f8"
            self.card = "#ffffff"
            self.fg = "#1d2329"
            self.sub = "#66717d"
            self.hover = "#e8edf3"
        self.accent = self.config.get("accent", "#5b8cff")
        self.background_color = self._rgba(self.bg)

    @staticmethod
    def _rgba(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4)) + (1,)

    def build_ui(self):
        # Top bar
        top = BoxLayout(size_hint_y=None, height=dp(54), padding=(dp(6), dp(6)), spacing=dp(5))
        for text, cb in [("‹", self.go_back), ("›", self.go_forward), ("↑", self.go_up), ("⟳", self.refresh)]:
            top.add_widget(Button(text=text, size_hint_x=None, width=dp(46), on_release=lambda _, f=cb: f()))
        self.address = TextInput(text="Home", multiline=False, size_hint_x=1)
        top.add_widget(self.address)
        top.add_widget(Button(text="Go", size_hint_x=None, width=dp(52), on_release=lambda *_: self.navigate_address()))
        top.add_widget(Button(text="🔎", size_hint_x=None, width=dp(48), on_release=lambda *_: self.search_files()))
        self.add_widget(top)

        # Search row
        search_row = BoxLayout(size_hint_y=None, height=dp(46), padding=(dp(8), dp(4)))
        self.search = TextInput(hint_text="Search current folder…", multiline=False)
        self.search.bind(on_text_validate=lambda *_: self.search_files())
        search_row.add_widget(self.search)
        search_row.add_widget(Button(text="Settings", size_hint_x=None, width=dp(90), on_release=lambda *_: self.open_settings()))
        self.add_widget(search_row)

        # Main content
        self.main_scroll = ScrollView(do_scroll_x=False)
        self.grid = GridLayout(cols=2 if self.config.get("view") == "grid" else 1, spacing=dp(8), padding=dp(8), size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        self.main_scroll.add_widget(self.grid)
        self.add_widget(self.main_scroll)

        # Bottom nav
        bottom = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(4), padding=dp(4))
        for text, cb in [("Home", self.show_home), ("Recent", self.show_recents), ("★", self.show_favorites), ("📦", self.show_archives), ("Menu", self.open_sidebar)] :
            bottom.add_widget(Button(text=text, on_release=lambda _, f=cb: f()))
        self.add_widget(bottom)

    def rebuild(self):
        self.theme()
        self.clear_widgets()
        self.build_ui()
        if self.current_path:
            self.open_folder(self.current_path, add_history=False)
        else:
            self.show_home()

    def show_message(self, title, text):
        Popup(title=title, content=Label(text=text), size_hint=(0.88, 0.42)).open()

    def show_home(self, *_):
        self.current_path = None
        self.address.text = "Home"
        homes = [self.storage_root]
        self.items = [str(p) for p in [self.storage_root / x for x in ("Download", "Documents", "Pictures", "Music", "Movies") if (self.storage_root / x).exists()]]
        if not self.items:
            self.items = homes
        self.selected.clear()
        self.render_items()

    def open_folder(self, path, add_history=True):
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            return
        self.current_path = path
        self.address.text = path
        try:
            self.items = [e.path for e in os.scandir(path)]
        except Exception as e:
            self.show_message("Access denied", str(e))
            return
        self.selected.clear()
        self.render_items()

    def render_items(self):
        self.grid.clear_widgets()
        paths = list(self.items)
        def key(p):
            try:
                if self.sort_key == "name": return os.path.basename(p).lower()
                if self.sort_key == "type": return Path(p).suffix.lower()
                if self.sort_key == "size": return 0 if os.path.isdir(p) else os.path.getsize(p)
                return os.path.getmtime(p)
            except Exception:
                return 0
        paths.sort(key=key, reverse=self.sort_reverse)
        self.grid.cols = 2 if self.config.get("view", "grid") == "grid" else 1
        for p in paths:
            if self.config.get("view", "grid") == "list":
                w = Button(text=f"{file_icon(p)}  {os.path.basename(p) or p}\n{('Folder' if os.path.isdir(p) else human_size(os.path.getsize(p)))}   {mod_time(p)}", size_hint_y=None, height=dp(65), halign="left")
                w.bind(on_release=lambda _, q=p: self.list_tap(q))
            else:
                w = Card(p, self, accent=self.accent, bg=self.card, fg=self.fg, sub=self.sub)
            self.grid.add_widget(w)
        self._refresh_status()

    def list_tap(self, path):
        now = time.monotonic()
        last = getattr(self, "_last_list_tap", (None, 0))
        if last[0] == path and now - last[1] < 0.32:
            self.open_path(path)
        else:
            self.select_path(path)
        self._last_list_tap = (path, now)

    def select_path(self, path):
        if path in self.selected:
            self.selected.remove(path)
        else:
            self.selected.add(path)
        self._refresh_selection()

    def _refresh_selection(self):
        for child in self.grid.children:
            if isinstance(child, Card):
                child.selected = child.path in self.selected
        self._refresh_status()

    def _refresh_status(self):
        pass

    def selected_paths(self):
        return list(self.selected)

    def open_path(self, path):
        if os.path.isdir(path):
            self.open_folder(path)
        elif Path(path).suffix.lower() == ".zip":
            ArchivePopup(self, path).open()
        else:
            self.open_file(path)

    def open_file(self, path):
        self.add_recent(path)
        try:
            try:
                from jnius import autoclass
                Intent = autoclass("android.content.Intent")
                Uri = autoclass("android.net.Uri")
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                intent = Intent(Intent.ACTION_VIEW)
                ext = Path(path).suffix.lower()
                mime = {
                    ".jpg": "image/*", ".jpeg": "image/*", ".png": "image/*", ".gif": "image/*", ".webp": "image/*",
                    ".mp3": "audio/*", ".wav": "audio/*", ".m4a": "audio/*",
                    ".mp4": "video/*", ".mkv": "video/*", ".avi": "video/*",
                    ".pdf": "application/pdf", ".txt": "text/plain", ".json": "application/json"
                }.get(ext, "*/*")
                intent.setDataAndType(Uri.parse("file://" + path), mime)
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                PythonActivity.mActivity.startActivity(intent)
            except ImportError:
                import webbrowser
                webbrowser.open(path)
        except Exception as e:
            self.show_message("Open failed", str(e))

    def add_recent(self, path):
        r = self.config.setdefault("recents", [])
        if path in r:
            r.remove(path)
        r.insert(0, path)
        self.config["recents"] = r[:60]
        save_config(self.config)

    def show_recents(self, *_):
        self.current_path = None
        self.address.text = "Recents"
        self.items = [p for p in self.config.get("recents", []) if os.path.exists(p)]
        self.render_items()

    def show_favorites(self, *_):
        self.current_path = None
        self.address.text = "Favorites"
        self.items = [p for p in self.config.get("favorites", []) if os.path.exists(p)]
        self.render_items()

    def show_archives(self, *_):
        roots = [self.storage_root / x for x in ("Download", "Documents", "Desktop") if (self.storage_root / x).exists()]
        found = []
        for root in roots:
            for base, _, files in os.walk(root):
                for f in files:
                    if Path(f).suffix.lower() in {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz"}:
                        found.append(os.path.join(base, f))
                if len(found) >= 300:
                    break
        self.current_path = None
        self.address.text = "Archives"
        self.items = found[:300]
        self.render_items()

    def navigate_address(self):
        p = self.address.text.strip()
        if os.path.isdir(p):
            self.open_folder(p)
        elif os.path.isfile(p):
            self.open_file(p)
        else:
            self.show_message("Invalid path", "That path does not exist.")

    def go_back(self):
        if self.current_path:
            parent = os.path.dirname(self.current_path.rstrip(os.sep))
            if parent and parent != self.current_path:
                self.open_folder(parent)

    def go_forward(self):
        # Android version intentionally keeps navigation simple.
        self.show_message("Navigation", "Forward history is not enabled in this Android port yet.")

    def go_up(self):
        self.go_back()

    def refresh(self):
        if self.current_path:
            self.open_folder(self.current_path, add_history=False)
        else:
            self.show_home()

    def search_files(self):
        if not self.current_path:
            self.show_message("Search", "Open a folder first.")
            return
        q = self.search.text.strip().lower()
        if not q:
            self.refresh()
            return
        self.items = []
        base = self.current_path
        def work():
            found = []
            try:
                for root, dirs, files in os.walk(base):
                    for n in dirs + files:
                        if q in n.lower():
                            found.append(os.path.join(root, n))
                    if len(found) >= 500:
                        break
            except Exception:
                pass
            Clock.schedule_once(lambda *_: self._finish_search(found, q))
        threading.Thread(target=work, daemon=True).start()

    def _finish_search(self, found, q):
        self.items = found
        self.address.text = f"Search: {q}"
        self.render_items()

    def context_menu(self, path):
        items = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        popup = Popup(title=os.path.basename(path) or path, content=items, size_hint=(0.85, 0.7))
        actions = [
            ("Open", lambda: (popup.dismiss(), self.open_path(path))),
            ("Copy", lambda: (popup.dismiss(), self.set_clipboard([path], "copy"))),
            ("Rename", lambda: (popup.dismiss(), self.rename(path))),
            ("Delete", lambda: (popup.dismiss(), self.delete([path]))),
            ("Compress ZIP", lambda: (popup.dismiss(), self.compress([path]))),
            ("Extract ZIP", lambda: (popup.dismiss(), self.extract(path)) if Path(path).suffix.lower() == ".zip" else popup.dismiss()),
            ("★ Favorite", lambda: (popup.dismiss(), self.favorite(path))),
            ("🏷 Tag", lambda: (popup.dismiss(), self.tag(path))),
            ("Properties", lambda: (popup.dismiss(), self.properties(path))),
        ]
        for text, cmd in actions:
            items.add_widget(Button(text=text, size_hint_y=None, height=dp(44), on_release=lambda _, f=cmd: f()))
        items.add_widget(Button(text="Cancel", size_hint_y=None, height=dp(44), on_release=lambda *_: popup.dismiss()))
        popup.open()

    def set_clipboard(self, paths, mode):
        self.clipboard = paths
        self.clipboard_mode = mode
        self.show_message("Clipboard", f"{len(paths)} item(s) {'copied' if mode == 'copy' else 'cut'}. Open a destination folder and use Paste from Menu.")

    def paste(self):
        if not getattr(self, "current_path", None) or not getattr(self, "clipboard", []):
            return
        for src in self.clipboard:
            target = os.path.join(self.current_path, os.path.basename(src))
            try:
                if self.clipboard_mode == "copy":
                    if os.path.isdir(src): shutil.copytree(src, target, dirs_exist_ok=True)
                    else: shutil.copy2(src, target)
                else:
                    shutil.move(src, target)
            except Exception as e:
                self.show_message("Paste failed", str(e))
        self.clipboard = []
        self.refresh()

    def rename(self, path):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        inp = TextInput(text=os.path.basename(path), multiline=False)
        box.add_widget(inp)
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        pop = Popup(title="Rename", content=box, size_hint=(0.85, 0.34))
        row.add_widget(Button(text="Cancel", on_release=lambda *_: pop.dismiss()))
        row.add_widget(Button(text="Save", on_release=lambda *_: self._do_rename(path, inp.text, pop)))
        box.add_widget(row)
        pop.open()

    def _do_rename(self, path, new, pop):
        new = new.strip()
        if not new:
            return
        try:
            os.rename(path, os.path.join(os.path.dirname(path), new))
            pop.dismiss()
            self.refresh()
        except Exception as e:
            self.show_message("Rename failed", str(e))

    def delete(self, paths):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        box.add_widget(Label(text=f"Delete {len(paths)} item(s)?"))
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        pop = Popup(title="Delete", content=box, size_hint=(0.84, 0.3))
        row.add_widget(Button(text="Cancel", on_release=lambda *_: pop.dismiss()))
        row.add_widget(Button(text="Delete", on_release=lambda *_: self._do_delete(paths, pop)))
        box.add_widget(row)
        pop.open()

    def _do_delete(self, paths, pop):
        try:
            for p in paths:
                if os.path.isdir(p): shutil.rmtree(p)
                elif os.path.exists(p): os.remove(p)
            pop.dismiss()
            self.refresh()
        except Exception as e:
            self.show_message("Delete failed", str(e))

    def compress(self, paths):
        dest = os.path.join(self.current_path or str(self.storage_root), "archive.zip")
        try:
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
                for p in paths:
                    if os.path.isdir(p):
                        for root, _, files in os.walk(p):
                            for f in files:
                                full = os.path.join(root, f)
                                z.write(full, os.path.relpath(full, os.path.dirname(p)))
                    else:
                        z.write(p, os.path.basename(p))
            self.show_message("Complete", f"ZIP created:\n{dest}")
            self.refresh()
        except Exception as e:
            self.show_message("Compression failed", str(e))

    def extract(self, archive):
        if Path(archive).suffix.lower() != ".zip":
            self.show_message("Unsupported", "This Android port currently extracts ZIP archives internally.")
            return
        dest = self.storage_root / "PyFileManager_Extracted"
        dest.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(archive, "r") as z:
                z.extractall(dest)
            self.show_message("Complete", f"Extracted to:\n{dest}")
            self.refresh()
        except Exception as e:
            self.show_message("Extraction failed", str(e))

    def favorite(self, path):
        f = self.config.setdefault("favorites", [])
        if path in f:
            f.remove(path)
            msg = "Removed from favorites"
        else:
            f.append(path)
            msg = "Added to favorites"
        save_config(self.config)
        self.show_message("Favorites", msg)

    def tag(self, path):
        colors = [("Red", "#e74c3c"), ("Orange", "#e67e22"), ("Yellow", "#f1c40f"), ("Green", "#2ecc71"), ("Blue", "#3498db"), ("Purple", "#9b59b6")]
        box = BoxLayout(orientation="vertical", spacing=dp(5), padding=dp(8))
        pop = Popup(title="Color tag", content=box, size_hint=(0.75, 0.62))
        for name, color in colors:
            box.add_widget(Button(text=name, on_release=lambda _, c=color: self._save_tag(path, c, pop)))
        box.add_widget(Button(text="Remove tag", on_release=lambda *_: self._save_tag(path, None, pop)))
        pop.open()

    def _save_tag(self, path, color, pop):
        t = self.config.setdefault("tags", {})
        if color: t[path] = color
        else: t.pop(path, None)
        save_config(self.config)
        pop.dismiss()

    def properties(self, p):
        try:
            size = 0
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        try: size += os.path.getsize(os.path.join(root, f))
                        except Exception: pass
            else:
                size = os.path.getsize(p)
            self.show_message("Properties", f"Name: {os.path.basename(p)}\n\nPath: {p}\n\nType: {'Folder' if os.path.isdir(p) else Path(p).suffix.upper() or 'File'}\n\nSize: {human_size(size)}\n\nModified: {mod_time(p)}")
        except Exception as e:
            self.show_message("Properties", str(e))

    def open_sidebar(self):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        pop = Popup(title="Py File Manager", content=box, size_hint=(0.82, 0.82))
        entries = [
            ("🏠 Home", self.show_home),
            ("🕘 Recents", self.show_recents),
            ("★ Favorites", self.show_favorites),
            ("📦 Archives", self.show_archives),
            ("📋 Paste", self.paste),
            ("⚙ Settings", self.open_settings),
        ]
        for text, f in entries:
            box.add_widget(Button(text=text, size_hint_y=None, height=dp(48), on_release=lambda _, cb=f: (pop.dismiss(), cb())))
        box.add_widget(Label(text=f"Storage\n{self.storage_root}"))
        pop.open()

    def open_settings(self):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        pop = Popup(title="Settings & Customization", content=box, size_hint=(0.9, 0.86))
        box.add_widget(Label(text="Appearance", size_hint_y=None, height=dp(28)))
        for mode in ("light", "dark", "black", "white"):
            box.add_widget(Button(text=mode.title(), size_hint_y=None, height=dp(44), on_release=lambda _, m=mode: self.set_mode(m, pop)))
        box.add_widget(Label(text="Accent color (hex)", size_hint_y=None, height=dp(28)))
        accent = TextInput(text=self.accent, multiline=False, size_hint_y=None, height=dp(44))
        box.add_widget(accent)
        box.add_widget(Button(text="Apply Accent", size_hint_y=None, height=dp(44), on_release=lambda *_: self.set_accent(accent.text, pop)))
        box.add_widget(Label(text="Layout", size_hint_y=None, height=dp(28)))
        box.add_widget(Button(text="▦ Large Grid", size_hint_y=None, height=dp(44), on_release=lambda *_: self.set_view("grid", pop)))
        box.add_widget(Button(text="☷ Detailed List", size_hint_y=None, height=dp(44), on_release=lambda *_: self.set_view("list", pop)))
        box.add_widget(Button(text="Open Android All-files-access settings", size_hint_y=None, height=dp(44), on_release=lambda *_: self.open_storage_settings()))
        box.add_widget(Button(text="Close", size_hint_y=None, height=dp(44), on_release=lambda *_: pop.dismiss()))
        pop.open()

    def set_mode(self, mode, pop):
        self.config["mode"] = mode
        if mode == "black": self.config["accent"] = "#ffffff"
        if mode == "white": self.config["accent"] = "#111111"
        save_config(self.config)
        pop.dismiss()
        self.rebuild()

    def set_accent(self, value, pop):
        value = value.strip()
        if not (value.startswith("#") and len(value) == 7):
            self.show_message("Accent", "Use a color such as #5b8cff")
            return
        try:
            int(value[1:], 16)
        except ValueError:
            self.show_message("Accent", "Invalid hex color")
            return
        self.config["accent"] = value
        save_config(self.config)
        pop.dismiss()
        self.rebuild()

    def set_view(self, view, pop=None):
        self.config["view"] = view
        save_config(self.config)
        if pop: pop.dismiss()
        self.rebuild()

    def open_storage_settings(self):
        try:
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            Settings = autoclass("android.provider.Settings")
            Uri = autoclass("android.net.Uri")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
            intent.setData(Uri.parse("package:" + PythonActivity.mActivity.getPackageName()))
            PythonActivity.mActivity.startActivity(intent)
        except Exception as e:
            self.show_message("Storage settings", str(e))


class PyFileManagerApp(App):
    title = APP_NAME

    def build(self):
        Window.clearcolor = (0.06, 0.07, 0.08, 1)
        self.request_android_permissions()
        return FileManagerAndroid()

    def request_android_permissions(self):
        try:
            from android.permissions import request_permissions, Permission
            perms = [
                Permission.READ_MEDIA_IMAGES,
                Permission.READ_MEDIA_VIDEO,
                Permission.READ_MEDIA_AUDIO,
            ]
            request_permissions(perms)
        except Exception:
            pass


if __name__ == "__main__":
    PyFileManagerApp().run()
