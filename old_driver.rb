#!/usr/bin/env ruby
# frozen_string_literal: true

# === TODO ===
#  - scrolling
#  - press and hold repeat (arrows)
#  - logging
#  - cl arguments
#  - make into service
#  - condense & documentation

# --- Configuration Settings ---
DEBUG_MODE = false
JS_DEVICE = '/dev/input/js0'
BUTTON_DEVICE = `ls /dev/input/by-id/*event-joystick`.chomp
DEADZONE  = 6000              # Ignores minor stick drift (0-32767)
SCALE     = 0.00025            # Cursor speed multiplier
TICK_RATE = 0.01              # Update loop delay (seconds)
SCROLL_INVERSE = false # TODO
QUICK_ZONE = 26000

# Dependency checks
unless `xdotool -v`.include? 'version'
  warn "Error: Dependency missing 'xdotool'"
  exit 1
end
# Ensure the joystick device node exists
unless File.exist?(JS_DEVICE)
  warn "Error: Device #{JS_DEVICE} not found. Is your controller connected?"
  exit(1)
end
# Ensure the button device node exists
unless File.exist?(BUTTON_DEVICE)
  warn "Error: Device #{BUTTON_DEVICE} not found. Is your controller connected?"
  exit(1)
end


# Track stick coordinates (normalized between -32768 and 32767)
x_axis = 0
y_axis = 0
rx_axis = 0
ry_axis = 0

# Open a non-blocking background pipe to write commands directly to xdotool
# Using xdotool in --sync mode within a persistent pipe prevents process overhead
xdotool = IO.popen('xdotool -', 'w')

# Thread 1: Continuously parse the raw Linux binary input stream
# Linux joystick events use an 8-byte structured format:
# - unsigned int (4 bytes): timestamp in milliseconds
# - short (2 bytes): axis/button value
# - unsigned char (1 byte): event type (1 = button, 2 = axis, 0x80 = initial state)
# - unsigned char (1 byte): axis/button index number
Thread.new { File.open(JS_DEVICE, 'rb') do |device|
  loop do
    # Read the explicit 8-byte chunk
    binary_packet = device.read(8)
    break unless binary_packet

    # Unpack format: 'I' = uint32, 's' = int16, 'C' = uint8, 'C' = uint8
    _, value, type, number = binary_packet.unpack('I s C C')

    # Filter out initial state flags and parse Axis movements (type == 2)
    actual_type = type & ~0x80
    if actual_type == 2
      case number
      when 0 then x_axis = value # Left Stick Horizontal
      when 1 then y_axis = value # Left Stick Vertical
      when 3 then rx_axis = value # Right Stick Horizontal
      when 4 then ry_axis = value # Right Stick Vertical
      end
    end
  end
end
}

# Thread 2 (Buttons)
Thread.new {
  IO.popen("sudo evtest #{BUTTON_DEVICE}") do |io|
    io.each_line do |l|
      puts l if DEBUG_MODE
      if l.include?("BTN_SOUTH), value 1")
        xdotool.puts 'mousedown 1'
      elsif l.include?("BTN_SOUTH), value 0")
        xdotool.puts 'mouseup 1'
      elsif l.include?("BTN_EAST), value 1")
        xdotool.puts 'click 3'
      elsif l.include?("BTN_SELECT), value 1")
        xdotool.puts 'key ctrl+c'
      elsif l.include?("BTN_START), value 1")
        xdotool.puts 'key Enter'
      elsif l.include?("BTN_WEST), value 1")
        Thread.new {`pgrep onboard && pkill onboard || onboard`}
      elsif l.include?("BTN_NORTH), value 1")
        xdotool.puts "key d"
      elsif l.include?("HAT0X), value 1")
        xdotool.puts 'key Right'
      elsif l.include?("HAT0X), value -1")
        xdotool.puts 'key Left'      
      elsif l.include?("HAT0Y), value 1")
        xdotool.puts 'key Down'
      elsif l.include?("HAT0Y), value -1")
        xdotool.puts 'key Up'
      end
    end
  end
}

# Thread 3: Main loop processing joystick vectors
begin
  puts "Controller stream started...\t(Press Ctrl+C to exit.)"
  loop do
    # Calculate vector lengths outside of deadzone threshold
    dx = x_axis.abs > DEADZONE ? ((x_axis.abs < QUICK_ZONE ? x_axis : 1.5 * x_axis) * SCALE) : 0
    dy = y_axis.abs > DEADZONE ? ((y_axis.abs < QUICK_ZONE ? y_axis : 1.5 * y_axis) * SCALE) : 0
    drx= rx_axis.abs > DEADZONE ? rx_axis * SCALE : 0
    dry= ry_axis.abs > DEADZONE ? ry_axis * SCALE : 0

    # Execute relative movement command if a vector threshold is met
    if dx != 0 || dy != 0
      xdotool.puts "mousemove_relative -- #{dx.round} #{dy.round}"
      xdotool.flush
    end

    # Scroll based on R-Joystick values TODO
    #xdotool.puts 'click 6' if drx > 0
    #xdotool.puts 'click 7' if drx < 0
#    xdotool.puts('click 4') && xdotools.flush if dry > 0
#    xdotool.puts('click 5') && xdotools.flush if dry < 0

    sleep(TICK_RATE)
  end
ensure
  # Clean up and close the open command pipe on termination
  xdotool.close if xdotool
end

