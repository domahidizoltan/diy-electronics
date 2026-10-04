#!/usr/bin/env python3

import argparse
from pathlib import Path

from PIL import Image, ImageColor

import image_to_hex_config as config


def parse_hex_color(value):
    if (
        not isinstance(value, str)
        or len(value) != 7
        or value[0] != "#"
    ):
        raise ValueError("BACKGROUND_COLOR must use #RRGGBB format.")

    try:
        return ImageColor.getrgb(value)
    except ValueError:
        raise ValueError("Invalid BACKGROUND_COLOR: " + str(value))


def get_resample():
    name = str(config.RESAMPLE).upper()

    if name == "NEAREST":
        return Image.Resampling.NEAREST

    raise ValueError("Unsupported RESAMPLE value: " + str(config.RESAMPLE))


def get_dither():
    name = str(config.DITHER).upper()

    if name == "NONE":
        return Image.Dither.NONE

    raise ValueError("Unsupported DITHER value: " + str(config.DITHER))


def get_quantize_method():
    name = str(config.QUANTIZE_METHOD).upper()

    methods = {
        "MEDIANCUT": Image.Quantize.MEDIANCUT,
        "MAXCOVERAGE": Image.Quantize.MAXCOVERAGE,
        "FASTOCTREE": Image.Quantize.FASTOCTREE,
        "LIBIMAGEQUANT": Image.Quantize.LIBIMAGEQUANT,
    }

    if name not in methods:
        raise ValueError(
            "Unsupported QUANTIZE_METHOD value: " + str(config.QUANTIZE_METHOD)
        )

    return methods[name]


def load_image(path):
    with Image.open(path) as source:
        source.seek(0)
        image = source.convert("RGBA")

    background_rgb = parse_hex_color(config.BACKGROUND_COLOR)

    background = Image.new(
        "RGBA",
        image.size,
        background_rgb + (255,),
    )
    background.alpha_composite(image)

    return background.convert("RGB")


def resize_to_target(image):
    if image.width != image.height:
        raise ValueError(
            "Input image must be square. "
            + str(image.width)
            + "x"
            + str(image.height)
            + " is not square."
        )

    return image.resize(
        (config.TARGET_SIZE, config.TARGET_SIZE),
        get_resample(),
    )


def quantize_image(image):
    palette_size = int(config.PALETTE_SIZE)

    if not 2 <= palette_size <= 256:
        raise ValueError("PALETTE_SIZE must be between 2 and 256.")

    return image.quantize(
        colors=palette_size,
        method=get_quantize_method(),
        dither=get_dither(),
    )


def rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(
        rgb[0],
        rgb[1],
        rgb[2],
    )


def get_used_colors(indexed):
    palette = indexed.getpalette()
    pixels = list(indexed.getdata())
    used_indexes = sorted(set(pixels))

    colors = {}

    for index in used_indexes:
        offset = index * 3
        colors[index] = tuple(palette[offset:offset + 3])

    return colors


def write_sprite(path, indexed, colors):
    prefix = str(config.COLOR_VARIABLE_PREFIX)
    sprite_name = str(config.SPRITE_VARIABLE_NAME)

    index_to_name = {}

    with open(path, "w", encoding="utf-8", newline="\n") as file:
        for color_number, palette_index in enumerate(colors):
            name = "{}{:02d}".format(prefix, color_number)
            index_to_name[palette_index] = name

            file.write(
                '{} = "{}"\n'.format(
                    name,
                    rgb_to_hex(colors[palette_index]),
                )
            )

        file.write("\n")
        file.write(sprite_name + " = [\n")

        pixels = list(indexed.getdata())
        width, height = indexed.size

        for y in range(height):
            row = []

            for x in range(width):
                palette_index = pixels[y * width + x]
                row.append(index_to_name[palette_index])

            file.write(
                "    [" + ", ".join(row) + "],\n"
            )

        file.write("]\n")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Resize a square PNG or GIF to the configured size, "
            "reduce it to a fixed color palette, and create a sprite file."
        )
    )

    parser.add_argument(
        "image",
        nargs="?",
        help="Input PNG or GIF image. If omitted, INPUT_IMAGE is used.",
    )

    args = parser.parse_args()
    image_path = args.image or config.INPUT_IMAGE

    if not image_path:
        parser.error(
            "No input image specified. Pass an image path or set INPUT_IMAGE."
        )

    source_path = Path(image_path)

    if not source_path.exists():
        raise FileNotFoundError(
            "Input image not found: " + str(source_path)
        )

    if source_path.suffix.lower() not in (".png", ".gif"):
        raise ValueError("Only PNG and GIF input files are supported.")

    image = load_image(source_path)
    image = resize_to_target(image)
    indexed = quantize_image(image)

    output_dir = Path(config.OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_image = (
        output_dir
        / (source_path.stem + config.OUTPUT_IMAGE_SUFFIX)
    )

    output_sprite = (
        output_dir
        / (source_path.stem + config.OUTPUT_SPRITE_SUFFIX)
    )

    if config.SAVE_QUANTIZED_IMAGE:
        indexed.save(output_image)

    colors = get_used_colors(indexed)

    write_sprite(
        output_sprite,
        indexed,
        colors,
    )

    print("Input:", source_path)
    print("Output image:", output_image)
    print("Output sprite:", output_sprite)
    print(
        "Size:",
        config.TARGET_SIZE,
        "x",
        config.TARGET_SIZE,
    )
    print("Colors used:", len(colors))
    print("Palette limit:", config.PALETTE_SIZE)

    for color_number, palette_index in enumerate(colors):
        print(
            "{}{:02d} = {}".format(
                config.COLOR_VARIABLE_PREFIX,
                color_number,
                rgb_to_hex(colors[palette_index]),
            )
        )


if __name__ == "__main__":
    main()
