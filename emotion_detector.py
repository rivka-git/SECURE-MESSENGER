from deepface import DeepFace
import cv2

def get_current_emotion(frame=None):
    """Analyze emotion from a provided frame or from the local camera."""
    if frame is None:
        # פותחים מצלמה רק לרגע אחד
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        if not ret:
            cap.release()
            return "neutral"
        cap.release()

    try:
        # ניתוח הרגש
        results = DeepFace.analyze(frame, actions=['emotion'], enforce_detection=False)
        emotion = results[0]['dominant_emotion']
    except:
        emotion = "neutral"
    
    return emotion