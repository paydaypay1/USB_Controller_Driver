#!/usr/bin/env python3

import json
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import evdev
from evdev import ecodes
from pynput import keyboard
from pynput import mouse


CONFIG_FILE = os.path.expanduser("~/.controller_mapper.json")

DEFAULT_MAPPINGS = {
    "BTN_SOUTH": "space",
    "BTN_EAST": "esc",
    "BTN_WEST": "x",
    "BTN_NORTH": "y",
    "BTN_TL": "ctrl",
    "BTN_TR": "shift",
    "BTN_SELECT": "alt",
    "BTN_START": "enter",
    "BTN_THUMBL": "f1",
    "BTN_THUMBR": "f2",
    "DPAD_UP": "up",
    "DPAD_DOWN": "down",
    "DPAD_LEFT": "left",
    "DPAD_RIGHT": "right",
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

        self.mappings = self.load_mappings()

        self.mouse_speed = tk.IntVar(value=15)
        self.deadzone = tk.IntVar(value=8000)
        self.mouse_stick = tk.StringVar(value="right")

        self.device_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Stopped")

        self.devices = {}

        # Latest physical stick positions.
        self.axis_lock = threading.Lock()
        self.axis_values = {
            ecodes.ABS_X: 0,
            ecodes.ABS_Y: 0,
            ecodes.ABS_RX: 0,
            ecodes.ABS_RY: 0,
        }
        self.axis_ranges = {}

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
        self.mapping_mouse_vars = {}
        self.mapping_set_buttons = {}

        self.build_gui()
        self.refresh_devices()

        # Mouse polling runs on Tk's event loop, so it can NEVER block
        # window close/stop handling.
        self.root.after(8, self.mouse_tick)

    # ---------------------------------------------------------
    # GUI
    # ---------------------------------------------------------

    def build_gui(self):
        self.root.title("USB Controller Mapper")
        self.root.geometry("980x950")
        self.root.minsize(820, 820)

        main = ttk.Frame(self.root, padding=15)
        main.pack(fill="both", expand=True)

        device_frame = ttk.LabelFrame(main, text="Controller", padding=10)
        device_frame.pack(fill="x")

        ttk.Label(device_frame, text="Device:").grid(
            row=0, column=0, sticky="w"
        )

        self.device_combo = ttk.Combobox(
            device_frame,
            textvariable=self.device_var,
            state="readonly",
            width=65,
        )
        self.device_combo.grid(
            row=0, column=1, padx=10, sticky="ew"
        )

        ttk.Button(
            device_frame, text="Refresh", command=self.refresh_devices
        ).grid(row=0, column=2)

        device_frame.columnconfigure(1, weight=1)

        status_frame = ttk.Frame(main)
        status_frame.pack(fill="x", pady=(10, 5))

        ttk.Label(status_frame, text="Status:").pack(side="left")
        ttk.Label(
            status_frame, textvariable=self.status_var
        ).pack(side="left", padx=8)

        mapping_frame = ttk.LabelFrame(
            main, text="Button Mappings", padding=10
        )
        mapping_frame.pack(fill="x", pady=10)

        ttk.Label(mapping_frame, text="Controller").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(mapping_frame, text="Action").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(mapping_frame, text="Mouse").grid(
            row=0, column=2, sticky="w"
        )
        ttk.Label(mapping_frame, text="Learn").grid(
            row=0, column=3, sticky="w"
        )

        for row, (button_name, default_action) in enumerate(
            DEFAULT_MAPPINGS.items(), start=1
        ):
            ttk.Label(mapping_frame, text=button_name).grid(
                row=row, column=0, sticky="w",
                padx=(0, 15), pady=2
            )

            variable = tk.StringVar(
                value=self.mappings.get(button_name, default_action)
            )
            entry = ttk.Entry(
                mapping_frame,
                textvariable=variable,
                width=28,
            )
            entry.grid(
                row=row, column=1, sticky="ew", pady=2
            )
            self.mapping_entries[button_name] = variable

            mouse_var = tk.StringVar(value="")
            mouse_combo = ttk.Combobox(
                mapping_frame,
                textvariable=mouse_var,
                values=MOUSE_ACTIONS,
                state="readonly",
                width=20,
            )
            mouse_combo.grid(
                row=row, column=2, padx=(8, 8), pady=2
            )
            mouse_combo.bind(
                "<<ComboboxSelected>>",
                lambda event, name=button_name:
                    self.set_mouse_mapping_from_combo(name),
            )
            self.mapping_mouse_vars[button_name] = mouse_var

            learn_button = ttk.Button(
                mapping_frame,
                text="Set Key",
                width=10,
                command=lambda name=button_name:
                    self.begin_key_capture(name),
            )
            learn_button.grid(
                row=row, column=3, padx=(0, 5), pady=2
            )
            self.mapping_set_buttons[button_name] = learn_button

        mapping_frame.columnconfigure(1, weight=1)

        mouse_frame = ttk.LabelFrame(
            main, text="Mouse / Analog Stick", padding=10
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

        ttk.Label(
            mouse_frame,
            text="Mouse actions can be selected per button above.",
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(8, 0))

        controls = ttk.Frame(main)
        controls.pack(fill="x", pady=10)

        ttk.Button(
            controls, text="Save", command=self.save_mappings
        ).pack(side="left", padx=3)

        ttk.Button(
            controls, text="Load", command=self.load_into_gui
        ).pack(side="left", padx=3)

        ttk.Button(
            controls, text="Start", command=self.start
        ).pack(side="left", padx=15)

        ttk.Button(
            controls, text="Stop", command=self.stop
        ).pack(side="left", padx=3)

        ttk.Button(
            controls, text="Test Mouse", command=self.test_mouse
        ).pack(side="left", padx=15)

        log_frame = ttk.LabelFrame(main, text="Event Log", padding=5)
        log_frame.pack(fill="both", expand=True)

        self.log = tk.Text(
            log_frame, height=12, state="disabled"
        )
        self.log.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(
            log_frame, command=self.log.yview
        )
        scrollbar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scrollbar.set)

        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # ---------------------------------------------------------
    # Devices
    # ---------------------------------------------------------

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
                        ecodes.BTN_THUMBL, ecodes.BTN_THUMBR,
                    )
                )

                has_axes = any(
                    code in axes for code in (
                        ecodes.ABS_X, ecodes.ABS_Y,
                        ecodes.ABS_RX, ecodes.ABS_RY,
                    )
                )

                if not (has_buttons or has_axes):
                    device.close()
                    continue

                name = device.name or "Unknown Controller"
                display = f"{name} ({path})"
                self.devices[display] = path
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
        code_name = ecodes.KEY.get(event.code, str(event.code))
        if isinstance(code_name, list):
            code_name = code_name[0]

        if event.value not in (0, 1, 2):
            return

        action = self.mappings.get(code_name, "").strip()
        if not action:
            return

        # Preserve press/release for mouse buttons.
        if event.value == 1:
            self.execute_action(action, pressed=True)
            self.ui_log(f"{code_name} -> {action} PRESS")
        elif event.value == 0:
            self.execute_action(action, pressed=False)
            self.ui_log(f"{code_name} -> {action} RELEASE")

    def handle_axis(self, event):
        if event.code not in self.axis_values:
            return

        with self.axis_lock:
            self.axis_values[event.code] = event.value

    # ---------------------------------------------------------
    # Smooth mouse
    # ---------------------------------------------------------

    def normalize_axis(self, code, value):
        axis_min, axis_max, flat = self.axis_ranges.get(
            code, (-32768, 32767, 0)
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
        ) / max(1.0 - deadzone, 0.001)

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

    # ---------------------------------------------------------
    # Learn keyboard / hotkey
    # ---------------------------------------------------------

    def begin_key_capture(self, mapping_name):
        self.cancel_key_capture()

        self.capture_mapping = mapping_name
        self.capture_parts.clear()
        self.capture_pressed.clear()

        self.mapping_set_buttons[mapping_name].configure(
            text="Press key..."
        )
        self.set_status(
            f"Learning {mapping_name}: press a key or hotkey"
        )
        self.append_log(
            f"Learning keyboard mapping for {mapping_name}"
        )

        listener = keyboard.Listener(
            on_press=self.capture_press,
            on_release=self.capture_release,
        )
        self.capture_listener = listener
        listener.start()

    def capture_name(self, key):
        if key in SPECIAL_CAPTURE_NAMES:
            return SPECIAL_CAPTURE_NAMES[key]

        if isinstance(key, keyboard.KeyCode):
            if key.char:
                return key.char.lower()

        return str(key).replace("Key.", "").lower()

    def capture_press(self, key):
        with self.capture_lock:
            if not self.capture_mapping:
                return

            name = self.capture_name(key)
            self.capture_pressed.add(name)
            self.capture_parts.add(name)

    def capture_release(self, key):
        with self.capture_lock:
            if not self.capture_mapping:
                return

            name = self.capture_name(key)
            self.capture_pressed.discard(name)

            # Commit when the actual non-modifier key is released.
            if name not in ("ctrl", "alt", "shift", "cmd"):
                modifiers = [
                    x for x in ("ctrl", "alt", "shift", "cmd")
                    if x in self.capture_parts
                ]
                others = [
                    x for x in self.capture_parts
                    if x not in ("ctrl", "alt", "shift", "cmd")
                ]

                if modifiers:
                    value = "+".join(modifiers + [name])
                    action = f"hotkey:{value}"
                else:
                    action = name

                mapping = self.capture_mapping
                self.cancel_key_capture()
                self.root.after(
                    0,
                    lambda: self.apply_learned_mapping(
                        mapping, action
                    ),
                )

            elif self.capture_parts == {name}:
                mapping = self.capture_mapping
                self.cancel_key_capture()
                self.root.after(
                    0,
                    lambda: self.apply_learned_mapping(
                        mapping, name
                    ),
                )

    def apply_learned_mapping(self, mapping_name, action):
        self.mapping_entries[mapping_name].set(action)
        self.mapping_mouse_vars[mapping_name].set("")
        self.mapping_set_buttons[mapping_name].configure(
            text="Set Key"
        )
        self.set_status(f"{mapping_name} = {action}")
        self.append_log(f"Mapped {mapping_name} -> {action}")

    def cancel_key_capture(self):
        listener = self.capture_listener
        self.capture_listener = None
        self.capture_mapping = None
        self.capture_parts.clear()
        self.capture_pressed.clear()

        if listener:
            try:
                listener.stop()
            except Exception:
                pass

        for button in self.mapping_set_buttons.values():
            button.configure(text="Set Key")

    # ---------------------------------------------------------
    # Mouse mapping UI
    # ---------------------------------------------------------

    def set_mouse_mapping_from_combo(self, mapping_name):
        action = self.mapping_mouse_vars[mapping_name].get()

        if not action:
            return

        self.mapping_entries[mapping_name].set(action)
        self.set_status(
            f"{mapping_name} = {action}"
        )
        self.append_log(
            f"Mapped {mapping_name} -> {action}"
        )

    # ---------------------------------------------------------
    # Save / load
    # ---------------------------------------------------------

    def collect_mappings(self):
        return {
            name: var.get().strip()
            for name, var in self.mapping_entries.items()
        }

    def save_mappings(self):
        self.mappings = self.collect_mappings()

        data = {
            "mappings": self.mappings,
            "mouse_speed": self.mouse_speed.get(),
            "deadzone": self.deadzone.get(),
            "mouse_stick": self.mouse_stick.get(),
        }

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            self.set_status(f"Saved {CONFIG_FILE}")
            self.append_log(f"Saved mappings to {CONFIG_FILE}")

        except Exception as exc:
            self.set_status(f"Save failed: {exc}")
            messagebox.showerror(
                "Save Error",
                f"{type(exc).__name__}: {exc}"
            )

    def load_mappings(self):
        if not os.path.exists(CONFIG_FILE):
            return DEFAULT_MAPPINGS.copy()

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            return data.get("mappings", DEFAULT_MAPPINGS.copy())

        except Exception:
            return DEFAULT_MAPPINGS.copy()

    def load_into_gui(self):
        try:
            if not os.path.exists(CONFIG_FILE):
                self.set_status("No saved configuration")
                return

            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.mappings = data.get(
                "mappings", DEFAULT_MAPPINGS.copy()
            )

            for name, variable in self.mapping_entries.items():
                variable.set(self.mappings.get(name, ""))
                if self.mappings.get(name, "").lower().startswith("mouse:"):
                    self.mapping_mouse_vars[name].set(
                        self.mappings[name]
                    )
                else:
                    self.mapping_mouse_vars[name].set("")

            if "mouse_speed" in data:
                self.mouse_speed.set(int(data["mouse_speed"]))
            if "deadzone" in data:
                self.deadzone.set(int(data["deadzone"]))
            if "mouse_stick" in data:
                self.mouse_stick.set(data["mouse_stick"])

            self.set_status(f"Loaded: {CONFIG_FILE}")
            self.append_log(f"Loaded mappings from {CONFIG_FILE}")

        except Exception as exc:
            self.set_status(f"Load failed: {exc}")
            messagebox.showerror(
                "Load Error",
                f"{type(exc).__name__}: {exc}"
            )

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def test_mouse(self):
        self.mouse.move(20, 0)
        time.sleep(0.03)
        self.mouse.move(-20, 0)
        self.mouse.click(mouse.Button.left)
        self.append_log("Mouse test passed")

    def set_status(self, text):
        if not self.closing:
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
