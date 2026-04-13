import numpy as np
from rembg import remove
from PIL import Image

def alpha_cutout(face_bgr):
    img = Image.fromarray(face_bgr[:, :, ::-1])  # BGR->RGB
    out = remove(img)  # PIL Image RGBA
    return np.array(out)[:, :, ::-1]  # BGRA
