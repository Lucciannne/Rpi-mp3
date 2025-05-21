#!/usr/bin/env python3
import time
import os
import glob
import RPi.GPIO as GPIO
import vlc
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from PIL import ImageFont

# Define GPIO pins for buttons
PLAY_PAUSE_BTN = 11
PREV_BTN = 13
NEXT_BTN = 15

# Music directory configuration
MUSIC_DIR = "/home/fran/music"
SUPPORTED_FORMATS = ['.mp3', '.flac', '.wav', '.ogg', '.m4a']

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
        
        # Initialize VLC instance and player
        self.vlc_instance = vlc.Instance('--no-xlib')
        self.player = self.vlc_instance.media_player_new()
        
        # Initialize button states
        self.last_play_pause_state = GPIO.input(PLAY_PAUSE_BTN)
        self.last_prev_state = GPIO.input(PREV_BTN)
        self.last_next_state = GPIO.input(NEXT_BTN)
        
        # Track list and current position
        self.tracks = []
        self.current_track_index = 0
        self.is_playing = False
        
        # Load tracks
        self.load_tracks()
        
        # Set up initial track
        if self.tracks:
            self.set_track(0)
        
        # Update display with initial state
        self.update_display()
    
    def load_tracks(self):
        """Load all music tracks from the music directory"""
        try:
            with canvas(self.device) as draw:
                draw.text((10, 10), "Loading", font=self.font, fill="white")
                draw.text((10, 40), "music files...", font=self.small_font, fill="white")
            
            self.tracks = []
            
            # Find all music files with supported extensions
            for extension in SUPPORTED_FORMATS:
                pattern = os.path.join(MUSIC_DIR, f"*{extension}")
                self.tracks.extend(glob.glob(pattern))
            
            # Sort tracks alphabetically
            self.tracks.sort()
            
            if not self.tracks:
                print("No music files found")
                with canvas(self.device) as draw:
                    draw.text((10, 10), "No music", font=self.font, fill="white")
                    draw.text((10, 40), f"Check: {MUSIC_DIR}", font=self.small_font, fill="white")
            else:
                track_count = len(self.tracks)
                print(f"Loaded {track_count} tracks")
                
        except Exception as e:
            print(f"Error loading tracks: {e}")
            with canvas(self.device) as draw:
                draw.text((10, 10), "Error:", font=self.small_font, fill="white")
                draw.text((10, 25), str(e)[:20], font=self.small_font, fill="white")
    
    def set_track(self, index):
        """Set the current track by index without playing"""
        if not self.tracks:
            return False
        
        # Ensure index is within bounds
        if index < 0:
            index = 0
        elif index >= len(self.tracks):
            index = len(self.tracks) - 1
        
        self.current_track_index = index
        
        # Create a new Media object
        media = self.vlc_instance.media_new(self.tracks[index])
        
        # Set the media to the player
        self.player.set_media(media)
        
        # Parse the media (this loads metadata)
        media.parse()
        
        return True
    
    def play_pause(self):
        """Toggle between play and pause"""
        if not self.tracks:
            return
        
        if self.player.is_playing():
            self.player.pause()
            self.is_playing = False
        else:
            self.player.play()
            self.is_playing = True
    
    def get_track_name(self):
        """Get the name of the current track"""
        if not self.tracks or self.current_track_index >= len(self.tracks):
            return "No track"
        
        # Get the track path
        track_path = self.tracks[self.current_track_index]
        
        # Try to get metadata from VLC
        media = self.player.get_media()
        if media:
            title = media.get_meta(vlc.Meta.Title)
            if title:
                return title
        
        # Fall back to filename if no metadata
        return os.path.basename(track_path)
    
    def update_display(self):
        """Update the OLED display with current track info"""
        try:
            total_tracks = len(self.tracks)
            
            if total_tracks == 0:
                # No tracks loaded
                with canvas(self.device) as draw:
                    draw.text((10, 10), "No tracks", font=self.font, fill="white")
                return
            
            # Get current track info (1-based for display)
            current_track_num = self.current_track_index + 1
            track_name = self.get_track_name()
            
            # Truncate track name if too long
            if len(track_name) > 15:
                track_name = track_name[:15] + "..."
            
            # Draw on the display
            with canvas(self.device) as draw:
                # Draw track number / total tracks
                draw.text((10, 10), f"{current_track_num}/{total_tracks}", font=self.font, fill="white")
                
                # Draw track name
                draw.text((10, 40), track_name, font=self.small_font, fill="white")
                
                # Draw play/pause status
                if self.is_playing:
                    draw.text((100, 10), "▶", font=self.font, fill="white")
                else:
                    draw.text((100, 10), "⏸", font=self.font, fill="white")
        
        except Exception as e:
            print(f"Display update error: {e}")
            with canvas(self.device) as draw:
                draw.text((10, 10), "Error:", font=self.small_font, fill="white")
                draw.text((10, 25), str(e)[:20], font=self.small_font, fill="white")
    
    def handle_play_pause(self):
        """Handle play/pause button press"""
        if not self.tracks:
            with canvas(self.device) as draw:
                draw.text((10, 10), "No tracks", font=self.font, fill="white")
            return
        
        self.play_pause()
        self.update_display()
    
    def handle_prev(self):
        """Handle previous track or rewind button press"""
        if not self.tracks:
            return
        
        if self.is_playing:
            # If playing, rewind 15 seconds
            current_time = self.player.get_time()
            if current_time > 15000:  # VLC time is in milliseconds
                self.player.set_time(current_time - 15000)
            else:
                self.player.set_time(0)
        else:
            # If paused, go to previous track
            if self.current_track_index > 0:
                self.set_track(self.current_track_index - 1)
                self.update_display()
    
    def handle_next(self):
        """Handle next track or fast forward button press"""
        if not self.tracks:
            return
        
        if self.is_playing:
            # If playing, fast forward 15 seconds
            current_time = self.player.get_time()
            self.player.set_time(current_time + 15000)
        else:
            # If paused, go to next track
            if self.current_track_index < len(self.tracks) - 1:
                self.set_track(self.current_track_index + 1)
                self.update_display()
    
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
    
    def run(self):
        """Main loop to run the MP3 player"""
        try:
            print("MP3 Player running. Press Ctrl+C to exit.")
            last_update_time = 0
            
            while True:
                # Check and handle button presses
                self.check_buttons()
                
                # Periodically update the display when playing
                current_time = time.time()
                if self.is_playing and current_time - last_update_time >= 5:
                    self.update_display()
                    last_update_time = current_time
                
                # Check if track ended and play next one
                if self.is_playing and not self.player.is_playing():
                    print("Track ended")
                    # Move to next track if available
                    if self.current_track_index < len(self.tracks) - 1:
                        self.set_track(self.current_track_index + 1)
                        self.player.play()
                        self.update_display()
                    else:
                        # At the end of the playlist
                        self.is_playing = False
                        self.update_display()
                
                # Small delay to prevent CPU hogging
                time.sleep(0.1)
                    
        except KeyboardInterrupt:
            print("Exiting...")
        finally:
            # Clean up
            GPIO.cleanup()
            self.player.stop()
            self.device.clear()

if __name__ == "__main__":
    player = MP3Player()
    player.run()
