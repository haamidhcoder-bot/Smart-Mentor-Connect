import os
import uuid

import cv2
import numpy as np

# Where captured face images are stored on disk. Teacher.face_id / Admin.face_id
# store just the filename (short, fits in the existing String(200) column) -
# not the image data itself.
FACE_ID_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "face_ids"
)
os.makedirs(FACE_ID_DIR, exist_ok=True)

# Faces are cropped and resized to this size before comparing, so
# registration and login captures (which are rarely the same resolution
# or framing) line up.
FACE_SIZE = (200, 200)

# LBPH's predict() returns a "confidence" score that is really a distance:
# 0 means pixel-identical, and it climbs the less alike two faces are.
# This threshold is deliberately on the strict side, since classical
# face-matching like LBPH can't tell people apart as sharply as a modern
# deep-learning model can - keeping it tight trades a few more "please
# retry" prompts for fewer wrong-person accepts. It's a plain number you
# can tune: lower = stricter (more retries), higher = more lenient (more
# risk of a false accept). Pair this with the username lookup already
# done in auth.py, which narrows matching to one specific stored face
# instead of the whole database.
MATCH_THRESHOLD = 55

# Haar cascade face detector bundled with OpenCV. This finds *where* a
# face is in the frame so we compare faces to faces, not faces to
# whatever happens to be in the background.
_face_detector = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def _decode(image_bytes):
    """Decode raw image bytes (e.g. an uploaded JPEG) into a BGR image."""
    arr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _extract_face(img):
    """
    Find the largest face in a BGR image and return it as a normalized
    grayscale crop ready for comparison, or None if no face was found.

    Steps (each one is a standard, well-documented OpenCV building block):
      1. Convert to grayscale - face detection works on brightness patterns.
      2. Detect faces with the Haar cascade classifier.
      3. Keep the largest detected face (closest / most prominent one).
      4. Crop to just that face, resize to a fixed size, and equalize the
         histogram so differences in lighting don't skew the comparison.
    """
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = _face_detector.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
    )

    if len(faces) == 0:
        return None

    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    face = gray[y:y + h, x:x + w]
    face = cv2.resize(face, FACE_SIZE)
    face = cv2.equalizeHist(face)
    return face


def face_detected(image_bytes):
    """True if a usable face can be found in the given image bytes."""
    return _extract_face(_decode(image_bytes)) is not None


def save_face(file_storage):
    """
    Save an uploaded face image (Flask FileStorage) to disk.

    Returns the filename to store in Teacher.face_id / Admin.face_id.
    """
    filename = f"{uuid.uuid4().hex}.jpg"
    file_storage.save(os.path.join(FACE_ID_DIR, filename))
    return filename


def match_face(stored_filename, captured_bytes):
    """
    Compare a freshly captured face (raw image bytes) against a
    previously stored one (filename in FACE_ID_DIR, as saved by
    save_face). Returns True if they're similar enough to be
    considered the same person.

    Uses OpenCV's LBPH (Local Binary Pattern Histogram) face recognizer:
    it summarizes the texture pattern around each pixel of the face into
    a histogram, then measures how different two faces' histograms are.
    It's a well-established, lightweight face-recognition algorithm - no
    GPU or external model download needed - and considerably more
    reliable than comparing whole raw photos, since it only looks at the
    detected face region rather than the background.
    """
    if not stored_filename:
        return False

    stored_path = os.path.join(FACE_ID_DIR, stored_filename)
    if not os.path.exists(stored_path):
        return False

    stored_img = cv2.imread(stored_path, cv2.IMREAD_COLOR)
    stored_face = _extract_face(stored_img)
    captured_face = _extract_face(_decode(captured_bytes))

    if stored_face is None or captured_face is None:
        return False

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train([stored_face], np.array([0]))
    _, distance = recognizer.predict(captured_face)

    return distance <= MATCH_THRESHOLD
