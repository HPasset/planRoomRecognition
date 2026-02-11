from __future__ import annotations

from typing import Iterable

import cv2
import easyocr


def preprocess_for_plans(img_bgr, scale: int = 2):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # Upscale for better OCR on plans.
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    thr = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        5,
    )
    return thr, scale


class OCREngine:
    def __init__(self, langs: Iterable[str], gpu: bool = False) -> None:
        self._reader = easyocr.Reader(list(langs), gpu=gpu)

    def read(self, img_bgr, preprocess: bool = True):
        if preprocess:
            img, scale = preprocess_for_plans(img_bgr)
        else:
            img, scale = img_bgr, 1
        results = self._reader.readtext(img)  # [(bbox, text, conf), ...]
        items = []
        for bbox, text, conf in results:
            if scale != 1:
                bbox = [[p[0] / scale, p[1] / scale] for p in bbox]
            bbox_py = [[int(p[0]), int(p[1])] for p in bbox]
            items.append(
                {
                    "text": text,
                    "bbox": bbox_py,
                    "confidence": float(conf),
                }
            )
        return items
