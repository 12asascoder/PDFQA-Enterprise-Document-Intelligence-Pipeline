"""
PDFQA Pipeline — OCR Image Preprocessor

Applies a sequence of OpenCV transformations to improve Tesseract
accuracy on scanned/image-based PDF pages:

1. Grayscale conversion
2. Adaptive thresholding
3. Denoising
4. Deskewing
5. Sharpening
6. Orientation correction (via Tesseract OSD)
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2  # type: ignore[import-untyped]
import numpy as np
from numpy.typing import NDArray
from PIL import Image

import pytesseract  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """Stateless image preprocessor for OCR optimisation."""

    def preprocess(self, image: Image.Image) -> Image.Image:
        """Apply the full preprocessing pipeline and return a PIL Image."""
        arr = np.array(image)

        arr = self._to_grayscale(arr)
        arr = self._adaptive_threshold(arr)
        arr = self._denoise(arr)
        arr = self._deskew(arr)
        arr = self._sharpen(arr)
        arr = self._correct_orientation(arr)

        return Image.fromarray(arr)

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------
    @staticmethod
    def _to_grayscale(img: NDArray) -> NDArray:
        """Convert to single-channel grayscale if needed."""
        if len(img.shape) == 3:
            return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        return img

    @staticmethod
    def _adaptive_threshold(img: NDArray) -> NDArray:
        """Apply adaptive Gaussian thresholding."""
        try:
            return cv2.adaptiveThreshold(
                img, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=11,
                C=2,
            )
        except cv2.error:
            logger.debug("Adaptive threshold failed — skipping")
            return img

    @staticmethod
    def _denoise(img: NDArray) -> NDArray:
        """Remove noise using non-local means denoising."""
        try:
            return cv2.fastNlMeansDenoising(img, h=10)
        except cv2.error:
            logger.debug("Denoising failed — skipping")
            return img

    @staticmethod
    def _deskew(img: NDArray) -> NDArray:
        """Correct skew using the minimum-area bounding rectangle."""
        try:
            coords = np.column_stack(np.where(img > 0))
            if coords.size == 0:
                return img
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            if abs(angle) < 0.5:
                return img  # negligible skew
            (h, w) = img.shape[:2]
            center = (w // 2, h // 2)
            matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
            return cv2.warpAffine(
                img, matrix, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
        except Exception:
            logger.debug("Deskew failed — skipping")
            return img

    @staticmethod
    def _sharpen(img: NDArray) -> NDArray:
        """Apply an unsharp-mask sharpening kernel."""
        try:
            blurred = cv2.GaussianBlur(img, (0, 0), 3)
            return cv2.addWeighted(img, 1.5, blurred, -0.5, 0)
        except cv2.error:
            logger.debug("Sharpen failed — skipping")
            return img

    @staticmethod
    def _correct_orientation(img: NDArray) -> NDArray:
        """Auto-rotate using Tesseract OSD (orientation and script detection)."""
        try:

            pil_img = Image.fromarray(img)
            osd = pytesseract.image_to_osd(pil_img, output_type=pytesseract.Output.DICT)
            rotation = osd.get("rotate", 0)
            if rotation and rotation != 0:
                logger.debug("OSD detected rotation: %d°", rotation)
                (h, w) = img.shape[:2]
                center = (w // 2, h // 2)
                matrix = cv2.getRotationMatrix2D(center, -rotation, 1.0)
                # Compute new bounding dimensions
                cos_a = abs(matrix[0, 0])
                sin_a = abs(matrix[0, 1])
                nw = int(h * sin_a + w * cos_a)
                nh = int(h * cos_a + w * sin_a)
                matrix[0, 2] += (nw / 2) - center[0]
                matrix[1, 2] += (nh / 2) - center[1]
                return cv2.warpAffine(img, matrix, (nw, nh),
                                       flags=cv2.INTER_CUBIC,
                                       borderMode=cv2.BORDER_REPLICATE)
        except Exception:
            # OSD may fail on very small or blank images — silently skip
            logger.debug("Orientation correction skipped")
        return img
