from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray
from skimage.filters import threshold_sauvola


def order_points(pts: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """
    Order points in the sequence: top-left, top-right, bottom-right, bottom-left.

    Args:
        pts: Array of four points

    Returns:
        NDArray[np.uint8]: Ordered points
    """
    rect = np.zeros((4, 2), dtype="float32")

    # top-left point has the smallest sum
    # bottom-right point has the largest sum
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    # compute the difference between the points
    # top-right has the smallest difference
    # bottom-left has the largest difference
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]

    return rect


def preprocess_image(image_path: str) -> str:
    """
    Process a screenshot of an Excel table by binarizing, finding table boundaries,
    and applying perspective correction.

    Args:
        image_path: Path to the image file or a numpy array containing the image

    Returns:
        str: Processed image with corrected perspective and binarized content
    """
    img = cv2.imread(image_path)

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Normalize brightness and contrast
    # 1. CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=0.5, tileGridSize=(8, 8))
    normalized = clahe.apply(gray)

    # 2. Normalize to full dynamic range
    normalized = cv2.normalize(normalized, None, 0, 255, cv2.NORM_MINMAX)

    # 3. Apply Gaussian blur to reduce noise
    blur = cv2.GaussianBlur(normalized, (5, 5), 0)

    # 4. Enhance contrast with unsharp mask
    gaussian = cv2.GaussianBlur(blur, (0, 0), 3)
    unsharp_mask = cv2.addWeighted(blur, 1.5, gaussian, -0.5, 0)

    # Edge detection
    edges = cv2.Canny(unsharp_mask, 40, 100, apertureSize=3)

    # Dilate to connect edge fragments
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=1)

    # Find contours
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filter contours by area and shape
    min_area = 0.1 * img.shape[0] * img.shape[1]  # At least 10% of image
    filtered_contours = [cnt for cnt in contours if cv2.contourArea(cnt) > min_area]

    if filtered_contours:
        # Find the contour that most resembles a rectangle
        best_contour = None
        best_score = 0

        for contour in filtered_contours:
            # Approximate the contour
            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)

            # Check if it's a quadrilateral
            if len(approx) == 4:
                # Calculate rectangle-likeness score
                area = cv2.contourArea(approx)
                x, y, w, h = cv2.boundingRect(approx)
                rect_area = w * h
                area_ratio = area / rect_area if rect_area > 0 else 0

                # The closer to 1, the more rectangle-like
                if area_ratio > best_score:
                    best_score = area_ratio
                    best_contour = approx

        # If we didn't find a good quadrilateral, use the largest contour
        if best_contour is None:
            largest_contour = max(filtered_contours, key=cv2.contourArea)
            # Approximate to get a polygon
            epsilon = 0.02 * cv2.arcLength(largest_contour, True)
            best_contour = cv2.approxPolyDP(largest_contour, epsilon, True)

        # If the contour has more or less than 4 points, find the bounding rectangle
        if len(best_contour) != 4:
            x, y, w, h = cv2.boundingRect(best_contour)
            best_contour = np.array(
                [[[x, y]], [[x + w, y]], [[x + w, y + h]], [[x, y + h]]]
            )

        # Reshape to get 4 points
        pts = best_contour.reshape(len(best_contour), 2)

        # If we have 4 points, process the perspective correction
        if len(pts) == 4:
            # Order points in the correct sequence
            rect = order_points(pts)

            # Calculate the width and height of the new image
            width_a = np.sqrt(
                ((rect[1][0] - rect[0][0]) ** 2) + ((rect[1][1] - rect[0][1]) ** 2)
            )
            width_b = np.sqrt(
                ((rect[3][0] - rect[2][0]) ** 2) + ((rect[3][1] - rect[2][1]) ** 2)
            )
            max_width = max(int(width_a), int(width_b))

            height_a = np.sqrt(
                ((rect[0][0] - rect[3][0]) ** 2) + ((rect[0][1] - rect[3][1]) ** 2)
            )
            height_b = np.sqrt(
                ((rect[1][0] - rect[2][0]) ** 2) + ((rect[1][1] - rect[2][1]) ** 2)
            )
            max_height = max(int(height_a), int(height_b))

            # Define destination points for the perspective transform
            dst = np.array(
                [
                    [0, 0],
                    [max_width - 1, 0],
                    [max_width - 1, max_height - 1],
                    [0, max_height - 1],
                ],
                dtype="float32",
            )

            # Calculate the perspective transform matrix and apply it
            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(normalized, M, (max_width, max_height))

            # Apply adaptive thresholding with Sauvola method (better for document images)
            thresh_sauvola = threshold_sauvola(warped, window_size=15, k=0.2)
            warped_binary = (warped > thresh_sauvola).astype(np.uint8) * 255
            output_path = (
                Path(image_path)
                .with_stem(Path(image_path).stem + "_binarized")
                .with_suffix(".jpg")
            )
            cv2.imwrite(output_path, warped_binary)
            return output_path

    # If no suitable contour found, return the binarized original image using Sauvola thresholding
    thresh_sauvola = threshold_sauvola(normalized, window_size=15, k=0.2)
    simple_binary = (normalized > thresh_sauvola).astype(np.uint8) * 255
    output_path = (
        Path(image_path)
        .with_stem(Path(image_path).stem + "_binarized")
        .with_suffix(".jpg")
    )
    cv2.imwrite(output_path, simple_binary)
    return output_path
