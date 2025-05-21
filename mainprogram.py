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
MUSIC_DIR = os.path.expanduser("~/music")  # Use absolute path
I2C_ADDRESS = 0x3C
BUTTONS = {
    'play': 11,   # BOARD pin 11
    'prev': 13,   # BOARD pin 13
    'next': 15,   # BOARD pin 15
}
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DISPLAY_CONFIG = {
    'main_font_size': 48,
    'meta_font_size': 14,
    'padding': 5
}
DEBOUNCE_MS = 300

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
            # Verify music directory exists
            if not os.path.isdir(MUSIC_DIR):
                raise FileNotFoundError(f"Music directory not found: {MUSIC_DIR}")

            # Clear existing data
            self.client.clear()
            logger.debug("Cleared current playlist")

            # Update database
            logger.debug(f"Updating database for {MUSIC_DIR}")
            self.client.update(os.path.basename(MUSIC_DIR))

            # Wait for update completion
            while 'updating_db' in self.client.status():
                logger.debug("Database update in progress...")
                time.sleep(1)

            # Add files to playlist
            logger.debug("Adding files to playlist")
            self.client.add("/")  # Add root of MPD's music directory

            # Handle playlist
            playlists = [p['playlist'] for p in self.client.listplaylists()]
            if self.playlist_name in playlists:
                self.client.rm(self.playlist_name)
            self.client.save(self.playlist_name)

            # Load and start playback
            self.client.load(self.playlist_name)
            self.client.play(0)
            self.client.pause()
            logger.info("Playback initialized successfully")

        except Exception as e:
            logger.error(f"Playlist initialization failed: {e}")
            raise

class DisplayManager:
    def __init__(self):
        self.serial = i2c(port=1, address=I2C_ADDRESS)
        self.device = ssd1306(self.serial)
        self.fonts = {
            'main': ImageFont.truetype(FONT_PATH, DISPLAY_CONFIG['main_font_size']),
            'meta': ImageFont.truetype(FONT_PATH, DISPLAY_CONFIG['meta_font_size'])
        }
        logger.info("OLED display initialized")

    def create_frame(self, current_pos, total_tracks, state):
        img = Image.new("1", self.device.size)
        draw = ImageDraw.Draw(img)
        
        # Main track number
        track_no = current_pos + 1
        main_text = f"{track_no}"
        bbox = draw.textbbox((0,0), main_text, font=self.fonts['main'])
        x = (self.device.width - (bbox[2]-bbox[0])) // 2
        y = (self.device.height - (bbox[3]-bbox[1])) // 3
        draw.text((x, y), main_text, font=self.fonts['main'], fill=255)
        
        # Track counter
        counter_text = f"{track_no} / {total_tracks}"
        bbox = draw.textbbox((0,0), counter_text, font=self.fonts['meta'])
        x = (self.device.width - (bbox[2]-bbox[0])) // 2
        y = self.device.height - (bbox[3]-bbox[1]) - DISPLAY_CONFIG['padding']
        draw.text((x, y), counter_text, font=self.fonts['meta'], fill=255)
        
        # Play state
        state_icon = "▶" if state == "play" else "⏸"
        bbox = draw.textbbox((0,0), state_icon, font=self.fonts['meta'])
        x = self.device.width - (bbox[2]-bbox[0]) - DISPLAY_CONFIG['padding']
        draw.text((x, DISPLAY_CONFIG['padding']), state_icon, 
                 font=self.fonts['meta'], fill=255)
        
        return img

class ButtonHandler:
    def __init__(self, mpd, display):
        self.mpd = mpd
        self.display = display
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

    def handle_skip(self, direction):
        if self._debounce(): return
        try:
            status = self.mpd.client.status()
            current = int(status.get('song', 0))
            total = int(status.get('playlistlength', 0))
            
            if direction == 'next':
                if current < total - 1:
                    self.mpd.client.next()
                    logger.debug("Next track")
                else:
                    logger.debug("End of playlist")
            elif direction == 'prev':
                if current > 0:
                    self.mpd.client.previous()
                    logger.debug("Previous track")
            
            self.update_display()
        except Exception as e:
            logger.error(f"Skip error: {e}")

    def _debounce(self):
        now = time.time()
        if (now - self.last_press) < (DEBOUNCE_MS / 1000):
            return True
        self.last_press = now
        return False

    def update_display(self):
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
        except Exception as e:
            logger.error(f"Display update failed: {e}")

def main():
    try:
        # Initialize components
        mpd = MPDController()
        display = DisplayManager()
        mpd.connect()
        mpd.initialize_playlist()
        
        handler = ButtonHandler(mpd, display)
        
        # Setup GPIO
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(BUTTONS['play'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(BUTTONS['prev'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(BUTTONS['next'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Add event detection
        GPIO.add_event_detect(BUTTONS['play'], GPIO.FALLING,
                            callback=handler.handle_playpause,
                            bouncetime=DEBOUNCE_MS)
        GPIO.add_event_detect(BUTTONS['prev'], GPIO.FALLING,
                            callback=lambda x: handler.handle_skip('prev'),
                            bouncetime=DEBOUNCE_MS)
        GPIO.add_event_detect(BUTTONS['next'], GPIO.FALLING,
                            callback=lambda x: handler.handle_skip('next'),
                            bouncetime=DEBOUNCE_MS)
        
        logger.info("System ready. Starting main loop...")
        
        # Main loop
        while True:
            handler.update_display()
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        GPIO.cleanup()
        if mpd.client:
            mpd.client.close()
            mpd.client.disconnect()
        logger.info("Cleanup complete")

if __name__ == "__main__":
    main()
