#!/usr/bin/env python3

import json
import math
import os
import subprocess
import threading
import time

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog
from tkinter import ttk, messagebox

import evdev
from evdev import ecodes

from pynput import keyboard
from pynput import mouse


CONFIG_FILE = os.path.expanduser("~/controller_mapper.json")
DEFAULT_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "default.json")

BUTTONS = (
    "South / A", "East / B", "West / X", "North / Y",
    "Left shoulder", "Right shoulder", "Left trigger button",
    "Right trigger button", "Select / Back", "Start",
    "Left stick click", "Right stick click", "D-pad up",
    "D-pad down", "D-pad left", "D-pad right",
)
CENTER_BUTTON = "Shmenxs-Böx Button"
SWITCHABLE_BUTTONS = BUTTONS + (CENTER_BUTTON,)

# Linux input event codes for the common gamepad layout. Other devices can
# override these codes in the vendor map in the configuration file.
DEFAULT_VENDOR_MAP = {
    "304": "South / A", "305": "East / B",
    "307": "West / X", "308": "North / Y",
    "310": "Left shoulder", "311": "Right shoulder",
    "312": "Left trigger button", "313": "Right trigger button",
    "314": "Select / Back", "315": "Start",
    "317": "Left stick click", "318": "Right stick click",
    # BTN_DPAD_* key events (some controllers expose these instead of hats).
    "544": "D-pad up", "545": "D-pad down",
    "546": "D-pad left", "547": "D-pad right",
    # Directional hat axes are translated from their values in handle_axis.
    "ABS_HAT0Y:-1": "D-pad up", "ABS_HAT0Y:1": "D-pad down",
    "ABS_HAT0X:-1": "D-pad left", "ABS_HAT0X:1": "D-pad right",
    "316":"Shmenxs-Böx Button",
}

DEFAULT_MAPPINGS = {
    "South / A": "space", "East / B": "esc",
    "West / X": "x", "North / Y": "y",
    "Left shoulder": "ctrl", "Right shoulder": "shift",
    "Left trigger button": "shift", "Right trigger button": "shift",
    "Select / Back": "alt", "Start": "enter",
    "Left stick click": "f1", "Right stick click": "f2",
    "D-pad up": "up", "D-pad down": "down",
    "D-pad left": "left", "D-pad right": "right",
}

KEY_MAP = {
    "space": keyboard.Key.space,
    "enter": keyboard.Key.enter,
    "esc": keyboard.Key.esc,
    "escape": keyboard.Key.esc,
    "tab": keyboard.Key.tab,
    "backspace": keyboard.Key.backspace,
    "shift": keyboard.Key.shift,
    "ctrl": keyboard.Key.ctrl,
    "control": keyboard.Key.ctrl,
    "alt": keyboard.Key.alt,
    "cmd": keyboard.Key.cmd,
    "win": keyboard.Key.cmd,
    "up": keyboard.Key.up,
    "down": keyboard.Key.down,
    "left": keyboard.Key.left,
    "right": keyboard.Key.right,
    "home": keyboard.Key.home,
    "end": keyboard.Key.end,
    "pageup": keyboard.Key.page_up,
    "pagedown": keyboard.Key.page_down,
    "insert": keyboard.Key.insert,
    "delete": keyboard.Key.delete,
    "f1": keyboard.Key.f1, "f2": keyboard.Key.f2,
    "f3": keyboard.Key.f3, "f4": keyboard.Key.f4,
    "f5": keyboard.Key.f5, "f6": keyboard.Key.f6,
    "f7": keyboard.Key.f7, "f8": keyboard.Key.f8,
    "f9": keyboard.Key.f9, "f10": keyboard.Key.f10,
    "f11": keyboard.Key.f11, "f12": keyboard.Key.f12,
}

MOUSE_ACTIONS = (
    "",
    "mouse:left",
    "mouse:middle",
    "mouse:right",
    "mouse:scroll_up",
    "mouse:scroll_down",
)

SPECIAL_CAPTURE_NAMES = {
    keyboard.Key.space: "space",
    keyboard.Key.enter: "enter",
    keyboard.Key.esc: "esc",
    keyboard.Key.tab: "tab",
    keyboard.Key.backspace: "backspace",
    keyboard.Key.shift: "shift",
    keyboard.Key.shift_l: "shift",
    keyboard.Key.shift_r: "shift",
    keyboard.Key.ctrl: "ctrl",
    keyboard.Key.ctrl_l: "ctrl",
    keyboard.Key.ctrl_r: "ctrl",
    keyboard.Key.alt: "alt",
    keyboard.Key.alt_l: "alt",
    keyboard.Key.alt_r: "alt",
    keyboard.Key.cmd: "cmd",
    keyboard.Key.cmd_l: "cmd",
    keyboard.Key.cmd_r: "cmd",
    keyboard.Key.up: "up",
    keyboard.Key.down: "down",
    keyboard.Key.left: "left",
    keyboard.Key.right: "right",
    keyboard.Key.home: "home",
    keyboard.Key.end: "end",
    keyboard.Key.page_up: "pageup",
    keyboard.Key.page_down: "pagedown",
    keyboard.Key.insert: "insert",
    keyboard.Key.delete: "delete",
    keyboard.Key.f1: "f1", keyboard.Key.f2: "f2",
    keyboard.Key.f3: "f3", keyboard.Key.f4: "f4",
    keyboard.Key.f5: "f5", keyboard.Key.f6: "f6",
    keyboard.Key.f7: "f7", keyboard.Key.f8: "f8",
    keyboard.Key.f9: "f9", keyboard.Key.f10: "f10",
    keyboard.Key.f11: "f11", keyboard.Key.f12: "f12",
}


class ControllerMapper:
    def __init__(self, root):
        self.root = root

        self.running = False
        self.closing = False
        self.device = None
        self.reader_thread = None

        self.keyboard = keyboard.Controller()
        self.mouse = mouse.Controller()

        self.config_dir = CONFIG_FILE if os.path.exists(CONFIG_FILE) else DEFAULT_CONFIG_FILE
        self.vendor_mappings = {}
        self.mappings = self.load_mappings()
        self.presets = getattr(self, "loaded_presets", {"Default": self.mappings.copy()})
        self.preset_categories = set(getattr(self, "loaded_categories", set()))
        if not self.presets:
            self.presets = {"Default": self.mappings.copy()}
        self.active_preset = next(iter(self.presets))
        self.preset_var = tk.StringVar(value=self.active_preset)
        self.switch_button_var = tk.StringVar(value=CENTER_BUTTON)
        self.switch_stick_var = tk.StringVar(value="right")
        self.switch_modifier_held = False
        self.switcher_hold_after_id = None
        self.switcher_hold_triggered = False
        self.switcher_window = None
        self.switcher_canvas = None
        self.switcher_items = []
        self.switcher_selected = 0
        self.switcher_path = ""
        self.switcher_nodes = []
        self.dark_mode_var = tk.BooleanVar(value=False)
        self.event_log_visible = tk.BooleanVar(value=True)

        self.mouse_speed = tk.IntVar(value=28)
        self.deadzone = tk.IntVar(value=13000)
        self.mouse_stick = tk.StringVar(value="right")

        self.device_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Stopped")

        self.devices = {}
        self.device_ids = {}
        self.vendor_mappings = {}

        # Latest physical stick positions.
        self.axis_lock = threading.Lock()
        self.axis_values = {
            ecodes.ABS_X: 0,
            ecodes.ABS_Y: 0,
            ecodes.ABS_RX: 0,
            ecodes.ABS_RY: 0,
        }
        self.axis_ranges = {}
        self.dpad_directions = set()

        # Fractional mouse movement is retained between Tk updates.
        self.mouse_remainder_x = 0.0
        self.mouse_remainder_y = 0.0

        # Keyboard learning state.
        self.capture_listener = None
        self.capture_mapping = None
        self.capture_parts = set()
        self.capture_pressed = set()
        self.capture_lock = threading.Lock()

        self.mapping_entries = {}
        self.mapping_display_vars = {}
        self.mapping_edit_buttons = {}
        self.mapping_clear_buttons = {}

        self.build_gui()
        if hasattr(self, "initial_config"):
            self.apply_config(self.initial_config)
        self.refresh_devices()
        self.refresh_preset_combo()

        # Mouse polling runs on Tk's event loop, so it can NEVER block
        # window close/stop handling.
        self.root.after(8, self.mouse_tick)

    # ---------------------------------------------------------
    # GUI
    # ---------------------------------------------------------

    def set_window_icon(self, window):
        if not hasattr(self, "window_icon"):
            icon = tk.PhotoImage(width=32, height=32)
            body = "#46a6ff"
            for y in range(32):
                for x in range(32):
                    in_shell = (
                        (6 <= x <= 25 and 7 <= y <= 21)
                        or (3 <= x <= 9 and 14 <= y <= 25)
                        or (22 <= x <= 28 and 14 <= y <= 25)
                    )
                    if in_shell:
                        icon.put(body, (x, y))
            # D-pad and four face buttons.
            for x, y in ((8, 15), (8, 17), (7, 16), (9, 16),
                         (23, 14), (25, 16), (23, 18), (21, 16)):
                icon.put("#102033", (x, y))
            self.window_icon = icon
        window.iconphoto(True, self.window_icon)

    def build_gui(self):
        self.root.title("USB Controller Mapper")
        self.root.geometry("720x1000")
        self.root.minsize(720, 960)
        self.set_window_icon(self.root)

        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Import", command=self.import_presets)
        file_menu.add_command(label="Export", command=self.export_presets)
        menubar.add_cascade(label="File", menu=file_menu)
        edit_menu = tk.Menu(menubar, tearoff=False)
        preset_edit_menu = tk.Menu(edit_menu, tearoff=False)
        preset_edit_menu.add_command(label="Create preset…", command=self.create_preset)
        preset_edit_menu.add_command(label="Rename active preset…", command=self.edit_preset)
        preset_edit_menu.add_command(label="Remove active preset", command=self.remove_preset)
        edit_menu.add_cascade(label="Presets", menu=preset_edit_menu)
        category_edit_menu = tk.Menu(edit_menu, tearoff=False)
        category_edit_menu.add_command(label="Add category…", command=self.create_category)
        category_edit_menu.add_command(label="Add subcategory…", command=self.create_subcategory)
        category_edit_menu.add_command(label="Rename selected category…", command=self.rename_category)
        category_edit_menu.add_command(label="Remove selected category", command=self.remove_category)
        edit_menu.add_cascade(label="Categories", menu=category_edit_menu)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        window_menu = tk.Menu(menubar, tearoff=False)
        window_menu.add_checkbutton(
            label="Dark Mode", variable=self.dark_mode_var,
            command=self.apply_theme,
        )
        window_menu.add_separator()
        window_menu.add_checkbutton(
            label="Show/Hide Event Log Window", variable=self.event_log_visible,
            command=self.toggle_event_log,
        )
        menubar.add_cascade(label="Window", menu=window_menu)
        self.root.configure(menu=menubar)
        self.menubar = menubar
        self.file_menu = file_menu
        self.edit_menu = edit_menu
        self.preset_edit_menu = preset_edit_menu
        self.category_edit_menu = category_edit_menu
        self.window_menu = window_menu

        main = ttk.Frame(self.root, padding=3)
        main.pack(fill="both", expand=True)

        device_frame = ttk.LabelFrame(main, text="Device", padding=3)
        device_frame.pack(fill="x")

        self.restart_button = ttk.Button(
            device_frame, text="Restart", command=self.restart, takefocus=True
        )
        self.restart_button.grid(row=0, column=0, padx=3)

        ttk.Button(
            device_frame, text="Start", command=self.start
        ).grid(row=0, column=1, padx=3)

        ttk.Button(
            device_frame, text="Exit", command=self.quit
        ).grid(row=0, column=3, padx=3)

        ttk.Button(
            device_frame, text="Stop", command=self.stop
        ).grid(row=0, column=2, padx=3)

        ttk.Label(device_frame, text="Device:").grid(
            row=1, column=0, sticky="w"
        )

        self.device_combo = ttk.Combobox(
            device_frame,
            textvariable=self.device_var,
            state="readonly",
            width=65,
        )
        self.device_combo.grid(
            row=1, column=1, padx=10, sticky="ew"
        )

        ttk.Button(
            device_frame, text="Refresh", command=self.refresh_devices
        ).grid(row=1, column=2)

        ttk.Label(device_frame, text="Status:").grid(row=2, column=0, padx=5)
        ttk.Label(
            device_frame, textvariable=self.status_var
        ).grid(row=2, column=1, padx=10)


        device_frame.columnconfigure(1, weight=1)

        preset_frame = ttk.LabelFrame(main, text="Presets", padding=3)
        preset_frame.pack(fill="x")

        ttk.Label(preset_frame, text="Active preset:").grid(row=0, column=0)

        self.preset_combo = ttk.Combobox(
            preset_frame, textvariable=self.preset_var, state="readonly", width=25
        )
        self.preset_combo.grid(row=0, column=1)
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_selected)

        ttk.Label(preset_frame, text="Category:").grid(row=1, column=0, padx=3)
        self.category_var = tk.StringVar(value="")
        self.category_combo = ttk.Combobox(
            preset_frame, textvariable=self.category_var, state="readonly", width=25
        )
        self.category_combo.grid(row=1, column=1, padx=3)
        self.category_combo.bind("<<ComboboxSelected>>", self.save_category_selection)
        ttk.Label(preset_frame, text="Tap / Hold button:").grid(row=2, column=0, padx=3)
        switch_button_combo = ttk.Combobox(
            preset_frame, textvariable=self.switch_button_var,
            values=("",) + SWITCHABLE_BUTTONS, state="readonly", width=20,
        )
        switch_button_combo.grid(row=2, column=1, padx=3)
        switch_button_combo.bind("<<ComboboxSelected>>", self.save_switcher_options)

        ttk.Label(preset_frame, text="+").grid(row=2, column=2, padx=5)
        switch_stick_combo = ttk.Combobox(
            preset_frame, textvariable=self.switch_stick_var,
            values=("left", "right"), state="readonly", width=7,
        )
        switch_stick_combo.grid(row=2, column=3, padx=3)
        switch_stick_combo.bind("<<ComboboxSelected>>", self.save_switcher_options)

        mapping_frame = ttk.LabelFrame(
            main, text="Button Mappings", padding=3
        )
        mapping_frame.pack(fill="x", pady=5)

        ttk.Label(mapping_frame, text="Controller").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(mapping_frame, text="Type: Action").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(mapping_frame, text="Edit action").grid(
            row=0, column=2, sticky="w"
        )
        ttk.Label(mapping_frame, text="Clear").grid(
            row=0, column=3, sticky="w"
        )

        for row, (button_name, default_action) in enumerate(
            DEFAULT_MAPPINGS.items(), start=1
        ):
            ttk.Label(mapping_frame, text=button_name).grid(
                row=row, column=0, sticky="w",
                padx=(0, 15), pady=2
            )

            variable = tk.StringVar(value="")
            entry = ttk.Entry(mapping_frame, textvariable=variable, width=38, state="disabled")
            entry.grid(row=row, column=1, sticky="ew", pady=2)
            self.mapping_display_vars[button_name] = variable
            self.mapping_entries[button_name] = variable

            edit_button = ttk.Button(
                mapping_frame, text="Edit action", width=12,
                command=lambda name=button_name: self.edit_action(name),
            )
            edit_button.grid(row=row, column=2, padx=(8, 5), pady=2)
            self.mapping_edit_buttons[button_name] = edit_button

            clear_button = ttk.Button(
                mapping_frame, text="Clear", width=7,
                command=lambda name=button_name: self.clear_mapping(name),
            )
            clear_button.grid(row=row, column=3, padx=(0, 4), pady=2)
            self.mapping_clear_buttons[button_name] = clear_button

        mapping_frame.columnconfigure(1, weight=1)

        mouse_frame = ttk.LabelFrame(
            main, text="Mouse / Analog Stick", padding=3
        )
        mouse_frame.pack(fill="x")

        ttk.Label(mouse_frame, text="Mouse stick:").grid(
            row=0, column=0, sticky="w"
        )

        ttk.Combobox(
            mouse_frame,
            textvariable=self.mouse_stick,
            values=("left", "right"),
            state="readonly",
            width=8,
        ).grid(row=0, column=1, padx=8, sticky="w")

        ttk.Label(mouse_frame, text="Speed:").grid(
            row=0, column=2, sticky="w"
        )

        ttk.Spinbox(
            mouse_frame, from_=1, to=100,
            textvariable=self.mouse_speed, width=8
        ).grid(row=0, column=3, padx=8, sticky="w")

        ttk.Label(mouse_frame, text="Deadzone:").grid(
            row=0, column=4, sticky="w"
        )

        ttk.Spinbox(
            mouse_frame, from_=500, to=30000, increment=500,
            textvariable=self.deadzone, width=8
        ).grid(row=0, column=5, padx=8, sticky="w")

        ttk.Button(
            mouse_frame, text="Test Mouse", command=self.test_mouse
        ).grid(row=0, column=6, padx=15)


        self.create_event_log_window()
        self.apply_theme()

        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # ---------------------------------------------------------
    # Devices
    # ---------------------------------------------------------

    def create_event_log_window(self):
        self.event_log_window = tk.Toplevel(self.root)
        self.set_window_icon(self.event_log_window)
        self.event_log_window.title("Controller Event Log")
        self.event_log_window.geometry("720x320")
        self.event_log_window.protocol("WM_DELETE_WINDOW", self.hide_event_log)
        frame = ttk.Frame(self.event_log_window, padding=0)
        frame.pack(fill="both", expand=True)
        self.log = tk.Text(
            frame,
            height=12,
            state="disabled",
            background="#000000",
            foreground="#00ff00",
            insertbackground="#00ff00",
            selectbackground="#006600",
            selectforeground="#ffffff",
            font=("Monospace", 10),
            wrap="none",
            borderwidth=0,
            highlightthickness=0,
        )
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(frame, command=self.log.yview)
        scrollbar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scrollbar.set)

    def hide_event_log(self):
        self.event_log_visible.set(False)
        self.event_log_window.withdraw()

    def toggle_event_log(self):
        if self.event_log_visible.get():
            self.event_log_window.deiconify()
            self.event_log_window.lift()
        else:
            self.event_log_window.withdraw()

    def apply_theme(self):
        style = ttk.Style(self.root)
        if not hasattr(self, "default_theme"):
            self.default_theme = style.theme_use()
            self.default_root_background = self.root.cget("background")
            menu_options = (
                "background", "foreground", "activebackground",
                "activeforeground", "disabledforeground", "selectcolor",
            )
            self.default_menu_options = {
                option: self.menubar.cget(option) for option in menu_options
            }
        if self.dark_mode_var.get():
            if "clam" in style.theme_names():
                style.theme_use("clam")
            background = "#202124"
            panel = "#2b2c30"
            foreground = "#e8eaed"
            field = "#151618"
            active = "#3c4043"
            self.root.configure(background=background)
            style.configure(".", background=background, foreground=foreground)
            style.configure("TFrame", background=background)
            style.configure("TLabel", background=background, foreground=foreground)
            style.configure("TLabelframe", background=background, foreground=foreground)
            style.configure("TLabelframe.Label", background=background, foreground=foreground)
            style.configure("TButton", background=panel, foreground=foreground)
            style.map("TButton", background=[("active", active), ("pressed", "#505257")])
            style.configure("TEntry", fieldbackground=field, foreground=foreground)
            style.configure("TCombobox", fieldbackground=field, background=panel, foreground=foreground, arrowcolor=foreground)
            style.map("TCombobox", fieldbackground=[("readonly", field)], foreground=[("readonly", foreground)])
            style.configure("TSpinbox", fieldbackground=field, background=panel, foreground=foreground, arrowcolor=foreground)
            menu_options = {
                "background": panel,
                "foreground": foreground,
                "activebackground": active,
                "activeforeground": foreground,
                "disabledforeground": "#777777",
                "selectcolor": foreground,
            }
        else:
            style.theme_use(self.default_theme)
            self.root.configure(background=self.default_root_background)
            menu_options = self.default_menu_options
        for menu in (self.menubar, self.file_menu, self.edit_menu,
                     self.preset_edit_menu, self.category_edit_menu, self.window_menu):
            menu.configure(**menu_options)

    def refresh_devices(self):
        self.devices.clear()
        entries = []

        for path in evdev.list_devices():
            try:
                device = evdev.InputDevice(path)
                capabilities = device.capabilities()
                keys = capabilities.get(ecodes.EV_KEY, [])
                axes = capabilities.get(ecodes.EV_ABS, [])

                has_buttons = any(
                    code in keys for code in (
                        ecodes.BTN_SOUTH, ecodes.BTN_EAST,
                        ecodes.BTN_WEST, ecodes.BTN_NORTH,
                        ecodes.BTN_TL, ecodes.BTN_TR,
                        ecodes.BTN_START, ecodes.BTN_SELECT,
                        ecodes.BTN_THUMBL, ecodes.BTN_THUMBR, 316,
                    )
                ) or any(ecodes.BTN_JOYSTICK <= code <= ecodes.BTN_THUMBR for code in keys) \
                    or any(code in keys for code in (544, 545, 546, 547))

                has_axes = any(
                    code in axes for code in (
                        ecodes.ABS_X, ecodes.ABS_Y,
                        ecodes.ABS_RX, ecodes.ABS_RY,
                        getattr(ecodes, "ABS_HAT0X", -1),
                        getattr(ecodes, "ABS_HAT0Y", -2),
                    )
                )

                if not (has_buttons or has_axes):
                    device.close()
                    continue

                name = device.name or "Unknown Controller"
                display = f"{name} ({path})"
                self.devices[display] = path
                self.device_ids[display] = f"{device.info.vendor:04x}:{device.info.product:04x}"
                entries.append(display)
                device.close()

            except (PermissionError, OSError):
                continue
            except Exception:
                continue

        self.device_combo["values"] = entries

        if entries:
            self.device_combo.current(0)
            self.set_status(f"Found {len(entries)} controller(s)")
        else:
            self.set_status("No game controllers found")

    # ---------------------------------------------------------
    # Controller lifecycle
    # ---------------------------------------------------------

    def start(self):
        if self.running or self.closing:
            return

        selected = self.device_var.get()
        path = self.devices.get(selected)

        if not path:
            messagebox.showwarning(
                "Controller", "Select a controller first."
            )
            return

        self.running = True

        with self.axis_lock:
            for code in self.axis_values:
                self.axis_values[code] = 0

        self.reader_thread = threading.Thread(
            target=self.read_controller,
            args=(path,),
            daemon=True,
        )
        self.reader_thread.start()

        self.set_status("Starting...")

    def stop(self):
        if not self.running and self.device is None:
            self.set_status("Stopped")
            return

        self.running = False
        self.update_dpad(set())

        with self.axis_lock:
            for code in self.axis_values:
                self.axis_values[code] = 0

        # Closing the evdev fd is what wakes a blocking read_loop().
        # Do NOT join the reader thread from Tkinter.
        device = self.device
        self.device = None

        if device:
            try:
                device.close()
            except Exception:
                pass

        self.reader_thread = None
        self.set_status("Stopped")

    def restart(self):
        selected = self.device_var.get()
        self.stop()
        if not self.devices.get(selected):
            self.refresh_devices()
            selected = self.device_var.get()
        if self.devices.get(selected):
            self.device_var.set(selected)
            self.start()

    def read_controller(self, path):
        device = None

        try:
            device = evdev.InputDevice(path)

            if not self.running:
                device.close()
                return

            self.device = device
            self.ui_log(f"Connected: {device.name}")
            self.ui_status(f"Connected: {device.name}")

            # Capture actual axis ranges.
            for code in (
                ecodes.ABS_X, ecodes.ABS_Y,
                ecodes.ABS_RX, ecodes.ABS_RY,
            ):
                try:
                    info = device.absinfo(code)
                    if info:
                        self.axis_ranges[code] = (
                            info.min, info.max, info.flat
                        )
                except Exception:
                    pass

            for event in device.read_loop():
                if not self.running or self.closing:
                    break

                if event.type == ecodes.EV_KEY:
                    self.handle_button(event)
                elif event.type == ecodes.EV_ABS:
                    self.handle_axis(event)

        except PermissionError:
            if not self.closing:
                self.ui_status("Permission denied reading controller")
                self.ui_log(f"Permission denied: {path}")

        except OSError as exc:
            if self.running and not self.closing:
                self.ui_status(f"Controller error: {exc}")
                self.ui_log(f"ERROR: {exc}")

        except Exception as exc:
            if not self.closing:
                self.ui_status(f"Controller error: {exc}")
                self.ui_log(f"ERROR: {type(exc).__name__}: {exc}")

        finally:
            if device:
                try:
                    device.close()
                except Exception:
                    pass

            if self.device is device:
                self.device = None

            if self.running and not self.closing:
                self.ui_status("Controller disconnected")

    # ---------------------------------------------------------
    # Controller events
    # ---------------------------------------------------------

    def handle_button(self, event):
        code_name = str(event.code)
        button_name = self.resolve_button(event.code)

        if event.value not in (0, 1, 2):
            self.ui_log(f"Invalid event value")
            return

        switch_button = self.switch_button_var.get()
        if switch_button and button_name == switch_button:
            if event.value == 1 and not self.switch_modifier_held:
                self.switch_modifier_held = True
                self.switcher_hold_triggered = False
                self.switch_axis_values = {ecodes.ABS_X: 0, ecodes.ABS_Y: 0,
                                           ecodes.ABS_RX: 0, ecodes.ABS_RY: 0}
            elif event.value == 0 and self.switch_modifier_held:
                self.switch_modifier_held = False
                self.root.after(0, self.finish_switch_button_press)
            self.root.after(0, self.update_switch_button_timer)
            return

        if self.switch_modifier_held:
            if button_name in ("Left stick click", "Right stick click"):
                if event.value == 1 and self.switcher_window and self.switcher_window.winfo_exists():
                    self.root.after(0, self.enter_selected_switcher_node)
                return

        action = self.mappings.get(button_name, "").strip() if button_name else ""
        if not action:
            self.ui_log(f"Detected input. (No mapping found for: {button_name or code_name})")
            return

        # Preserve press/release for mouse buttons.
        if event.value == 1:
            self.execute_action(action, pressed=True)
            self.ui_log(f"{button_name} -> {action} PRESS")
        elif event.value == 0:
            self.execute_action(action, pressed=False)
            self.ui_log(f"{button_name} -> {action} RELEASE")

    def resolve_button(self, code):
        selected = self.device_var.get()
        vendor_id = self.device_ids.get(selected, "default")
        vendor_map = self.vendor_mappings.get(vendor_id, DEFAULT_VENDOR_MAP)
        code_name = ecodes.KEY.get(code, str(code))
        if isinstance(code_name, list):
            code_name = code_name[0]
        return vendor_map.get(str(code), vendor_map.get(str(code_name)))

    def handle_axis(self, event):
        if self.switch_modifier_held:
            stick = self.switch_stick_var.get()
            switch_codes = (
                (ecodes.ABS_X, ecodes.ABS_Y)
                if stick == "left" else (ecodes.ABS_RX, ecodes.ABS_RY)
            )
            if event.code in switch_codes:
                self.switch_axis_values[event.code] = event.value
                x = self.switch_axis_values[switch_codes[0]]
                y = self.switch_axis_values[switch_codes[1]]
                if abs(x) > 12000 or abs(y) > 12000:
                    self.root.after(0, lambda x=x, y=y: self.select_switcher_direction(x, y))
                return

        hat_axes = {}
        for hat_number in range(4):
            hat_axes[getattr(ecodes, f"ABS_HAT{hat_number}X", -100 - hat_number)] = (
                "D-pad left", "D-pad right", "horizontal"
            )
            hat_axes[getattr(ecodes, f"ABS_HAT{hat_number}Y", -200 - hat_number)] = (
                "D-pad up", "D-pad down", "vertical"
            )
        if event.code in hat_axes:
            negative, positive, axis = hat_axes[event.code]
            active = set()
            if event.value < 0:
                active.add(negative)
            elif event.value > 0:
                active.add(positive)
            # Reconcile each axis independently so a vertical update does not
            # release a still-held horizontal direction on a diagonal hat.
            same_axis_directions = (
                {"D-pad left", "D-pad right"}
                if axis == "horizontal" else {"D-pad up", "D-pad down"}
            )
            # Clear any previously held direction on this axis, while
            # preserving the other axis so diagonal input remains supported.
            other_axis_directions = set(BUTTONS[-4:]) - same_axis_directions
            new_directions = (self.dpad_directions & other_axis_directions) | active
            self.update_dpad(new_directions)
            return

        if event.code not in self.axis_values:
            return

        with self.axis_lock:
            self.axis_values[event.code] = event.value

    def update_dpad(self, directions):
        for name in self.dpad_directions - directions:
            action = self.mappings.get(name, "").strip()
            if action:
                self.execute_action(action, pressed=False)
                self.ui_log(f"{name} -> {action} RELEASE")
        for name in directions - self.dpad_directions:
            action = self.mappings.get(name, "").strip()
            if action:
                self.execute_action(action, pressed=True)
                self.ui_log(f"{name} -> {action} PRESS")
            else:
                self.ui_log(f"Detected input. (No mapping found for: {name})")
        self.dpad_directions = directions

    def show_preset_switcher(self):
        if not self.presets and not self.preset_categories:
            return
        if self.switcher_window and self.switcher_window.winfo_exists():
            return
        self.open_switcher_level("")

    def update_switch_button_timer(self):
        if not self.switch_modifier_held or self.switcher_hold_triggered:
            return
        if self.switcher_hold_after_id is None:
            self.switcher_hold_after_id = self.root.after(420, self.trigger_long_hold)

    def trigger_long_hold(self):
        self.switcher_hold_after_id = None
        if self.switch_modifier_held:
            self.switcher_hold_triggered = True
            self.show_preset_switcher()

    def finish_switch_button_press(self):
        if self.switcher_hold_after_id is not None:
            self.root.after_cancel(self.switcher_hold_after_id)
            self.switcher_hold_after_id = None
        if self.switcher_hold_triggered:
            self.commit_preset_switcher()
        else:
            self.toggle_management_window()

    def toggle_management_window(self):
        if self.root.state() in ("withdrawn", "iconic"):
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        else:
            self.root.withdraw()

    def children_for_path(self, path):
        prefix = f"{path}/" if path else ""
        candidates = {}
        for category in self.preset_categories:
            if category.startswith(prefix):
                remainder = category[len(prefix):]
                if remainder:
                    name = remainder.split("/", 1)[0]
                    candidates[name] = {
                        "name": name,
                        "path": f"{prefix}{name}".rstrip("/"),
                        "type": "subcategory" if path else "category",
                    }
        for preset_path in self.presets:
            if preset_path.startswith(prefix):
                remainder = preset_path[len(prefix):]
                if remainder:
                    parts = remainder.split("/", 1)
                    name = parts[0]
                    if len(parts) == 1:
                        candidates[name] = {
                            "name": name,
                            "path": preset_path,
                            "type": "preset",
                        }
                    else:
                        candidates.setdefault(name, {
                            "name": name,
                            "path": f"{prefix}{name}".rstrip("/"),
                            "type": "subcategory" if path else "category",
                        })
        return sorted(candidates.values(), key=lambda node: (node["type"] == "preset", node["name"].casefold()))

    def open_switcher_level(self, path):
        self.switcher_path = path
        self.switcher_nodes = self.children_for_path(path)
        if path:
            self.switcher_nodes.insert(0, {"name": "↩ Back", "path": path.rpartition("/")[0], "type": "back"})
        names = [node["path"] for node in self.switcher_nodes]
        active_index = next((
            index for index, node in enumerate(self.switcher_nodes)
            if self.active_preset == node["path"] or self.active_preset.startswith(node["path"] + "/")
        ), 0)
        self.switcher_selected = active_index
        window = tk.Toplevel(self.root)
        self.set_window_icon(window)
        self.switcher_window = window
        title = f"Preset Switcher — {path}" if path else "Preset Switcher"
        window.title(title)
        window.attributes("-topmost", True)
        window.focus_force()
        canvas = tk.Canvas(window, width=760, height=760, bg="#20242b", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        self.switcher_canvas = canvas
        self.draw_preset_switcher()

    def draw_preset_switcher(self):
        canvas = self.switcher_canvas
        if not canvas or not canvas.winfo_exists():
            return
        canvas.delete("all")
        nodes = self.switcher_nodes
        if not nodes:
            canvas.create_text(380, 380, text="No items in this category", fill="white", font=("TkDefaultFont", 28))
            return
        radius = max(250, 38 * len(nodes))
        size = max(760, 2 * (radius + 130))
        cx = cy = size // 2
        canvas.configure(width=size, height=size)
        self.switcher_window.geometry(f"{size}x{size}")
        canvas.create_oval(cx - 76, cy - 76, cx + 76, cy + 76, outline="#aab2bf", width=3)
        center_label = self.switcher_path.split("/")[-1] if self.switcher_path else "Presets"
        canvas.create_text(cx, cy - 12, text=center_label, fill="white", font=("TkDefaultFont", 24, "bold"), width=170)
        canvas.create_text(cx, cy + 38, text="Release to select", fill="#c8cdd4", font=("TkDefaultFont", 18))
        self.switcher_items = []
        for index, node in enumerate(nodes):
            angle = -math.pi / 2 + 2 * math.pi * index / len(nodes)
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            color = self.switcher_color(node["type"], index == self.switcher_selected)
            canvas.create_oval(x - 112, y - 58, x + 112, y + 58, fill=color, outline="white", width=3)
            label = node["name"] + ("  ›" if node["type"] in ("category", "subcategory") else "")
            label = self.fit_switcher_label(label, width=200, max_lines=3)
            canvas.create_text(x, y, text=label, fill="white", width=200,
                               font=self.switcher_label_font, justify="center")
            self.switcher_items.append((x, y))
        legend = (("Category", "category"), ("Subcategory", "subcategory"),
                  ("Preset", "preset"), ("Back", "back"))
        legend_y = size - 34
        x = 18
        for label, node_type in legend:
            canvas.create_rectangle(x, legend_y - 10, x + 20, legend_y + 10,
                                    fill=self.switcher_color(node_type, False), outline="white")
            canvas.create_text(x + 28, legend_y, text=label, fill="white",
                               anchor="w", font=("TkDefaultFont", 14))
            x += 130

    def fit_switcher_label(self, text, width, max_lines):
        if not hasattr(self, "switcher_label_font"):
            self.switcher_label_font = tkfont.Font(
                root=self.root, family="TkDefaultFont", size=20, weight="bold"
            )
        font = self.switcher_label_font
        lines = []
        current = ""
        for word in text.split():
            pending = word
            while pending:
                candidate = f"{current} {pending}".strip()
                if font.measure(candidate) <= width:
                    current = candidate
                    break
                if current:
                    lines.append(current)
                    current = ""
                    continue
                chunk = ""
                for char in pending:
                    if chunk and font.measure(chunk + char) > width:
                        lines.append(chunk)
                        chunk = char
                    else:
                        chunk += char
                current = chunk
                pending = ""
        if current:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            last = lines[-1]
            while last and font.measure(last + "…") > width:
                last = last[:-1]
            lines[-1] = last.rstrip() + "…"
        return "\n".join(lines)

    @staticmethod
    def switcher_color(node_type, selected):
        colors = {
            "category": ("#365a8c", "#5e9dea"),
            "subcategory": ("#65508a", "#a987e8"),
            "preset": ("#286b50", "#4bd89a"),
            "back": ("#555b62", "#aab2bb"),
        }
        return colors.get(node_type, colors["preset"])[1 if selected else 0]

    def select_switcher_direction(self, x, y):
        if not self.switcher_nodes or (x == 0 and y == 0):
            return
        angle = math.atan2(y, x)
        positions = [(-math.pi / 2 + 2 * math.pi * i / len(self.switcher_nodes)) for i in range(len(self.switcher_nodes))]
        self.switcher_selected = min(
            range(len(positions)),
            key=lambda i: abs((angle - positions[i] + math.pi) % (2 * math.pi) - math.pi),
        )
        self.draw_preset_switcher()
        node = self.switcher_nodes[self.switcher_selected]
    def enter_selected_switcher_node(self):
        if not self.switch_modifier_held or not self.switcher_window or not self.switcher_window.winfo_exists():
            return
        if not (0 <= self.switcher_selected < len(self.switcher_nodes)):
            return
        node = self.switcher_nodes[self.switcher_selected]
        if node["type"] not in ("category", "subcategory", "back"):
            return
        self.switcher_window.destroy()
        self.switcher_window = None
        self.open_switcher_level(node["path"])

    def commit_preset_switcher(self):
        if 0 <= self.switcher_selected < len(self.switcher_nodes):
            selected = self.switcher_nodes[self.switcher_selected]
            if selected["type"] == "preset":
                self.apply_preset(selected["path"])
        if self.switcher_window and self.switcher_window.winfo_exists():
            self.switcher_window.destroy()
        self.switcher_window = None

    # ---------------------------------------------------------
    # Smooth mouse
    # ---------------------------------------------------------

    def normalize_axis(self, code, value):
        axis_min, axis_max, flat = self.axis_ranges.get(
            code, (22000, 22000, 0) # -32768, 32767
        )

        center = (axis_min + axis_max) / 2.0
        half_range = max(
            (axis_max - axis_min) / 2.0, 1.0
        )

        normalized = (value - center) / half_range
        normalized = max(-1.0, min(1.0, normalized))

        deadzone = max(
            self.deadzone.get() / half_range,
            (flat or 0) / half_range,
        )

        if abs(normalized) <= deadzone:
            return 0.0

        magnitude = (
            abs(normalized) - deadzone
        ) / max(1.0 - deadzone, 0.00005)

        magnitude = max(0.0, min(1.0, magnitude))

        # Smooth but still reaches full speed at the edge.
        magnitude = magnitude * magnitude

        return magnitude if normalized >= 0 else -magnitude

    def mouse_tick(self):
        if not self.closing:
            stick = self.mouse_stick.get()

            x_code = (
                ecodes.ABS_RX if stick == "right"
                else ecodes.ABS_X
            )
            y_code = (
                ecodes.ABS_RY if stick == "right"
                else ecodes.ABS_Y
            )

            with self.axis_lock:
                x_value = self.axis_values[x_code]
                y_value = self.axis_values[y_code]

            x = self.normalize_axis(x_code, x_value)
            y = self.normalize_axis(y_code, y_value)

            # Speed is pixels/frame at 60 Hz.
            # The 8ms timer makes the motion smooth without depending
            # on repeated Linux ABS events.
            speed = max(1, self.mouse_speed.get())
            scale = speed * 0.008 * 60.0

            self.mouse_remainder_x += x * scale
            self.mouse_remainder_y += y * scale

            dx = int(self.mouse_remainder_x)
            dy = int(self.mouse_remainder_y)

            self.mouse_remainder_x -= dx
            self.mouse_remainder_y -= dy

            if dx or dy:
                self.mouse.move(dx, dy)

            self.root.after(8, self.mouse_tick)

    # ---------------------------------------------------------
    # Actions
    # ---------------------------------------------------------

    def execute_action(self, action, pressed=True):
        action = action.strip()
        lower = action.lower()

        mouse_buttons = {
            "mouse:left": mouse.Button.left,
            "mouse:middle": mouse.Button.middle,
            "mouse:right": mouse.Button.right,
        }

        if lower in mouse_buttons:
            button = mouse_buttons[lower]
            if pressed:
                self.mouse.press(button)
            else:
                self.mouse.release(button)
            return

        if pressed and lower == "mouse:scroll_up":
            self.mouse.scroll(0, 1)
            return

        if pressed and lower == "mouse:scroll_down":
            self.mouse.scroll(0, -1)
            return

        if lower.startswith("hotkey:"):
            if pressed:
                self.press_hotkey(action[7:])
            return

        if lower.startswith("key:"):
            if pressed:
                self.press_key(action[4:].strip().lower())
            return

        if lower.startswith("text:"):
            if pressed:
                self.keyboard.type(action[5:])
            return

        if lower.startswith("command:"):
            if pressed:
                command = action[len("command:"):].strip()
                if command:
                    try:
                        subprocess.Popen(command, shell=True)
                        self.ui_log(f"Started command: {command}")
                    except Exception as exc:
                        self.ui_log(f"Command failed: {exc}")
            return

        if pressed:
            self.press_key(lower)

    def resolve_key(self, name):
        name = name.strip().lower()
        if name in KEY_MAP:
            return KEY_MAP[name]
        if len(name) == 1:
            return name
        return None

    def press_key(self, name):
        key = self.resolve_key(name)
        if key is None:
            self.ui_log(f"Unknown key: {name}")
            return
        self.keyboard.press(key)
        self.keyboard.release(key)

    def press_hotkey(self, value):
        names = [
            x.strip().lower()
            for x in value.split("+")
            if x.strip()
        ]

        keys = []
        for name in names:
            key = self.resolve_key(name)
            if key is None:
                self.ui_log(f"Unknown hotkey key: {name}")
                return
            keys.append(key)

        for key in keys:
            self.keyboard.press(key)
        for key in reversed(keys):
            self.keyboard.release(key)

    def clear_mapping(self, mapping_name):
        self.mappings[mapping_name] = ""
        self.mapping_entries[mapping_name].set("")
        if self.active_preset in self.presets:
            self.presets[self.active_preset] = self.mappings.copy()
            self.persist_presets()
        self.refresh_mapping_displays()
        self.set_status(f"Cleared mapping for {mapping_name}")

    def action_summary(self, action):
        if not action:
            return "None"
        lower = action.lower()
        if lower.startswith("command:"):
            return f"Command: {action[8:]}"
        if lower.startswith("mouse:"):
            return f"Mouse: {action[6:]}"
        if lower.startswith("hotkey:"):
            return f"Keyboard: {action[7:]}"
        if lower.startswith("key:"):
            return f"Keyboard: {action[4:]}"
        if lower.startswith("text:"):
            return f"Keyboard text: {action[5:]}"
        return f"Keyboard: {action}"

    def edit_action(self, button_name):
        current = self.mappings.get(button_name, "")
        kind = "keyboard"
        value = current
        if current.lower().startswith("command:"):
            kind, value = "command", current[8:]
        elif current.lower().startswith("mouse:"):
            kind, value = "mouse", current[6:]
        elif current.lower().startswith("hotkey:"):
            value = current[7:]
        elif current.lower().startswith("key:"):
            value = current[4:]
        elif current.lower().startswith("text:"):
            value = current[5:]

        dialog = tk.Toplevel(self.root)
        self.set_window_icon(dialog)
        dialog.title(f"Edit action — {button_name}")
        dialog.transient(self.root)
        dialog.grab_set()
        kind_var = tk.StringVar(value=kind)
        value_var = tk.StringVar(value=value)
        ttk.Label(dialog, text="Action type:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        type_box = ttk.Combobox(dialog, textvariable=kind_var, values=("command", "keyboard", "mouse"), state="readonly", width=18)
        type_box.grid(row=0, column=1, padx=10, pady=8, sticky="ew")
        field_label = ttk.Label(dialog, text="Command:" if kind == "command" else "Mouse action:" if kind == "mouse" else "Key / hotkey / text:")
        field_label.grid(row=1, column=0, padx=10, pady=8, sticky="w")
        field = ttk.Entry(dialog, textvariable=value_var, width=42)
        field.grid(row=1, column=1, padx=10, pady=8, sticky="ew")
        mouse_box = ttk.Combobox(dialog, textvariable=value_var, values=("left", "middle", "right", "scroll_up", "scroll_down"), state="readonly", width=39)
        dialog.columnconfigure(1, weight=1)
        hint = ttk.Label(dialog, text="Keyboard examples: space, hotkey:ctrl+c, text:hello")
        hint.grid(row=2, column=0, columnspan=2, padx=10, sticky="w")

        def update_field(*_):
            selected = kind_var.get()
            field_label.configure(text={"command": "Command:", "keyboard": "Key / hotkey / text:", "mouse": "Mouse action:"}[selected])
            if selected == "mouse":
                hint.configure(text="Choose a mouse button or scroll action.")
                value_var.set(value_var.get().removeprefix("mouse:") if value_var.get().startswith("mouse:") else value_var.get())
                field.grid_remove()
                mouse_box.grid(row=1, column=1, padx=10, pady=8, sticky="ew")
            else:
                hint.configure(text="Keyboard examples: space, hotkey:ctrl+c, text:hello" if selected == "keyboard" else "Enter a command to run when the controller button is pressed.")
                mouse_box.grid_remove()
                field.grid()

        kind_var.trace_add("write", update_field)
        update_field()
        def save():
            raw = value_var.get().strip()
            selected = kind_var.get()
            if selected == "command":
                action = f"command:{raw}" if raw else ""
            elif selected == "mouse":
                action = f"mouse:{raw}" if raw else ""
            elif raw.lower().startswith(("hotkey:", "key:", "text:")):
                action = raw
            else:
                action = raw
            self.mappings[button_name] = action
            self.mapping_entries[button_name].set(self.action_summary(action))
            if self.active_preset:
                self.presets[self.active_preset] = self.mappings.copy()
                self.persist_presets()
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(buttons, text="Save", command=save).pack(side="left", padx=5)
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=5)

    def refresh_mapping_displays(self):
        for name, variable in self.mapping_display_vars.items():
            variable.set(self.action_summary(self.mappings.get(name, "")))

    def refresh_preset_combo(self):
        if hasattr(self, "preset_combo"):
            self.preset_combo["values"] = tuple(self.presets)
            self.preset_var.set(self.active_preset)
        if hasattr(self, "category_combo"):
            self.category_combo["values"] = ("",) + tuple(sorted(self.preset_categories, key=lambda p: (p.count("/"), p.casefold())))
            parent = self.active_preset.rpartition("/")[0]
            self.category_var.set(parent if parent in self.preset_categories else "")
        self.refresh_mapping_displays()

    def on_preset_selected(self, _event=None):
        self.apply_preset(self.preset_var.get())

    def save_switcher_options(self, _event=None):
        self.persist_presets()

    def apply_preset(self, name):
        if name not in self.presets:
            return
        self.active_preset = name
        self.preset_var.set(name)
        parent = name.rpartition("/")[0]
        if hasattr(self, "category_var"):
            self.category_var.set(parent if parent in self.preset_categories else "")
        self.mappings = self.presets[name].copy()
        self.refresh_mapping_displays()
        self.persist_presets()
        self.set_status(f"Preset: {name}")

    def preset_name_dialog(self, title, initial=""):
        dialog = tk.Toplevel(self.root)
        self.set_window_icon(dialog)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.grab_set()
        value = tk.StringVar(value=initial)
        ttk.Label(dialog, text="Preset name:").pack(padx=12, pady=(12, 4), anchor="w")
        entry = ttk.Entry(dialog, textvariable=value, width=32)
        entry.pack(padx=12, pady=4)
        entry.focus_set()
        result = {"value": None}
        def accept():
            name = value.get().strip()
            if not name:
                messagebox.showwarning("Preset", "Enter a preset name.", parent=dialog)
                return
            result["value"] = name
            dialog.destroy()
        actions = ttk.Frame(dialog)
        actions.pack(pady=10)
        ttk.Button(actions, text="OK", command=accept).pack(side="left", padx=4)
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="left", padx=4)
        self.root.wait_window(dialog)
        return result["value"]

    def create_preset(self):
        name = self.preset_name_dialog("Create preset")
        if not name:
            return
        if "/" in name:
            path = name.strip("/")
        else:
            category = self.category_var.get() if hasattr(self, "category_var") else ""
            path = f"{category}/{name}" if category else name
        ancestors = self.category_ancestors(path)
        if not self.valid_hierarchy_path(path) or path in self.presets or path in self.preset_categories or any(item in self.presets for item in ancestors):
            messagebox.showerror("Preset", "A preset with that name already exists.")
            return
        self.preset_categories.update(ancestors)
        self.presets[path] = self.mappings.copy()
        self.active_preset = path
        self.persist_presets()
        self.refresh_preset_combo()

    def create_category(self):
        name = self.preset_name_dialog("Create category")
        if not name:
            return
        path = name.strip("/")
        ancestors = self.category_ancestors(path)
        if not self.valid_hierarchy_path(path) or path in self.preset_categories or path in self.presets or any(item in self.presets for item in ancestors):
            messagebox.showerror("Category", "That path already exists.")
            return
        self.preset_categories.update(self.category_ancestors(path, include_self=True))
        self.persist_presets()
        self.refresh_preset_combo()

    def create_subcategory(self):
        parent = self.category_var.get().strip("/")
        if not parent:
            messagebox.showinfo("Category", "Select a parent category first.")
            return
        child = self.preset_name_dialog("Create subcategory")
        if not child:
            return
        path = f"{parent}/{child.strip('/')}"
        ancestors = self.category_ancestors(path, include_self=True)
        if not self.valid_hierarchy_path(path) or path in self.preset_categories or path in self.presets or any(item in self.presets for item in ancestors):
            messagebox.showerror("Category", "That path already exists.")
            return
        self.preset_categories.update(ancestors)
        self.persist_presets()
        self.refresh_preset_combo()

    def save_category_selection(self, _event=None):
        self.persist_presets()

    @staticmethod
    def category_ancestors(path, include_self=False):
        parts = path.split("/")
        limit = len(parts) if include_self else len(parts) - 1
        return {"/".join(parts[:index]) for index in range(1, limit + 1)}

    @staticmethod
    def valid_hierarchy_path(path):
        return bool(path) and all(part.strip() and part == part.strip() for part in path.split("/"))

    def rename_category(self):
        old = self.category_var.get().strip("/")
        if not old:
            messagebox.showinfo("Category", "Select a category first.")
            return
        new_leaf = self.preset_name_dialog("Rename category", old.rsplit("/", 1)[-1])
        if not new_leaf:
            return
        parent = old.rpartition("/")[0]
        new = f"{parent}/{new_leaf.strip('/')}" if parent else new_leaf.strip("/")
        if new == old:
            return
        if not self.valid_hierarchy_path(new) or new.startswith(old + "/") or new in self.preset_categories or new in self.presets:
            messagebox.showerror("Category", "That path already exists.")
            return
        renamed_categories = {
            (new + path[len(old):]) if path == old or path.startswith(old + "/") else path
            for path in self.preset_categories
        }
        for category in tuple(renamed_categories):
            renamed_categories.update(self.category_ancestors(category, include_self=True))
        self.preset_categories = renamed_categories
        self.preset_categories.update(
            ancestor
            for category in tuple(self.preset_categories)
            for ancestor in self.category_ancestors(category, include_self=True)
        )
        self.presets = {
            (new + path[len(old):]) if path.startswith(old + "/") else path: mapping
            for path, mapping in self.presets.items()
        }
        if self.active_preset.startswith(old + "/"):
            self.active_preset = new + self.active_preset[len(old):]
        self.persist_presets()
        self.refresh_preset_combo()

    def remove_category(self):
        path = self.category_var.get().strip("/")
        if not path:
            messagebox.showinfo("Category", "Select a category first.")
            return
        if not messagebox.askyesno("Remove category", f"Remove '{path}' and everything inside it?"):
            return
        self.preset_categories = {
            item for item in self.preset_categories
            if item != path and not item.startswith(path + "/")
        }
        self.presets = {
            name: mapping for name, mapping in self.presets.items()
            if not (name == path or name.startswith(path + "/"))
        }
        if not self.presets:
            self.presets["Default"] = DEFAULT_MAPPINGS.copy()
        if self.active_preset not in self.presets:
            self.active_preset = next(iter(self.presets))
        self.apply_preset(self.active_preset)
        self.refresh_preset_combo()

    def edit_preset(self):
        old = self.active_preset
        if not old:
            return
        name = self.preset_name_dialog("Rename preset", old.rsplit("/", 1)[-1])
        if not name:
            return
        parent = old.rpartition("/")[0]
        new = f"{parent}/{name}" if parent else name
        if new != old and (not self.valid_hierarchy_path(new) or new in self.presets or new in self.preset_categories):
            messagebox.showerror("Preset", "A preset with that name already exists.")
            return
        del self.presets[old]
        self.presets[new] = self.mappings.copy()
        self.preset_categories.update(self.category_ancestors(new))
        self.active_preset = new
        self.persist_presets()
        self.refresh_preset_combo()

    def remove_preset(self):
        if not self.active_preset:
            return
        if len(self.presets) <= 1:
            messagebox.showwarning("Preset", "At least one preset must remain.")
            return
        if not messagebox.askyesno("Remove preset", f"Remove '{self.active_preset}'?"):
            return
        del self.presets[self.active_preset]
        self.active_preset = next(iter(self.presets))
        self.apply_preset(self.active_preset)
        self.persist_presets()
        self.refresh_preset_combo()

    def persist_presets(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as stream:
                json.dump(self.config_data(), stream, indent=2)
            self.config_dir = CONFIG_FILE
        except Exception as exc:
            self.set_status(f"Preset save failed: {exc}")

    # ---------------------------------------------------------
    # Save / load
    # ---------------------------------------------------------

    def collect_mappings(self):
        return self.mappings.copy()

    def save_mappings(self):
        self.mappings = self.collect_mappings()
        try:
            self.write_config(self.config_dir)
            self.set_status(f"Saved {self.config_dir}")
            self.append_log(f"Saved mappings to {self.config_dir}")
        except Exception as exc:
            self.set_status(f"Save failed: {exc}")
            messagebox.showerror(
                "Save Error",
                f"{type(exc).__name__}: {exc}"
            )

    def load_mappings(self):
        path = getattr(self, "config_dir", CONFIG_FILE)
        if not os.path.exists(path):
            return DEFAULT_MAPPINGS.copy()

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.initial_config = data
            self.vendor_mappings = data.get("vendor_mappings", {})
            raw_presets = data.get("presets")
            if raw_presets:
                self.loaded_presets, self.loaded_categories = self.decode_presets(raw_presets)
                if not self.loaded_presets:
                    self.loaded_presets = {"Default": DEFAULT_MAPPINGS.copy()}
                self.active_preset = data.get("active_preset", next(iter(self.loaded_presets)))
                self.switch_button_default = data.get("switch_button", "Shmenxs-Böx Button")
                self.switch_stick_default = data.get("switch_stick", "right")
                mappings = self.loaded_presets.get(self.active_preset, next(iter(self.loaded_presets.values())))
                return self.normalize_mapping(mappings)
            mappings = data.get("mappings", DEFAULT_MAPPINGS.copy())
            if mappings and all(key not in BUTTONS for key in mappings):
                # Migrate the old event-code -> action format to named rows.
                translated = DEFAULT_MAPPINGS.copy()
                for code, action in mappings.items():
                    button = DEFAULT_VENDOR_MAP.get(str(code))
                    if button:
                        translated[button] = action
                return translated
            return mappings

        except Exception as exc:
            self.ui_log(exc)
            return DEFAULT_MAPPINGS.copy()

    def load_into_gui(self):
        try:
            if not os.path.exists(self.config_dir):
                self.set_status("No saved configuration")
                return

            with open(self.config_dir, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.apply_config(data)

            self.set_status(f"Loaded: {self.config_dir}")
            self.append_log(f"Loaded mappings from {self.config_dir}")

        except Exception as exc:
            self.set_status(f"Load failed: {exc}")
            messagebox.showerror(
                "Load Error",
                f"{type(exc).__name__}: {exc}"
            )

    def apply_config(self, data):
        presets = data.get("presets")
        if presets:
            self.presets, self.preset_categories = self.decode_presets(presets)
            if not self.presets:
                self.presets = {"Default": self.normalize_mapping(data.get("mappings", DEFAULT_MAPPINGS))}
                self.preset_categories = set()
            self.active_preset = data.get("active_preset", next(iter(self.presets)))
            if self.active_preset not in self.presets:
                self.active_preset = next(iter(self.presets))
            mappings = self.presets[self.active_preset].copy()
        else:
            mappings = data.get("mappings", DEFAULT_MAPPINGS.copy())
            mappings = self.normalize_mapping(mappings)
            self.presets = {"Default": mappings.copy()}
            self.preset_categories = set()
            self.active_preset = "Default"
        # Accept legacy configs that used event codes as mapping keys.
        if mappings and all(key not in BUTTONS for key in mappings):
            migrated = {name: "" for name in BUTTONS}
            for code, action in mappings.items():
                name = DEFAULT_VENDOR_MAP.get(str(code))
                if name:
                    migrated[name] = action
            mappings = migrated
        self.mappings = mappings
        self.vendor_mappings = data.get("vendor_mappings", {})
        switch_button = data.get("switch_button", getattr(self, "switch_button_default", "Shmenxs-Böx Button"))
        self.switch_button_var.set(switch_button or "Shmenxs-Böx Button")
        self.switch_stick_var.set(data.get("switch_stick", getattr(self, "switch_stick_default", "right")))

        if "mouse_speed" in data:
            self.mouse_speed.set(int(data["mouse_speed"]))
        if "deadzone" in data:
            self.deadzone.set(int(data["deadzone"]))
        if "mouse_stick" in data:
            self.mouse_stick.set(data["mouse_stick"])

        self.refresh_preset_combo()

    def normalize_mapping(self, mappings):
        normalized = {name: "" for name in BUTTONS}
        if mappings and all(name not in BUTTONS for name in mappings):
            for code, action in mappings.items():
                button = DEFAULT_VENDOR_MAP.get(str(code))
                if button:
                    normalized[button] = action
        else:
            normalized.update({name: action for name, action in mappings.items() if name in BUTTONS})
        return normalized

    def decode_presets(self, preset_data):
        flat = {}
        categories = set()
        if isinstance(preset_data, dict) and preset_data.get("type") == "category":
            def visit(node, parent_path=""):
                for name, child in node.get("children", {}).items():
                    path = f"{parent_path}/{name}" if parent_path else str(name)
                    if child.get("type") == "preset":
                        flat[path] = self.normalize_mapping(child.get("mappings", {}))
                    elif child.get("type") in ("category", "subcategory"):
                        categories.add(path)
                        visit(child, path)
            visit(preset_data)
        else:
            # Read earlier flat preset files and convert names containing '/'
            # into nested category paths.
            for name, mapping in preset_data.items():
                if isinstance(mapping, dict):
                    flat[str(name)] = self.normalize_mapping(mapping)
                    categories.update(self.category_ancestors(str(name)))
        return flat, categories

    def encode_presets(self, preset_names=None):
        selected = set(self.presets if preset_names is None else preset_names)
        root = {"type": "category", "name": "Presets", "children": {}}
        categories = set(self.preset_categories) if preset_names is None else {
            category for category in self.preset_categories
            if any(name == category or name.startswith(category + "/") for name in selected)
        }
        for name in selected:
            categories.update(self.category_ancestors(name))

        def category_node(children, segment, depth):
            node_type = "category" if depth == 0 else "subcategory"
            if segment not in children or children[segment].get("type") not in ("category", "subcategory"):
                children[segment] = {"type": node_type, "children": {}}
            return children[segment]["children"]

        for category in sorted(categories, key=lambda path: (path.count("/"), path.casefold())):
            parts = category.split("/")
            children = root["children"]
            for depth, segment in enumerate(parts):
                children = category_node(children, segment, depth)
        for path in sorted(selected, key=str.casefold):
            if path not in self.presets:
                continue
            parts = path.split("/")
            children = root["children"]
            for depth, segment in enumerate(parts[:-1]):
                children = category_node(children, segment, depth)
            children[parts[-1]] = {"type": "preset", "mappings": self.presets[path]}
        return root

    def config_data(self):
        return {
            "mappings": self.collect_mappings(),
            "presets": self.encode_presets(),
            "active_preset": self.active_preset,
            "vendor_mappings": self.vendor_mappings,
            "mouse_speed": self.mouse_speed.get(),
            "deadzone": self.deadzone.get(),
            "mouse_stick": self.mouse_stick.get(),
            "switch_button": self.switch_button_var.get(),
            "switch_stick": self.switch_stick_var.get(),
        }

    def write_config(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.config_data(), f, indent=2)

    def export_presets(self):
        dialog = tk.Toplevel(self.root)
        self.set_window_icon(dialog)
        dialog.title("Export presets")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="Select presets to export:").pack(anchor="w", padx=10, pady=(10, 4))
        listing = tk.Listbox(dialog, selectmode="extended", exportselection=False,
                             height=min(12, max(4, len(self.presets))))
        listing.pack(fill="both", expand=True, padx=10, pady=4)
        for name in self.presets:
            listing.insert("end", name)
        selection = {"names": []}
        def accept():
            selection["names"] = [listing.get(i) for i in listing.curselection()]
            dialog.destroy()
        buttons = ttk.Frame(dialog)
        buttons.pack(pady=8)
        ttk.Button(buttons, text="Export", command=accept).pack(side="left", padx=4)
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=4)
        self.root.wait_window(dialog)
        if not selection["names"]:
            return
        path = filedialog.asksaveasfilename(
            title="Export selected presets", defaultextension=".json",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            payload = {"presets": self.encode_presets(selection["names"])}
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
            self.set_status(f"Exported {len(selection['names'])} preset(s) to {path}")
        except Exception as exc:
            messagebox.showerror("Export Error", f"{type(exc).__name__}: {exc}")

    def import_presets(self):
        path = filedialog.askopenfilename(
            title="Import presets",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            incoming_data = data.get("presets")
            if not incoming_data:
                legacy = data.get("mappings", data)
                incoming_data = {os.path.splitext(os.path.basename(path))[0] or "Imported": legacy}
            incoming, incoming_categories = self.decode_presets(incoming_data)
            category_renames = {}

            def remap_import_path(import_path):
                result = import_path
                changed = True
                while changed:
                    changed = False
                    for old_path in sorted(category_renames, key=len, reverse=True):
                        if result == old_path or result.startswith(old_path + "/"):
                            updated = category_renames[old_path] + result[len(old_path):]
                            if updated != result:
                                result = updated
                                changed = True
                                break
                return result

            for original in sorted(incoming_categories, key=lambda value: (value.count("/"), value.casefold())):
                category = remap_import_path(original)
                if category in self.presets:
                    parent, _, leaf = category.rpartition("/")
                    candidate = category
                    suffix = 2
                    while candidate in self.presets or candidate in self.preset_categories:
                        candidate = f"{parent + '/' if parent else ''}{leaf} ({suffix})"
                        suffix += 1
                    category_renames[category] = candidate
            incoming = {remap_import_path(name): mapping for name, mapping in incoming.items()}
            incoming_categories = {remap_import_path(name) for name in incoming_categories}
            self.preset_categories.update(incoming_categories)
            added = []
            for name, mapping in incoming.items():
                base = str(name).strip("/") or "Imported"
                candidate = base
                suffix = 2
                while candidate in self.presets or candidate in self.preset_categories:
                    parent, _, leaf = base.rpartition("/")
                    candidate = f"{parent + '/' if parent else ''}{leaf} ({suffix})"
                    suffix += 1
                self.presets[candidate] = self.normalize_mapping(mapping)
                self.preset_categories.update(self.category_ancestors(candidate))
                added.append(candidate)
            if added:
                self.apply_preset(added[0])
            if added or incoming_categories:
                self.persist_presets()
                self.refresh_preset_combo()
            self.set_status(f"Imported {len(added)} preset(s) from {path}")
        except Exception as exc:
            messagebox.showerror("Import Error", f"{type(exc).__name__}: {exc}")

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def select_file(self):
        file_types = [
            ('JSON Files', '*.json'),
            ('All Files', '*.*')
        ]
        file_path = filedialog.askopenfilename(
            title='Select a Mapping File',
            filetypes=file_types
        )
        if file_path:
            self.config_dir = file_path
            print(f"Selected map file: {file_path}")

    def test_mouse(self):
        self.mouse.move(20, 0)
        time.sleep(0.03)
        self.mouse.move(-20, 0)
        self.mouse.click(mouse.Button.left)
        self.append_log("Mouse test passed")

    def quit(self):
        exit(0)

    def set_status(self, text):
        if not self.closing:
            self.ui_log(text)
            self.status_var.set(text)

    def ui_status(self, text):
        if not self.closing:
            self.root.after(
                0, lambda: self.set_status(text)
            )

    def ui_log(self, text):
        if not self.closing:
            self.root.after(
                0, lambda: self.append_log(text)
            )

    def append_log(self, text):
        if self.closing:
            return
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def close(self):
        if self.closing:
            return

        self.closing = True
        self.running = False

        self.cancel_key_capture()

        with self.axis_lock:
            for code in self.axis_values:
                self.axis_values[code] = 0

        # Close the fd immediately. This wakes read_loop().
        device = self.device
        self.device = None
        if device:
            try:
                device.close()
            except Exception:
                pass

        # No join here. Tk must remain responsive.
        self.root.destroy()


def main():
    root = tk.Tk()
    ControllerMapper(root)
    root.mainloop()


if __name__ == "__main__":
    main()

out.write_text(code, encoding="utf-8")
print(out)
