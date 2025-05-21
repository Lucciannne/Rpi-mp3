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
            # Clear existing playlist and database
            self.client.clear()
            logger.debug("Cleared current playlist")
            
            # Update database using specific music directory
            logger.debug("Starting database update...")
            self.client.update(os.path.basename(MUSIC_DIR))  # Only update specific directory
            
            # Wait for update to complete
            while True:
                status = self.client.status()
                if 'updating_db' not in status:
                    break
                logger.debug("Database update in progress...")
                time.sleep(1)

            # Add files from music directory
            logger.debug("Adding files to playlist")
            self.client.add(os.path.basename(MUSIC_DIR) + "/")  # Add specific directory
            
            # Save and load fresh playlist
            if self.playlist_name in self.client.listplaylists():
                self.client.rm(self.playlist_name)
            self.client.save(self.playlist_name)
            self.client.load(self.playlist_name)
            
            # Start playback correctly
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
            'large': ImageFont.truetype(FONT_PATH, 40),
            'medium': ImageFont.truetype(FONT_PATH, 20),
            'small': ImageFont.truetype(FONT_PATH, 14)
        }
        logger.info("OLED display initialized")

    def create_frame(self, current_pos, total_tracks, state, elapsed=0, duration=0):
        img = Image.new("1", self.device.size)
        draw = ImageDraw.Draw(img)
        
        # Main track number (centered)
        track_str = f"{current_pos + 1:02d}"
        bbox = draw.textbbox((0,0), track_str, font=self.fonts['large'])
        x = (self.device.width - (bbox[2]-bbox[0])) // 2
        y = (self.device.height - (bbox[3]-bbox[1])) // 3
        draw.text((x, y), track_str, font=self.fonts['large'], fill=255)
        
        # Progress indicator
        progress = elapsed/duration if duration > 0 else 0
        bar_width = int(self.device.width * 0.8)
        draw.rectangle([
            (self.device.width*0.1, self.device.height-15),
            (self.device.width*0.1 + bar_width*progress, self.device.height-10)
        ], fill=255)
        
        # Track counter
        counter_str = f"Track {current_pos + 1} of {total_tracks}"
        bbox = draw.textbbox((0,0), counter_str, font=self.fonts['small'])
        draw.text(
            (self.device.width//2 - (bbox[2]-bbox[0])//2, self.device.height-25),
            counter_str,
            font=self.fonts['small'],
            fill=255
        )
        
        # Play state
        state_icon = "▶" if state == "play" else "⏸"
        bbox = draw.textbbox((0,0), state_icon, font=self.fonts['medium'])
        draw.text(
            (self.device.width - (bbox[2]-bbox[0]) - 5, 5),
            state_icon,
            font=self.fonts['medium'],
            fill=255
        )
        
        return img

class ButtonHandler:
    def __init__(self, mpd_controller, display_manager):
        self.mpd = mpd_controller
        self.display = display_manager
        self.last_press = time.time()
        
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
            self.update_display()
        except Exception as e:
            logger.error(f"Play/pause error: {e}")

    def handle_skip(self, channel):
        if self._debounce(): return
        try:
            status = self.mpd.client.status()
            current_pos = int(status.get('song', 0))
            total_tracks = int(status.get('playlistlength', 0))
            
            # Long press (2 seconds) for seek
            if time.time() - self.last_press > 2:
                elapsed = float(status.get('elapsed', 0))
                duration = float(self.mpd.client.currentsong().get('time', 0))
                if duration > 0:
                    new_pos = min(elapsed + 15, duration)
                    self.mpd.client.seekcur(new_pos)
                    logger.debug(f"Skipped 15s forward to {new_pos}s")
            else:
                # Short press for next track
                if current_pos < total_tracks - 1:
                    self.mpd.client.next()
                    logger.debug("Skipped to next track")
            
            self.update_display()
        except Exception as e:
            logger.error(f"Skip error: {e}")

    def _debounce(self):
        now = time.time()
        if now - self.last_press < DEBOUNCE_MS/1000:
            return True
        self.last_press = now
        return False

    def update_display(self):
        try:
            status = self.mpd.client.status()
            current = self.mpd.client.currentsong()
            frame = self.display.create_frame(
                current_pos=int(status.get('song', 0)),
                total_tracks=int(status.get('playlistlength', 0)),
                state=status.get('state', 'stop'),
                elapsed=float(status.get('elapsed', 0)),
                duration=float(current.get('time', 0))
            )
            self.display.device.display(frame)
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
        
        # Assign buttons with proper pull-up resistors
        GPIO.add_event_detect(BUTTONS['play'], GPIO.FALLING, 
                             callback=handler.handle_playpause, bouncetime=DEBOUNCE_MS)
        GPIO.add_event_detect(BUTTONS['prev'], GPIO.FALLING,
                             callback=lambda x: handler.handle_skip('prev'), bouncetime=DEBOUNCE_MS)
        GPIO.add_event_detect(BUTTONS['next'], GPIO.FALLING,
                             callback=lambda x: handler.handle_skip('next'), bouncetime=DEBOUNCE_MS)
        
        logger.info("Starting main loop...")
        while True:
            handler.update_display()
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        GPIO.cleanup()
        mpd.client.close()
        mpd.client.disconnect()

if __name__ == "__main__":
    main()
