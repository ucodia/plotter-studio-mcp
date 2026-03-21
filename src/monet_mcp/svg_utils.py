"""SVG wrapping utilities, paper dimensions, and constants."""

# Paper dimensions
PAPER_WIDTH_INCHES = 11.0
PAPER_HEIGHT_INCHES = 15.0

# 96 DPI is the SVG default
DPI = 96
PAPER_WIDTH_PX = PAPER_WIDTH_INCHES * DPI
PAPER_HEIGHT_PX = PAPER_HEIGHT_INCHES * DPI

SVG_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'width="{w_in}in" height="{h_in}in" '
    'viewBox="0 0 {w_px} {h_px}">\n'
)
SVG_FOOTER = "</svg>\n"


def wrap_svg(content: str) -> str:
    """Wrap raw SVG paths/elements in a properly sized SVG document."""
    header = SVG_HEADER.format(
        w_in=PAPER_WIDTH_INCHES,
        h_in=PAPER_HEIGHT_INCHES,
        w_px=PAPER_WIDTH_PX,
        h_px=PAPER_HEIGHT_PX,
    )
    return header + content + SVG_FOOTER
