#!/usr/bin/env python3


import math
import json
import sys
import os

from copy import deepcopy

from typing import Literal

from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw

from pathlib import Path

resource_path = Path("resources")
outdir = Path("out")
parse_queue = []
ngenerated = 0


class Font:
    def __init__(self, path: Path, size: int = 10, antialias: bool = True):
        self.size = size
        if antialias:
            self.fontmode = "L"
        else:
            self.fontmode = "1"

        match path.suffix:
            case ".ttf" | ".otf":
                self.type = "ttf"
                fontf = path.open("rb")
                self.resolved = ImageFont.truetype(fontf, size)
                fontf.close()
            case ".pil":
                self.type = "pil"
                self.resolved = ImageFont.load(path)
            case ".tmf":
                self.type = "tmf"
                # todo impl
            case "_":
                raise ValueError("Not a supported font type!")

    def wraptext(self, text: str, maxwidth: int, canvas=None, break_on_any: bool = False) -> (str, int):
        textcut = text[:]
        textout = ""

        while len(textcut) > 0:
            textwidth = self.textsize(textcut, canvas)[0]
            if textwidth < maxwidth:
                textout += textcut
                break

            # binary search for the longest substring that can fit in the designated width
            startpos = 0
            endpos = len(textcut)
            last_below = 0
            for i in range(0, math.floor(math.log2(len(textcut)) + 1)):
                curpos = (len(textcut[startpos:endpos]) // 2) + startpos
                textwidth = self.textsize(textcut[:curpos], canvas)[0]

                if textwidth < maxwidth:
                    startpos = curpos + 1
                    last_below = curpos
                elif textwidth > maxwidth:
                    endpos = curpos - 1
                else:
                    last_below = curpos
                    break

            # break at the nearest space instead of the found position, if possible
            breakpos = textcut.rfind(" ", 0, last_below + 1)
            if breakpos == -1 or break_on_any:
                textout += textcut[:last_below] + "\n"
                textcut = textcut[last_below:]
            else:
                textout += textcut[:breakpos] + "\n"
                textcut = textcut[breakpos + 1:]

        return textout, textout.count("\n") + 1

    def textsize(self, text: str, canvas=None) -> tuple[int, int]:
        match self.type:
            case "ttf" | "pil":
                if canvas is None:
                    # dummy canvas
                    canvas = ImageDraw.Draw(Image.new("RGBA", (1000, 1000), (0, 0, 0, 0)))
                canvas.fontmode = self.fontmode
                bbox = canvas.multiline_textbbox((0, 0), text, self.resolved)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
            case "tmf":
                pass

    def rendertext(
            self,
            canvas: ImageDraw.ImageDraw,
            xy,
            text,
            fill=None,
            # font=None,
            anchor=None,
            spacing=4,
            align: Literal["left", "center", "right"] = "left",
            # direction=None,
            # features=None,
            # language=None,
            # stroke_width=0,
            # stroke_fill=None,
            # embedded_color=False
            ):
        canvas.fontmode = self.fontmode
        match self.type:
            case "ttf" | "pil":
                canvas.multiline_text(xy, text, fill, self.resolved, anchor, spacing, align)
            case "tmf":
                pass


def load_json(path: Path):
    jfile = path.open()
    result = json.load(jfile)
    jfile.close()
    return result


def paste_alpha(base: Image.Image, overlay: Image.Image, offset: tuple = (0, 0)) -> Image.Image:
    padded_overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    padded_overlay.paste(overlay, offset)
    return Image.alpha_composite(base, padded_overlay)


# PIL.Image.Resampling exists but pycharm does not believe that
# noinspection PyUnresolvedReferences
def get_filter(imgfilter: str, default: int = Image.Resampling.NEAREST):
    match imgfilter.lower():
        case "bilinear":
            return Image.Resampling.BILINEAR
        case "bicubic":
            return Image.Resampling.BICUBIC
        case "box":
            return Image.Resampling.BOX
        case "lanczos":
            return Image.Resampling.LANCZOS
        case "hamming":
            return Image.Resampling.HAMMING
        case "nearest":
            return Image.Resampling.NEAREST
        case _:
            return default


def find_nth(haystack, needle, n):
    start = haystack.find(needle)
    while start >= 0 and n > 1:
        start = haystack.find(needle, start+len(needle))
        n -= 1
    return start


def merge_dicts(a: dict, b: dict) -> dict:
    result = {}

    for key in a:
        if key in b:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                result[key] = merge_dicts(a[key], b[key])
            else:
                result[key] = deepcopy(b[key])
        else:
            result[key] = deepcopy(a[key])

    for key in b:
        if key not in a:
            result[key] = deepcopy(b[key])

    return result


def create_expand(base_imagepath: Path, image_data: dict) -> Image.Image:
    base_image = Image.open(base_imagepath)
    # target width and height
    w, h = image_data["size"]
    # division lines on base image
    dx1, dx2, dy1, dy2 = image_data["divide"]
    # max x and y for base image
    mx, my = base_image.size
    # right section width, bottom section height
    rsw, bsh = mx - dx2, my - dy2
    # transformed right/bottom division line locations for target
    dtx, dty = w - rsw, h - bsh
    # size values for scalable regions
    xs, ys = (dtx - dx1), (dty - dy1)

    # [x1 [y1 x2) y2)
    section_bounds = {
        "tl": (0,   0,   dx1, dy1),
        "tm": (dx1, 0,   dx2, dy1),
        "tr": (dx2, 0,   mx,  dy1),
        "ml": (0,   dy1, dx1, dy2),
        "mm": (dx1, dy1, dx2, dy2),
        "mr": (dx2, dy1, mx,  dy2),
        "bl": (0,   dy2, dx1, my),
        "bm": (dx1, dy2, dx2, my),
        "br": (dx2, dy2, mx,  my)
    }
    # x y
    section_locations = {
        "tl": (0,   0),
        "tm": (dx1, 0),
        "tr": (dtx, 0),
        "ml": (0,   dy1),
        "mm": (dx1, dy1),
        "mr": (dtx, dy1),
        "bl": (0,   dty),
        "bm": (dx1, dty),
        "br": (dtx, dty)
    }
    # w h
    section_sizes = {
        "tl": (dx1, dy1),
        "tm": (xs,  dy1),
        "tr": (rsw, dy1),
        "ml": (dx1, ys),
        "mm": (xs,  ys),
        "mr": (rsw, ys),
        "bl": (dx1, bsh),
        "bm": (xs,  bsh),
        "br": (rsw, bsh)
    }

    output = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for section in section_locations:
        output.paste(base_image.resize(section_sizes[section], Image.NEAREST, section_bounds[section]),
                     section_locations[section])

    return output


def get_styles() -> list[str]:
    return load_json(resource_path / "styles.json")


def eval_predicate(predicate: str, predicate_data: dict) -> bool:
    if predicate == "default":
        return True

    for ppart_or in predicate.split("|"):
        presult = True
        for ppart in ppart_or.split("&"):
            ptype, _, pval = ppart.partition(":")
            match ptype:
                case "exists" | "flag":
                    if ptype not in predicate_data or pval not in predicate_data[ptype]:
                        presult = False
                case "lines":
                    if ptype in predicate_data:
                        tname, _, val = pval.partition(">")
                        if tname not in predicate_data[ptype] or not predicate_data[ptype][tname] > val:
                            presult = False
                    else:
                        presult = False
        if presult:
            return True
    return False


def merge_data(style_data: dict, predicate_data: dict) -> dict:
    result = {}

    for predicate in style_data["predicates"].keys():
        if eval_predicate(predicate, predicate_data):
            result = merge_dicts(result, style_data["predicates"][predicate])

    return result


def parse_input(rinput):
    global parse_queue, ngenerated

    iargs = rinput[:] if isinstance(rinput, list) else rinput.split(" ")
    parse_queue = [iargs]
    ngenerated = 0

    if (outdir / "textbox.png").exists():
        os.remove(outdir / "textbox.png")
    for image in (outdir / "parts").glob("textbox*.png"):
        os.remove(image)

    while len(parse_queue) > 0:

        # parse input
        args = parse_queue[0][:]
        style = args[0]
        del args[0]
        if style not in get_styles():
            raise ValueError(style + " is not a recognized style!")
        style_path = resource_path / style
        style_data = load_json(style_path / "style.json")
        key_mappings = load_json(style_path / "map.json")
        predicate_data = {
            "flag": [],
            "exists": []
            # "lines" will be added later
        }
        keys = {}
        text = {}

        def parse_key(name: str, val: str):
            if name in key_mappings:
                if val in key_mappings[name]:
                    keys[name] = key_mappings[name][val]
                else:
                    raise ValueError("value " + val + " does not exist in mapping table for key " + name)
            else:
                keys[name] = val

        while args[0].startswith("f:"):
            predicate_data["flag"].append(args[0][2:])
            del args[0]

        for syntaxpart in style_data["syntax"].split():
            stype, _, sval = syntaxpart.partition(":")
            match stype:
                case "key":
                    if args[0] != "!NONE!":
                        predicate_data["exists"].append("key:" + sval)
                        parse_key(sval, args[0])
                    del args[0]
                case "text":
                    if args[0] != "!NONE!":
                        predicate_data["exists"].append("text:" + sval)
                        text[sval] = args[0]
                    del args[0]
                case "rtext":
                    if "!REPEAT!" not in args:
                        predicate_data["exists"].append("text:" + sval)
                        text[sval] = " ".join(args)
                        args = []
                    else:
                        repeat_at = args.index("!REPEAT!")
                        predicate_data["exists"].append("text:" + sval)
                        text[sval] = " ".join(args[:repeat_at])
                        args = args[repeat_at + 1:]

        # repeat parsing later if there are leftovers
        if len(args) > 0:
            args.insert(0, style)
            parse_queue.append(args)

        # key-based overrides
        # TODO decide on syntax in data files for this

        # resolve fonts
        data = merge_data(style_data, predicate_data)
        fonts = {}

        for font in data["fonts"].keys():
            fonts[font] = Font(style_path / data["fonts"][font]["path"],
                               data["fonts"][font]["size"],
                               data["fonts"][font]["aa"])

        # preload textbox data
        textboxes = {}
        repeater = None
        torepeat = {}
        predicate_data["lines"] = {}

        for textbox in data["textboxes"].keys():
            textboxes[textbox] = {}
            tbfont = fonts[data["textboxes"][textbox]["font"]]
            textboxes[textbox]["font"] = tbfont

            tbsize = data["textboxes"][textbox]["size"]
            wrapped_text, nlines = tbfont.wraptext(text[data["textboxes"][textbox]["text"]], tbsize[0])
            if nlines > tbsize[1]:
                if "overflow" in data["textboxes"][textbox] and data["textboxes"][textbox]["overflow"] == "repeat":
                    # i literally just wrote this code and it needs a whole ass rework already
                    if repeater is not None:
                        raise ValueError("duplicate repeating textboxes: " + repeater + ", " + textbox)
                    repeater = textbox
                    torepeat["text"] = []
                    torepeat["size"] = []
                    start = 0

                    while start >= 0:
                        end = find_nth(wrapped_text, "\n", tbsize[1] * (len(torepeat["text"]) + 1))
                        if end < 0:
                            break
                        torepeat["text"].append(wrapped_text[start:end])
                        torepeat["size"].append(tbfont.textsize(wrapped_text[start:end]))
                        start = find_nth(wrapped_text, "\n", tbsize[1] * (len(torepeat["text"]))) + 1
                    torepeat["text"].append(wrapped_text[start:])
                    torepeat["size"].append(tbfont.textsize(wrapped_text[start:]))

                    textboxes[textbox]["text"] = torepeat["text"][0]
                    textboxes[textbox]["size"] = torepeat["size"][0]
                    del torepeat["text"][0]
                    del torepeat["size"][0]

                else:
                    bpoint = find_nth(wrapped_text, "\n", tbsize[1])
                    textboxes[textbox]["text"] = wrapped_text[:bpoint]
                    textboxes[textbox]["size"] = tbfont.textsize(wrapped_text[:bpoint])
                predicate_data["lines"][textbox] = tbsize[1]

            else:
                textboxes[textbox]["text"] = wrapped_text
                textboxes[textbox]["size"] = tbfont.textsize(wrapped_text)
                predicate_data["lines"][textbox] = nlines

            textboxes[textbox]["pos"] = data["textboxes"][textbox]["pos"]

        while repeater is None or len(torepeat["text"]) > 0:
            print(predicate_data)
            data = merge_data(style_data, predicate_data)

            # resolve images
            images = {}

            for image in data["images"].keys():
                if "textbox" in data["images"][image]:
                    # TODO expand
                    pass
                elif "key" in data["images"][image]:
                    images[image] = Image.open(style_path / keys[data["images"][image]["key"]])
                else:
                    images[image] = Image.open(style_path / data["images"][image]["path"])

            # paste everything together
            composite = None
            if "basesize" in data["images"]:
                composite = Image.new("RGBA", data["images"]["basesize"], (0, 0, 0, 0))
            for image in images:
                if composite is None:
                    composite = images[image].copy()
                    continue
                composite = paste_alpha(composite, images[image], data["images"][image]["pos"])

            canvas = ImageDraw.Draw(composite)
            for textbox in textboxes:
                text = textboxes[textbox]["text"]

                fill = tuple(data["textboxes"][textbox]["color"]) if "color" in data["textboxes"][textbox] else None
                anchor = data["textboxes"][textbox]["anchor"] if "anchor" in data["textboxes"][textbox] else None
                spacing = data["textboxes"][textbox]["spacing"] if "spacing" in data["textboxes"][textbox] else 4
                align = data["textboxes"][textbox]["align"] if "align" in data["textboxes"][textbox] else "left"

                textboxes[textbox]["font"].rendertext(canvas,
                                                      data["textboxes"][textbox]["pos"],
                                                      text,
                                                      fill,
                                                      anchor,
                                                      spacing,
                                                      align)

            composite.save(outdir / "parts" / ("textbox" + str(ngenerated) + ".png"))
            ngenerated += 1

            if repeater is None:
                break

            # repeat if necessary
            textboxes[repeater]["text"] = torepeat["text"][0]
            textboxes[repeater]["size"] = torepeat["size"][0]
            del torepeat["text"][0]
            del torepeat["size"][0]
            predicate_data["lines"][repeater] = textboxes[repeater]["text"].count("\n") + 1

            if len(torepeat["text"]) <= 0:
                repeater = None

        del parse_queue[0]

    # paste all generated images together
    genimgs = list((outdir / "parts").glob("textbox*.png"))
    genimgs.sort(key=lambda fname: int(fname.name.strip("textbox").rstrip(".png")))
    totalh = 0
    maxw = 0
    images = []
    for image in genimgs:
        imgd = Image.open(image)
        totalh += imgd.height
        if maxw < imgd.width:
            maxw = imgd.width
        images.append(imgd)
    composite = Image.new("RGBA", (maxw, totalh), (0, 0, 0, 0))
    currenth = 0
    for image in images:
        composite.paste(image, (0, currenth))
        currenth += image.height
    composite.save(outdir / "textbox.png")


if __name__ == "__main__":
    parse_input(sys.argv[1:])
