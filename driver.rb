#!/usr/bin/env ruby
require 'glimmer-dsl-swt'
require 'json'
require 'thread'

class ControllerDriver
  include Glimmer
  DEFAULT_MAPPINGS = {
    "A"          => "space",
    "B"          => "Escape",
    "X"          => "x",
    "Y"          => "y",
    "LB"         => "ctrl",
    "RB"         => "shift",
    "BACK"       => "Alt_L",
    "START"      => "Return",
    "LS"         => "F1",
    "RS"         => "F2",
    "DPAD_UP"    => "Up",
    "DPAD_DOWN"  => "Down",
    "DPAD_LEFT"  => "Left",
    "DPAD_RIGHT" => "Right"
  }
  # Standard Linux Xbox controller button numbers.
  BUTTONS = {
    0  => "A",
    1  => "B",
    2  => "X",
    3  => "Y",
    4  => "LB",
    5  => "RB",
    6  => "BACK",
    7  => "START",
    8  => "LS",
    9  => "RS",
    10 => "DPAD_UP",
    11 => "DPAD_DOWN",
    12 => "DPAD_LEFT",
    13 => "DPAD_RIGHT"
  }
  JS_EVENT_BUTTON = 0x01
  JS_EVENT_AXIS   = 0x02
  JS_EVENT_INIT   = 0x80

  def initialize
    @mappings = load_mappings
    @running = false
    @controller_thread = nil
    @pressed = {}
    @mouse_speed = 15
    @deadzone = 8_000
  end

  def launch
    @shell = shell {
      text 'USB Controller Driver'
      # minimum_size Point.new(700, 600)
      grid_layout(2, false) {
              margin_width 15
              margin_height 15
              horizontal_spacing 10
              vertical_spacing 10
                            }
      label {
              text 'Xbox Controller'
            }
      @device_combo = combo {
                              layout_data {
                                          # horizontal_span 1
                                          horizontal_alignment :fill
                                          }
                            }
      refresh_devices
      label { text 'Status' }
      @status_label = label { text 'Disconnected' }
      label { text 'Button' }
      label { text 'xdotool action' }
      BUTTONS.values.each do |button_name|
        label { text button_name }
        text {
                    text @mappings[button_name] || ''
                    layout_data { horizontal_alignment :fill
                                  # vertical_alignment :fill
                                }
                    on_modify_text { @mappings[button_name] = text }
                  }
      end
      label { text 'Mouse speed' }
      @speed_spinner = spinner {
                                  minimum 1
                                  maximum 100
                                  selection @mouse_speed
                                  on_modify_text { @mouse_speed = selection }
                                }
      label { text 'Deadzone' }
      @deadzone_spinner = spinner {
                                    minimum 1000
                                    maximum 30000
                                    increment 1000
                                    selection @deadzone
                                    on_modify_text { @deadzone = selection }
                                  }
      button {
                text 'Save Mappings'
                on_widget_selected { save_mappings }
              }
      button {
                text 'Load Mappings'
                on_widget_selected {
                                    @mappings = load_mappings
                                    refresh_ui
                                  }
              }
      button {
                text 'Refresh Controllers'
                on_widget_selected { refresh_devices }
              }
      @start_button = button {
                                text 'Start Controller'
                                on_widget_selected { start_controller }
                              }
      button {
                text 'Stop Controller'
                on_widget_selected { stop_controller }
              }

      @shell.open
      start_controller if controller_devices.any?
      while @shell.visible?
        display.read_and_dispatch || display.sleep
      end
      stop_controller
      }
  end

  private

  def controller_devices
    Dir.glob('/dev/input/js*').sort
  end

  def refresh_devices
    devices = controller_devices
    @device_combo.items = devices
    if devices.any?
      @device_combo.select(0)
      set_status("Found #{devices.length} controller(s)")
    else
      set_status('No /dev/input/js* controllers found')
    end
  end

  def selected_device
    @device_combo.text
  end

  def start_controller
    stop_controller
    device = selected_device

    if device.nil? || device.empty?
      set_status('No controller selected')
      return
    end

    unless File.readable?(device)
      set_status("Cannot read #{device}")
      return
    end

    @running = true
    @controller_thread = Thread.new do
      begin
        File.open(device, 'rb') do |io|
          set_status("Connected: #{device}")
          while @running
            ready = IO.select([io], nil, nil, 0.25)
            next unless ready
            event = io.read(8)
            next unless event && event.length == 8

            time, value, type, number = event.unpack('l<sCC')
            type &= ~JS_EVENT_INIT
            case type
            when JS_EVENT_BUTTON
              handle_button(number, value)
            when JS_EVENT_AXIS
              handle_axis(number, value)
            end
          end
        end
      rescue => e
        set_status("Controller error: e.message")
      end
    end
  end

  def stop_controller
    @running = false
    if @controller_thread
      @controller_thread.join(0.5)
      @controller_thread = nil
    end
    set_status('Stopped')
  end

  def handle_button(number, value)
    button = BUTTONS[number]
    return unless button
    pressed = value != 0
    # Avoid repeatedly firing actions for held buttons.
    if pressed && !@pressed[number]
      action = @mappings[button]
      execute_action(action) unless action.nil? || action.strip.empty?
    end
    @pressed[number] = pressed
  end

  def handle_axis(number, value)
    # Typical Xbox mapping:
    #
    # 0 = left stick X
    # 1 = left stick Y
    # 2 = triggers / other axis
    # 3 = right stick X
    # 4 = right stick Y
    #
    # Exact numbering depends on the Linux driver.
    case number
    when 0
      move_mouse_x(value)
    when 1
      move_mouse_y(value)
    # when 3
    #   move_mouse_x(value)
    # when 4
    #   move_mouse_y(value)
    end
  end

  def move_mouse_x(value)
    return if value.abs < @deadzone
    amount = (value.to_f / 32767 * @mouse_speed).round
    return if amount.zero?
    xdotool_mousemove_relative(amount, 0)
  end

  def move_mouse_y(value)
    return if value.abs < @deadzone
    amount = (value.to_f / 32767 * @mouse_speed).round
    return if amount.zero?
    xdotool_mousemove_relative(0, amount)
  end

  def execute_action(action)
    action = action.strip
    return if action.empty?
    case action
    when /^mouse:(left|middle|right)$/i
      button = Regexp.last_match(1).downcase
      system('xdotool', 'click', mouse_button_number(button))
    when /^key:(.+)$/i
      key = Regexp.last_match(1).strip
      system('xdotool', 'key', key)
    when /^text:(.+)$/i
      text = Regexp.last_match(1)
      system('xdotool', 'type', text)
    else
      # Treat a bare mapping as an xdotool key name.
      system('xdotool', 'key', action)
    end
  end

  def mouse_button_number(button)
    {
      'left' => '1',
      'middle' => '2',
      'right' => '3'
    }[button]
  end

  def xdotool_mousemove_relative(x, y)
    system(
      'xdotool',
      'mousemove_relative',
      '--',
      x.to_s,
      y.to_s
    )
  end

  def mappings_file
    File.expand_path('~/.xbox_xdotool_mappings.json')
  end

  def load_mappings
    if File.exist?(mappings_file)
      JSON.parse(File.read(mappings_file))
    else
      DEFAULT_MAPPINGS.dup
    end
  rescue JSON::ParserError
    DEFAULT_MAPPINGS.dup
  end

  def save_mappings
    File.write(
      mappings_file,
      JSON.pretty_generate(@mappings)
    )
    set_status("Saved mappings_file")
  rescue => e
    set_status("Save failed: e.message")
  end

  def refresh_ui
    # Rebuilding the widgets isn't necessary for normal use.
    # Mapping changes are written directly from the text boxes.
  end

  def set_status(text)
    return unless @status_label
    display.async_exec do
      begin
        @status_label.text = text
        @status_label.redraw
      rescue
        # SWT may already be shutting down.
      end
    end
  end
end

ControllerDriver.new.launch
