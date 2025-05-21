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
        
        # Show initialization message
        with canvas(self.device) as draw:
            draw.text((10, 10), "Starting...", font=self.font, fill="white")
        
        # Initialize MPD client and connect
        self.mpd_client = MPDClient()
        self.mpd_client.timeout = 10
        self.mpd_client.idletimeout = None  # Don't timeout waiting for idle events
        self.connect_mpd()
        
        # Initialize button states
        self.last_play_pause_state = GPIO.input(PLAY_PAUSE_BTN)
        self.last_prev_state = GPIO.input(PREV_BTN)
        self.last_next_state = GPIO.input(NEXT_BTN)
        
        # Set up the playlist and position to the first track
        self.setup_playlist()
        
        # Update initial display
        self.update_display()
    
    def connect_mpd(self):
        """Connect to MPD server with error handling"""
        try:
            self.mpd_client.connect(MPD_HOST, MPD_PORT)
            print("Connected to MPD server")
        except Exception as e:
            print(f"Error connecting to MPD: {e}")
            # Display error on OLED
            with canvas(self.device) as draw:
                draw.text((10, 10), "MPD Error", fill="white")
                draw.text((10, 30), "Check MPD", fill="white")
                draw.text((10, 45), "service", fill="white")
            time.sleep(5)
            exit(1)
    
    def setup_playlist(self):
        """Set up the playlist with all tracks from the music directory"""
        try:
            # Show loading message
            with canvas(self.device) as draw:
                draw.text((10, 10), "Loading", font=self.font, fill="white")
                draw.text((10, 40), "music files...", font=self.small_font, fill="white")
            
            # Clear the current playlist
            self.mpd_client.clear()
            
            # Update the MPD database to find all available music files
            self.mpd_client.update()
            
            # Wait a moment for the database update to complete
            time.sleep(2)
            
            # List all files in the music directory
            files = self.mpd_client.listall()
            
            # Filter to only include MP3 files (or any music files MPD supports)
            music_files = []
            for item in files:
                if 'file' in item and (item['file'].endswith('.mp3') or 
                                       item['file'].endswith('.flac') or 
                                       item['file'].endswith('.ogg') or
                                       item['file'].endswith('.wav')):
                    music_files.append(item['file'])
            
            # Sort files alphabetically for consistent ordering
            music_files.sort()
            
            # Add each file to the playlist
            for file in music_files:
                self.mpd_client.add(file)
            
            # Check if any files were added
            status = self.mpd_client.status()
            playlist_length = int(status.get('playlistlength', 0))
            
            if playlist_length > 0:
                # Stop any current playback
                self.mpd_client.stop()
                
                # Position to the first track (index 0) without playing
                self.mpd_client.playid(0)
                self.mpd_client.pause(1)  # Pause immediately to prevent autoplay
                
                print(f"Loaded {playlist_length} tracks and positioned to first track")
            else:
                print("No music files found")
                with canvas(self.device) as draw:
                    draw.text((10, 10), "No music", font=self.font, fill="white")
                    draw.text((10, 40), f"Check: {MUSIC_DIR}", font=self.small_font, fill="white")
                
        except Exception as e:
            print(f"Error setting up playlist: {e}")
            with canvas(self.device) as draw:
                draw.text((10, 10), "Playlist Error", font=self.small_font, fill="white")
                draw.text((10, 30), str(e)[:15], font=self.small_font, fill="white")
    
    def update_display(self):
        """Update the OLED display with current track info"""
        try:
            # Get current status and song info
            status = self.mpd_client.status()
            playlist_length = int(status.get('playlistlength', 0))
            
            if playlist_length == 0:
                # No tracks in playlist
                with canvas(self.device) as draw:
                    draw.text((10, 10), "No tracks", font=self.font, fill="white")
                return
            
            # Get current track number (1-based for display)
            current_song = int(status.get('song', 0)) + 1 if 'song' in status else 1
            
            # Try to get current song info
            try:
                song_info = self.mpd_client.currentsong()
            except:
                song_info = {}
            
            # Draw on the display
            with canvas(self.device) as draw:
                # Draw track number / total tracks
                draw.text((10, 10), f"{current_song}/{playlist_length}", font=self.font, fill="white")
                
                # Draw track title or filename
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
                
                # Draw play/pause/stop status
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
        """Handle play/pause button press"""
        try:
            status = self.mpd_client.status()
            state = status.get('state', 'stop')
            
            # Check if there are songs in the playlist
            if int(status.get('playlistlength', 0)) == 0:
                print("No songs in playlist")
                return
            
            if state == 'play':
                # If playing, pause
                self.mpd_client.pause(1)
            else:
                # If paused or stopped, play (resume)
                self.mpd_client.pause(0)
            
            # Update display after state change
            self.update_display()
            
        except Exception as e:
            print(f"Play/pause error: {e}")
    
    def handle_prev(self):
        """Handle previous track or rewind button press"""
        try:
            status = self.mpd_client.status()
            state = status.get('state', 'stop')
            
            # Check if there are songs in the playlist
            if int(status.get('playlistlength', 0)) == 0:
                print("No songs in playlist")
                return
            
            if state == 'play':
                # If playing, rewind 15 seconds
                current_time = float(status.get('elapsed', 0))
                if current_time > 15:
                    self.mpd_client.seekcur(current_time - 15)
                else:
                    self.mpd_client.seekcur(0)
            else:
                # If paused or stopped, go to previous track without playing
                current_song = int(status.get('song', 0))
                if current_song > 0:
                    # Move to previous song
                    self.mpd_client.previous()
                    # Ensure it's paused
                    self.mpd_client.pause(1)
                else:
                    # If at first track, stay there
                    print("Already at first track")
            
            # Update display after track change
            self.update_display()
            
        except Exception as e:
            print(f"Previous track error: {e}")
    
    def handle_next(self):
        """Handle next track or fast forward button press"""
        try:
            status = self.mpd_client.status()
            state = status.get('state', 'stop')
            
            # Check if there are songs in the playlist
            playlist_length = int(status.get('playlistlength', 0))
            if playlist_length == 0:
                print("No songs in playlist")
                return
            
            if state == 'play':
                # If playing, fast forward 15 seconds
                current_time = float(status.get('elapsed', 0))
                self.mpd_client.seekcur(current_time + 15)
            else:
                # If paused or stopped, go to next track without playing
                current_song = int(status.get('song', 0))
                if current_song < playlist_length - 1:
                    # Move to next song
                    self.mpd_client.next()
                    # Ensure it's paused
                    self.mpd_client.pause(1)
                else:
                    # If at last track, stay there
                    print("Already at last track")
            
            # Update display after track change
            self.update_display()
            
        except Exception as e:
            print(f"Next track error: {e}")
    
    def check_buttons(self):
        """Check button states and handle presses"""
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
        """Main loop to run the MP3 player"""
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
                
                # Periodically update the display when playing
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
