"""Webcam capture logic."""

import base64
from typing import Optional

import cv2


def _capture_frame(camera_index: int) -> Optional[str]:
    """Capture a single frame from a webcam, return as base64 JPEG."""
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return None
    try:
        # Give the camera a moment to adjust exposure
        for _ in range(5):
            cap.read()
        ret, frame = cap.read()
        if not ret:
            return None
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return base64.b64encode(buf.tobytes()).decode("utf-8")
    finally:
        cap.release()
