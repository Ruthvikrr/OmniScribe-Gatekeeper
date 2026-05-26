_model = None


def get_model():
    global _model
    if _model is None:
        try:
            import whisper
        except ImportError as exc:
            raise RuntimeError(
                "Local Whisper is not installed. Install openai-whisper to enable audio transcription."
            ) from exc
        print("Loading Whisper model (first time only)...")
        _model = whisper.load_model("base")
    return _model


def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe an audio file locally using Whisper base model.
    Returns the full transcript as a string.
    """
    model = get_model()
    result = model.transcribe(audio_path)
    return result["text"].strip()
