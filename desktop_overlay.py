import ctypes
import json
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pyperclip
import pystray
import requests
from PIL import Image, ImageDraw
from pynput import keyboard, mouse


SETTINGS_FILE = Path(__file__).with_name("desktop_overlay_settings.json")
DEFAULT_SETTINGS = {
    "api_base_url": "http://127.0.0.1:8000",
    "hotkey": "<ctrl>+<alt>+k",
    "reset_context_hotkey": "<ctrl>+<alt>+r",
    "max_suggestions": 9,
    "window_min_width": 560,
}


def load_settings():
    if not SETTINGS_FILE.exists():
        return DEFAULT_SETTINGS.copy()

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
            loaded_settings = json.load(file)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()

    settings = DEFAULT_SETTINGS.copy()
    settings.update({
        key: value
        for key, value in loaded_settings.items()
        if key in DEFAULT_SETTINGS
    })
    return settings


class KhmerOverlay:
    def __init__(self):
        self.settings = load_settings()
        self.api_base_url = self.settings["api_base_url"].rstrip("/")
        self.suggest_url = f"{self.api_base_url}/api/suggest"
        self.select_url = f"{self.api_base_url}/api/select"
        self.hotkey = self.settings["hotkey"]
        self.reset_context_hotkey = self.settings["reset_context_hotkey"]
        self.max_suggestions = int(self.settings["max_suggestions"])

        self.root = tk.Tk()
        self.root.title("Khmer Overlay")
        self.root.withdraw()
        self.root.attributes("-topmost", True)

        self.keyboard_controller = keyboard.Controller()
        self.mouse_controller = mouse.Controller()
        self.fetch_after_id = None
        self.fetch_serial = 0
        self.suggestions = []
        self.selected_index = 0
        self.last_selected_khmer = ""
        self.tray_icon = None
        self.target_window_handle = None

        self.configure_style()
        self.build_window()

    def configure_style(self):
        self.root.configure(bg="#21140d")
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure(
            "Overlay.TFrame",
            background="#21140d",
        )
        self.style.configure(
            "Title.TLabel",
            background="#21140d",
            foreground="#ffe0a3",
            font=("Segoe UI", 12, "bold"),
        )
        self.style.configure(
            "Overlay.TLabel",
            background="#21140d",
            foreground="#d7c2a7",
            font=("Segoe UI", 9),
        )
        self.style.configure(
            "Hint.TLabel",
            background="#21140d",
            foreground="#9e8b74",
            font=("Segoe UI", 8),
        )
        self.style.configure(
            "Overlay.TButton",
            background="#ffc875",
            foreground="#1d120c",
            borderwidth=0,
            font=("Segoe UI", 9, "bold"),
            padding=(10, 6),
        )

    def build_window(self):
        self.window = tk.Toplevel(self.root)
        self.window.title("Romanized Khmer")
        self.window.withdraw()
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self.hide)
        self.window.configure(bg="#21140d")
        self.window.minsize(int(self.settings["window_min_width"]), 420)

        self.input_var = tk.StringVar()
        self.input_var.trace_add("write", self.schedule_fetch)

        frame = ttk.Frame(self.window, padding=14, style="Overlay.TFrame")
        frame.grid(row=0, column=0, sticky="nsew")

        header = ttk.Frame(frame, style="Overlay.TFrame")
        header.grid(row=0, column=0, sticky="ew")

        label = ttk.Label(
            header,
            text="Romanized Khmer",
            style="Title.TLabel",
        )
        label.grid(row=0, column=0, sticky="w")

        self.context_var = tk.StringVar(value="Context: none")
        self.context_label = ttk.Label(
            header,
            textvariable=self.context_var,
            style="Overlay.TLabel",
        )
        self.context_label.grid(row=0, column=1, sticky="e")
        header.columnconfigure(1, weight=1)

        self.input_entry = ttk.Entry(frame, textvariable=self.input_var, width=42)
        self.input_entry.grid(row=1, column=0, sticky="ew", pady=(8, 8))

        self.status_var = tk.StringVar(value="Type romanized Khmer...")
        self.status_label = ttk.Label(
            frame,
            textvariable=self.status_var,
            style="Overlay.TLabel",
        )
        self.status_label.grid(row=2, column=0, sticky="w", pady=(0, 8))

        self.listbox = tk.Listbox(
            frame,
            height=self.max_suggestions,
            width=44,
            font=("Khmer OS Siemreap", 18),
            activestyle="dotbox",
            bg="#2d1b12",
            fg="#fff7e8",
            selectbackground="#8f6128",
            selectforeground="#fff7e8",
            highlightthickness=1,
            highlightbackground="#6e4a24",
            borderwidth=0,
        )
        self.listbox.grid(row=3, column=0, sticky="nsew")

        buttons = ttk.Frame(frame, style="Overlay.TFrame")
        buttons.grid(row=4, column=0, sticky="ew", pady=(10, 0))

        insert_button = ttk.Button(
            buttons,
            text="Insert",
            command=self.commit_selected,
            style="Overlay.TButton",
        )
        insert_button.grid(row=0, column=0, sticky="w")

        insert_space_button = ttk.Button(
            buttons,
            text="Insert + Space",
            command=lambda: self.commit_selected(append_space=True, reopen=True),
            style="Overlay.TButton",
        )
        insert_space_button.grid(row=0, column=1, sticky="w", padx=(8, 0))

        clear_context_button = ttk.Button(
            buttons,
            text="Clear Context",
            command=self.clear_context,
            style="Overlay.TButton",
        )
        clear_context_button.grid(row=0, column=2, sticky="w", padx=(8, 0))

        hint = ttk.Label(
            frame,
            text=(
                f"{self.hotkey} = show/hide, "
                f"{self.reset_context_hotkey} = reset context, "
                "Enter/1-9 = insert, Ctrl+Enter = insert + space, Esc = close"
            ),
            style="Hint.TLabel",
        )
        hint.grid(row=5, column=0, sticky="w", pady=(8, 0))

        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)

        self.window.bind("<Escape>", lambda _event: self.hide())
        self.window.bind("<Return>", lambda _event: self.commit_selected())
        self.window.bind(
            "<Control-Return>",
            lambda _event: self.commit_selected(append_space=True, reopen=True),
        )
        self.window.bind("<Up>", self.move_selection_up)
        self.window.bind("<Down>", self.move_selection_down)
        self.window.bind("<KeyPress>", self.handle_keypress)
        self.listbox.bind("<Double-Button-1>", lambda _event: self.commit_selected())
        self.listbox.bind("<<ListboxSelect>>", self.sync_selection_from_listbox)

    def toggle(self):
        if self.window.state() == "withdrawn":
            self.show()
        else:
            self.hide()

    def show(self):
        if self.window.state() == "withdrawn":
            self.target_window_handle = self.get_foreground_window()

        self.input_var.set("")
        self.suggestions = []
        self.selected_index = 0
        self.render_suggestions()
        self.status_var.set("Type romanized Khmer...")
        self.update_context_label()

        self.window.deiconify()
        self.window.lift()
        self.position_window_near_cursor()
        self.input_entry.focus_force()

    def hide(self):
        self.window.withdraw()

    def get_foreground_window(self):
        try:
            return ctypes.windll.user32.GetForegroundWindow()
        except AttributeError:
            return None

    def focus_target_window(self):
        if not self.target_window_handle:
            return

        try:
            ctypes.windll.user32.SetForegroundWindow(self.target_window_handle)
        except AttributeError:
            return

    def clear_context(self):
        self.last_selected_khmer = ""
        self.update_context_label()
        self.status_var.set("Previous-word context cleared.")

    def update_context_label(self):
        if self.last_selected_khmer:
            self.context_var.set(f"Context: {self.last_selected_khmer}")
        else:
            self.context_var.set("Context: none")

    def position_window_near_cursor(self):
        self.window.update_idletasks()
        cursor_x, cursor_y = self.mouse_controller.position
        window_width = self.window.winfo_reqwidth()
        window_height = self.window.winfo_reqheight()
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()

        x = min(max(0, cursor_x + 16), max(0, screen_width - window_width - 16))
        y = min(max(0, cursor_y + 16), max(0, screen_height - window_height - 48))

        self.window.geometry(f"+{x}+{y}")

    def schedule_fetch(self, *_args):
        if self.fetch_after_id is not None:
            self.root.after_cancel(self.fetch_after_id)

        self.fetch_after_id = self.root.after(180, self.fetch_suggestions_async)

    def fetch_suggestions_async(self):
        query = self.input_var.get().strip()
        self.fetch_serial += 1
        serial = self.fetch_serial

        if not query:
            self.suggestions = []
            self.status_var.set("Type romanized Khmer...")
            self.render_suggestions()
            return

        self.status_var.set("Loading suggestions...")
        thread = threading.Thread(
            target=self.fetch_suggestions,
            args=(serial, query),
            daemon=True,
        )
        thread.start()

    def fetch_suggestions(self, serial, query):
        try:
            response = requests.get(
                self.suggest_url,
                params={
                    "q": query,
                    "limit": self.max_suggestions,
                    "previous_word": self.last_selected_khmer,
                },
                timeout=2,
            )
            response.raise_for_status()
            data = response.json()
            suggestions = data.get("suggestions", [])[:self.max_suggestions]
            status = f"{len(suggestions)} suggestion(s)"
        except requests.RequestException as error:
            suggestions = []
            status = (
                "API error. Start the server with: "
                "python -m uvicorn app:app --host 127.0.0.1 --port 8000"
            )

        self.root.after(
            0,
            lambda: self.apply_fetch_result(serial, suggestions, status),
        )

    def apply_fetch_result(self, serial, suggestions, status):
        if serial != self.fetch_serial:
            return

        self.suggestions = suggestions
        self.selected_index = 0
        self.status_var.set(status)
        self.render_suggestions()

    def render_suggestions(self):
        self.listbox.delete(0, tk.END)

        for index, suggestion in enumerate(self.suggestions, start=1):
            khmer = suggestion.get("khmer", "")
            source = suggestion.get("source", "")
            score = self.format_score(
                suggestion.get("rank_score", suggestion.get("score", ""))
            )
            meta = f"    {source}"

            if score:
                meta += f" {score}"

            self.listbox.insert(tk.END, f"{index}. {khmer}{meta}")

        if self.suggestions:
            self.listbox.selection_set(self.selected_index)
            self.listbox.activate(self.selected_index)

    def format_score(self, score):
        if score in ("", None):
            return ""

        try:
            return f"{float(score):.3f}"
        except (TypeError, ValueError):
            return str(score)

    def move_selection_up(self, _event):
        if not self.suggestions:
            return "break"

        self.selected_index = max(0, self.selected_index - 1)
        self.render_suggestions()
        return "break"

    def move_selection_down(self, _event):
        if not self.suggestions:
            return "break"

        self.selected_index = min(len(self.suggestions) - 1, self.selected_index + 1)
        self.render_suggestions()
        return "break"

    def sync_selection_from_listbox(self, _event):
        selection = self.listbox.curselection()

        if selection:
            self.selected_index = selection[0]

    def handle_keypress(self, event):
        if event.char and event.char.isdigit():
            index = int(event.char) - 1

            if 0 <= index < len(self.suggestions):
                self.selected_index = index
                self.commit_selected()
                return "break"

        return None

    def commit_selected(self, append_space=False, reopen=False):
        if not self.suggestions:
            return "break"

        suggestion = self.suggestions[self.selected_index]
        khmer = suggestion.get("khmer", "")
        query = self.input_var.get().strip()

        if not khmer:
            return "break"

        text_to_paste = khmer + (" " if append_space else "")

        self.root.after(120, lambda: self.paste_text(text_to_paste))
        self.record_selection_async(query, khmer)
        self.last_selected_khmer = khmer
        self.update_context_label()

        self.input_var.set("")
        self.suggestions = []
        self.selected_index = 0
        self.render_suggestions()
        self.status_var.set("Inserted. Type the next romanized word or press Esc.")
        self.root.after(180, self.input_entry.focus_force)

        return "break"

    def paste_text(self, text):
        old_clipboard = None
        self.focus_target_window()
        time.sleep(0.08)

        try:
            old_clipboard = pyperclip.paste()
        except pyperclip.PyperclipException:
            old_clipboard = None

        pyperclip.copy(text)
        time.sleep(0.05)

        with self.keyboard_controller.pressed(keyboard.Key.ctrl):
            self.keyboard_controller.press("v")
            self.keyboard_controller.release("v")

        if old_clipboard is not None:
            self.root.after(300, lambda: pyperclip.copy(old_clipboard))

    def record_selection_async(self, query, khmer):
        if not query or not khmer:
            return

        previous_khmer = self.last_selected_khmer
        thread = threading.Thread(
            target=self.record_selection,
            args=(query, khmer, previous_khmer),
            daemon=True,
        )
        thread.start()

    def record_selection(self, query, khmer, previous_khmer):
        try:
            requests.post(
                self.select_url,
                json={
                    "q": query,
                    "khmer": khmer,
                    "previous_khmer": previous_khmer,
                },
                timeout=2,
            )
        except requests.RequestException:
            pass

    def create_tray_image(self):
        image = Image.new("RGBA", (64, 64), "#21140d")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (6, 6, 58, 58),
            radius=12,
            fill="#2d1b12",
            outline="#ffc875",
            width=3,
        )
        draw.text((20, 16), "KH", fill="#ffc875")
        return image

    def start_tray_icon(self):
        menu = pystray.Menu(
            pystray.MenuItem(
                "Show / Hide",
                lambda _icon, _item: self.root.after(0, self.toggle),
                default=True,
            ),
            pystray.MenuItem(
                "Clear Context",
                lambda _icon, _item: self.root.after(0, self.clear_context),
            ),
            pystray.MenuItem(
                "Quit",
                lambda _icon, _item: self.root.after(0, self.quit),
            ),
        )
        self.tray_icon = pystray.Icon(
            "khmer_overlay",
            self.create_tray_image(),
            "Khmer Transliteration Overlay",
            menu,
        )

        thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        thread.start()

    def quit(self):
        if self.tray_icon is not None:
            self.tray_icon.stop()

        self.root.quit()

    def run(self):
        hotkey = keyboard.GlobalHotKeys({
            self.hotkey: lambda: self.root.after(0, self.toggle),
            self.reset_context_hotkey: lambda: self.root.after(0, self.clear_context),
        })
        hotkey.start()
        self.start_tray_icon()

        print(f"Khmer desktop overlay running. Press {self.hotkey} to show/hide.")
        print(f"Press {self.reset_context_hotkey} to clear previous-word context.")
        print("Use the tray icon for Show / Hide, Clear Context, or Quit.")
        print("Keep your FastAPI server running at http://127.0.0.1:8000.")

        try:
            self.root.mainloop()
        finally:
            hotkey.stop()
            if self.tray_icon is not None:
                self.tray_icon.stop()


if __name__ == "__main__":
    KhmerOverlay().run()
