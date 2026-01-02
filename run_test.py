import os
from colorcode import GridCode, Canvas

# Create an output directory
# Change this name if you want a different output directory
OUTPUT = "output"
os.makedirs(OUTPUT, exist_ok=True)

# Input and output files
JSON_FILE = "json/test.json"
OUTPUT_FILE = f"{OUTPUT}/test.svg"

# Encode; will make an SVG file called test.svg in output directory
gc = GridCode.fromJSON(JSON_FILE)
Canvas(gc).render(fname=OUTPUT_FILE)

# Decode; will read any block or steg codes from provided SVG file
# This will work for all cases if it's output from this library
GridCode.decode(OUTPUT_FILE)
