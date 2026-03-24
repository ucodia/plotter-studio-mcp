"""AxiDraw plotter control: state management and plotting."""

import logging
import threading
import time
from typing import Any, Dict, Optional

from .webhook import _send_webhook

logger = logging.getLogger("plotter-studio")


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
        self._active_plotter: Optional[Any] = None

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
            self._active_plotter = None

    def set_active_plotter(self, plotter: Any):
        with self._lock:
            self._active_plotter = plotter

    def cancel_plot(self) -> bool:
        with self._lock:
            if self._status != self.PLOTTING or self._active_plotter is None:
                return False
            try:
                import ctypes

                # We store the thread ident when starting the plot
                if hasattr(self, "_plot_thread_id") and self._plot_thread_id:
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(
                        ctypes.c_ulong(self._plot_thread_id),
                        ctypes.py_object(KeyboardInterrupt),
                    )
                    return True
                return False
            except Exception:
                return False

    def finish_plot(self, svg_path: str):
        with self._lock:
            self._status = self.IDLE
            self._last_completed_svg = svg_path
            self._current_job = None
            self._job_start_time = None
            self._active_plotter = None

    def set_error(self, msg: str):
        with self._lock:
            self._status = self.ERROR
            self._error = msg
            self._current_job = None
            self._active_plotter = None

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
        from nextdraw import NextDraw

        ad = NextDraw()
        ad.plot_setup(svg_path)

        ad.options.model = options.get("model", 2)
        ad.options.penlift = options.get("penlift", 3)
        ad.options.keyboard_pause = True

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

        plotter_state.set_active_plotter(ad)
        plotter_state._plot_thread_id = threading.current_thread().ident
        ad.plot_run()

        error_code = ad.errors.code if hasattr(ad, "errors") else 0
        if error_code == 0:
            plotter_state.finish_plot(svg_path)
            logger.info(f"Plot complete: {svg_path}")
            _send_webhook("plot_complete", {"svg_path": svg_path})
        elif error_code == 102:
            plotter_state.finish_plot(svg_path)
            logger.info(f"Plot paused by button: {svg_path}")
            _send_webhook("plot_paused", {"svg_path": svg_path, "reason": "button"})
        elif error_code == 103:
            plotter_state.finish_plot(svg_path)
            logger.info(f"Plot cancelled: {svg_path}")
            _send_webhook("plot_cancelled", {"svg_path": svg_path})
        else:
            msg = f"NextDraw error code {error_code}"
            plotter_state.set_error(msg)
            logger.error(f"Plot error: {msg}")
            _send_webhook("plot_error", {"svg_path": svg_path, "error": msg})

    except KeyboardInterrupt:
        plotter_state.finish_plot(svg_path)
        logger.info(f"Plot cancelled via interrupt: {svg_path}")
        _send_webhook("plot_cancelled", {"svg_path": svg_path})
    except Exception as e:
        plotter_state.set_error(str(e))
        logger.error(f"Plot error: {e}")
        _send_webhook("plot_error", {"svg_path": svg_path, "error": str(e)})
