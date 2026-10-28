# USB_Controller_Driver
Driver to run various (custom) hotkey mappings in Unix through a GUI


### To run:
```python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

source .venv/bin/activate
python usb_driver.py
```


### Dependencies
**See: requirements.txt**

### Actions and presets
Use **Edit action** on a mapping row to choose a keyboard, mouse, or command
action. Keyboard actions accept a key name, `hotkey:ctrl+c`, or `text:hello`.
Mouse actions include buttons and scroll. Commands use `command:<shell command>`;
for example, `command:notify-send 'Controller button pressed'`. Commands run
as the current user.

Create, rename/update, and remove presets from the Presets controls. Editing a
mapping updates the active preset. **Export** writes any selected presets to a
JSON file; **Import** merges presets from a JSON file and renames conflicts.
The bundled `default.json` supplies the initial mapping if no user preset file
exists. **Restart** stops and reconnects the selected controller.

Choose a controller button as the preset-switcher hold button and choose the
left or right stick. Hold the button to open the circular preset selector,
point the stick toward a preset, then release the button to activate it.

#### Updates to Dependencies:
```python -m pip freeze > requirements.txt```

