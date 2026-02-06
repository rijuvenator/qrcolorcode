import os
from colorcode import StegCode, BlockCode, QRCode, Canvas, logger
import fpdf

# :::::::::: CONFIGURATION SECTION ::::::::::
# This section defines some constants for configuring the rest of the script.

# Create an output directory
# Change this name if you want a different output directory
OUTPUT = "output"
os.makedirs(OUTPUT, exist_ok=True)

# How many G4G codes to generate; used both here and in the PDF section
N = 170

# Only used for PDFs: how many rows, columns, filename
nCols = 2
nRows = 3
margin = 0.25
PDF_FILENAME = "G4GGifts.pdf"


# :::::::::: SVG CREATION SECTION ::::::::::
# This section creates the initial G4G SVGs one by one
# They will be joined together in the PDF section for convenience

logger.info("**** CREATING G4G SVGs ****")

# Since we are creating QR Code messages dynamically, we won't use the JSON file
# and instead will do what the JSON function is doing manually by writing strings and creating instances

# Define the blockMsg and stegMsg, here they are static
blockMsg = "Thank you for listening to my talk on Color Code Cryptography at Gathering 4 Gardner #16, February 18-22, 2026! This image encodes text in 3 different independent ways: a QR code; colored blocks whose RGB values give 3 ASCII codes when divided by 2; and steganography, which sets the least-significant bits of 7 sequential color channels to encode an ASCII code. Multiplying colors by 2 bit-shifts them left, leaving room for LSBs and producing a lighter, aesthetic image, but blocks must be dark for a QR code to scan, so block colors are XOR'd with 0xFEFEFE to push them into the dark half of the spectrum without data loss."

stegMsg = "My name is Abhigyan (Riju) Dasgupta; visit the repo @ github.com/rijuvenator/qrcolorcode"

# Each G4G code has a unique QR code, construct qrMsg dynamically
# Then create each of the 3 message codes, add them together, and write it out
for i in range(1, N + 1):
    qrMsg = f"G4G16#{i:03d}"
    sc = StegCode(stegMsg)
    bc = BlockCode(blockMsg)
    qc = QRCode(qrMsg)
    qc.addCode(bc)
    qc.addCode(sc)
    Canvas(qc).render(fname=f"{OUTPUT}/g4g_code{i:03d}.svg")

logger.info("**** ALL G4G SVGs CREATED ****")


# :::::::::: PDF CREATION SECTION ::::::::::
# This section joins together the SVGs into a single PDF
# as well as writes out the text on the back
# I'm using FPDF2 here, and it's new to me so this code is a bit rough
# It's mostly for positioning purposes, I'll try to write comments

logger.info("**** CREATING COMBINED PDF ****")

# Create a letter size PDF and set margins
pdf = fpdf.FPDF(unit="in", format=(8.5, 11))
pdf.set_margins(margin, margin)

# For each G4G SVG:
# - if we need a new page, make 2 pages, because the other side will be text
#   and we will fill in the text later in a different loop
# - open the SVG as an FPDF object
# - transform to page viewport; I couldn't get this to work for an arbitrary rect,
#   but presumably there's a way to position it somewhere so all the scaling and
#   transforming is not necessary, but this works, so I will keep it
# - following the example in FPDF, transform so that the center of the code
#   is the "origin" and is in the top left corner
# - then scale; by default, the SVG is taken to be in POINTS when specified without
#   units, and the output SVGs say things like "width=210"; points have a specific
#   conversion, but we actually just want to scale down to 1 inch and then scale up
#   so 1/width (of the SVG) will do that, and then scale up by pdf.height/nRows
#   We want a little bit of a margin, so the scale factor gets - margin * 2
# - then translate; the expression figures out how many OVER and how many DOWN
#   by modding and floor dividing the index i (this is why it's 0 indexed)
#   first, just figure out which index within the page by modding by nCols*nRows
#   i.e. it should be 6, so which one within the 6 is it; and then % and //
#   For example, QR Code 3 should be 0 over, 1 down; QR Code 4 should be 1 over, etc.
# - Finally, draw the paths to the PDF
for i in range(N):
    if i % (nCols * nRows) == 0:
        pdf.add_page()
        pdf.add_page()
    svg = fpdf.svg.SVGObject.from_file(f"{OUTPUT}/g4g_code{i+1:03d}.svg")
    width, height, paths = svg.transform_to_page_viewport(pdf, align_viewbox=False)
    over = (i % (nCols * nRows)) % nCols
    down = (i % (nCols * nRows)) // nCols
    paths.transform = paths.transform @ fpdf.drawing.Transform.translation(
        -width / 2, -height / 2
    ).scale(1 / width * (pdf.h / nRows - margin * 2)).translate(
        pdf.w / nCols * over + pdf.w / nCols / 2,
        pdf.h / nRows * down + pdf.h / nRows / 2,
    )
    pdf.draw_path(paths)


# Now we write out the text on each of the empty pages
# - the textwidth is used a lot and we subtract a multiple of the margin
#   off the basic width, which is pdf.width/nCols
# - note that over and down, down is the same, but over needs to be FLIPPED
#   so that when the PDF is printed, flip on LONG EDGE, and it matches up
#   therefore the over uses (i+1) for the purposes of modding
# - set some locations, since the PDF needs locations to write at
# - set the page manually, i.e. figure out which empty page to write to
#   it's annoying to look at but (i//6 + 1) * 2 - 1 is the page number needed
# - writeLine: encapsulates a pdf.cell or pdf.multicell
#   multicell auto-wraps, but I think we don't want it all the time
#   We always manually reset the x since we're doing things weird, but
#   allow the PDF functions to figure out the lineheigh and therefore next y
# - now we have everything set up to write every piece of text out
#   write it out and render the final PDF
for i in range(N):
    TEXTWIDTH = pdf.w / nCols - margin * 4
    over = ((i + 1) % (nCols * nRows)) % nCols
    down = (i % (nCols * nRows)) // nCols
    LEFT = margin * 2 + pdf.w / nCols * over
    TOP = margin * 3 + pdf.h / nRows * down
    pdf.page = (i // 6 + 1) * 2 - 1
    pdf.set_xy(LEFT, TOP)

    def writeLine(text, style="", size=8, multi=False):
        pdf.set_font("Helvetica", style=style, size=size)
        func = "cell" if not multi else "multi_cell"
        getattr(pdf, func)(
            w=TEXTWIDTH, text=text, new_y="NEXT", align="C" if not multi else "J"
        )
        pdf.set_x(LEFT)

    writeLine("QR Code Message:", style="B")
    writeLine(f"G4G16#{i+1:03d}", style="")
    writeLine(" ")

    # The blocks message can be used as-is without any modifications, so use it
    writeLine("RGB Blocks Message:", style="B")
    writeLine(
        blockMsg,
        style="",
        multi=True,
    )
    writeLine(" ")

    # I want a newline in the steg message, so I will split it up by hand here
    writeLine("Steganography Message:", style="B")
    writeLine("My name is Abhigyan (Riju) Dasgupta;", style="")
    writeLine("visit the repo @ github.com/rijuvenator/qrcolorcode", style="")
    writeLine(" ")


# Final write of the PDF file
pdf.output(f"{OUTPUT}/{PDF_FILENAME}")

logger.info(f"**** COMBINED PDF CREATED: {OUTPUT}/{PDF_FILENAME} ****")
