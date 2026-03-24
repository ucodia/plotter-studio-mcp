"""Tests for SVG wrapping utilities."""

from plotter_studio.svg_utils import (
    DPI,
    PAPER_HEIGHT_INCHES,
    PAPER_HEIGHT_PX,
    PAPER_WIDTH_INCHES,
    PAPER_WIDTH_PX,
    wrap_svg,
)


def test_paper_dimensions():
    """Paper pixel dimensions should equal inches * DPI."""
    assert PAPER_WIDTH_PX == PAPER_WIDTH_INCHES * DPI
    assert PAPER_HEIGHT_PX == PAPER_HEIGHT_INCHES * DPI


def test_dpi_is_96():
    """SVG default DPI is 96."""
    assert DPI == 96


def test_wrap_svg_produces_valid_svg():
    """wrap_svg should produce a complete SVG document."""
    content = '<circle cx="100" cy="100" r="50"/>'
    result = wrap_svg(content)

    assert result.startswith('<?xml version="1.0"')
    assert "<svg" in result
    assert "xmlns" in result
    assert content in result
    assert result.endswith("</svg>\n")


def test_wrap_svg_has_correct_dimensions():
    """The wrapped SVG should declare the paper dimensions."""
    result = wrap_svg('<line x1="0" y1="0" x2="100" y2="100"/>')

    assert f'width="{PAPER_WIDTH_INCHES}in"' in result
    assert f'height="{PAPER_HEIGHT_INCHES}in"' in result
    assert f'viewBox="0 0 {PAPER_WIDTH_PX} {PAPER_HEIGHT_PX}"' in result


def test_wrap_svg_preserves_content():
    """Inner SVG content should appear unchanged inside the wrapper."""
    content = (
        '<path d="M 10 10 L 200 200" stroke="black" stroke-width="2"/>\n'
        '<rect x="50" y="50" width="100" height="100" fill="none" stroke="red"/>'
    )
    result = wrap_svg(content)
    assert content in result
