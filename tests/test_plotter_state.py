"""Tests for PlotterState state machine."""

from plotter_studio.plotter import PlotterState


def test_initial_state_is_idle():
    """A fresh PlotterState should be idle."""
    ps = PlotterState()
    assert ps.status == PlotterState.IDLE


def test_start_plot_transitions_to_plotting():
    ps = PlotterState()
    ps.start_plot("test_job.svg")
    assert ps.status == PlotterState.PLOTTING

    info = ps.get_info()
    assert info["current_job"] == "test_job.svg"
    assert "elapsed_seconds" in info


def test_finish_plot_returns_to_idle():
    ps = PlotterState()
    ps.start_plot("test_job.svg")
    ps.finish_plot("/path/to/test_job.svg")

    assert ps.status == PlotterState.IDLE
    info = ps.get_info()
    assert info["current_job"] is None
    assert info["last_completed_svg"] == "/path/to/test_job.svg"


def test_error_state():
    ps = PlotterState()
    ps.start_plot("test_job.svg")
    ps.set_error("USB disconnected")

    assert ps.status == PlotterState.ERROR
    info = ps.get_info()
    assert info["error"] == "USB disconnected"
    assert info["current_job"] is None


def test_cancel_plot_when_idle_returns_false():
    ps = PlotterState()
    assert ps.cancel_plot() is False


def test_cancel_plot_without_active_plotter_returns_false():
    ps = PlotterState()
    ps.start_plot("test_job.svg")
    # No set_active_plotter called, so _active_plotter is None
    assert ps.cancel_plot() is False
    assert ps.status == PlotterState.PLOTTING
