#!/usr/bin/env python3
import time
import os
import RPi.GPIO as GPIO
from mpd import MPDClient
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from PIL import ImageFont

# Define GPIO pins for buttons
PLAY_PAUSE_BTN = 11
PREV_BTN = 13
NEXT_BTN = 15

# MPD Configuration
MPD_HOST = "localhost"
MPD_PORT = 6600

# OLED Display Configuration
OLED_WIDTH = 128
OLED_HEIGHT = 64
OLED_ADDR = 0x3C

class MP3Player:
    def __init__(self):
        # Initialize GPIO
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(PLAY_PAUSE_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PREV_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(NEXT_BTN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Initialize MPD client
        self.mpd_client = MPDClient()
        self.mpd_client.timeout = 10
        self.mpd_client.connect(MPD_HOST, MPD_PORT)
        
        # Initialize OLED display with luma.oled
        serial = i2c(port=1, address=OLED_ADDR)
        self.device = ssd1306(serial, width=OLED_WIDTH, height=OLED_HEIGHT)
        
        # Load fonts for display
        self.font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
        self.small_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 12)
        
        # Initialize button states
        self.last_play_pause_state = GPIO.input(PLAY_PAUSE_BTN)
        self.last_prev_state = GPIO.input(PREV_BTN)
        self.last_next_state = GPIO.input(NEXT_BTN)
        
        # Update initial display
        self.update_display()
    
    def update_display(self):
        # Get current status
        status = self.mpd_client.status()
        song_info = self.mpd_client.currentsong()
        
        # Get current track index and total tracks
        current_index = int(status.get('song', '0')) + 1 if 'song' in status else 0
        total_songs = status.get('playlistlength', '0')
        
        # Draw on the display using luma.oled's canvas context manager
        with canvas(self.device) as draw:
            # Draw the track index in large font
            draw.text((10, 10), f"{current_index}/{total_songs}", font=self.font, fill="white")
            
            # Draw song title (if available) in smaller font
            if 'title' in song_info:
                title = song_info['title']
                if len(title) > 15:
                    title = title[:15] + "..."
                draw.text((10, 40), title, font=self.small_font, fill="white")
            
            # Draw play/pause status
            state = status.get('state', 'stop')
            if state == 'play':
                draw.text((100, 10), "▶", font=self.font, fill="white")
            elif state == 'pause':
                draw.text((100, 10), "⏸", font=self.font, fill="white")
    
    def handle_play_pause(self):
        status = self.mpd_client.status()
        state = status.get('state', 'stop')
        
        if state == 'play':
            self.mpd_client.pause(1)
        else:
            self.mpd_client.play()
        
        self.update_display()
    
    def handle_prev(self):
        status = self.mpd_client.status()
        state = status.get('state', 'stop')
        
        if state == 'play':
            # Rewind 15 seconds if playing
            current_time = float(status.get('elapsed', 0))
            if current_time > 15:
                self.mpd_client.seekcur(current_time - 15)
            else:
                self.mpd_client.seekcur(0)
        else:
            # Go to previous track if paused
            self.mpd_client.previous()
        
        self.update_display()
    
    def handle_next(self):
        status = self.mpd_client.status()
        state = status.get('state', 'stop')
        
        if state == 'play':
            # Fast forward 15 seconds if playing
            current_time = float(status.get('elapsed', 0))
            self.mpd_client.seekcur(current_time + 15)
        else:
            # Go to next track if paused
            self.mpd_client.next()
        
        self.update_display()
    
    def check_buttons(self):
        # Check play/pause button
        current_play_pause_state = GPIO.input(PLAY_PAUSE_BTN)
        if current_play_pause_state == 0 and self.last_play_pause_state == 1:
            self.handle_play_pause()
        self.last_play_pause_state = current_play_pause_state
        
        # Check previous button
        current_prev_state = GPIO.input(PREV_BTN)
        if current_prev_state == 0 and self.last_prev_state == 1:
            self.handle_prev()
        self.last_prev_state = current_prev_state
        
        # Check next button
        current_next_state = GPIO.input(NEXT_BTN)
        if current_next_state == 0 and self.last_next_state == 1:
            self.handle_next()
        self.last_next_state = current_next_state
    
    def run(self):
        try:
            print("MP3 Player running. Press Ctrl+C to exit.")
            while True:
                self.check_buttons()
                status = self.mpd_client.status()
                time.sleep(0.1)  # Small delay to prevent CPU hogging
                
                # Periodically update the display for time changes
                if status.get('state') == 'play' and int(time.time()) % 5 == 0:
                    self.update_display()
                    
        except KeyboardInterrupt:
            print("Exiting...")
        finally:
            # Clean up
            GPIO.cleanup()
            self.mpd_client.close()
            self.mpd_client.disconnect()
            self.device.clear()

if __name__ == "__main__":
    player = MP3Player()
    player.run()
