
from pathlib import Path
import time

import openwakeword
import sounddevice as sd
from openwakeword.model import Model


SAMPLE_RATE = 16000
CHUNK_SIZE = 1280
THRESHOLD = 0.5
COOLDOWN_SECONDS = 2.0


def main():
    model_dir = Path(openwakeword.__file__).parent / "resources" / "models"
    model_path = model_dir / "hey_jarvis_v0.1.onnx"

    if not model_path.is_file():
        raise FileNotFoundError(f"Wake-word model not found: {model_path}")

    detector = Model(
        wakeword_model_paths=[str(model_path)],

    )

    print("FRIDAY wake-word test started.")
    print("Say: Hey Jarvis")
    print("Press Ctrl+C to stop.\n")

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
                    print("Warning: microphone audio overflowed.")

                predictions = detector.predict(audio.reshape(-1))

                now = time.monotonic()
                if now - last_detection < COOLDOWN_SECONDS:
                    continue

                for name, score in predictions.items():
                    if score >= THRESHOLD:
                        print(f"Wake word detected: {name} ({score:.2f})")
                        last_detection = now
                        break

    except KeyboardInterrupt:
        print("\nWake-word test stopped.")


if __name__ == "__main__":
    main()
