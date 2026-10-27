
"""Standalone standby test for FRIDAY's wake-word detector."""

from pathlib import Path
import time

import numpy as np
import openwakeword
import sounddevice as sd
from openwakeword.model import Model


SAMPLE_RATE = 16000
CHUNK_SIZE = 1280
THRESHOLD = 0.60
COOLDOWN_SECONDS = 3.0


def main() -> None:
    model_dir = (
        Path(openwakeword.__file__).parent
        / "resources"
        / "models"
    )
    model_path = model_dir / "hey_jarvis_v0.1.onnx"

    if not model_path.is_file():
        raise FileNotFoundError(
            f"Wake-word model not found: {model_path}"
        )

    detector = Model(
        wakeword_model_paths=[str(model_path)],
    )

    print("FRIDAY: Standby mode.")
    print('FRIDAY: Say "Hey Jarvis" to wake me.')
    print("FRIDAY: Press Ctrl+C to stop.\n")

    last_detection = 0.0

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        ) as microphone:
            while True:
                audio, overflowed = microphone.read(CHUNK_SIZE)

                if overflowed:
                    print("FRIDAY: Microphone buffer overflow.")

                scores = detector.predict(
                    np.asarray(audio).reshape(-1)
                )

                now = time.monotonic()

                if now - last_detection < COOLDOWN_SECONDS:
                    continue

                for name, score in scores.items():
                    if score >= THRESHOLD:
                        print(
                            f"FRIDAY: Wake word detected "
                            f"({score:.2f})."
                        )
                        print(
                            "FRIDAY: Standby test continues; "
                            "Whisper has not been started."
                        )
                        last_detection = now
                        break

    except KeyboardInterrupt:
        print("\nFRIDAY: Standby test stopped.")


if __name__ == "__main__":
    main()
