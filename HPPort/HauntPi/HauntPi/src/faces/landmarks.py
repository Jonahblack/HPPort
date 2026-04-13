import numpy as np, cv2

# Optional MediaPipe landmarks
try:
    import mediapipe as mp
    _mp_face_mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=True, refine_landmarks=True, max_num_faces=1)
except Exception:
    _mp_face_mesh = None

EYE_LEFT_IDX = 33
EYE_RIGHT_IDX = 263
MOUTH_CENTER_IDX = 13
CHIN_IDX = 152

def mediapipe_landmarks(face_bgr):
    if _mp_face_mesh is None: return None
    rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
    res = _mp_face_mesh.process(rgb)
    if not res.multi_face_landmarks: return None
    lm = res.multi_face_landmarks[0].landmark
    h, w = face_bgr.shape[:2]
    def p(i): 
        pt = lm[i]; return np.array([int(pt.x*w), int(pt.y*h)], dtype=np.int32)
    return np.stack([p(EYE_LEFT_IDX), p(EYE_RIGHT_IDX), p(MOUTH_CENTER_IDX), p(CHIN_IDX)], axis=0)
