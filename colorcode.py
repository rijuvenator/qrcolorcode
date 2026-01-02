from __future__ import annotations
import math
import itertools as it
import xml.etree.ElementTree as ET
import json
from typing import Sequence
from dataclasses import dataclass
import svg
import logging
import qrcode

# define logger
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s]: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)


class Color:
    def __init__(self, value=0xFFFFFF):
        self.value = value

    def __repr__(self):
        return f"Color(0x{self.value:06X})"

    # allows hex(), bin(), int(), etc.
    def __index__(self):
        return self.value

    def svghex(self):
        return f"#{self.value:06X}"

    # "inverts" the color by XOR'ing with 0xFEFEFE
    # ensures that negation of a x2'd color never touches the LSB
    # so that LSB addCode can be done independently, i.e. doesn't need to be added to a block code if present
    def __neg__(self):
        return Color(self.value ^ 0xFEFEFE)

    # this is used:
    # to implement LSB steganography by "adding" a color like 0x010001 = 1, 0, 1 to an existing color
    # which will not work at all unless the 2* method to shift 7 bits left is used; and
    # to similarly add colors to dark modules in QR code grids, which start out as black
    def __add__(self, other):
        if other is None:
            return self
        return Color(self.value + other.value)

    __radd__ = __add__

    # create a color from an RGB sequence of integers; not enforcing 0-255 but don't abuse it
    # a color like (255, 0, 255) -> 255 * 16^4 + 0 * 16^2 + 255 * 16^0, note that 16 is 0x10
    # since this class stores a color as a number only, that's all that's required
    @classmethod
    def fromRGB(cls, RGB: Sequence[int]):
        powers = [4, 2, 0]
        value = sum([channel * 0x10**power for channel, power in zip(RGB, powers)])
        return cls(value)


@dataclass
class Coord:
    i: int
    j: int

    def __add__(self, other):
        return Coord(self.i + other.i, self.j + other.j)

    __radd__ = __add__


class ColorGrid:
    def __init__(self, nRows, nCols):
        self.nRows = nRows
        self.nCols = nCols
        self.data: list[list[Color]] = []

        for i in range(self.nRows):
            self.data.append([])
            for j in range(self.nCols):
                self.data[-1].append(None)

    def area(self) -> int:
        return self.nRows * self.nCols

    def coordFromIdx(self, idx: int) -> Coord:
        return Coord(idx // self.nCols, idx % self.nCols)

    def hasColor(self, coord: Coord) -> bool:
        return self.data[coord.i][coord.j] is not None

    def fill(self, coord: Coord, color: Color) -> None:
        self.data[coord.i][coord.j] = color

    def __iter__(self):
        return iter(it.chain(*self.data))


class Canvas:
    QUIET = 0
    # def __init__(self, width=500, height=500):

    def __init__(self, gridContainer, moduleSize=10):
        self.moduleSize = moduleSize
        self.gridContainer = gridContainer

        # if it's a QR code, it should always be False
        # if it's a block code, it should always be True
        # if it's a steg code, it probably doesn't matter, but
        # it's technically possibly to ADD a block code to steg code (why!)
        # and in that case you might write out a steg code that has light colors
        # just... don't do that lol
        self.lightColoredBlocks = isinstance(gridContainer, BlockCode)

        QUIET = Canvas.QUIET
        self.width = (self.gridContainer.grid.nCols + 2 * QUIET) * self.moduleSize
        self.height = (self.gridContainer.grid.nRows + 2 * QUIET) * self.moduleSize

    def boundingBox(self) -> svg.Rect:
        return svg.Rect(
            x=0,
            y=0,
            width=self.width,
            height=self.height,
            stroke="black",
            fill_opacity=0,
        )

    def getElements(self):
        i0 = Canvas.QUIET
        j0 = i0

        elements = []
        for i, row in enumerate(self.gridContainer.grid.data):
            for j, color in enumerate(row):
                if color is None:
                    continue
                elements.append(
                    svg.Rect(
                        x=(j0 + j) * self.moduleSize,
                        y=(i0 + i) * self.moduleSize,
                        width=self.moduleSize,
                        height=self.moduleSize,
                        fill=color.svghex(),
                        extra={"desc": "light" if self.lightColoredBlocks else "dark"},
                    )
                )

        return elements

    def render(self, elements=None, bounding_box=False, fname="test.svg"):
        if elements is None:
            elements = self.getElements()
        elements = list(elements)

        if bounding_box:
            elements.append(self.boundingBox())

        canvas = svg.SVG(width=self.width, height=self.height, elements=elements)
        self.writeCanvas(canvas, fname=fname)

    def writeCanvas(self, canvas, fname="test.svg"):
        with open(fname, "w") as f:
            f.write(str(canvas))
            logging.info(f"{fname} written")


# some shared code, related to adding different codes together
# the addCode function is a little overcomplicated in pursuit of generalization, but it works
# whether or not to negate a color is dependent on whether it's a "dark" or "light" block code that was XOR'd for scan reasons
# whether or not to skip Nones also depends on whether we are iterating over a QR code or blocks
# if blocks, it's desirable to be able to add to None if necessary; if QR, we don't want to mess with the Nones
# the big single decode function is here, which will read in the SVG Rects and decode the colors
# a method for reading in a json file and automating the whole process is also here
class GridCode:

    @staticmethod
    def transformBlockColor(color):
        return -color

    @staticmethod
    def transformStegColor(color):
        return color

    @staticmethod
    def ensurePrintableASCII(message):
        for char in message:
            if not (32 <= ord(char) <= 126):
                raise ValueError(
                    "Message must contain standard printable ASCII characters only"
                )

    def addCode(self, code):
        if isinstance(code, BlockCode):
            msgMax = self.blockMax()
            transformFunc = self.transformBlockColor
        elif isinstance(code, StegCode):
            msgMax = self.stegMax()
            transformFunc = self.transformStegColor
        if len(code.message) > msgMax:
            logging.warning(
                f"Message is too long; currently {len(code.message)}, max length is {msgMax}; skipping"
            )
            return
        logging.info(
            f"{code.__class__.__name__}: Message max: {msgMax}, currently {len(code.message)}"
        )
        self.code = code
        colors = iter(code.grid)
        for i, row in enumerate(self.grid.data):
            for j, color in enumerate(row):
                if self.skipNones(color):
                    continue
                try:
                    nextColor = next(colors)
                    if nextColor is not None:
                        self.grid.data[i][j] += transformFunc(nextColor)
                    else:
                        return
                except StopIteration:
                    return

    @staticmethod
    def decode(filename, lightColoredBlocks=None):
        # svg is just XML, and these files are simple; just a bunch of Rect within root
        # so get the tree root and every child is a Rect, with its color as an attribute
        tree = ET.parse(filename)

        # Unfortunately, it doesn't seem easily possible to "detect" specifically
        # if it's a block code GRID, for which x2 without XOR = lighter colors are preferred
        # or if it's a block code as part of a QR code, for which x2 XOR = darker colored are required
        # So, as a normal part of writing out the SVG, I include desc='light' or desc='dark' in appropriate contexts
        # If reading in the SVG with no data loss, the parameter is not required and it will detect what to do
        # That is, desc='light' will NOT negate/XOR, and desc='dark' will do so
        # However you might wish to override it for some reason, and also see exactly what's happening, so
        # for posterity I keep the lightColoredBlocks flag here, and tell you what it means
        # so lightColoredBlocks=True specifically says: do not undo the XOR that was never applied
        # So I have to take it as a parameter. There might be some other way of doing this in the future
        # Currently, this means:
        # - QR               :
        # - QR + Block       :
        # - QR + Block + Steg:
        # - QR         + Steg:
        # -      Block       : lightColoredBlocks=True
        # -      Block + Steg: lightColoredBlocks=True
        # -              Steg:

        # Decode the block message
        channels = []
        chars = []
        for child in tree.getroot():
            # child.attrib['fill'] is the #ABCDEF hex color code in the svg Rects, strip off the #
            # takes #ABCDEF -> XOR with #FEFEFE -> converts to hex -> strips 0x
            color = Color(int(child.attrib["fill"][1:], 16))
            if lightColoredBlocks is not None:
                if not lightColoredBlocks:
                    color = GridCode.transformBlockColor(color)
            elif "desc" in child.attrib:
                rectDesc = child.attrib["desc"]
                if rectDesc == "dark":
                    color = GridCode.transformBlockColor(color)
            colorHex = hex(color)[2:].rjust(6, "0")

            # split into channels (2 digits at a time) and convert to characters
            # this following piece of logic isn't being used right now as it doesn't seem necessary
            # skip 0x00 and 0xFF if found since they are non-printing padding/null
            # also skip 0x01 and 0xFE because if this is steganography-only, there will ONLY be such channels
            # and we can re-do this process without negation and without skipping
            for hexSlice in it.batched(colorHex, 2):
                channel = int("".join(hexSlice), 16)
                # if channel in (0xFF, 0x00, 0x01, 0xFE): continue
                channels.append(channel)
                chars.append(BlockCode.channelToChar(channel))

        logging.info("Block message:\n\n" + "".join(chars) + "\n")

        # Decode the steganography message
        # get all the LSBs; this is just & 1 for each channel
        # if we ever run out of bits, or hit all 0's, or all 1's, we can break or skip
        stegBits = [_ & 1 for _ in channels]
        chars = []
        for bitSlice in it.batched(stegBits, StegCode.ASCIILEN):
            if len(bitSlice) != StegCode.ASCIILEN:
                break
            bits = "".join([str(_) for _ in bitSlice])
            if int(bits, 2) == 0 or int(bits, 2) == 2**7 - 1:
                break
            chars.append(chr(int(bits, 2)))

        logging.info("Steganography message:\n\n" + "".join(chars) + "\n")

    @staticmethod
    def fromJSON(filename):
        with open(filename) as f:
            data = json.load(f)
        sc = None
        if "steg" in data:
            sc = StegCode(data["steg"])
        bc = None
        if "block" in data:
            bc = BlockCode(data["block"])
        qc = None
        if "qr" in data:
            qc = QRCode(data["qr"])

        if qc is not None:
            if bc is not None:
                qc.addCode(bc)
            if sc is not None:
                qc.addCode(sc)
            gc = qc
        elif bc is not None:
            if sc is not None:
                bc.addCode(sc)
            gc = bc
        elif sc is not None:
            gc = sc

        if gc is None:
            raise ValueError(
                "Input JSON must have 1-3 of the ASCII message fields: qr, block, steg"
            )

        return gc


class StegCode(GridCode):
    ASCIILEN = 7
    NULL = 0

    def __init__(
        self,
        message: str,
        nRows: int = None,
        nCols: int = None,
    ):
        super().__init__()
        GridCode.ensurePrintableASCII(message)
        self.message = message
        self.grid = ColorGrid(
            *BlockCode.computeDimensions(self.nBlocks(), nRows, nCols)
        )
        self.fillColors()

    def nBlocks(self) -> int:
        return math.ceil(len(self.message) * StegCode.ASCIILEN / BlockCode.RGBLEN)

    def fillColors(self):
        # make a list of bits; there should be ASCIILEN * len(message) such bits
        # str(bin(ord()))[2:] gives the binary string of a character with 0b stripped off
        # rjust ensures there are ASCIILEN bits, 0 padded; convert them to ints for later
        bits = []
        for char in self.message:
            bits.extend(
                [
                    int(bit)
                    for bit in str(bin(ord(char)))[2:].rjust(StegCode.ASCIILEN, "0")
                ]
            )

        # make a linear array of "colors"
        # step through the steg bits RGBLEN at a time and slice; pad with 0 to get exactly RGBLEN
        # the slice is already a sequence of ints; instantiate color; append
        colorArray = []
        for bitSlice in it.batched(bits, BlockCode.RGBLEN):
            bitSlice = list(bitSlice)
            while len(bitSlice) < BlockCode.RGBLEN:
                bitSlice.append(StegCode.NULL)

            color = Color.fromRGB(bitSlice)
            colorArray.append(color)

        for idx, color in enumerate(colorArray):
            self.grid.fill(self.grid.coordFromIdx(idx), color)


class BlockCode(GridCode):
    RGBLEN = 3
    NULL = chr(0)

    def skipNones(self, color):
        return False

    # encapsulate the conversion from a character to a channel
    # in this case, it is simple: 2 * the ascii value of the character
    @staticmethod
    def charToChannel(char):
        return 2 * ord(char)

    # encapsulate the conversion from a channel to a character, inverting
    @staticmethod
    def channelToChar(channel):
        return chr(channel // 2)

    def __init__(
        self,
        message: str,
        nRows: int = None,
        nCols: int = None,
    ):
        super().__init__()
        GridCode.ensurePrintableASCII(message)
        self.message = message
        self.grid = ColorGrid(
            *BlockCode.computeDimensions(self.nBlocks(), nRows, nCols)
        )
        self.fillColors()

    def nBlocks(self) -> int:
        return math.ceil(len(self.message) / BlockCode.RGBLEN)

    def stegMax(self) -> int:
        return self.grid.area() * BlockCode.RGBLEN // StegCode.ASCIILEN

    # compute dimensions
    # with no constraints, make the dimensions square
    # otherwise, prioritize nCols over nRows
    @staticmethod
    def computeDimensions(nBlocks: int, nRows: int, nCols: int) -> tuple[int]:

        # neither nCols nor nRows was specified
        # so define dimensions to be as square as possible
        # do this by rounding down the sqrt of the number of blocks
        # if the resulting square doesn't have enough blocks, add a row
        # if the resulting square+1 row doesn't have enough blocks, add a column
        # it cannot possibly need to be any bigger
        if nRows is None and nCols is None:
            sqrt = int(math.sqrt(nBlocks))
            nRows = sqrt
            nCols = sqrt
            # if this isn't the right size, add a row
            if nRows * nCols < nBlocks:
                nRows += 1
            # if this isn't the right size, add a column
            if nRows * nCols < nBlocks:
                nCols += 1

        # nCols was specified, nRows was not
        elif nRows is None and nCols is not None:
            nRows = math.ceil(nBlocks / nCols)

        # nRows was specified, nCols was not
        elif nRows is not None and nCols is None:
            nCols = math.ceil(nBlocks / nRows)

        # both were specified; raise an error if there's not enough
        else:
            nRows = nRows
            nCols = nCols
            if nRows * nCols < nBlocks:
                raise ValueError(
                    f"{nRows} x {nCols} is insufficient; specify nCols or nRows only or neither"
                )

        return nRows, nCols

    def fillColors(self):
        # make colors for the block message
        # make a linear array of colors
        # step through the block message RGBLEN at a time and slice; pad with NULL to get exactly RGBLEN
        # convert each character to channel (probably ord * 2); instantiate color; append
        colorArray = []
        for messageSlice in it.batched(self.message, BlockCode.RGBLEN):
            messageSlice = list(messageSlice)
            while len(messageSlice) < BlockCode.RGBLEN:
                messageSlice += BlockCode.NULL

            RGB = [BlockCode.charToChannel(char) for char in messageSlice]
            color = Color.fromRGB(RGB)
            colorArray.append(color)

        for idx, color in enumerate(colorArray):
            self.grid.fill(self.grid.coordFromIdx(idx), color)


class QRCode(GridCode):
    def __init__(self, message: str):
        super().__init__()
        GridCode.ensurePrintableASCII(message)
        self.message = message

        self.qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L)
        self.qr.add_data(self.message)
        self.qr.make(fit=True)

        self.grid = ColorGrid(self.qr.modules_count, self.qr.modules_count)

        self.fillColors()

    def skipNones(self, color):
        return color is None

    def blockMax(self):
        nFilled = sum([_ is not None for _ in self.grid])
        return nFilled * BlockCode.RGBLEN

    def stegMax(self) -> int:
        nFilled = sum([_ is not None for _ in self.grid])
        return nFilled * BlockCode.RGBLEN // StegCode.ASCIILEN

    def fillColors(self):
        for i, row in enumerate(self.qr.modules):
            for j, filled in enumerate(row):
                if filled:
                    self.grid.fill(Coord(i, j), Color(0))


if __name__ == "__main__":

    def testCode(steg=True, block=True, qr=True):

        # print an identifying title
        titles = []
        if qr:
            titles.append("QR")
        if block:
            titles.append("Block")
        if steg:
            titles.append("Steg")
        if len(titles) == 0:
            return
        logging.info("\033[1m" + " + ".join(titles) + "\033[m")

        with open("json/lorem.json") as f:
            data = json.load(f)

        sc = StegCode(data["steg"]) if steg else None
        bc = BlockCode(data["block"]) if block else None
        qc = QRCode(data["qr"]) if qr else None

        # same logic as in fromJSON
        if qc is not None:
            if bc is not None:
                qc.addCode(bc)
            if sc is not None:
                qc.addCode(sc)
            gc = qc
        elif bc is not None:
            if sc is not None:
                bc.addCode(sc)
            gc = bc
        elif sc is not None:
            gc = sc

        Canvas(gc).render()
        GridCode.decode("test.svg")
        return gc

    for qr in (True, False):
        for block in (True, False):
            for steg in (True, False):
                testCode(steg, block, qr)
