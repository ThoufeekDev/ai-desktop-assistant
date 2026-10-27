
"""Local microphone noise suppression using the system RNNoise library."""

import ctypes
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly


class NoiseSuppressionError(RuntimeError):
    """Raised when RNNoise cannot process audio."""


class RNNoiseSuppressor:
    """Suppress background noise in mono float32 audio recorded at 16 kHz."""

    INPUT_RATE = 16_000
    RNNOISE_RATE = 48_000
    FRAME_SIZE = 480

    def __init__(self, library_path: str = "librnnoise.so") -> None:
        try:
            self._library = ctypes.CDLL(library_path)
        except OSError as exc:
            raise NoiseSuppressionError(
                f"Could not load RNNoise library: {exc}"
            ) from exc

        library = self._library

        library.rnnoise_create.argtypes = [ctypes.c_void_p]
        library.rnnoise_create.restype = ctypes.c_void_p

        library.rnnoise_destroy.argtypes = [ctypes.c_void_p]
        library.rnnoise_destroy.restype = None

        library.rnnoise_get_frame_size.argtypes = []
        library.rnnoise_get_frame_size.restype = ctypes.c_int

        library.rnnoise_process_frame.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
        ]
        library.rnnoise_process_frame.restype = ctypes.c_float

        frame_size = library.rnnoise_get_frame_size()
        if frame_size != self.FRAME_SIZE:
            raise NoiseSuppressionError(
                f"Expected {self.FRAME_SIZE} RNNoise samples, "
                f"but the library reports {frame_size}."
            )

        self._state = library.rnnoise_create(None)
        if not self._state:
            raise NoiseSuppressionError("RNNoise state creation failed.")



    def process_frame(self, audio: np.ndarray) -> np.ndarray:
        """Suppress noise in one 10 ms mono float32 frame at 16 kHz."""
        if self._state is None:
            raise RuntimeError("RNNoiseSuppressor is closed.")

        if not isinstance(audio, np.ndarray):
            raise TypeError("Audio must be a NumPy array.")

        if audio.ndim != 1 or audio.shape[0] != 160:
            raise ValueError("Expected exactly 160 mono samples at 16 kHz.")

        if audio.dtype != np.float32:
            raise TypeError("Audio must use float32 samples.")

        if not np.all(np.isfinite(audio)):
            raise ValueError("Audio contains invalid numeric samples.")

        # One 160-sample frame at 16 kHz becomes 480 samples at 48 kHz.
        audio_48k = resample_poly(audio, 3, 1).astype(np.float32)

        # RNNoise expects samples scaled similarly to signed 16-bit PCM.
        audio_scaled = np.clip(
            audio_48k * 32768.0, -32768.0, 32767.0
        ).astype(np.float32)

        output_frame = np.empty(self.FRAME_SIZE, dtype=np.float32)

        self._library.rnnoise_process_frame(
            self._state,
            output_frame.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            audio_scaled.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
        )

        # Restore the original 16 kHz float32 audio format.
        output_16k = resample_poly(output_frame / 32768.0, 1, 3)

        return output_16k[:160].astype(np.float32, copy=False)

    def process(self, audio: np.ndarray) -> np.ndarray:
        """Process mono float32 audio at 16 kHz and return 16 kHz audio."""
        if self._state is None:
            raise RuntimeError("RNNoiseSuppressor is closed.")

        if not isinstance(audio, np.ndarray):
            raise TypeError("Audio must be a NumPy array.")

        if audio.ndim != 1:
            raise ValueError("Audio must be mono (one-dimensional).")

        if audio.dtype != np.float32:
            raise TypeError("Audio must use float32 samples.")

        if not np.all(np.isfinite(audio)):
            raise ValueError("Audio contains invalid numeric samples.")

        if audio.size == 0:
            return audio.copy()

        # Convert 16 kHz audio to RNNoise's required 48 kHz rate.
        audio_48k = resample_poly(audio, 3, 1).astype(np.float32)

        # RNNoise expects float samples scaled like signed 16-bit PCM.
        audio_scaled = np.clip(
            audio_48k * 32768.0, -32768.0, 32767.0
        ).astype(np.float32)

        frame_count = (
            audio_scaled.size + self.FRAME_SIZE - 1
        ) // self.FRAME_SIZE

        padded_size = frame_count * self.FRAME_SIZE
        padded = np.pad(
            audio_scaled,
            (0, padded_size - audio_scaled.size),
        )

        output = np.empty_like(padded)

        try:
            for offset in range(0, padded_size, self.FRAME_SIZE):
                input_frame = np.ascontiguousarray(
                    padded[offset : offset + self.FRAME_SIZE],
                    dtype=np.float32,
                )
                output_frame = np.empty(
                    self.FRAME_SIZE, dtype=np.float32
                )

                self._library.rnnoise_process_frame(
                    self._state,
                    output_frame.ctypes.data_as(
                        ctypes.POINTER(ctypes.c_float)
                    ),
                    input_frame.ctypes.data_as(
                        ctypes.POINTER(ctypes.c_float)
                    ),
                )

                output[offset : offset + self.FRAME_SIZE] = output_frame
        except Exception as exc:
            raise NoiseSuppressionError(
                f"RNNoise audio processing failed: {exc}"
            ) from exc

        # Return to the input rate and restore float32 audio scale.
        output_48k = output[: audio_scaled.size] / 32768.0
        output_16k = resample_poly(output_48k, 1, 3)

        return output_16k[: audio.size].astype(np.float32, copy=False)

    def close(self) -> None:
        """Release the RNNoise processing state."""
        if self._state:
            self._library.rnnoise_destroy(self._state)
            self._state = None

    def __enter__(self) -> "RNNoiseSuppressor":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
