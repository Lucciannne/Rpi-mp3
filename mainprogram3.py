#!/usr/bin/env python3
import time
import os
import RPi.GPIO as GPIO
from mpd import MPDClient
import adafruit_ssd1306
import board
import busio
from PIL import Image, ImageDraw, ImageFont

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
        
        # Initialize I2C for OLED display
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.oled = adafruit_ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, self.i2c, addr=OLED_ADDR)
        
        # Clear display
        self.oled.fill(0)
        self.oled.show()
        
        # Load font for display
        self.font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
        self.small_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 12)
        
        # Create an image buffer for PIL to draw on
        self.image = Image.new('1', (OLED_WIDTH, OLED_HEIGHT))
        self.draw = ImageDraw.Draw(self.image)
        
        # Initialize button states
        self.last_play_pause_state = GPIO.input(PLAY_PAUSE_BTN)
        self.last_prev_state = GPIO.input(PREV_BTN)
        self.last_next_state = GPIO.input(NEXT_BTN)
        
        # Update initial display
        self.update_display()
    
    def update_display(self):
        # Clear the image buffer
        self.draw.rectangle((0, 0, OLED_WIDTH, OLED_HEIGHT), outline=0, fill=0)
        
        # Get current status
        status = self.mpd_client.status()
        song_info = self.mpd_client.currentsong()
        
        # Get current track index and total tracks
        current_index = int(status.get('song', '0')) + 1 if 'song' in status else 0
        total_songs = status.get('playlistlength', '0')
        
        # Draw the track index in large font
        self.draw.text((10, 10), f"{current_index}/{total_songs}", font=self.font, fill=255)
        
        # Draw song title (if available) in smaller font
        if 'title' in song_info:
            title = song_info['title']
            if len(title) > 15:
                title = title[:15] + "..."
            self.draw.text((10, 40), title, font=self.small_font, fill=255)
        
        # Draw play/pause status
        state = status.get('state', 'stop')
        if state == 'play':
            self.draw.text((100, 10), "▶", font=self.font, fill=255)
        elif state == 'pause':
            self.draw.text((100, 10), "⏸", font=self.font, fill=255)
        
        # Display the image buffer on the OLED
        self.oled.image(self.image)
        self.oled.show()
    
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
            self.oled.fill(0)
            self.oled.show()

if __name__ == "__main__":
    player = MP3Player()
    player.run()
