import time
import RPi.GPIO as GPIO
from mpd import MPDClient
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import ImageFont, ImageDraw, Image

# GPIO pin setup (BOARD numbering)
BUTTON_PLAY = 11       # BCM 17
BUTTON_PREV_FF = 13     # BCM 27
BUTTON_NEXT_RW = 15     # BCM 22

# Font path and size for display
FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_SIZE = 48

# MPD setup

def init_mpd_client(host='localhost', port=6600):
    client = MPDClient()
    client.timeout = 10
    client.idletimeout = None
    client.connect(host, port)
    return client

# OLED setup

def init_oled():
    serial = i2c(port=1, address=0x3C)
    device = ssd1306(serial)
    device.clear()
    return device

# Draw large centered text (track index)

def draw_index(device, idx):
    device.clear()
    width, height = device.width, device.height
    image = Image.new('1', (width, height))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    text = str(idx)
    w, h = draw.textsize(text, font=font)
    x = (width - w) // 2
    y = (height - h) // 2
    draw.text((x, y), text, font=font, fill=255)
    device.display(image)

# Get current track index (1-based), or 0 if unknown

def get_current_index(client):
    try:
        status = client.status()
        if 'song' in status:
            return int(status['song']) + 1
    except Exception:
        pass
    return 0

# Update the OLED display

def update_display():
    idx = get_current_index(mpd)
    draw_index(oled, idx)

# Button callbacks

def on_play_pause(channel):
    try:
        status = mpd.status()
        if status.get('state') == 'play':
            mpd.pause()
        else:
            mpd.play()
    except Exception as e:
        print('Play/Pause error:', e)
    update_display()


def on_prev_ff(channel):
    try:
        status = mpd.status()
        state = status.get('state')
        elapsed = float(status.get('elapsed', 0))
        pos = int(status.get('song', 0))
        if state == 'play':
            # rewind 15s within track
            new_time = max(0, elapsed - 15)
            mpd.seek(pos, new_time)
        else:
            # go to previous track and stay paused
            mpd.previous()
            mpd.pause()
    except Exception as e:
        print('Prev/RW error:', e)
    update_display()


def on_next_rw(channel):
    try:
        status = mpd.status()
        state = status.get('state')
        elapsed = float(status.get('elapsed', 0))
        pos = int(status.get('song', 0))
        if state == 'play':
            # fast-forward 15s within track
            new_time = elapsed + 15
            mpd.seek(pos, new_time)
        else:
            # go to next track and stay paused
            mpd.next()
            mpd.pause()
    except Exception as e:
        print('Next/FF error:', e)
    update_display()

# Main

def main():
    global mpd, oled
    mpd = init_mpd_client()
    oled = init_oled()

    GPIO.setmode(GPIO.BOARD)
    for pin in (BUTTON_PLAY, BUTTON_PREV_FF, BUTTON_NEXT_RW):
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    GPIO.add_event_detect(BUTTON_PLAY, GPIO.FALLING,
                          callback=on_play_pause, bouncetime=200)
    GPIO.add_event_detect(BUTTON_PREV_FF, GPIO.FALLING,
                          callback=on_prev_ff, bouncetime=200)
    GPIO.add_event_detect(BUTTON_NEXT_RW, GPIO.FALLING,
                          callback=on_next_rw, bouncetime=200)

    # Initial draw
    update_display()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        mpd.close()
        mpd.disconnect()

if __name__ == '__main__':
    main()
