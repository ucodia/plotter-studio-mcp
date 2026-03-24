"""Webcam capture logic."""

import logging
from typing import Optional

import cv2

logger = logging.getLogger("plotter-studio")


def capture_frame(camera_index: int, rotate_degrees: int = 0) -> Optional[bytes]:
    """Capture a single frame from a webcam, return as JPEG bytes.

    Returns full-resolution JPEG at 80% quality (keeps 1080p under ~500KB).
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return None
    try:
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
                f"PLOTTER_CAMERA_ROTATE={rotate_degrees} is not a multiple of 90, ignoring rotation"
            )

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes()
    finally:
        cap.release()
