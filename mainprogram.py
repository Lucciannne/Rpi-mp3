#!/usr/bin/env python3
import os
import time
from mpd import MPDClient
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
MUSIC_DIR    = "/home/fran/music"
I2C_ADDRESS  = 0x3C
BUTTON_PLAY  = 11   # BOARD pin 11
BUTTON_REW   = 13   # BOARD pin 13
BUTTON_FFWD  = 15   # BOARD pin 15
FONT_PATH    = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SIZE    = 80
DEBOUNCE_MS  = 200
# ──────────────────────────────────────────────────────────────────────────────

# Globals
client = None
oled   = None
font   = None

def scan_and_load():
    """Builds a fresh playlist of all audio files under MUSIC_DIR."""
    try:
        client.clear()
        client.update()  # Update MPD database
        time.sleep(5)    # Allow time for update (crude, consider better method)
        client.add("/")  # Add all tracks from database to playlist
        client.save('alltracks')  # Optional: save playlist
        client.play(0)
        client.pause()
    except Exception as e:
        print(f"Error building playlist: {e}")

def init_mpd():
    global client
    client = MPDClient()
    client.timeout = 10
    client.idletimeout = None
    try:
        client.connect("localhost", 6600)
        scan_and_load()
    except Exception as e:
        print(f"MPD connection failed: {e}")

def init_oled():
    global oled, font
    serial = i2c(port=1, address=I2C_ADDRESS)
    oled   = ssd1306(serial)
    font   = ImageFont.truetype(FONT_PATH, FONT_SIZE)

def get_status():
    try:
        st = client.status()
        state = st.get("state", "stop")
        song_idx = int(st.get("song", 0)) if 'song' in st else 0
        elapsed = float(st.get("elapsed", 0))
        total_tracks = int(st.get("playlistlength", 0))
        return state, song_idx, elapsed, total_tracks
    except Exception as e:
        print(f"Error getting status: {e}")
        return "stop", 0, 0.0, 0

def update_oled():
    try:
        state, song_idx, elapsed, total_tracks = get_status()
        if total_tracks == 0:
            return  # No tracks to display
        
        track_no = song_idx + 1
        msg = "▶" if state == "play" else "⏸"
        
        img = Image.new("1", (oled.width, oled.height))
        draw = ImageDraw.Draw(img)
        
        # Large track number
        font_large = ImageFont.truetype(FONT_PATH, FONT_SIZE)
        track_str = str(track_no)
        w, h = draw.textsize(track_str, font=font_large)
        x = (oled.width - w) // 2
        y = (oled.height - FONT_SIZE) // 2
        draw.text((x, y), track_str, font=font_large, fill=255)
        
        # Total tracks (small)
        font_small = ImageFont.truetype(FONT_PATH, FONT_SIZE//2)
        total_str = f"/{total_tracks}"
        tw, th = draw.textsize(total_str, font=font_small)
        tx = x + w + 2
        ty = y + (h - th)
        draw.text((tx, ty), total_str, font=font_small, fill=255)
        
        # State icon
        state_font = ImageFont.truetype(FONT_PATH, FONT_SIZE//2)
        state_w, _ = draw.textsize(msg, font=state_font)
        draw.text((oled.width - state_w - 2, oled.height - FONT_SIZE//2 - 2),
                  msg, font=state_font, fill=255)
        
        oled.display(img)
    except Exception as e:
        print(f"Display error: {e}")

def handle_mpd_command(func, *args):
    """Helper to handle MPD commands with reconnect on failure."""
    try:
        return func(*args)
    except (ConnectionError, BrokenPipeError):
        print("Reconnecting to MPD...")
        client.disconnect()
        client.connect("localhost", 6600)
        return func(*args)
    except Exception as e:
        print(f"MPD command failed: {e}")

def btn_play_pause(channel):
    try:
        state, _, _, total = get_status()
        if total == 0:
            return
        if state == "play":
            handle_mpd_command(client.pause, 1)
        else:
            handle_mpd_command(client.play)
        update_oled()
    except Exception as e:
        print(f"Play/Pause error: {e}")

def btn_rewind_prev(channel):
    try:
        state, idx, elapsed, total = get_status()
        if total == 0:
            return
        if state == "play":
            if elapsed > 15:
                handle_mpd_command(client.seekcur, int(elapsed) - 15)
            else:
                if idx > 0:
                    handle_mpd_command(client.previous)
        else:
            if idx > 0:
                handle_mpd_command(client.previous)
                handle_mpd_command(client.pause, 1)
        update_oled()
    except Exception as e:
        print(f"Rewind error: {e}")

def btn_ffwd_next(channel):
    try:
        state, idx, elapsed, total = get_status()
        if total == 0 or idx >= total - 1:
            return  # No next track
        if state == "play":
            song = handle_mpd_command(client.currentsong)
            length = float(song.get("time", 0))
            if elapsed + 15 < length:
                handle_mpd_command(client.seekcur, int(elapsed) + 15)
            else:
                handle_mpd_command(client.next)
        else:
            handle_mpd_command(client.next)
            handle_mpd_command(client.pause, 1)
        update_oled()
    except Exception as e:
        print(f"FFwd error: {e}")

def init_gpio():
    GPIO.setmode(GPIO.BOARD)
    for pin, cb in ((BUTTON_PLAY, btn_play_pause),
                    (BUTTON_REW,  btn_rewind_prev),
                    (BUTTON_FFWD, btn_ffwd_next)):
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(pin, GPIO.FALLING,
                              callback=cb, bouncetime=DEBOUNCE_MS)

def main():
    try:
        init_mpd()
        init_oled()
        init_gpio()
        update_oled()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        if client:
            client.close()
            client.disconnect()

if __name__ == "__main__":
    main()
