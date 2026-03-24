"""
Plotter Studio MCP Server
=========================
An MCP server that gives AI agents eyes and a robotic arm via a pen plotter
and webcam.

Usage:
    plotter-studio   # if installed via pip install -e .
"""

import asyncio
import json
import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP, Image
from pydantic import BaseModel, ConfigDict, Field

from .camera import capture_frame
from .plotter import PlotterState, _plot_svg_blocking
from .svg_utils import (
    DPI,
    PAPER_HEIGHT_INCHES,
    PAPER_HEIGHT_PX,
    PAPER_WIDTH_INCHES,
    PAPER_WIDTH_PX,
    wrap_svg,
)
from .webhook import _send_webhook, configure_webhook

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SVG_DIR = Path(os.environ.get("PLOTTER_SVG_DIR", os.path.expanduser("~/plotter-studio/output")))
WEBHOOK_URL = os.environ.get("PLOTTER_WEBHOOK_URL", "")
PLOTTER_MODEL = int(os.environ.get("PLOTTER_MODEL", "2"))
PLOTTER_PENLIFT = int(os.environ.get("PLOTTER_PENLIFT", "3"))
CAMERA_INDEX = int(os.environ.get("PLOTTER_CAMERA", "0"))

logging.basicConfig(
    level=logging.INFO,
    format="[plotter-studio] %(asctime)s %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("plotter-studio")

configure_webhook(WEBHOOK_URL)

plotter_state = PlotterState()

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Plotter Studio MCP started. SVG dir: {SVG_DIR}")
    yield {}
    logger.info("Plotter Studio MCP shutting down.")


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("plotter-studio", lifespan=app_lifespan)

# ---- Plotting tools -------------------------------------------------------


class PlotSvgInput(BaseModel):
    """Input for plotting an SVG."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    svg_content: str = Field(
        ...,
        description=(
            "Complete SVG content to plot. Can be a full SVG document or just "
            "the inner elements (paths, circles, lines, etc.) which will be "
            "wrapped in a document sized to the paper. "
            "All coordinates should be in pixels at 96 DPI."
        ),
    )
    filename: Optional[str] = Field(
        default=None,
        description="Optional filename for the SVG (without path). Auto-generated if omitted.",
    )
    speed_pendown: Optional[int] = Field(
        default=25,
        description="Pen-down speed as percentage of max (1-100). Lower is slower/more precise.",
        ge=1,
        le=100,
    )
    speed_penup: Optional[int] = Field(
        default=75,
        description="Pen-up travel speed as percentage of max (1-100).",
        ge=1,
        le=100,
    )
    pen_pos_down: Optional[int] = Field(
        default=0,
        description="Pen-down height as percentage (0=lowest). Adjust for pen/marker type.",
        ge=0,
        le=100,
    )
    pen_pos_up: Optional[int] = Field(
        default=50,
        description="Pen-up height as percentage (100=highest).",
        ge=0,
        le=100,
    )
    accel: Optional[int] = Field(
        default=75,
        description="Acceleration as percentage of max (1-100). Lower for more delicate work.",
        ge=1,
        le=100,
    )


@mcp.tool(
    name="monet_plot_svg",
    annotations={
        "title": "Plot SVG on plotter",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def monet_plot_svg(params: PlotSvgInput) -> str:
    """Send an SVG to the AxiDraw for plotting. The plot runs in the background.
    Use monet_get_status to check progress. Only one plot can run at a time.

    The paper is 11x15 inches portrait, 96 DPI (1056x1440 px).
    Pen starts at the top-left corner of the paper.

    Args:
        params (PlotSvgInput): SVG content and plotter settings.

    Returns:
        str: JSON with job status and saved SVG path.
    """
    if plotter_state.status == PlotterState.PLOTTING:
        return json.dumps(
            {"error": "A plot is already running. Wait for it to finish."}
        )

    if plotter_state.status == PlotterState.WAITING_PEN_CHANGE:
        return json.dumps({"error": "Waiting for pen change. Confirm before plotting."})

    svg = params.svg_content.strip()
    if not svg.startswith("<?xml") and not svg.startswith("<svg"):
        svg = wrap_svg(svg)

    filename = (
        params.filename or f"plot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.svg"
    )
    if not filename.endswith(".svg"):
        filename += ".svg"
    svg_path = SVG_DIR / filename
    svg_path.write_text(svg, encoding="utf-8")

    options = {"model": PLOTTER_MODEL, "penlift": PLOTTER_PENLIFT}
    if params.speed_pendown is not None:
        options["speed_pendown"] = params.speed_pendown
    if params.speed_penup is not None:
        options["speed_penup"] = params.speed_penup
    if params.pen_pos_down is not None:
        options["pen_pos_down"] = params.pen_pos_down
    if params.pen_pos_up is not None:
        options["pen_pos_up"] = params.pen_pos_up
    if params.accel is not None:
        options["accel"] = params.accel

    plotter_state.start_plot(filename)
    _send_webhook("plot_started", {"filename": filename, "svg_path": str(svg_path)})
    thread = threading.Thread(
        target=_plot_svg_blocking,
        args=(str(svg_path), options, plotter_state),
        daemon=True,
    )
    thread.start()

    return json.dumps(
        {
            "status": "plotting_started",
            "svg_path": str(svg_path),
            "filename": filename,
            "paper_size": f"{PAPER_WIDTH_INCHES}x{PAPER_HEIGHT_INCHES} inches portrait",
            "dpi": DPI,
            "canvas_px": f"{PAPER_WIDTH_PX}x{PAPER_HEIGHT_PX}",
        }
    )


class PreviewSvgInput(BaseModel):
    """Input for previewing (saving without plotting) an SVG."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    svg_content: str = Field(..., description="SVG content to save for preview.")
    filename: Optional[str] = Field(
        default=None, description="Optional filename. Auto-generated if omitted."
    )


@mcp.tool(
    name="monet_preview_svg",
    annotations={
        "title": "Save SVG without plotting (preview)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def monet_preview_svg(params: PreviewSvgInput) -> str:
    """Save an SVG file to disk without sending it to the plotter.
    Useful for reviewing the SVG before committing to a physical plot.

    Args:
        params (PreviewSvgInput): SVG content and optional filename.

    Returns:
        str: JSON with the saved file path.
    """
    svg = params.svg_content.strip()
    if not svg.startswith("<?xml") and not svg.startswith("<svg"):
        svg = wrap_svg(svg)

    filename = (
        params.filename or f"preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.svg"
    )
    if not filename.endswith(".svg"):
        filename += ".svg"
    svg_path = SVG_DIR / filename
    svg_path.write_text(svg, encoding="utf-8")

    return json.dumps(
        {"status": "saved", "svg_path": str(svg_path), "filename": filename}
    )


# ---- Status tools ----------------------------------------------------------


@mcp.tool(
    name="monet_get_status",
    annotations={
        "title": "Get plotter status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def monet_get_status() -> str:
    """Check the current status of the AxiDraw plotter.
    Returns whether it is idle, plotting, waiting for a pen change, or in error.

    Returns:
        str: JSON with current plotter state.
    """
    return json.dumps(plotter_state.get_info())


@mcp.tool(
    name="monet_stop_plot",
    annotations={
        "title": "Stop the current plot",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def monet_stop_plot() -> str:
    """Cancel the currently running plot. The plotter will finish its current
    movement segment and then stop gracefully with pen raised.

    Returns:
        str: JSON with cancellation result.
    """
    if plotter_state.status != PlotterState.PLOTTING:
        return json.dumps(
            {"error": f"No plot running. Plotter is {plotter_state.status}."}
        )

    success = plotter_state.cancel_plot()
    if success:
        logger.info("Plot cancellation requested.")
        return json.dumps({"status": "cancelling", "message": "Plot stop requested. The plotter will finish its current segment and stop."})
    else:
        return json.dumps({"error": "Could not cancel plot. No active plotter reference."})


# ---- Pen management tools --------------------------------------------------


class PenChangeInput(BaseModel):
    """Input for requesting a pen change."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    pen_description: str = Field(
        ...,
        description="Description of the pen to load, e.g. 'Sakura Micron 0.05mm black'.",
        min_length=1,
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional notes for the human, e.g. 'add spring for extra pressure'.",
    )


@mcp.tool(
    name="monet_request_pen_change",
    annotations={
        "title": "Request pen change",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def monet_request_pen_change(params: PenChangeInput) -> str:
    """Request the human to change the pen on the AxiDraw.
    This sets the plotter to a waiting state. The human must call
    monet_confirm_pen_change when the swap is complete.

    Args:
        params (PenChangeInput): Description of desired pen and optional notes.

    Returns:
        str: JSON confirming the request was made.
    """
    if plotter_state.status == PlotterState.PLOTTING:
        return json.dumps({"error": "Cannot change pen while plotting."})

    message = f"Please load: {params.pen_description}"
    if params.notes:
        message += f"\nNote: {params.notes}"

    plotter_state.request_pen_change(params.pen_description)
    logger.info(f"Pen change requested: {params.pen_description}")
    _send_webhook(
        "pen_change_requested",
        {
            "pen": params.pen_description,
            "notes": params.notes,
            "message": message,
        },
    )

    return json.dumps(
        {
            "status": "waiting_for_pen_change",
            "pen_requested": params.pen_description,
            "notes": params.notes,
            "message": message,
        }
    )


@mcp.tool(
    name="monet_confirm_pen_change",
    annotations={
        "title": "Confirm pen change is complete",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def monet_confirm_pen_change() -> str:
    """Confirm that the pen change has been completed. Call this after physically
    swapping the pen on the AxiDraw.

    Returns:
        str: JSON confirming the plotter is ready.
    """
    if plotter_state.status != PlotterState.WAITING_PEN_CHANGE:
        return json.dumps(
            {
                "status": plotter_state.status,
                "message": "No pen change was pending.",
            }
        )

    plotter_state.confirm_pen_change()
    logger.info("Pen change confirmed.")
    return json.dumps(
        {"status": "idle", "message": "Pen change confirmed. Ready to plot."}
    )


# ---- Camera tools ----------------------------------------------------------


@mcp.tool(
    name="monet_capture",
    annotations={
        "title": "Capture image from webcam",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def monet_capture() -> Image:
    """Capture a photo from the webcam to see the current state of the paper.
    Returns a full-resolution JPEG image inline.

    Returns:
        Image: JPEG image content block.
    """
    jpeg_bytes = await asyncio.to_thread(capture_frame, CAMERA_INDEX)
    if jpeg_bytes:
        return Image(data=jpeg_bytes, format="jpeg")
    raise ValueError(f"Failed to capture from camera (index {CAMERA_INDEX}).")


# ---- Paper info tool -------------------------------------------------------


@mcp.tool(
    name="monet_get_paper_info",
    annotations={
        "title": "Get paper and canvas dimensions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def monet_get_paper_info() -> str:
    """Returns the working area dimensions for SVG generation.
    Paper is Fabriano watercolor, 11x15 inches portrait.

    Returns:
        str: JSON with paper size in inches, pixels, and DPI.
    """
    return json.dumps(
        {
            "paper": "Fabriano watercolor cold press",
            "orientation": "portrait",
            "width_inches": PAPER_WIDTH_INCHES,
            "height_inches": PAPER_HEIGHT_INCHES,
            "dpi": DPI,
            "width_px": PAPER_WIDTH_PX,
            "height_px": PAPER_HEIGHT_PX,
            "origin": "top-left corner",
            "note": "Pen starts at top-left. All SVG coordinates at 96 DPI.",
        }
    )


# ---- Manual control tools --------------------------------------------------


class ManualMoveInput(BaseModel):
    """Input for manual pen movement."""

    model_config = ConfigDict(extra="forbid")

    x_inches: float = Field(
        ...,
        description="X position in inches from left edge.",
        ge=0,
        le=PAPER_WIDTH_INCHES,
    )
    y_inches: float = Field(
        ...,
        description="Y position in inches from top edge.",
        ge=0,
        le=PAPER_HEIGHT_INCHES,
    )


@mcp.tool(
    name="monet_move_to",
    annotations={
        "title": "Move pen to position (pen up)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def monet_move_to(params: ManualMoveInput) -> str:
    """Move the AxiDraw pen to a specific position with pen up (no drawing).
    Useful for repositioning between operations. Only works when plotter is idle.

    Args:
        params (ManualMoveInput): Target position in inches.

    Returns:
        str: JSON confirming the move.
    """
    if plotter_state.status != PlotterState.IDLE:
        return json.dumps({"error": f"Plotter is {plotter_state.status}, cannot move."})

    def _do_move():
        try:
            from nextdraw import NextDraw

            ad = NextDraw()
            ad.interactive()
            ad.options.model = PLOTTER_MODEL
            ad.options.penlift = PLOTTER_PENLIFT
            if not ad.connect():
                return {"error": "Could not connect to plotter."}
            ad.moveto(params.x_inches, params.y_inches)
            ad.disconnect()
            return {"status": "moved", "x": params.x_inches, "y": params.y_inches}
        except Exception as e:
            return {"error": str(e)}

    result = await asyncio.to_thread(_do_move)
    return json.dumps(result)


@mcp.tool(
    name="monet_pen_up",
    annotations={
        "title": "Raise the pen",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def monet_pen_up() -> str:
    """Raise the pen. Useful before manual repositioning.

    Returns:
        str: JSON confirming pen was raised.
    """
    if plotter_state.status != PlotterState.IDLE:
        return json.dumps({"error": f"Plotter is {plotter_state.status}."})

    def _do_pen_up():
        try:
            from nextdraw import NextDraw

            ad = NextDraw()
            ad.interactive()
            ad.options.model = PLOTTER_MODEL
            ad.options.penlift = PLOTTER_PENLIFT
            if not ad.connect():
                return {"error": "Could not connect to plotter."}
            ad.penup()
            ad.disconnect()
            return {"status": "pen_up"}
        except Exception as e:
            return {"error": str(e)}

    result = await asyncio.to_thread(_do_pen_up)
    return json.dumps(result)


@mcp.tool(
    name="monet_home",
    annotations={
        "title": "Return pen to home position",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def monet_home() -> str:
    """Return the AxiDraw pen carriage to the home (0,0) position.

    Returns:
        str: JSON confirming return to home.
    """
    if plotter_state.status != PlotterState.IDLE:
        return json.dumps({"error": f"Plotter is {plotter_state.status}."})

    def _do_home():
        try:
            from nextdraw import NextDraw

            ad = NextDraw()
            ad.interactive()
            ad.options.model = PLOTTER_MODEL
            ad.options.penlift = PLOTTER_PENLIFT
            if not ad.connect():
                return {"error": "Could not connect to plotter."}
            ad.moveto(0, 0)
            ad.disconnect()
            return {"status": "home", "x": 0, "y": 0}
        except Exception as e:
            return {"error": str(e)}

    result = await asyncio.to_thread(_do_home)
    return json.dumps(result)


# ---- Notify human tool -----------------------------------------------------


class NotifyInput(BaseModel):
    """Input for sending a notification to the human."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    message: str = Field(
        ..., description="Message to display to the human operator.", min_length=1
    )


@mcp.tool(
    name="monet_notify",
    annotations={
        "title": "Send message to human operator",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def monet_notify(params: NotifyInput) -> str:
    """Send a notification message to the human operator. This is logged
    and can be used to communicate status, ask questions, or request actions.

    Args:
        params (NotifyInput): The message to send.

    Returns:
        str: JSON confirming the notification was sent.
    """
    logger.info(f"NOTIFICATION: {params.message}")
    _send_webhook("notification", {"message": params.message})
    return json.dumps(
        {
            "status": "notified",
            "message": params.message,
            "timestamp": datetime.now().isoformat(),
        }
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Entry point for the plotter-studio console script."""
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
