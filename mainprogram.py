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
draw   = None
font   = None

def scan_and_load():
    """Builds a fresh playlist of all audio files under MUSIC_DIR."""
    client.clear()
    for root, _, files in os.walk(MUSIC_DIR):
        for fn in sorted(files):
            if fn.lower().endswith((".mp3", ".flac", ".wav", ".ogg", ".m4a")):
                path = os.path.join(root, fn)
                client.add(path)
    client.play(0)
    client.pause()  # start paused

def init_mpd():
    global client
    client = MPDClient()
    client.connect("localhost", 6600)
    scan_and_load()

def init_oled():
    global oled, draw, font
    serial = i2c(port=1, address=I2C_ADDRESS)
    oled   = ssd1306(serial)
    font   = ImageFont.truetype(FONT_PATH, FONT_SIZE)

def get_status():
    try:
        st = client.status()
        print(f"Current status: {st}")
        return st.get("state", "stop"), int(st.get("song", 0)), float(st.get("elapsed", 0))
    except Exception as e:
        print(f"Error getting status: {e}")
        return "stop", 0, 0.0

def update_oled():
    state, song_idx, elapsed = get_status()
    print(f"State: {state}, Song Index: {song_idx}, Elapsed: {elapsed:.1f}s")
    
    # Verify we're actually getting a valid index
    if song_idx < 0:
        print("Warning: Invalid song index received!")
        return
        
    track_no = song_idx + 1
    msg = "▶" if state == "play" else "⏸"
    
    # Draw logic remains the same
    img = Image.new("1", (oled.width, oled.height))
    draw_local = ImageDraw.Draw(img)
    w, h = draw_local.textsize(str(track_no), font=font)
    x = (oled.width - w) // 2
    y = (oled.height - FONT_SIZE) // 2
    draw_local.text((x, y), str(track_no), font=font, fill=255)
    draw_local.text((oled.width - FONT_SIZE//2 - 2, oled.height - FONT_SIZE//2 - 2),
                    msg, font=ImageFont.truetype(FONT_PATH, FONT_SIZE//2), fill=255)
    oled.display(img)
    
def btn_play_pause(channel):
    state, _, _ = get_status()
    if state == "play":
        client.pause(1)
    else:
        client.play()
    update_oled()

def btn_rewind_prev(channel):
    state, _, elapsed = get_status()
    if state == "play" and elapsed > 15:
        client.seekcur(int(elapsed) - 15)
    else:
        was_playing = (state == "play")
        client.previous()
        if not was_playing:
            client.pause(1)
    update_oled()

def btn_ffwd_next(channel):
    state, _, elapsed = get_status()
    # MPD doesn't support 'seekcur' beyond track length; so always next if paused
    if state == "play":
        # get length to check boundary
        song = client.currentsong()
        length = float(song.get("time", 0))
        if elapsed + 15 < length:
            client.seekcur(int(elapsed) + 15)
        else:
            client.next()
    else:
        was_playing = False
        client.next()
        client.pause(1)
    update_oled()

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
        # keep alive
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
