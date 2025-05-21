import time
import RPi.GPIO as GPIO
from mpd import MPDClient
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import ImageFont, ImageDraw, Image

# GPIO pin setup
BUTTON_PLAY = 11  # BCM 17
BUTTON_PREV_FF = 13  # BCM 27
BUTTON_NEXT_RW = 15  # BCM 22

# MPD setup
def init_mpd_client(host='localhost', port=6600):
    client = MPDClient()
    client.timeout = 10
    client.connect(host, port)
    return client

# OLED setup
def init_oled():
    serial = i2c(port=1, address=0x3C)
    device = ssd1306(serial)
    return device

# Draw large text for track index
def draw_index(device, index):
    device.clear()
    width = device.width
    height = device.height
    image = Image.new('1', (width, height))
    draw = ImageDraw.Draw(image)
    # Use a large font; adjust path as needed
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 48)
    text = str(index)
    w, h = draw.textsize(text, font=font)
    draw.text(((width - w) // 2, (height - h) // 2), text, font=font, fill=255)
    device.display(image)

# Read current playlist and position
def get_current_index(client):
    status = client.status()
    if 'playlistid' in status and 'song' in status:
        return int(status['song']) + 1  # zero-based to one-based
    return 0

# Button callbacks def
def on_play_pause(channel):
    try:
        status = mpd.status()
        if status.get('state') == 'play':
            mpd.pause()
        else:
            mpd.play()
    except Exception as e:
        print('Error toggling play/pause:', e)
    update_display()


def on_prev_ff(channel):
    try:
        status = mpd.status()
        if status.get('state') == 'play':
            # rewind 15 seconds\ n            mpd.seekcur(max(0, int(status.get('elapsed', 0)) - 15))
        else:
            mpd.previous()
    except Exception as e:
        print('Error prev/ff:', e)
    update_display()


def on_next_rw(channel):
    try:
        status = mpd.status()
        if status.get('state') == 'play':
            # fast-forward 15 seconds
            mpd.seekcur(int(status.get('elapsed', 0)) + 15)
        else:
            mpd.next()
    except Exception as e:
        print('Error next/rw:', e)
    update_display()

# Refresh display
 def update_display():
    idx = get_current_index(mpd)
    draw_index(oled, idx)

# Main setup
def main():
    global mpd, oled
    mpd = init_mpd_client()
    oled = init_oled()

    GPIO.setmode(GPIO.BOARD)
    for pin in (BUTTON_PLAY, BUTTON_PREV_FF, BUTTON_NEXT_RW):
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    GPIO.add_event_detect(BUTTON_PLAY, GPIO.FALLING, callback=on_play_pause, bouncetime=200)
    GPIO.add_event_detect(BUTTON_PREV_FF, GPIO.FALLING, callback=on_prev_ff, bouncetime=200)
    GPIO.add_event_detect(BUTTON_NEXT_RW, GPIO.FALLING, callback=on_next_rw, bouncetime=200)

    # initial display
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
