from machine import Pin
import os
import neopixel
import time
import random

from config import (
    LED_PIN,
    MOTION_PIN,
    BUTTON_PIN,
    WIDTH,
    HEIGHT,
    NUM_LEDS,
    SERPENTINE,
    FLIP_X,
    FLIP_Y,
    FADE_IN_MS,
    FADE_OUT_MS,
    OFF_DELAY_MS,
    LOOP_DELAY_MS,
    FADE_STEP_MS,
    BUTTON_DEBOUNCE_MS,
    BRIGHTNESS_LEVELS,
    MAX_LED_BRIGHTNESS,
    CAL_R,
    CAL_G,
    CAL_B,
    SPRITE_PREFIX_LENGTH,
    SPRITE_DIRECTORY,
    PRINT_LOADED_SPRITES,
)

brightness_index = 0


def clamp8(value):
    if value < 0:
        return 0
    if value > 255:
        return 255
    return int(value)


def parse_color(value, filename):
    if (
        not isinstance(value, str)
        or len(value) != 7
        or value[0] != "#"
    ):
        raise ValueError(
            "Invalid color in " + filename + ": " + str(value)
        )

    try:
        return (
            int(value[1:3], 16),
            int(value[3:5], 16),
            int(value[5:7], 16),
        )
    except ValueError:
        raise ValueError(
            "Invalid HEX color in " + filename + ": " + str(value)
        )


def load_sprites():
    sprites = []
    filenames = []

    path = SPRITE_DIRECTORY
    entries = os.listdir(path) if path else os.listdir()

    for filename in entries:
        if (
            len(filename) >= SPRITE_PREFIX_LENGTH + 5
            and filename[:SPRITE_PREFIX_LENGTH].isdigit()
            and filename[SPRITE_PREFIX_LENGTH] == "_"
            and filename.endswith(".py")
            and filename not in (
                "main.py",
                "config.py",
                "boot.py",
                "main.pyc",
                "config.pyc",
            )
        ):
            filenames.append(filename)

    filenames.sort()

    for filename in filenames:
        namespace = {}
        full_path = (
            path + "/" + filename
            if path
            else filename
        )

        with open(full_path, "r") as file:
            source = file.read()

        exec(source, namespace)

        if "SPRITE" not in namespace:
            raise ValueError(
                "Missing SPRITE variable in " + filename
            )

        sprite_data = namespace["SPRITE"]

        if not sprite_data:
            raise ValueError(
                "Empty SPRITE in " + filename
            )

        sprite = []

        for row in sprite_data:
            rgb_row = []

            for color in row:
                rgb_row.append(parse_color(color, filename))

            sprite.append(rgb_row)

        height = len(sprite)
        width = len(sprite[0])

        if width != WIDTH or height != HEIGHT:
            raise ValueError(
                "Sprite size must be "
                + str(WIDTH)
                + "x"
                + str(HEIGHT)
                + ": "
                + filename
            )

        for row in sprite:
            if len(row) != width:
                raise ValueError(
                    "Sprite is not rectangular: " + filename
                )

        sprites.append((filename, sprite))

    if not sprites:
        raise RuntimeError("No sprite files found.")

    if PRINT_LOADED_SPRITES:
        print("Loaded sprites:")
        for filename, sprite in sprites:
            print(
                "  ",
                filename,
                len(sprite[0]),
                "x",
                len(sprite),
            )

    return sprites


SPRITES = load_sprites()

np = neopixel.NeoPixel(
    Pin(LED_PIN, Pin.OUT),
    NUM_LEDS,
)

motion_pin = Pin(MOTION_PIN, Pin.IN)
button = Pin(BUTTON_PIN, Pin.IN)


def scale_color(rgb, brightness):
    r, g, b = rgb

    r = r * CAL_R
    g = g * CAL_G
    b = b * CAL_B

    level = brightness * MAX_LED_BRIGHTNESS

    return (
        clamp8(r * level),
        clamp8(g * level),
        clamp8(b * level),
    )


def xy_to_index(x, y):
    if FLIP_X:
        x = WIDTH - 1 - x

    if FLIP_Y:
        y = HEIGHT - 1 - y

    if SERPENTINE and (y % 2 == 1):
        x = WIDTH - 1 - x

    return y * WIDTH + x


def show_matrix(sprite, brightness):
    for y in range(HEIGHT):
        for x in range(WIDTH):
            np[xy_to_index(x, y)] = scale_color(
                sprite[y][x],
                brightness,
            )

    np.write()


def clear():
    for index in range(NUM_LEDS):
        np[index] = (0, 0, 0)

    np.write()

sprite_idx = -1
sprites_len = -1
def choose_next_sprite():
    # return random.choice(SPRITES) # fully random

    # first image is random, then sequential
    global sprite_idx
    global sprites_len
    if sprite_idx == -1:
        sprites_len = len(SPRITES)
        sprite_idx = random.randrange(sprites_len)
    else:
        sprite_idx = (sprite_idx+1)%sprites_len

    return SPRITES[sprite_idx]

last_button_state = button.value()
last_button_time = time.ticks_ms()


def handle_button():
    global brightness_index
    global last_button_state
    global last_button_time

    state = button.value()
    now = time.ticks_ms()
    pressed = False

    if last_button_state == 1 and state == 0:
        if time.ticks_diff(
            now,
            last_button_time,
        ) >= BUTTON_DEBOUNCE_MS:
            brightness_index = (
                brightness_index + 1
            ) % len(BRIGHTNESS_LEVELS)

            last_button_time = now
            pressed = True

    last_button_state = state
    return pressed


def fade_in(sprite):
    start = time.ticks_ms()

    while True:
        handle_button()

        elapsed = time.ticks_diff(
            time.ticks_ms(),
            start,
        )

        if elapsed >= FADE_IN_MS:
            show_matrix(
                sprite,
                BRIGHTNESS_LEVELS[brightness_index],
            )
            return

        fraction = elapsed / FADE_IN_MS
        level = (
            BRIGHTNESS_LEVELS[brightness_index]
            * fraction
        )

        show_matrix(sprite, level)
        time.sleep_ms(FADE_STEP_MS)


def fade_out(sprite):
    start_level = BRIGHTNESS_LEVELS[brightness_index]
    start = time.ticks_ms()

    while True:
        if motion_pin.value():
            return False

        handle_button()

        elapsed = time.ticks_diff(
            time.ticks_ms(),
            start,
        )

        if elapsed >= FADE_OUT_MS:
            clear()
            return True

        fraction = elapsed / FADE_OUT_MS
        level = start_level * (1.0 - fraction)

        show_matrix(sprite, level)
        time.sleep_ms(FADE_STEP_MS)


clear()

current_sprite_name = None
current_sprite = None
lamp_on = False
no_motion_since = None


while True:
    if handle_button():
        if lamp_on and current_sprite is not None:
            show_matrix(
                current_sprite,
                BRIGHTNESS_LEVELS[brightness_index],
            )

    motion = motion_pin.value() == 1

    if motion and not lamp_on:
        current_sprite_name, current_sprite = (
            choose_next_sprite()
        )
        print("showing sprite ", current_sprite_name)

        fade_in(current_sprite)

        lamp_on = True
        no_motion_since = None

    if motion and lamp_on:
        no_motion_since = None

    if lamp_on and not motion:
        if no_motion_since is None:
            no_motion_since = time.ticks_ms()

        if time.ticks_diff(
            time.ticks_ms(),
            no_motion_since,
        ) >= OFF_DELAY_MS:
            turned_off = fade_out(current_sprite)

            if turned_off:
                lamp_on = False
                no_motion_since = None
                current_sprite_name = None
                current_sprite = None
            else:
                lamp_on = True
                no_motion_since = None

    time.sleep_ms(LOOP_DELAY_MS)
