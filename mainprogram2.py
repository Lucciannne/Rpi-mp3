#!/usr/bin/env python3
import os
import time
import logging
from mpd import MPDClient
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
MUSIC_DIR = os.path.expanduser("~/music")
I2C_ADDRESS = 0x3C
# Use BCM numbering for reliable button input
BUTTONS = {
    'play': 17,   # BCM 17 (BOARD 11)
    'prev': 27,   # BCM 27 (BOARD 13)
    'next': 22,   # BCM 22 (BOARD 15)
}
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DISPLAY_CONFIG = {
    'title_font_size': 16,
    'info_font_size': 12,
    'padding': 4
}
DEBOUNCE_MS = 300
UPDATE_INTERVAL = 0.5

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MPDController:
    def __init__(self):
        self.client = MPDClient()
        self.client.timeout = 10

    def connect(self):
        self.client.connect("localhost", 6600)
        logger.info("Connected to MPD")

        def init_playlist(self):
        # Clear and update entire MPD database
        self.client.clear()
        self.client.update()
        # wait for updating
        while 'updating_db' in self.client.status():
            time.sleep(1)
        # Add all tracks from root of MPD's music directory
        self.client.add('/')
        self.client.play(0)
        self.client.pause()
        logger.info("Playlist initialized")

    def status(self):
        return self.client.status()

    def current_song(self):
        return self.client.currentsong()

    def next(self):
        self.client.next()

    def previous(self):
        self.client.previous()

    def play(self):
        self.client.play()

    def pause(self):
        self.client.pause()

class DisplayManager:
    def __init__(self):
        self.serial = i2c(port=1, address=I2C_ADDRESS)
        self.device = ssd1306(self.serial)
        self.title_font = ImageFont.truetype(FONT_PATH, DISPLAY_CONFIG['title_font_size'])
        self.info_font = ImageFont.truetype(FONT_PATH, DISPLAY_CONFIG['info_font_size'])
        logger.info("OLED initialized")

    def render(self, song, status):
        img = Image.new("1", self.device.size)
        draw = ImageDraw.Draw(img)
        w, h = self.device.size
        pad = DISPLAY_CONFIG['padding']

        # Draw track info
        title = song.get('title', 'Unknown')[:20]
        artist = song.get('artist', '')[:20]
        draw.text((pad, pad), title, font=self.title_font, fill=255)
        draw.text((pad, pad + DISPLAY_CONFIG['title_font_size'] + 2), artist, font=self.info_font, fill=255)

        # Draw state icon
        icon = '▶' if status == 'play' else '⏸'
        tw, th = draw.textsize(icon, font=self.info_font)
        draw.text((w - tw - pad, pad), icon, font=self.info_font, fill=255)

        # Draw progress bar
        pos = int(song.get('elapsed', 0))
        length = int(song.get('time', 1))
        bar_w = w - 2 * pad
        filled = int((pos / length) * bar_w)
        y_bar = h - pad - 4
        draw.rectangle([pad, y_bar, pad + bar_w, y_bar + 4], outline=255, fill=0)
        draw.rectangle([pad, y_bar, pad + filled, y_bar + 4], outline=255, fill=255)

        self.device.display(img)

class ButtonHandler:
    def __init__(self, mpd, display):
        self.mpd = mpd
        self.display = display
        self.last = 0

    def debounce(self):
        now = time.time()
        if now - self.last < DEBOUNCE_MS / 1000:
            return True
        self.last = now
        return False

    def on_play(self, channel):
        if self.debounce(): return
        st = self.mpd.status().get('state')
        if st == 'play':
            self.mpd.pause()
        else:
            self.mpd.play()
        self.update()

    def on_next(self, channel):
        if self.debounce(): return
        self.mpd.next()
        self.update()

    def on_prev(self, channel):
        if self.debounce(): return
        self.mpd.previous()
        self.update()

    def update(self):
        status = self.mpd.status().get('state')
        song = self.mpd.current_song()
        self.display.render(song, status)

def main():
    mpd = MPDController()
    disp = DisplayManager()
    mpd.connect()
    mpd.init_playlist()

    handler = ButtonHandler(mpd, disp)

    # GPIO setup using BCM
    GPIO.setmode(GPIO.BCM)
    for name, pin in BUTTONS.items():
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(BUTTONS['play'], GPIO.FALLING, handler.on_play, bouncetime=DEBOUNCE_MS)
    GPIO.add_event_detect(BUTTONS['next'], GPIO.FALLING, handler.on_next, bouncetime=DEBOUNCE_MS)
    GPIO.add_event_detect(BUTTONS['prev'], GPIO.FALLING, handler.on_prev, bouncetime=DEBOUNCE_MS)

    try:
        while True:
            handler.update()
            time.sleep(UPDATE_INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        mpd.client.close()
        mpd.client.disconnect()

if __name__ == '__main__':
    main()
