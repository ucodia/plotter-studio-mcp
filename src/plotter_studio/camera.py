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
    quality: int = 90,
) -> Optional[bytes]:
    """Capture a single frame from a webcam, return as JPEG bytes.

    Requests the maximum resolution the camera supports.
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

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes()
    finally:
        cap.release()


def _recompress_jpeg(data: bytes, rotate_degrees: int = 0, quality: int = 90) -> bytes:
    """Re-encode JPEG at the given quality, optionally rotating."""
    import io

    img = Image.open(io.BytesIO(data))
    angle = rotate_degrees % 360
    if angle != 0:
        # PIL rotates counter-clockwise, so negate for clockwise
        img = img.rotate(-angle, expand=True)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def capture_gphoto2(rotate_degrees: int = 0, quality: int = 90) -> Optional[bytes]:
    """Capture a still frame via gphoto2, return as JPEG bytes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Use %f.%C to preserve original filenames and extensions so
        # JPG and RAW files don't overwrite each other
        filename_pattern = str(Path(tmpdir) / "%f.%C")
        try:
            result = subprocess.run(
                [
                    "gphoto2",
                    "--capture-image-and-download",
                    "--filename",
                    filename_pattern,
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
        jpeg_files = [
            f
            for f in Path(tmpdir).iterdir()
            if f.suffix.lower() in (".jpg", ".jpeg")
        ]
        if not jpeg_files:
            logger.error("gphoto2 did not produce a JPEG file")
            return None

        data = jpeg_files[0].read_bytes()
        data = _recompress_jpeg(data, rotate_degrees, quality)
        return data
