# delegate functions for working with multiple font formats
# including a custom one... yay
# ttf, pil, tmf

import math

from typing import Literal

from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw

from pathlib import Path


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
                return canvas.multiline_textsize(text, self.resolved)
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
