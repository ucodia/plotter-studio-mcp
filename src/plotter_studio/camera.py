"""Webcam and gphoto2 capture logic."""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import cv2
from PIL import Image

logger = logging.getLogger("plotter-studio")


def capture_frame(
    camera_index: int,
    rotate_degrees: int = 0,
) -> Optional[bytes]:
    """Capture a single frame from a webcam, return as JPEG bytes.

    Requests the maximum resolution the camera supports and returns
    a JPEG at 90% quality.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 10000)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 10000)
        for _ in range(5):
            cap.read()
        ret, frame = cap.read()
        if not ret:
            return None

        angle = rotate_degrees % 360
        if angle == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif angle == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        elif angle != 0:
            logger.warning(
                f"Camera rotation {rotate_degrees} is not a multiple of 90, ignoring"
            )

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return buf.tobytes()
    finally:
        cap.release()


def _rotate_jpeg(data: bytes, rotate_degrees: int) -> bytes:
    """Rotate JPEG bytes using Pillow and return as JPEG."""
    import io

    angle = rotate_degrees % 360
    if angle == 0:
        return data

    img = Image.open(io.BytesIO(data))
    # PIL rotates counter-clockwise, so negate for clockwise
    img = img.rotate(-angle, expand=True)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def capture_gphoto2(rotate_degrees: int = 0) -> Optional[bytes]:
    """Capture a still frame via gphoto2, return as JPEG bytes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outpath = Path(tmpdir) / "capture.jpg"
        try:
            result = subprocess.run(
                [
                    "gphoto2",
                    "--capture-image-and-download",
                    "--filename",
                    str(outpath),
                    "--force-overwrite",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            logger.error("gphoto2 is not installed")
            return None
        except subprocess.TimeoutExpired:
            logger.error("gphoto2 capture timed out")
            return None

        if result.returncode != 0:
            logger.error(f"gphoto2 failed: {result.stderr.strip()}")
            return None

        # gphoto2 may save multiple files (JPG + RAW), find the JPEG
        jpeg_files = list(Path(tmpdir).glob("*.jpg"))
        if not jpeg_files:
            logger.error("gphoto2 did not produce a JPEG file")
            return None

        data = jpeg_files[0].read_bytes()
        if rotate_degrees % 360 != 0:
            data = _rotate_jpeg(data, rotate_degrees)
        return data
