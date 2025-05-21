import os
import time
import signal
from mpd import MPDClient, CommandError
import RPi.GPIO as GPIO
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import Image, ImageDraw, ImageFont

# Configuration
MUSIC_DIR = '/home/fran/music'
I2C_PORT = 1
OLED_ADDR = 0x3C
BUTTON_PINS = {
    'play_pause': 11,
    'rewind': 13,
    'forward': 15,
}
REWIND_SECONDS = 15
FAST_FORWARD_SECONDS = 15
FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_SIZE_TRACK = 48
FONT_SIZE_STATE = 14

# Global state
track_list = []
client = None
device = None
font_track = None
font_state = None


def scan_music(directory):
    """Recursively scan for music files and return sorted list."""
    exts = ('.mp3', '.flac', '.wav', '.ogg', '.m4a')
    files = []
    for root, _, filenames in os.walk(directory):
        for f in filenames:
            if f.lower().endswith(exts):
                files.append(os.path.join(root, f))
    files.sort()
    return files


def init_mpd():
    """Connect to MPD and load playlist."""
    global client
    client = MPDClient()
    client.timeout = 10
    client.idletimeout = None
    client.connect('localhost', 6600)
    client.clear()
    # Add tracks
    for f in track_list:
        client.add(f)
    # Start paused on first track
    client.play(0)
    client.pause()


def init_oled():
    """Initialize the OLED display."""
    global device, font_track, font_state
    serial = i2c(port=I2C_PORT, address=OLED_ADDR)
    device = ssd1306(serial)
    # Load fonts
    try:
        font_track = ImageFont.truetype(FONT_PATH, FONT_SIZE_TRACK)
        font_state = ImageFont.truetype(FONT_PATH, FONT_SIZE_STATE)
    except IOError:
        font_track = ImageFont.load_default()
        font_state = ImageFont.load_default()


def update_display():
    """Render current track number and play state on OLED."""
    status = client.status()
    track_idx = int(status.get('song', 0))
    state = status.get('state', 'stop')
    # Prepare image
    img = Image.new('1', (device.width, device.height), "BLACK")
    draw = ImageDraw.Draw(img)
    # Track number (1-based)
    track_str = str(track_idx + 1)
    w, h = draw.textsize(track_str, font=font_track)
    x = (device.width - w) // 2
    y = 0
    draw.text((x, y), track_str, font=font_track, fill=255)
    # State text
    state_str = state.upper()
    w2, h2 = draw.textsize(state_str, font=font_state)
    x2 = (device.width - w2) // 2
    y2 = device.height - h2
    draw.text((x2, y2), state_str, font=font_state, fill=255)
    device.display(img)


def button_play_pause(channel):
    """Toggle play/pause."""
    try:
        client.pause()
        update_display()
    except CommandError:
        pass


def button_rewind(channel):
    """Rewind or previous track."""
    status = client.status()
    if status.get('state') == 'play':
        song_idx = int(status.get('song', 0))
        elapsed = float(status.get('elapsed', 0))
        newpos = max(elapsed - REWIND_SECONDS, 0)
        client.seek(song_idx, newpos)
    else:
        client.previous()
    update_display()


def button_forward(channel):
    """Fast forward or next track."""
    status = client.status()
    if status.get('state') == 'play':
        song_idx = int(status.get('song', 0))
        elapsed = float(status.get('elapsed', 0))
        newpos = elapsed + FAST_FORWARD_SECONDS
        client.seek(song_idx, newpos)
    else:
        client.next()
    update_display()


def cleanup(signum, frame):
    """Cleanup resources on exit."""
    GPIO.cleanup()
    if client:
        try:
            client.close()
            client.disconnect()
        except:
            pass
    device.clear()
    exit(0)


def main():
    global track_list
    # Scan music files
    track_list = scan_music(MUSIC_DIR)
    if not track_list:
        print("No music files found in {}".format(MUSIC_DIR))
        return
    # Initialize components
    init_mpd()
    init_oled()
    # Setup GPIO buttons
    GPIO.setmode(GPIO.BOARD)
    for cb_name, pin in BUTTON_PINS.items():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(BUTTON_PINS['play_pause'], GPIO.FALLING, callback=button_play_pause, bouncetime=200)
    GPIO.add_event_detect(BUTTON_PINS['rewind'], GPIO.FALLING, callback=button_rewind, bouncetime=200)
    GPIO.add_event_detect(BUTTON_PINS['forward'], GPIO.FALLING, callback=button_forward, bouncetime=200)
    # Handle exit signals
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    # Initial display
    update_display()
    # Keep running
    while True:
        time.sleep(1)

if __name__ == '__main__':
    main()
