
"""Local wake-word detection for JARVIS."""

import math
import time
import warnings
import threading
from collections import deque
from pathlib import Path

import numpy as np
import openwakeword
import sounddevice as sd
from openwakeword.model import Model

# Suppress the CUDA provider warning when ONNX Runtime falls back to CPU.
warnings.filterwarnings(
    "ignore",
    message=r".*CUDAExecutionProvider.*",
    category=UserWarning,
)


class WakeWordDetector:
    """Wait for the configured wake word using the microphone."""

    def __init__(
        self,
        model_path: Path | str | None = None,
        threshold: float = 0.5,
        sample_rate: int = 16000,
        chunk_size: int = 1280,
    ) -> None:
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold)
        ):
            raise ValueError("Wake-word threshold must be a finite number.")

        if not 0.0 < threshold <= 1.0:
            raise ValueError(
                "Wake-word threshold must be between 0.0 and 1.0."
            )

        if (
            isinstance(sample_rate, bool)
            or not isinstance(sample_rate, int)
            or sample_rate != 16000
        ):
            raise ValueError("Wake-word sample_rate must be 16000 Hz.")

        if (
            isinstance(chunk_size, bool)
            or not isinstance(chunk_size, int)
            or chunk_size <= 0
            or chunk_size % 1280 != 0
        ):
            raise ValueError(
                "chunk_size must be a positive multiple of 1280 samples."
            )

        # Use OpenWakeWord's original, bundled Hey Jarvis model.
        if model_path is None:
            resolved_path = (
                Path(openwakeword.__file__).resolve().parent
                / "resources"
                / "models"
                / "hey_jarvis_v0.1.onnx"
            )
        else:
            resolved_path = Path(model_path).expanduser().resolve()

        if not resolved_path.is_file():
            raise FileNotFoundError(
                f"Wake-word model not found: {resolved_path}"
            )

        self.model_path = resolved_path
        self.threshold = float(threshold)
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size

        try:
            self.detector = Model(
                wakeword_model_paths=[str(resolved_path)],
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load wake-word model '{resolved_path}': {exc}"
            ) from exc

        expected_name = resolved_path.stem
        if expected_name in self.detector.models:
            self.model_key = expected_name
        elif self.detector.models:
            self.model_key = next(iter(self.detector.models))
        else:
            raise RuntimeError(
                f"No wake-word model was loaded from {resolved_path}."
            )

    def wait_until_detected(
        self,
        stream: sd.InputStream | None = None,
        return_stream: bool = True,
        stop_event: threading.Event | None = None,
    ) -> tuple[sd.InputStream, np.ndarray] | None:
        """Wait for 'Hey Jarvis' and optionally preserve the active stream."""

        self.detector.reset()

        print(
            f'JARVIS: Standing by. Say "Hey Jarvis" '
            f"(threshold: {self.threshold:.2f})."
        )

        owned_stream: sd.InputStream | None = None

        if stream is None:
            try:
                active_stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=self.chunk_size,
                )
                active_stream.start()
                owned_stream = active_stream
            except (sd.PortAudioError, OSError) as exc:
                raise RuntimeError(
                    f"Could not open microphone for wake-word detection: {exc}"
                ) from exc
        else:
            active_stream = stream
            if not active_stream.active:
                try:
                    active_stream.start()
                except (sd.PortAudioError, OSError) as exc:
                    raise RuntimeError(
                        f"Could not start microphone stream: {exc}"
                    ) from exc

        last_diagnostic_time = 0.0
        rolling_buffer: deque[np.ndarray] = deque(maxlen=2)

        try:
            while stop_event is None or not stop_event.is_set():
                try:
                    audio, overflowed = active_stream.read(self.chunk_size)
                except (sd.PortAudioError, OSError) as exc:
                    raise RuntimeError(
                        f"Microphone read error during wake-word detection: {exc}"
                    ) from exc
                if stop_event is not None and stop_event.is_set():
                    return None                    

                if overflowed:
                    print("\nJARVIS: Microphone buffer overflow.")

                chunk = np.asarray(audio, dtype=np.int16).reshape(-1)
                rolling_buffer.append(chunk)

                scores = self.detector.predict(chunk)
                score = float(
                    scores.get(
                        self.model_key,
                        max(scores.values(), default=0.0),
                    )
                )

                now = time.monotonic()

                if score >= self.threshold:
                    print(
                        f"\nJARVIS: 'Hey Jarvis' detected "
                        f"(score: {score:.3f}, threshold: "
                        f"{self.threshold:.2f}). I'm listening..."
                    )

                    # Preserve recent audio for speech-recognition handoff.
                    post_wake = (
                        np.concatenate(list(rolling_buffer)).astype(np.float32)
                        / 32768.0
                    )

                    if return_stream:
                        # Transfer stream ownership to the caller.
                        # The finally block must not close this stream.
                        owned_stream = None
                        return active_stream, post_wake

                    if owned_stream is not None:
                        owned_stream.close()
                        owned_stream = None

                    return None

                if score >= 0.05 or now - last_diagnostic_time >= 1.0:
                    print(
                        f"\rJARVIS: Waiting for 'Hey Jarvis' "
                        f"(score: {score:.3f} / "
                        f"threshold: {self.threshold:.2f})  ",
                        end="",
                        flush=True,
                    )
                    last_diagnostic_time = now

        except KeyboardInterrupt:
            print("\nJARVIS: Wake-word detection stopped.")
            raise

        finally:
            # Only close streams created by this method. A caller-supplied
            # stream remains owned by the caller.
            if owned_stream is not None:
                try:
                    owned_stream.close()
                except Exception:
                    pass
