"""
emoji_mapper.py — Maps emotions to emojis for enhanced messaging.
"""

EMOTION_EMOJI_MAP = {
    "happy": "�",
    "sad": "😢",
    "angry": "😡",
    "fear": "😱",
    "surprise": "😲",
    "disgust": "🤢",
    "neutral": "😐",
}

def emotion_to_emoji(emotion: str) -> str:
    """Convert emotion to emoji. Returns neutral emoji if emotion not found."""
    return EMOTION_EMOJI_MAP.get(emotion.lower(), "😐")

def get_all_emotions() -> dict:
    """Return the complete emotion→emoji mapping."""
    return EMOTION_EMOJI_MAP.copy()
