"""Voice bonus: speech-to-text for input, browser TTS for output.

No paid API keys required:
- STT uses SpeechRecognition's free Google Web Speech endpoint (rate-limited,
  fine for a demo; not for production volume - documented tradeoff).
- TTS is done client-side via the browser's built-in speechSynthesis API
  (see the render_speak_button HTML snippet), so no server-side TTS call at all.
"""

import io

import speech_recognition as sr

_recognizer = sr.Recognizer()


class TranscriptionError(RuntimeError):
    pass


def transcribe(audio_bytes: bytes) -> str:
    """Transcribe a WAV recording (as produced by st.audio_input) to text.

    English-only by design (language="en-US") - the agent's tool schema,
    airport reference data, and scoring output are all English, so mixed-
    language input would just fail downstream in a confusing way.
    """
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            audio = _recognizer.record(source)
        return _recognizer.recognize_google(audio, language="en-US")
    except sr.UnknownValueError:
        raise TranscriptionError("Could not understand the audio - please try again in English.")
    except sr.RequestError as exc:
        raise TranscriptionError(f"Speech recognition service error: {exc}")


def speak_button_html(text: str, key: str) -> str:
    """A small self-contained button that reads `text` aloud via the
    browser's native speechSynthesis - no server round-trip, no API key.

    Forces English explicitly (utter.lang + picking an "en" voice) rather
    than trusting the browser/OS default voice, which follows system
    locale and would otherwise read English text with whatever voice
    (e.g. Hebrew) the OS happens to default to.
    """
    escaped = text.replace("\\", "\\\\").replace("`", "\\`").replace("</", "<\\/")
    return f"""
    <button id="speak-{key}" style="
        background:#f0f2f6;border:1px solid #d0d2d6;border-radius:6px;
        padding:4px 10px;cursor:pointer;font-size:13px;">
        🔊 Read aloud
    </button>
    <button id="stop-{key}" style="
        background:#f0f2f6;border:1px solid #d0d2d6;border-radius:6px;
        padding:4px 10px;cursor:pointer;font-size:13px;margin-left:6px;">
        ⏹ Stop
    </button>
    <script>
        document.getElementById("speak-{key}").onclick = function() {{
            const utter = new SpeechSynthesisUtterance(`{escaped}`);
            utter.lang = "en-US";
            const voices = window.speechSynthesis.getVoices();
            const enVoice = voices.find(v => v.lang && v.lang.toLowerCase().startsWith("en"));
            if (enVoice) {{ utter.voice = enVoice; }}
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(utter);
        }};
        document.getElementById("stop-{key}").onclick = function() {{
            window.speechSynthesis.cancel();
        }};
    </script>
    """
