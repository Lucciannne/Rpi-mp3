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
            self.client.clear()
            self.client.update()
            logger.debug("Waiting for database update...")
            time.sleep(2)  # Allow time for database update
            
            if self.playlist_name in self.client.listplaylists():
                self.client.rm(self.playlist_name)
                logger.debug("Removed existing playlist")
                
            self.client.add("/")
            self.client.save(self.playlist_name)
            logger.info("Created new playlist with all tracks")
            
            self.client.load(self.playlist_name)
            self.client.play(0)
            self.client.pause()
        except Exception as e:
            logger.error(f"Playlist initialization failed: {e}")
            raise

class DisplayManager:
    def __init__(self):
        self.serial = i2c(port=1, address=I2C_ADDRESS)
        self.device = ssd1306(self.serial)
        self.fonts = {
            'track': ImageFont.truetype(FONT_PATH, DISPLAY_CONFIG['track_font_size']),
            'meta': ImageFont.truetype(FONT_PATH, DISPLAY_CONFIG['meta_font_size'])
        }
        logger.info("OLED display initialized")

    def create_frame(self, track_num, total_tracks, state, progress=0):
        img = Image.new("1", self.device.size)
        draw = ImageDraw.Draw(img)
        
        # Track number display
        track_str = f"{track_num:02d}"
        bbox = draw.textbbox((0,0), track_str, font=self.fonts['track'])
        track_w = bbox[2] - bbox[0]
        track_pos = (
            (self.device.width - track_w) // 2,
            DISPLAY_CONFIG['padding']
        )
        draw.text(track_pos, track_str, font=self.fonts['track'], fill=255)
        
        # Track count
        count_str = f"{track_num}/{total_tracks}"
        count_pos = (
            DISPLAY_CONFIG['padding'],
            self.device.height - DISPLAY_CONFIG['meta_font_size'] - DISPLAY_CONFIG['padding']
        )
        draw.text(count_pos, count_str, font=self.fonts['meta'], fill=255)
        
        # Play state indicator
        state_icon = "▶" if state == "play" else "⏸"
        icon_bbox = draw.textbbox((0,0), state_icon, font=self.fonts['meta'])
        icon_pos = (
            self.device.width - (icon_bbox[2] - icon_bbox[0]) - DISPLAY_CONFIG['padding'],
            count_pos[1]
        )
        draw.text(icon_pos, state_icon, font=self.fonts['meta'], fill=255)
        
        # Progress bar
        if total_tracks > 0 and progress > 0:
            bar_width = self.device.width - (2 * DISPLAY_CONFIG['padding'])
            fill_width = int(bar_width * progress)
            draw.rectangle([
                (DISPLAY_CONFIG['padding'], self.device.height - DISPLAY_CONFIG['progress_height'] - 2),
                (DISPLAY_CONFIG['padding'] + fill_width, self.device.height - 2)
            ], fill=255)
        
        return img

class ButtonHandler:
    def __init__(self, mpd_controller, display_manager):
        self.mpd = mpd_controller
        self.display = display_manager
        self.last_event = 0
        
    def get_status(self):
        try:
            status = self.mpd.client.status()
            current = self.mpd.client.currentsong()
            return {
                'state': status.get('state', 'stop'),
                'position': int(status.get('song', 0)),
                'elapsed': float(status.get('elapsed', 0)),
                'total': int(status.get('playlistlength', 0)),
                'duration': float(current.get('time', 0)) if current else 0
            }
        except Exception as e:
            logger.error(f"Status check failed: {e}")
            return {'state': 'stop', 'position': 0, 'elapsed': 0, 'total': 0, 'duration': 0}

    def update_display(self):
        status = self.get_status()
        if status['total'] == 0:
            return
            
        progress = status['elapsed'] / status['duration'] if status['duration'] > 0 else 0
        frame = self.display.create_frame(
            track_num=status['position'] + 1,
            total_tracks=status['total'],
            state=status['state'],
            progress=progress
        )
        self.display.device.display(frame)
        logger.debug(f"Display updated: Pos {status['position']} State {status['state']}")

    def handle_playpause(self, channel):
        if self.debounce_check(): return
        status = self.get_status()
        try:
            if status['state'] == 'play':
                self.mpd.client.pause(1)
                logger.debug("Playback paused")
            else:
                self.mpd.client.play()
                logger.debug("Playback started")
            self.update_display()
        except Exception as e:
            logger.error(f"Play/pause failed: {e}")

    def handle_skip(self, direction):
        if self.debounce_check(): return
        status = self.get_status()
        try:
            if direction == 'next' and status['position'] < status['total'] - 1:
                self.mpd.client.next()
                logger.debug("Skipped to next track")
            elif direction == 'prev' and status['position'] > 0:
                self.mpd.client.previous()
                logger.debug("Skipped to previous track")
            self.update_display()
        except Exception as e:
            logger.error(f"Skip {direction} failed: {e}")

    def debounce_check(self):
        now = time.time() * 1000
        if now - self.last_event < DEBOUNCE_MS:
            return True
        self.last_event = now
        return False

def main():
    try:
        # Initialize components
        mpd = MPDController()
        display = DisplayManager()
        
        mpd.connect()
        mpd.initialize_playlist()
        
        handler = ButtonHandler(mpd, display)
        
        # GPIO Setup
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
        
        logger.info("Initialization complete. Starting main loop...")
        
        # Main loop
        while True:
            handler.update_display()
            time.sleep(1)
            
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
