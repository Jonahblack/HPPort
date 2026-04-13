import cv2

class Camera:
    def __init__(self, index=0, width=1280, height=720, fps=30, backend='auto'):
        self.cap = None
        self.backend = backend
        if backend == 'picam2':
            try:
                from picamera2 import Picamera2
                from libcamera import Transform
                self.picam2 = Picamera2()
                self.picam2.configure(self.picam2.create_preview_configuration(main={"size": (width, height)}))
                self.picam2.start()
                self.use_picam = True
            except Exception:
                self.use_picam = False
        else:
            self.use_picam = False
        if not self.use_picam:
            self.cap = cv2.VideoCapture(index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.cap.set(cv2.CAP_PROP_FPS, fps)

    def read(self):
        if self.use_picam:
            frame = self.picam2.capture_array()
            return True, frame[:, :, ::-1]  # Picamera2 gives RGB; convert to BGR
        else:
            return self.cap.read()

    def release(self):
        if self.use_picam:
            self.picam2.stop()
        else:
            self.cap.release()
