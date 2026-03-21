# Monet

**An MCP server that gives Claude eyes and a robotic arm.**

Named after Claude Monet. Because of course it is.

Monet connects Claude to an AxiDraw pen plotter and webcams via the Model Context Protocol, enabling Claude to compose generative art as SVG, send it to the plotter, watch the result through cameras, and iterate.

## How it works

1. Claude composes SVG artwork sized to your paper
2. Monet sends the SVG to the AxiDraw via pyaxidraw
3. Claude requests pen changes between passes (you do the swap)
4. Claude captures webcam frames to see the result
5. Claude composes the next layer based on what it sees
6. Repeat until the piece is done

## Requirements

- Python 3.10+
- AxiDraw pen plotter (A3 model) with pyaxidraw installed
- One or two USB webcams

## Installation

```bash
git clone https://github.com/ucodia/monet-mcp.git
cd monet-mcp
uv sync
```

## Setup

### 1. Configure Claude Desktop

Add this to your `claude_desktop_config.json`:

```json
{
    "mcpServers": {
        "monet": {
            "command": "uv",
            "args": ["run", "monet"],
            "env": {
                "MONET_INVENTORY": "/path/to/pen_inventory.csv",
                "MONET_PAPER_INVENTORY": "/path/to/paper_inventory.csv",
                "MONET_CAMERA_TOP": "0",
                "MONET_CAMERA_ANGLE": "1",
                "MONET_SVG_DIR": "/path/to/svg/output",
                "MONET_WEBHOOK_URL": "https://ntfy.sh/monet-mcp"
            }
        }
    }
}
```

### 2. Set up your inventories

Copy the templates from `examples/` and fill them with your actual gear:

- **Pen inventory**: `pen_inventory_template.csv` with columns `name`, `type`, `tip_size_mm`, `color`, `notes`
- **Paper inventory**: `paper_inventory_template.csv` with columns `name`, `brand`, `type`, `width_inches`, `height_inches`, `orientation`, `notes`

### 3. Find your camera indices

If you're not sure which index is which camera:

```python
import cv2
for i in range(5):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        print(f"Camera {i}: available")
        cap.release()
```

### 4. Test the connection

Start Claude Desktop. Ask Claude to check the plotter status or capture a camera frame.

## Tools

| Tool | What it does |
|------|-------------|
| `monet_plot_svg` | Send SVG to AxiDraw for plotting (async) |
| `monet_preview_svg` | Save SVG to disk without plotting |
| `monet_get_status` | Check if plotter is idle, plotting, or waiting |
| `monet_request_pen_change` | Ask human to swap the pen |
| `monet_confirm_pen_change` | Human confirms pen is swapped |
| `monet_capture` | Grab a frame from top/angle/both cameras |
| `monet_get_pen_inventory` | List available pens from spreadsheet |
| `monet_get_paper_inventory` | List available papers from spreadsheet |
| `monet_get_paper_info` | Get paper dimensions and coordinate system |
| `monet_move_to` | Move pen to a position (pen up) |
| `monet_pen_up` | Raise the pen |
| `monet_home` | Return to home position |
| `monet_notify` | Send a message to the human operator |

## Paper and coordinate system

- Paper: 11 x 15 inches, Fabriano watercolor, portrait orientation
- SVG coordinate system: 96 DPI (1056 x 1440 pixels)
- Origin: top-left corner of the paper
- Pen starts at (0, 0)

## Project structure

```
src/monet_mcp/
    __init__.py
    server.py       # MCP server, tool definitions, config
    plotter.py      # AxiDraw control and state machine
    camera.py       # Webcam capture
    inventory.py    # Pen and paper inventory loading
    webhook.py      # Push notifications
    svg_utils.py    # SVG wrapping, paper constants
examples/
    pen_inventory_template.csv
    paper_inventory_template.csv
tests/
    test_svg_utils.py
    test_plotter_state.py
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONET_INVENTORY` | (none) | Path to pen inventory .xlsx or .csv |
| `MONET_PAPER_INVENTORY` | (none) | Path to paper inventory .xlsx or .csv |
| `MONET_CAMERA_TOP` | `0` | Video device index for overhead camera |
| `MONET_CAMERA_ANGLE` | `-1` | Video device index for angle camera (-1 = disabled) |
| `MONET_SVG_DIR` | `~/monet_svgs` | Directory to save generated SVGs |
| `MONET_WEBHOOK_URL` | (none) | Webhook URL for push notifications (ntfy.sh supported natively) |

## Notifications

Monet sends push notifications on key events so you don't have to watch the screen. Set `MONET_WEBHOOK_URL` to a [ntfy.sh](https://ntfy.sh) topic URL and subscribe on your phone:

```
MONET_WEBHOOK_URL=https://ntfy.sh/monet-mcp
```

You'll get notified when:
- A plot starts and finishes (or errors)
- A pen change is needed (high priority, so your phone will ping)
- Claude sends you a message via `monet_notify`

Generic JSON webhooks also work. If the URL doesn't contain "ntfy", the server POSTs a JSON body with `event`, `timestamp`, and event-specific fields.

## Notes on specific pen types

**Posca paint markers**: Need to be pumped before use. A spring on the plotter arm helps with pressure. They can clog when plotting overlapping parallel or near-parallel lines. This is a feature, not a bug.

**Brush pens**: Line weight varies with speed and pressure. The plotter produces consistent pressure, so variation comes from speed changes in the motion plan.

**Fine liners**: Most predictable. Good for detailed base layers. 0.05mm tips can dry out during long plots.

## License

AGPL-3.0-or-later
