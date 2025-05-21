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
MUSIC_DIR = "/home/fran/music"

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
        self.mpd_client.idletimeout = None  # Don't timeout waiting for idle events
        self.connect_mpd()
        
        # Initialize OLED display with luma.oled
        serial = i2c(port=1, address=OLED_ADDR)
        self.device = ssd1306(serial, width=OLED_WIDTH, height=OLED_HEIGHT)
        
        # Load fonts for display
        try:
            self.font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
            self.small_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 12)
        except IOError:
            # Fallback to default font if DejaVu is not available
            self.font = ImageFont.load_default()
            self.small_font = ImageFont.load_default()
        
        # Initialize button states
        self.last_play_pause_state = GPIO.input(PLAY_PAUSE_BTN)
        self.last_prev_state = GPIO.input(PREV_BTN)
        self.last_next_state = GPIO.input(NEXT_BTN)
        
        # Ensure the playlist is loaded and ready
        self.ensure_playlist_loaded()
        
        # Update initial display
        self.update_display()
    
    def connect_mpd(self):
        """Connect to MPD server with error handling"""
        try:
            self.mpd_client.connect(MPD_HOST, MPD_PORT)
            print("Connected to MPD server")
        except Exception as e:
            print(f"Error connecting to MPD: {e}")
            # Display error on OLED if available
            if hasattr(self, 'device'):
                with canvas(self.device) as draw:
                    draw.text((10, 10), "MPD Error", fill="white")
                    draw.text((10, 30), "Check MPD", fill="white")
                    draw.text((10, 45), "service", fill="white")
            time.sleep(5)
            exit(1)
    
    def ensure_playlist_loaded(self):
        """Make sure there are songs in the playlist"""
        try:
            status = self.mpd_client.status()
            
            # Check if playlist is empty
            if int(status.get('playlistlength', 0)) == 0:
                print("Playlist is empty, adding all music files")
                
                # Clear current playlist
                self.mpd_client.clear()
                
                # Update MPD database to find new files
                self.mpd_client.update()
                
                # Wait for update to complete (can take time for large libraries)
                print("Updating MPD database...")
                time.sleep(2)  # Give some time for database update
                
                # Add all files to playlist
                self.mpd_client.add("/")
                
                # Check if files were added
                status = self.mpd_client.status()
                if int(status.get('playlistlength', 0)) == 0:
                    print("No music files found in MPD library")
                    with canvas(self.device) as draw:
                        draw.text((10, 10), "No songs", fill="white")
                        draw.text((10, 30), f"Check: {MUSIC_DIR}", fill="white")
                else:
                    print(f"Added {status.get('playlistlength')} songs to playlist")
            else:
                print(f"Playlist already contains {status.get('playlistlength')} songs")
                
        except Exception as e:
            print(f"Error ensuring playlist: {e}")
            # Display error on OLED
            with canvas(self.device) as draw:
                draw.text((10, 10), "Playlist Error", fill="white")
                draw.text((10, 30), str(e)[:15], fill="white")
    
    def update_display(self):
        try:
            # Get current status
            status = self.mpd_client.status()
            
            # Get current track index and total tracks
            current_index = int(status.get('song', '0')) + 1 if 'song' in status else 0
            total_songs = status.get('playlistlength', '0')
            
            # Get song info if available
            song_info = {}
            if 'song' in status:
                try:
                    song_info = self.mpd_client.currentsong()
                except:
                    song_info = {}
            
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
                elif 'file' in song_info:
                    # Use filename if title not available
                    filename = os.path.basename(song_info['file'])
                    if len(filename) > 15:
                        filename = filename[:15] + "..."
                    draw.text((10, 40), filename, font=self.small_font, fill="white")
                
                # Draw play/pause status
                state = status.get('state', 'stop')
                if state == 'play':
                    draw.text((100, 10), "▶", font=self.font, fill="white")
                elif state == 'pause':
                    draw.text((100, 10), "⏸", font=self.font, fill="white")
                else:
                    draw.text((100, 10), "■", font=self.font, fill="white")
        except Exception as e:
            print(f"Display update error: {e}")
            # Show error on display
            with canvas(self.device) as draw:
                draw.text((10, 10), "Error:", font=self.small_font, fill="white")
                draw.text((10, 25), str(e)[:20], font=self.small_font, fill="white")
    
    def handle_play_pause(self):
        try:
            status = self.mpd_client.status()
            state = status.get('state', 'stop')
            
            playlist_length = int(status.get('playlistlength', 0))
            if playlist_length == 0:
                print("No songs in playlist")
                with canvas(self.device) as draw:
                    draw.text((10, 10), "No songs", font=self.font, fill="white")
                return
            
            if state == 'play':
                self.mpd_client.pause(1)
            else:
                # If stopped, start from the beginning
                if state == 'stop':
                    self.mpd_client.play(0)
                else:
                    self.mpd_client.play()
            
            self.update_display()
        except Exception as e:
            print(f"Play/pause error: {e}")
    
    def handle_prev(self):
        try:
            status = self.mpd_client.status()
            state = status.get('state', 'stop')
            
            # First check if there are songs in the playlist
            if int(status.get('playlistlength', 0)) == 0:
                print("No songs in playlist")
                return
            
            if state == 'play':
                # Rewind 15 seconds if playing
                current_time = float(status.get('elapsed', 0))
                if current_time > 15:
                    self.mpd_client.seekcur(current_time - 15)
                else:
                    self.mpd_client.seekcur(0)
            else:
                # If we're not playing, we need to ensure there's a current song
                if 'song' in status:
                    self.mpd_client.previous()
                else:
                    # If no current song, play the first one
                    self.mpd_client.play(0)
            
            self.update_display()
        except Exception as e:
            print(f"Previous track error: {e}")
            with canvas(self.device) as draw:
                draw.text((10, 10), "Error:", font=self.small_font, fill="white")
                draw.text((10, 25), str(e)[:20], font=self.small_font, fill="white")
    
    def handle_next(self):
        try:
            status = self.mpd_client.status()
            state = status.get('state', 'stop')
            
            # First check if there are songs in the playlist
            if int(status.get('playlistlength', 0)) == 0:
                print("No songs in playlist")
                return
            
            if state == 'play':
                # Fast forward 15 seconds if playing
                current_time = float(status.get('elapsed', 0))
                self.mpd_client.seekcur(current_time + 15)
            else:
                # If we're not playing, we need to ensure there's a current song
                if 'song' in status:
                    self.mpd_client.next()
                else:
                    # If no current song, play the first one
                    self.mpd_client.play(0)
            
            self.update_display()
        except Exception as e:
            print(f"Next track error: {e}")
    
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
    
    def check_mpd_connection(self):
        """Ensure MPD connection is still active"""
        try:
            self.mpd_client.ping()
        except:
            print("MPD connection lost, reconnecting...")
            try:
                self.mpd_client.disconnect()
            except:
                pass
            self.connect_mpd()
    
    def run(self):
        try:
            print("MP3 Player running. Press Ctrl+C to exit.")
            last_connection_check = time.time()
            
            while True:
                # Check and handle button presses
                self.check_buttons()
                
                # Periodically check MPD connection
                current_time = time.time()
                if current_time - last_connection_check > 30:  # Check every 30 seconds
                    self.check_mpd_connection()
                    last_connection_check = current_time
                
                # Get current status and update display when playing
                try:
                    status = self.mpd_client.status()
                    if status.get('state') == 'play' and int(time.time()) % 5 == 0:
                        self.update_display()
                except Exception as e:
                    print(f"Error getting MPD status: {e}")
                
                # Small delay to prevent CPU hogging
                time.sleep(0.1)
                    
        except KeyboardInterrupt:
            print("Exiting...")
        finally:
            # Clean up
            GPIO.cleanup()
            try:
                self.mpd_client.close()
                self.mpd_client.disconnect()
            except:
                pass
            self.device.clear()

if __name__ == "__main__":
    player = MP3Player()
    player.run()
