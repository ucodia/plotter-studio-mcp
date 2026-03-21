"""AxiDraw plotter control: state management and plotting."""

import logging
import threading
import time
from typing import Any, Dict, Optional

from .webhook import _send_webhook

logger = logging.getLogger("monet")


class PlotterState:
    """Thread-safe plotter state tracker."""

    IDLE = "idle"
    PLOTTING = "plotting"
    WAITING_PEN_CHANGE = "waiting_for_pen_change"
    ERROR = "error"

    def __init__(self):
        self._lock = threading.Lock()
        self._status = self.IDLE
        self._current_job: Optional[str] = None
        self._error: Optional[str] = None
        self._pen_change_event = threading.Event()
        self._pen_change_event.set()  # Not waiting initially
        self._requested_pen: Optional[str] = None
        self._job_start_time: Optional[float] = None
        self._last_completed_svg: Optional[str] = None

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    def start_plot(self, job_name: str):
        with self._lock:
            self._status = self.PLOTTING
            self._current_job = job_name
            self._job_start_time = time.time()
            self._error = None

    def finish_plot(self, svg_path: str):
        with self._lock:
            self._status = self.IDLE
            self._last_completed_svg = svg_path
            self._current_job = None
            self._job_start_time = None

    def set_error(self, msg: str):
        with self._lock:
            self._status = self.ERROR
            self._error = msg
            self._current_job = None

    def request_pen_change(self, pen_description: str):
        with self._lock:
            self._status = self.WAITING_PEN_CHANGE
            self._requested_pen = pen_description
            self._pen_change_event.clear()

    def confirm_pen_change(self):
        with self._lock:
            self._status = self.IDLE
            self._requested_pen = None
            self._pen_change_event.set()

    def wait_for_pen_change(self, timeout: float = 300.0) -> bool:
        return self._pen_change_event.wait(timeout=timeout)

    def get_info(self) -> Dict[str, Any]:
        with self._lock:
            info = {
                "status": self._status,
                "current_job": self._current_job,
                "error": self._error,
                "requested_pen": self._requested_pen,
                "last_completed_svg": self._last_completed_svg,
            }
            if self._job_start_time and self._status == self.PLOTTING:
                info["elapsed_seconds"] = round(time.time() - self._job_start_time, 1)
            return info


def _plot_svg_blocking(
    svg_path: str,
    options: Dict[str, Any],
    plotter_state: PlotterState,
) -> None:
    """Run a plot synchronously. Called from a background thread."""
    try:
        from pyaxidraw import axidraw

        ad = axidraw.AxiDraw()
        ad.plot_setup(svg_path)

        # A3 model
        ad.options.model = 2

        # Apply user-specified options
        if "speed_pendown" in options:
            ad.options.speed_pendown = options["speed_pendown"]
        if "speed_penup" in options:
            ad.options.speed_penup = options["speed_penup"]
        if "pen_pos_down" in options:
            ad.options.pen_pos_down = options["pen_pos_down"]
        if "pen_pos_up" in options:
            ad.options.pen_pos_up = options["pen_pos_up"]
        if "accel" in options:
            ad.options.accel = options["accel"]

        ad.plot_run()
        plotter_state.finish_plot(svg_path)
        logger.info(f"Plot complete: {svg_path}")
        _send_webhook("plot_complete", {"svg_path": svg_path})

    except Exception as e:
        plotter_state.set_error(str(e))
        logger.error(f"Plot error: {e}")
        _send_webhook("plot_error", {"svg_path": svg_path, "error": str(e)})
