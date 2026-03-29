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

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from .camera import capture_frame
from .filestore import get_file, store_file
from .plotter import PlotterState, run_plot
from .webhook import _send_webhook, configure_webhook

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SVG_DIR = Path(os.environ.get("PLOTTER_SVG_DIR", os.path.expanduser("output")))
WEBHOOK_URL = os.environ.get("PLOTTER_WEBHOOK_URL", "")
PLOTTER_MODEL = int(os.environ.get("PLOTTER_MODEL", "2"))
PLOTTER_PENLIFT = int(os.environ.get("PLOTTER_PENLIFT", "3"))
PLOTTER_PEN_POS_DOWN = int(os.environ.get("PLOTTER_PEN_POS_DOWN", "0"))
PLOTTER_PEN_POS_UP = int(os.environ.get("PLOTTER_PEN_POS_UP", "50"))
CAMERA_INDEX = int(os.environ.get("PLOTTER_CAMERA", "0"))
CAMERA_ROTATE = int(os.environ.get("PLOTTER_CAMERA_ROTATE", "0"))
MCP_PORT = int(os.environ.get("MCP_PORT", "8888"))
HTTP_BASE_URL = os.environ.get(
    "PLOTTER_HTTP_BASE_URL", f"http://localhost:{MCP_PORT}"
).rstrip("/")

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

mcp = FastMCP(
    "plotter-studio",
    lifespan=app_lifespan,
    port=MCP_PORT,
)

# ---- File transfer routes --------------------------------------------------


@mcp.custom_route("/files", methods=["POST"])
async def upload_file(request: Request):
    form = await request.form()
    upload = form["file"]
    filename = upload.filename or "upload"
    if not filename.lower().endswith(".svg"):
        return JSONResponse({"error": "Only SVG files are accepted."}, status_code=400)
    data = await upload.read()
    file_id = store_file(data, filename, "image/svg+xml")
    return JSONResponse(
        {
            "id": file_id,
            "filename": filename,
            "url": f"{HTTP_BASE_URL}/files/{file_id}",
        }
    )


@mcp.custom_route("/files/{file_id}", methods=["GET"])
async def download_file(request: Request):
    file_id = request.path_params["file_id"]
    result = get_file(file_id)
    if result is None:
        return JSONResponse({"error": "File not found"}, status_code=404)
    path, filename, content_type = result
    return FileResponse(path, media_type=content_type, filename=filename)


# ---- Plotting tools -------------------------------------------------------


class PlotSvgInput(BaseModel):
    """Input for plotting an SVG."""

    model_config = ConfigDict(extra="forbid")

    svg_file_id: str = Field(
        ...,
        description=(
            "File id of an SVG previously uploaded via POST /files. "
            "Upload your SVG first, then pass the returned id here."
        ),
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
    accel: Optional[int] = Field(
        default=75,
        description="Acceleration as percentage of max (1-100). Lower for more delicate work.",
        ge=1,
        le=100,
    )


@mcp.tool(
    name="plot_start",
    annotations={
        "title": "Plot SVG on plotter",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def plot_start(params: PlotSvgInput) -> str:
    """Upload your SVG via POST /files first, then pass the returned file id here.
    The plot runs in the background. Use plot_status to check progress.
    Only one plot can run at a time.
    """
    if plotter_state.status == PlotterState.PLOTTING:
        return json.dumps(
            {"error": "A plot is already running. Wait for it to finish."}
        )

    result = get_file(params.svg_file_id)
    if result is None:
        return json.dumps({"error": f"File not found: {params.svg_file_id}"})
    src_path, orig_filename, _ct = result
    svg = src_path.read_text(encoding="utf-8").strip()

    if orig_filename and orig_filename.endswith(".svg"):
        filename = orig_filename
    else:
        filename = f"plot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.svg"
    svg_path = SVG_DIR / filename
    svg_path.write_text(svg, encoding="utf-8")

    options = {
        "model": PLOTTER_MODEL,
        "penlift": PLOTTER_PENLIFT,
        "pen_pos_down": PLOTTER_PEN_POS_DOWN,
        "pen_pos_up": PLOTTER_PEN_POS_UP,
    }
    if params.speed_pendown is not None:
        options["speed_pendown"] = params.speed_pendown
    if params.speed_penup is not None:
        options["speed_penup"] = params.speed_penup
    if params.accel is not None:
        options["accel"] = params.accel

    plotter_state.start_plot(filename)
    _send_webhook("plot_started", {"filename": filename, "svg_path": str(svg_path)})
    thread = threading.Thread(
        target=run_plot,
        args=(str(svg_path), options, plotter_state),
        daemon=True,
    )
    thread.start()

    return json.dumps(
        {
            "status": "plotting_started",
            "svg_path": str(svg_path),
            "filename": filename,
        }
    )


# ---- Status tools ----------------------------------------------------------


@mcp.tool(
    name="plot_status",
    annotations={
        "title": "Get plotter status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def plot_status() -> str:
    """Check the current status of the AxiDraw plotter.
    Returns whether it is idle, plotting, or in error.

    Returns:
        str: JSON with current plotter state.
    """
    return json.dumps(plotter_state.get_info())


@mcp.tool(
    name="plot_stop",
    annotations={
        "title": "Stop the current plot",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def plot_stop() -> str:
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
        return json.dumps(
            {
                "status": "cancelling",
                "message": "Plot stop requested. The plotter will finish its current segment and stop.",
            }
        )
    else:
        return json.dumps(
            {"error": "Could not cancel plot. No active plotter reference."}
        )


# ---- Server info -----------------------------------------------------------


@mcp.tool(
    name="server_info",
    annotations={
        "title": "Get server connection info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def server_info() -> str:
    """Returns the HTTP base URL and available endpoints for file upload/download.
    Call this once at the start of a session to learn where to send files.
    """
    return json.dumps(
        {
            "http_base_url": HTTP_BASE_URL,
            "endpoints": {
                "upload": "POST /files",
                "download": "GET /files/{id}",
            },
        }
    )


# ---- Camera tools ----------------------------------------------------------


@mcp.tool(
    name="capture",
    annotations={
        "title": "Capture image from webcam",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def capture() -> str:
    """Capture a photo from the webcam to see the current state of the paper.
    Returns a file reference. Retrieve the full image via GET /files/{id}.

    Returns:
        str: JSON with file_id and url for the captured JPEG.
    """
    jpeg_bytes = await asyncio.to_thread(capture_frame, CAMERA_INDEX, CAMERA_ROTATE)
    if not jpeg_bytes:
        raise ValueError(f"Failed to capture from camera (index {CAMERA_INDEX}).")
    file_id = store_file(jpeg_bytes, "capture.jpg", "image/jpeg")
    return json.dumps({"file_id": file_id, "url": f"{HTTP_BASE_URL}/files/{file_id}"})


# ---- Tool control ----------------------------------------------------------


class ManualMoveInput(BaseModel):
    """Input for manual pen movement."""

    model_config = ConfigDict(extra="forbid")

    x_inches: float = Field(
        ...,
        description="X position in inches from left edge (max 11).",
        ge=0,
        le=11,
    )
    y_inches: float = Field(
        ...,
        description="Y position in inches from top edge (max 15).",
        ge=0,
        le=15,
    )


@mcp.tool(
    name="tool_move",
    annotations={
        "title": "Move tool to position (pen up)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tool_move(params: ManualMoveInput) -> str:
    """Move the AxiDraw tool to a specific position with pen up (no drawing).
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
    name="tool_raise",
    annotations={
        "title": "Raise the tool",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tool_raise() -> str:
    """Raise the tool. Useful before manual repositioning.

    Returns:
        str: JSON confirming tool was raised.
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
            return {"status": "raised"}
        except Exception as e:
            return {"error": str(e)}

    result = await asyncio.to_thread(_do_pen_up)
    return json.dumps(result)


@mcp.tool(
    name="tool_home",
    annotations={
        "title": "Return tool to home position",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tool_home() -> str:
    """Return the AxiDraw tool carriage to the home (0,0) position.

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
    name="notify",
    annotations={
        "title": "Send message to human operator",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def notify(params: NotifyInput) -> str:
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
