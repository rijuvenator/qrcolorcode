# Color Code Cryptography

This repository produces SVG images encoded with ASCII text in 3 different independent ways:
* QR Code: encodes text with a standardized grid pattern
* RGB Blocks: encodes ASCII codes into RGB color channels
* Steganography: encodes ASCII values across the LSBs of the RGB channels

## Installation

This library requires Python 3.12. Required packages are found in `requirements.txt`. Note:
* `svg.py` and `qrcode` are required
* `black` and `flake8` are only for development formatting purposes
* `fpdf2` is only for joining SVGs together (as in the G4G script)

An example environment setup script using Anaconda on a Unix-like machine is provided in `setup.sh`.

## Basic Usage

After installation, run

```sh
python3 run_test.py
```

This script:
* Loads modules from `colorcode.py`
* Creates an output directory
* Reads a JSON file containing the message plaintext
* Produces an SVG file
* Decodes the SVG file and prints the results to standard output

In the script, the output directory, input JSON file, and outfile file name are specified.

To create your own Color Code Cryptography Code, provide a JSON file in the same format:

```json
{
    "qr":"QR Code Message",
    "block":"Contents of the Block Code Message",
    "steg":"Steg Message"
}
```

Because the methods are independent, you can provide 1, 2, or all 3 fields. For example, if the QR code message is omitted, then a grid of colored blocks is created from the `block` message and the `steg` message. This type of colored grid has customizable dimensions if using the full set of classes and not just the `.fromJSON()` wrapper function.

Note that only standard printable ASCII, without newlines, is allowed. (I would have allowed newlines, but I cannot be sure that Windows users and Unix-like users are providing newlines in the same way, and it seemed out of scope to load multi-line strings in a platform-independent way.)

JSON files are a convenient way to store static data and interact with the library, but Python makes it easy to generate strings dynamically, and the individual classes can be customized with options, or inherited from for full control.

## G4G QR Codes

`run_g4g.py` produces 170 unique QR codes encoding `G4G16#DDD`, where `DDD` ranges from `001` to `170`, and simultaneously encodes an RGB block message and a steganography LSB message. It then joins the codes together into a printable PDF, adding the explanatory text to the back of each code.

## Technical Details

### Dependencies and Structure

This library uses `svg.py` to write SVG files and `qrcode` to generate QR codes.

`svg.py` provides a Python interface for writing SVG files, making it convenient to create custom `Canvas` classes while still performing all of the computation and geometry within Python.

`qrcode` produces QR codes, but for the purposes of this project, no files are written; instead, we use the library's implementation of the QR code specification and extract the binary array of black-and-white squares to add on the RGB block and steganography concepts.

The library implements `Color` and `Coord` dataclasses, as well as a hierarchy of code classes for each of the 3 encoding methods, as well as a parent class for some shared methods. Convenient overloading of "addition" and "inversion" concepts for colors and codes are implemented to make combining different combinations of codes intuitive.

The `Canvas` class takes an instantiated code, containing all the necessay information about colors and positioning, and produces SVG outputs by rendering them as a file.

The `GridCode.decode()` static method takes a rendered SVG file produced from this process and writes any decoded plaintext to standard output.

### Encoding

#### QR Code
A QR code is just a 2D array of binary truth values: a "module" is either on or off. Most of the time, the "on" modules are black squares and the "off" modules are white squares. QR codes have many features to aid in scanning legibility, some structural, and some algorithmic; for example, there are distinctive "alignment" patterns, as well as Reed-Solomon error-correcting codes so that QR codes remain scannable even when damaged or, as in our case, artistically manipulated. The black squares offer extra dimensions in which to embed more information; the QR code only cares whether it's black or white.

#### ASCII Code
ASCII codes encode text as 7-bit numbers from 0 to 127; for example, the letter `R` is 82<sub>10</sub> = 1010010<sub>2</sub> = 52<sub>16</sub> in base 10, 2, and 16, respectively.

#### RGB Colors
RGB colors encode colors as three 8-bit numbers from 0 to 255, one for each channel; for example, a red color would have red channel value 255<sub>10</sub> = FF<sub>16</sub>, and 0 for the green and blue channels, so the color could be represented as RGB(255, 00, 00) = RGB(FF, 00, 00).

The core concept of this color encoding is to generate RGB colors corresponding to ASCII text: for example, `Dog` has ASCII values 68, 111, and 103, which would correspond to the color RGB(68, 111, 103).

#### Steganography LSBs

When I first developed this idea (see also my `colorcode` repository), I found that doing this produced unappealing dark colors, because ASCII is only in the range 0-127, whereas RGB is the in the range 0-255. So for the purpose of generating a nicer set of colors, I multiply each ASCII value by 2, shifting every color into the brighter half of the spectrum. We just have to remember to divide each color by 2 when dividing.

This has another consequence: the final, "least-significant" bit of each channel is now 0, because multiplying by 2 simply bit-shifts to the left. Consider the letter `R` again:

(82<sub>10</sub> = 1010010<sub>2</sub>) &times; 2 = (164<sub>10</sub> = 10100100<sub>2</sub>)

This provides a final opportunity: use each of the LSBs as yet another way to encode ASCII, by taking the last bit of each of every 7 color channels to encode one more ASCII character. Since we will divide by 2 to get the normal RGB "block" content, the LSB is ignored, and does not interfere with the color encoding above.

#### XOR with #FEFEFE for QR Codes

We saw that steganography does not interfere with the other 7 bits used for RGB blocks. So the first thing to try is to take these colors, and square-by-square, replace the black-and-white QR code with the colored squares, hoping that the result remains scannable.

As it turns out, it did not remain scannable for me. The colors are too light-colored to provide enough contrast. We also cannot use just the lower 7 bits, since we need the last bit for the steganography message, and those bits would be destroyed.

However, there is one final trick. Colors can be "inverted" by subtracting them from 255, or equivalently, XOR'ing them with white, e.g. RGB(255, 255, 255). This does not cause any data loss, since to undo it, you just have to XOR again. Because we do not want to touch the steganography bits, we will XOR with RGB(254, 254, 254) = #FEFEFE instead, which will always leave the final bit of each channel alone. This will push each light color into the dark half of the spectrum, providing enough contrast for the QR code to scan, and allow us to complete the task of simulataneously encoding 3 separate messages independently.

For plain color grids without a QR code, we'll keep the un-XOR'd version, since it looks a little nicer. This leads to some subtleties in the decoding. In this library, the SVG rectangles get encoded with a piece of metadata instructing the decoding function whether or not it needs to be XOR'd. The decoding function can override this behavior, but for a general SVG not produced with this library, or a screenshot, etc., some tweaking may be required.

#### Summary
The procedure to successfully encode 3 separate messages (QR, Block, and Steganography) simultaneously and independently is:

1. Multiply the ASCII code for a "block" character by 2. This is a channel.
2. Interleave the bits of a "steganography" character ASCII code into the LSBs of the channels.
3. XOR each channel with #FE to push it into the dark half of the spectrum. Skip this step if there is no QR code.
4. String 3 channels together as R, G, B to form a color.
5. Replace QR code blocks with these colors, or string them together as blocks if there is no QR code.

Observe that this means that every 7 colors can hold 21 channels = 21 Block characters = 3 Steganography characters.
