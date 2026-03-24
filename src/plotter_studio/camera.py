"""Webcam capture logic."""

from typing import Optional

import cv2


def capture_frame(camera_index: int) -> Optional[bytes]:
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
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes()
    finally:
        cap.release()
