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
MUSIC_DIR = "/home/fran/music"
I2C_ADDRESS = 0x3C
BUTTONS = {
    'play': 11,   # BOARD pin 11
    'prev': 13,   # BOARD pin 13
    'next': 15,   # BOARD pin 15
}
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DISPLAY_CONFIG = {
    'track_font_size': 40,
    'meta_font_size': 14,
    'progress_height': 4,
    'padding': 5,
}
DEBOUNCE_MS = 200

# Initialize logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# ──────────────────────────────────────────────────────────────────────────────

class MPDController:
    def __init__(self):
        self.client = MPDClient()
        self.client.timeout = 10
        self.client.idletimeout = None
        self.playlist_name = "alltracks"
        
    def connect(self):
        try:
            self.client.connect("localhost", 6600)
            logger.info("Connected to MPD server")
        except Exception as e:
            logger.error(f"MPD connection failed: {e}")
            raise

    def initialize_playlist(self):
        try:
            # Clear existing data
            self.client.clear()
            logger.debug("Cleared current playlist")

            # Update database with correct path
            logger.debug(f"Updating database for {MUSIC_DIR}")
            self.client.update(MUSIC_DIR)  # Use full path
            
            # Wait for update completion
            while True:
                status = self.client.status()
                if 'updating_db' not in status:
                    break
                logger.debug("Database update in progress...")
                time.sleep(1)

            # Add files using proper URI format
            logger.debug(f"Adding files from {MUSIC_DIR}")
            self.client.add(f"file://{MUSIC_DIR}")  # Use file:// URI
            
            # Handle playlist creation
            playlists = [p['playlist'] for p in self.client.listplaylists()]
            if self.playlist_name in playlists:
                self.client.rm(self.playlist_name)
            self.client.save(self.playlist_name)
            
            # Load and start playback
            self.client.load(self.playlist_name)
            self.client.play(0)
            self.client.pause()
            logger.info("Playback initialized with first track")

        except Exception as e:
            logger.error(f"Playlist initialization failed: {e}")
            raise
            
class DisplayManager:
    def __init__(self):
        self.serial = i2c(port=1, address=I2C_ADDRESS)
        self.device = ssd1306(self.serial)
        self.fonts = {
            'main': ImageFont.truetype(FONT_PATH, 48),
            'meta': ImageFont.truetype(FONT_PATH, 14)
        }
        logger.info("OLED display initialized")

    def create_frame(self, current_pos, total_tracks, state):
        img = Image.new("1", self.device.size)
        draw = ImageDraw.Draw(img)
        
        # Main track number (big and centered)
        main_text = f"{current_pos + 1}"
        bbox = draw.textbbox((0,0), main_text, font=self.fonts['main'])
        x = (self.device.width - (bbox[2]-bbox[0])) // 2
        y = (self.device.height - (bbox[3]-bbox[1])) // 3
        draw.text((x, y), main_text, font=self.fonts['main'], fill=255)
        
        # Track counter (bottom center)
        counter_text = f"{current_pos + 1} / {total_tracks}"
        bbox = draw.textbbox((0,0), counter_text, font=self.fonts['meta'])
        x = (self.device.width - (bbox[2]-bbox[0])) // 2
        y = self.device.height - (bbox[3]-bbox[1]) - 5
        draw.text((x, y), counter_text, font=self.fonts['meta'], fill=255)
        
        # Play state indicator (top right)
        state_icon = "▶" if state == "play" else "⏸"
        bbox = draw.textbbox((0,0), state_icon, font=self.fonts['meta'])
        x = self.device.width - (bbox[2]-bbox[0]) - 5
        draw.text((x, 5), state_icon, font=self.fonts['meta'], fill=255)
        
        return img

class ButtonHandler:
    def __init__(self, mpd_controller, display_manager):
        self.mpd = mpd_controller
        self.display = display_manager
        self.last_press = 0
        
    def handle_playpause(self, channel):
        if self._debounce(): return
        try:
            status = self.mpd.client.status()
            if status['state'] == 'play':
                self.mpd.client.pause(1)
                logger.debug("Paused playback")
            else:
                self.mpd.client.play()
                logger.debug("Started playback")
            self._update_display()
        except Exception as e:
            logger.error(f"Play/pause error: {e}")

    def handle_skip(self, direction):
        if self._debounce(): return
        try:
            status = self.mpd.client.status()
            current_pos = int(status.get('song', 0))
            total_tracks = int(status.get('playlistlength', 0))
            
            if direction == 'next':
                if current_pos < total_tracks - 1:
                    self.mpd.client.next()
                    logger.debug("Next track")
                else:
                    logger.debug("Already at last track")
            elif direction == 'prev':
                self.mpd.client.previous()
                logger.debug("Previous track")
            
            self._update_display()
        except Exception as e:
            logger.error(f"Skip error: {e}")

    def _debounce(self):
        now = time.time()
        if now - self.last_press < DEBOUNCE_MS/1000:
            return True
        self.last_press = now
        return False

    def _update_display(self):
        try:
            status = self.mpd.client.status()
            current_pos = int(status.get('song', 0))
            total_tracks = int(status.get('playlistlength', 0))
            state = status.get('state', 'stop')
            
            frame = self.display.create_frame(
                current_pos=current_pos,
                total_tracks=total_tracks,
                state=state
            )
            self.display.device.display(frame)
            logger.debug(f"Display updated - Pos: {current_pos+1} State: {state}")
        except Exception as e:
            logger.error(f"Display update failed: {e}")
            
def main():
    try:
        mpd = MPDController()
        display = DisplayManager()
        mpd.connect()
        mpd.initialize_playlist()
        
        handler = ButtonHandler(mpd, display)
        
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(BUTTONS['play'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(BUTTONS['prev'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(BUTTONS['next'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        GPIO.add_event_detect(BUTTONS['play'], GPIO.FALLING, 
                            callback=handler.handle_playpause, bouncetime=DEBOUNCE_MS)
        GPIO.add_event_detect(BUTTONS['prev'], GPIO.FALLING,
                            callback=lambda x: handler.handle_skip('prev'), bouncetime=DEBOUNCE_MS)
        GPIO.add_event_detect(BUTTONS['next'], GPIO.FALLING,
                            callback=lambda x: handler.handle_skip('next'), bouncetime=DEBOUNCE_MS)
        
        logger.info("System ready - starting main loop")
        while True:
            handler._update_display()
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        GPIO.cleanup()
        mpd.client.close()
        mpd.client.disconnect()

if __name__ == "__main__":
    main()
