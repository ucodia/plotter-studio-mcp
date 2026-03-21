"""Tests for PlotterState state machine."""

from monet_mcp.plotter import PlotterState


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


def test_pen_change_request_and_confirm():
    ps = PlotterState()

    ps.request_pen_change("Sakura Micron 0.05mm black")
    assert ps.status == PlotterState.WAITING_PEN_CHANGE
    info = ps.get_info()
    assert info["requested_pen"] == "Sakura Micron 0.05mm black"

    ps.confirm_pen_change()
    assert ps.status == PlotterState.IDLE
    info = ps.get_info()
    assert info["requested_pen"] is None


def test_pen_change_wait_returns_immediately_after_confirm():
    ps = PlotterState()
    ps.request_pen_change("Posca 0.7mm white")
    ps.confirm_pen_change()

    # Should return True immediately since event is already set
    assert ps.wait_for_pen_change(timeout=0.1) is True


def test_pen_change_wait_times_out():
    ps = PlotterState()
    ps.request_pen_change("Posca 0.7mm white")

    # Should time out since nobody confirmed
    assert ps.wait_for_pen_change(timeout=0.05) is False


def test_full_lifecycle():
    """Test a full plotting cycle: idle -> plot -> idle -> pen change -> idle -> plot -> idle."""
    ps = PlotterState()
    assert ps.status == PlotterState.IDLE

    # First plot
    ps.start_plot("layer1.svg")
    assert ps.status == PlotterState.PLOTTING
    ps.finish_plot("/svgs/layer1.svg")
    assert ps.status == PlotterState.IDLE

    # Pen change
    ps.request_pen_change("red marker")
    assert ps.status == PlotterState.WAITING_PEN_CHANGE
    ps.confirm_pen_change()
    assert ps.status == PlotterState.IDLE

    # Second plot
    ps.start_plot("layer2.svg")
    assert ps.status == PlotterState.PLOTTING
    ps.finish_plot("/svgs/layer2.svg")
    assert ps.status == PlotterState.IDLE
    assert ps.get_info()["last_completed_svg"] == "/svgs/layer2.svg"
