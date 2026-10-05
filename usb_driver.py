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
    "tab": keyboard.Key.tab,
    "backspace": keyboard.Key.backspace,
    "shift": keyboard.Key.shift,
    "ctrl": keyboard.Key.ctrl,
    "alt": keyboard.Key.alt,
    "cmd": keyboard.Key.cmd,

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

    "f1": keyboard.Key.f1,
    "f2": keyboard.Key.f2,
    "f3": keyboard.Key.f3,
    "f4": keyboard.Key.f4,
    "f5": keyboard.Key.f5,
    "f6": keyboard.Key.f6,
    "f7": keyboard.Key.f7,
    "f8": keyboard.Key.f8,
    "f9": keyboard.Key.f9,
    "f10": keyboard.Key.f10,
    "f11": keyboard.Key.f11,
    "f12": keyboard.Key.f12,
}


class ControllerMapper:
    def __init__(self, root):
        self.root = root

        self.running = False
        self.device = None
        self.reader_thread = None

        self.keyboard = keyboard.Controller()
        self.mouse = mouse.Controller()

        self.mappings = self.load_mappings()

        self.mouse_speed = tk.IntVar(value=15)
        self.deadzone = tk.IntVar(value=8000)

        self.device_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Stopped")

        self.devices = {}

        self.build_gui()
        self.refresh_devices()

    # ---------------------------------------------------------
    # GUI
    # ---------------------------------------------------------

    def build_gui(self):
        self.root.title("USB Controller Mapper")
        self.root.geometry("800x700")
        self.root.minsize(640, 900)

        main = ttk.Frame(self.root, padding=15)
        main.pack(fill="both", expand=True)

        # Device section
        device_frame = ttk.LabelFrame(
            main,
            text="Controller",
            padding=10
        )
        device_frame.pack(fill="x")

        ttk.Label(
            device_frame,
            text="Device:"
        ).grid(row=0, column=0, sticky="w")

        self.device_combo = ttk.Combobox(
            device_frame,
            textvariable=self.device_var,
            state="readonly",
            width=65
        )
        self.device_combo.grid(
            row=0,
            column=1,
            padx=10,
            sticky="ew"
        )

        ttk.Button(
            device_frame,
            text="Refresh",
            command=self.refresh_devices
        ).grid(row=0, column=2)

        device_frame.columnconfigure(1, weight=1)

        # Status
        status_frame = ttk.Frame(main)
        status_frame.pack(fill="x", pady=(10, 5))

        ttk.Label(
            status_frame,
            text="Status:"
        ).pack(side="left")

        self.status_label = ttk.Label(
            status_frame,
            textvariable=self.status_var
        )
        self.status_label.pack(side="left", padx=8)

        # Mapping area
        mapping_frame = ttk.LabelFrame(
            main,
            text="Button Mappings",
            padding=10
        )
        mapping_frame.pack(
            fill="both",
            expand=True,
            pady=10
        )

        ttk.Label(
            mapping_frame,
            text="Controller"
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            mapping_frame,
            text="Action"
        ).grid(row=0, column=1, sticky="w")

        self.mapping_entries = {}

        row = 1

        for button_name, default_action in DEFAULT_MAPPINGS.items():
            ttk.Label(
                mapping_frame,
                text=button_name
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 20),
                pady=2
            )

            variable = tk.StringVar(
                value=self.mappings.get(
                    button_name,
                    default_action
                )
            )

            entry = ttk.Entry(
                mapping_frame,
                textvariable=variable,
                width=30
            )

            entry.grid(
                row=row,
                column=1,
                sticky="ew",
                pady=2
            )

            self.mapping_entries[button_name] = variable

            row += 1

        mapping_frame.columnconfigure(1, weight=1)

        # Mouse configuration
        mouse_frame = ttk.LabelFrame(
            main,
            text="Mouse / Analog Stick",
            padding=10
        )
        mouse_frame.pack(fill="x")

        ttk.Label(
            mouse_frame,
            text="Mouse speed:"
        ).grid(row=0, column=0, sticky="w")

        ttk.Spinbox(
            mouse_frame,
            from_=1,
            to=100,
            textvariable=self.mouse_speed,
            width=8
        ).grid(row=0, column=1, padx=10)

        ttk.Label(
            mouse_frame,
            text="Deadzone:"
        ).grid(row=0, column=2, sticky="w")

        ttk.Spinbox(
            mouse_frame,
            from_=1000,
            to=30000,
            increment=1000,
            textvariable=self.deadzone,
            width=8
        ).grid(row=0, column=3, padx=10)

        # Buttons
        controls = ttk.Frame(main)
        controls.pack(fill="x", pady=10)

        ttk.Button(
            controls,
            text="Save",
            command=self.save_mappings
        ).pack(side="left", padx=3)

        ttk.Button(
            controls,
            text="Load",
            command=self.load_into_gui
        ).pack(side="left", padx=3)

        ttk.Button(
            controls,
            text="Start",
            command=self.start
        ).pack(side="left", padx=15)

        ttk.Button(
            controls,
            text="Stop",
            command=self.stop
        ).pack(side="left", padx=3)

        # Log
        log_frame = ttk.LabelFrame(
            main,
            text="Event Log",
            padding=5
        )
        log_frame.pack(fill="both", expand=True)

        self.log = tk.Text(
            log_frame,
            height=8,
            state="disabled"
        )
        self.log.pack(
            side="left",
            fill="both",
            expand=True
        )

        scrollbar = ttk.Scrollbar(
            log_frame,
            command=self.log.yview
        )
        scrollbar.pack(side="right", fill="y")

        self.log.configure(
            yscrollcommand=scrollbar.set
        )

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close
        )

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

                has_gamepad_buttons = any(
                    code in keys
                    for code in (
                        ecodes.BTN_SOUTH,
                        ecodes.BTN_EAST,
                        ecodes.BTN_WEST,
                        ecodes.BTN_NORTH,
                        ecodes.BTN_TL,
                        ecodes.BTN_TR,
                        ecodes.BTN_START,
                        ecodes.BTN_SELECT,
                        ecodes.BTN_THUMBL,
                        ecodes.BTN_THUMBR,
                    )
                )

                has_gamepad_axes = any(
                    code in axes
                    for code in (
                        ecodes.ABS_X,
                        ecodes.ABS_Y,
                        ecodes.ABS_RX,
                        ecodes.ABS_RY,
                    )
                )

                if not (
                    has_gamepad_buttons
                    or has_gamepad_axes
                ):
                    device.close()
                    continue

                name = device.name or "Unknown Controller"

                display = f"{name} ({path})"

                self.devices[display] = path
                entries.append(display)

                device.close()

            except PermissionError:
                continue

            except Exception:
                continue

        self.device_combo["values"] = entries

        if entries:
            self.device_combo.current(0)

            self.set_status(
                f"Found {len(entries)} controller(s)"
            )

        else:
            self.set_status(
                "No game controllers found"
            )

    # ---------------------------------------------------------
    # Controller thread
    # ---------------------------------------------------------

    def start(self):
        if self.running:
            return

        selected = self.device_var.get()

        if not selected:
            messagebox.showwarning(
                "Controller",
                "Select a controller first."
            )
            return

        path = self.devices.get(selected)

        if not path:
            messagebox.showerror(
                "Controller",
                "Selected controller is no longer available."
            )
            return

        self.running = True

        self.reader_thread = threading.Thread(
            target=self.read_controller,
            args=(path,),
            daemon=True
        )

        self.reader_thread.start()

        self.set_status("Starting...")

    def stop(self):
        self.running = False

        self.set_status("Stopped")

        if self.reader_thread:
            self.reader_thread.join(timeout=0.5)
            self.reader_thread = None

        self.device = None

    def read_controller(self, path):
        try:
            self.device = evdev.InputDevice(path)

            self.ui_log(
                f"Connected: {self.device.name}"
            )

            self.ui_status(
                f"Connected: {self.device.name}"
            )

            for event in self.device.read_loop():

                if not self.running:
                    break

                self.handle_event_debug(event)

                if event.type == ecodes.EV_KEY:
                    self.handle_button(event)

                elif event.type == ecodes.EV_ABS:
                    self.handle_axis(event)

        except PermissionError:
            self.ui_status(
                "Permission denied reading controller"
            )

            self.ui_log(
                f"Permission denied: {path}"
            )

        except Exception as exc:
            self.ui_status(
                f"Controller error: {exc}"
            )

            self.ui_log(
                f"ERROR: {exc}"
            )

        finally:
            if self.device:
                try:
                    self.device.close()
                except Exception:
                    pass

            self.device = None

    # ---------------------------------------------------------
    # Button handling
    # ---------------------------------------------------------

    def handle_button(self, event):
        code_name = ecodes.KEY.get(
            event.code,
            str(event.code)
        )

        if isinstance(code_name, list):
            code_name = code_name[0]

        # Only process press/release.
        if event.value not in (0, 1):
            return

        action = self.mappings.get(code_name)

        if not action:
            return

        if event.value == 1:
            self.execute_action(action)

            self.ui_log(
                f"{code_name} -> {action}"
            )

    # ---------------------------------------------------------
    # Analog sticks
    # ---------------------------------------------------------

    def handle_axis(self, event):
        if event.code == ecodes.ABS_X:
            self.move_mouse_x(event.value)

        elif event.code == ecodes.ABS_Y:
            self.move_mouse_y(event.value)

        elif event.code == ecodes.ABS_RX:
            self.move_mouse_x(event.value)

        elif event.code == ecodes.ABS_RY:
            self.move_mouse_y(event.value)

    def normalize_axis(self, value):
        deadzone = self.deadzone.get()

        if abs(value) < deadzone:
            return 0

        # Preserve direction while removing the deadzone.
        sign = 1 if value > 0 else -1

        adjusted = abs(value) - deadzone
        maximum = 32767 - deadzone

        if maximum <= 0:
            return 0

        normalized = adjusted / maximum

        return sign * min(normalized, 1.0)

    def move_mouse_x(self, value):
        normalized = self.normalize_axis(value)

        if normalized == 0:
            return

        amount = int(
            normalized * self.mouse_speed.get()
        )

        if amount:
            self.mouse.move(amount, 0)

    def move_mouse_y(self, value):
        normalized = self.normalize_axis(value)

        if normalized == 0:
            return

        amount = int(
            normalized * self.mouse_speed.get()
        )

        if amount:
            self.mouse.move(0, amount)

    # ---------------------------------------------------------
    # Action engine
    # ---------------------------------------------------------

    def execute_action(self, action):
        action = action.strip()

        if not action:
            return

        lower = action.lower()

        # Mouse
        if lower in (
            "mouse:left",
            "mouse:middle",
            "mouse:right"
        ):
            button_name = lower.split(":")[1]

            button = {
                "left": mouse.Button.left,
                "middle": mouse.Button.middle,
                "right": mouse.Button.right,
            }[button_name]

            self.mouse.click(button)

            return

        # Keyboard
        if lower.startswith("key:"):
            key_name = action[4:].strip().lower()
            self.press_key(key_name)
            return

        # Text
        if lower.startswith("text:"):
            text = action[5:]
            self.keyboard.type(text)
            return

        # Bare key
        self.press_key(lower)

    def press_key(self, key_name):
        key = KEY_MAP.get(key_name)

        if key is None:
            if len(key_name) == 1:
                key = key_name
            else:
                self.ui_log(
                    f"Unknown key: {key_name}"
                )
                return

        self.keyboard.press(key)
        self.keyboard.release(key)

    # ---------------------------------------------------------
    # Configuration
    # ---------------------------------------------------------

    def collect_mappings(self):
        return {
            name: variable.get()
            for name, variable
            in self.mapping_entries.items()
        }

    def save_mappings(self):
        self.mappings = self.collect_mappings()

        data = {
            "mappings": self.mappings,
            "mouse_speed": self.mouse_speed.get(),
            "deadzone": self.deadzone.get(),
        }

        try:
            with open(
                CONFIG_FILE,
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    data,
                    file,
                    indent=2
                )

            self.set_status(
                f"Saved {CONFIG_FILE}"
            )

            self.append_log(
                f"Saved mappings to {CONFIG_FILE}"
            )

        except Exception as exc:
            self.set_status(
                f"Save failed: {exc}"
            )

            self.append_log(
                f"SAVE ERROR: {type(exc).__name__}: {exc}"
            )

            messagebox.showerror(
                "Save Error",
                f"{type(exc).__name__}: {exc}"
            )

    def load_mappings(self):
        if not os.path.exists(CONFIG_FILE):
            return DEFAULT_MAPPINGS.copy()

        try:
            with open(
                CONFIG_FILE,
                "r",
                encoding="utf-8"
            ) as file:
                data = json.load(file)

            if "mappings" in data:
                return data["mappings"]

            return data

        except Exception:
            return DEFAULT_MAPPINGS.copy()

    def load_into_gui(self):
        try:
            if not os.path.exists(CONFIG_FILE):
                self.set_status("No saved configuration")
                return

            with open(
                CONFIG_FILE,
                "r",
                encoding="utf-8"
            ) as file:
                data = json.load(file)

            self.mappings = data.get(
                "mappings",
                DEFAULT_MAPPINGS.copy()
            )

            for name, variable in self.mapping_entries.items():
                variable.set(
                    self.mappings.get(name, "")
                )

            if "mouse_speed" in data:
                self.mouse_speed.set(
                    int(data["mouse_speed"])
                )

            if "deadzone" in data:
                self.deadzone.set(
                    int(data["deadzone"])
                )

            self.set_status(
                f"Loaded: {CONFIG_FILE}"
            )

            self.append_log(
                f"Loaded mappings from {CONFIG_FILE}"
            )

        except Exception as exc:
            self.set_status(
                f"Load failed: {exc}"
            )

            self.append_log(
                f"LOAD ERROR: {type(exc).__name__}: {exc}"
            )

            messagebox.showerror(
                "Load Error",
                f"{type(exc).__name__}: {exc}"
            )

    # ---------------------------------------------------------
    # GUI helpers
    # ---------------------------------------------------------

    def set_status(self, text):
        self.root.after(
            0,
            lambda: self.status_var.set(text)
        )

    def ui_status(self, text):
        self.root.after(
            0,
            lambda: self.status_var.set(text)
        )

    def ui_log(self, text):
        self.root.after(
            0,
            lambda: self.append_log(text)
        )

    def append_log(self, text):
        self.log.configure(state="normal")

        self.log.insert(
            "end",
            text + "\n"
        )

        self.log.see("end")

        self.log.configure(state="disabled")

    def handle_event_debug(self, event):
        type_name = evdev.ecodes.EV[event.type] if event.type in evdev.ecodes.EV else str(event.type)

        if event.type == ecodes.EV_KEY:
            code_name = ecodes.KEY.get(event.code, str(event.code))
            value_name = {
                0: "RELEASE",
                1: "PRESS",
                2: "HOLD",
            }.get(event.value, str(event.value))

            self.ui_log(
                f"KEY  {code_name:<20} {value_name}"
            )

        elif event.type == ecodes.EV_ABS:
            code_name = ecodes.ABS.get(event.code, str(event.code))

            self.ui_log(
                f"AXIS {code_name:<20} {event.value}"
            )

        else:
            self.ui_log(
                f"{type_name:<6} code={event.code} value={event.value}"
            )

    def close(self):
        self.stop()
        self.root.destroy()


def main():
    root = tk.Tk()

    ControllerMapper(root)

    root.mainloop()


if __name__ == "__main__":
    main()
