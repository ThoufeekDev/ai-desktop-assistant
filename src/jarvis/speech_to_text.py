"""Local speech recognition for JARVIS using faster-whisper."""

import re
import time
from collections import deque
from collections.abc import Callable

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from jarvis.noise_suppression import RNNoiseSuppressor


class SpeechToText:
    """Record speech automatically and transcribe it locally."""

    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        sample_rate: int = 16000,
        device: str = "cuda",
        compute_type: str = "float16",
    ) -> None:
        if sample_rate != RNNoiseSuppressor.INPUT_RATE:
            raise ValueError(
                "RNNoise requires a microphone sample rate of 16000 Hz."
            )

        self.model_size = model_size
        self.sample_rate = sample_rate
        self.device = device
        self.compute_type = compute_type
        self._model: WhisperModel | None = None

        # Recording and voice-activity settings.
        self.silence_seconds = 1.2
        self.speech_timeout = 8.0
        self.max_recording_seconds = 20.0
        self.volume_threshold = 0.015
        self.pre_roll_seconds = 0.3
        self.barge_in_grace_seconds = 0.50
        self.barge_in_min_threshold = 0.045

        # Local noise suppression.
        self.noise_suppressor: RNNoiseSuppressor | None = (
            RNNoiseSuppressor()
        )

    def close(self) -> None:
        """Release the RNNoise processing state."""
        if self.noise_suppressor is not None:
            self.noise_suppressor.close()
            self.noise_suppressor = None

    def _suppress_noise(self, audio: np.ndarray) -> np.ndarray:
        """Suppress noise in a complete mono recording."""
        if self.noise_suppressor is None:
            raise RuntimeError(
                "The noise suppressor is closed. Create a new "
                "SpeechToText instance before listening again."
            )

        return self.noise_suppressor.process(
            np.asarray(audio, dtype=np.float32).reshape(-1)
        )

    @staticmethod
    def _preload_nvidia_libraries() -> None:
        """Preload bundled NVIDIA CUDA/cuBLAS/cuDNN libraries from site-packages if available."""
        import ctypes
        import sys
        from pathlib import Path

        seen_dirs = set()
        for p in sys.path:
            p_obj = Path(p)
            if p_obj.is_dir() and "site-packages" in p:
                nvidia_dir = p_obj / "nvidia"
                if nvidia_dir.is_dir():
                    for lib_dir in nvidia_dir.glob("*/lib"):
                        d_str = str(lib_dir)
                        if d_str not in seen_dirs:
                            seen_dirs.add(d_str)
                            for so_file in sorted(lib_dir.glob("*.so*")):
                                try:
                                    ctypes.CDLL(str(so_file))
                                except Exception:
                                    pass

    def _load_model(self) -> WhisperModel:
        """Load Whisper once, then reuse the same model."""
        if self._model is None:
            if self.device == "cuda":
                self._preload_nvidia_libraries()

            print(f"JARVIS: Loading Whisper '{self.model_size}' model...")
            try:
                self._model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Could not load Whisper on {self.device} "
                    f"using {self.compute_type}: {exc}"
                ) from exc

        return self._model

    def _transcribe(self, audio: np.ndarray) -> str:
        """Transcribe a mono float32 audio recording."""
        if audio.size == 0:
            return ""

        try:
            model = self._load_model()
            segments, _ = model.transcribe(
                audio,
                language="en",
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                condition_on_previous_text=False,
            )

            # Iterating the generator performs the actual transcription.
            transcript = " ".join(
                segment.text.strip() for segment in segments
            ).strip()

        except Exception as exc:
            raise RuntimeError(
                f"Speech recognition failed: {exc}"
            ) from exc

        if not transcript:
            print(
                "JARVIS: I couldn't detect any speech. "
                "Try speaking clearly and closer to the microphone."
            )
            return ""

        # Strip accidental wake-word prefix (e.g. "Jarvis, what is the weather")
        cleaned_transcript = re.sub(
            r"^(hey\s+)?jarvis[,.\s]*", "", transcript, flags=re.IGNORECASE
        ).strip()
        final_transcript = cleaned_transcript if cleaned_transcript else transcript

        print(f"You said: {final_transcript}")
        return final_transcript

    def listen_once(
        self,
        stream: sd.InputStream | None = None,
        initial_audio: np.ndarray | None = None,
    ) -> str:
        """Record one utterance, stopping after silence.

        Supports taking an existing active microphone stream and initial audio
        buffer to enable smooth handoff from the wake-word detector without dropping
        speech frames.
        """
        if self.noise_suppressor is None:
            raise RuntimeError(
                "The noise suppressor is closed. "
                "Create a new SpeechToText instance before listening."
            )

        block_size = 1280  # 80 ms at 16 kHz (matches openWakeWord and prevents buffer overflows)
        silence_blocks_needed = max(
            1,
            int(self.silence_seconds * self.sample_rate / block_size),
        )
        pre_roll_blocks = max(
            1,
            int(self.pre_roll_seconds * self.sample_rate / block_size),
        )
        max_frames = int(self.max_recording_seconds * self.sample_rate)

        speech_deadline = time.monotonic() + self.speech_timeout
        audio_chunks: list[np.ndarray] = []
        pre_roll: deque[np.ndarray] = deque(maxlen=pre_roll_blocks)

        speech_started = False
        silent_blocks = 0
        recorded_frames = 0
        ambient_noise = 0.005

        if initial_audio is not None and initial_audio.size > 0:
            init_clean = np.asarray(initial_audio, dtype=np.float32).reshape(-1)
            audio_chunks.append(init_clean)
            recorded_frames += len(init_clean)
            init_vol = float(np.sqrt(np.mean(init_clean * init_clean)))
            if init_vol >= self.volume_threshold:
                speech_started = True

        owned_stream: sd.InputStream | None = None
        if stream is None:
            try:
                active_stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=block_size,
                )
                active_stream.start()
                owned_stream = active_stream
            except (sd.PortAudioError, OSError) as exc:
                raise RuntimeError(
                    f"Could not record microphone audio: {exc}"
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

        print("JARVIS: Listening... Speak now.")

        try:
            while True:
                try:
                    block, overflowed = active_stream.read(block_size)
                except (sd.PortAudioError, OSError) as exc:
                    raise RuntimeError(
                        f"Could not record microphone audio: {exc}"
                    ) from exc

                if overflowed:
                    print("JARVIS: Audio buffer overflow; continuing.")

                # Convert incoming samples to normalized float32
                raw_block = np.asarray(block).reshape(-1)
                if raw_block.dtype == np.int16:
                    raw_float = raw_block.astype(np.float32) / 32768.0
                else:
                    raw_float = raw_block.astype(np.float32, copy=True)

                volume = float(np.sqrt(np.mean(raw_float * raw_float)))

                if not speech_started:
                    pre_roll.append(raw_float)
                    # Dynamically adapt to ambient noise floor
                    ambient_noise = 0.90 * ambient_noise + 0.10 * volume
                    start_threshold = max(
                        self.volume_threshold,
                        ambient_noise * 2.2,
                    )

                    if volume >= start_threshold:
                        speech_started = True
                        print("JARVIS: Speech detected.")
                        audio_chunks.extend(pre_roll)
                        recorded_frames = sum(len(c) for c in audio_chunks)
                    elif time.monotonic() >= speech_deadline:
                        print("JARVIS: I didn't hear anything.")
                        return ""
                    continue

                audio_chunks.append(raw_float)
                recorded_frames += len(raw_float)

                silence_threshold = max(
                    0.006,
                    min(self.volume_threshold * 0.8, ambient_noise * 1.5),
                )
                if volume < silence_threshold:
                    silent_blocks += 1
                else:
                    silent_blocks = 0

                if silent_blocks >= silence_blocks_needed:
                    break

                if recorded_frames >= max_frames:
                    break

        except KeyboardInterrupt:
            print("\nJARVIS: Voice mode interrupted.")
            raise

        finally:
            if owned_stream is not None and not owned_stream.closed:
                try:
                    owned_stream.close()
                except Exception:
                    pass

        if not speech_started or not audio_chunks:
            return ""

        audio = np.concatenate(audio_chunks, axis=0).reshape(-1)
        if len(audio) < self.sample_rate // 2:
            print("JARVIS: I didn't catch enough speech.")
            return ""

        # Suppress noise once on the complete continuous recording
        filtered_audio = self._suppress_noise(audio)
        return self._transcribe(filtered_audio)

    def listen_for_barge_in(
        self,
        is_playing: Callable[[], bool],
        stop_playback: Callable[[], None],
    ) -> str | None:
        """Listen during TTS playback and capture an interrupting utterance."""
        if self.noise_suppressor is None:
            raise RuntimeError(
                "The noise suppressor is closed. "
                "Create a new SpeechToText instance before listening."
            )

        block_size = 480  # 30 ms at 16 kHz
        startup_grace_seconds = self.barge_in_grace_seconds
        min_interruption_threshold = self.barge_in_min_threshold
        required_speech_blocks = 4  # ~120 ms of speech
        silence_blocks_needed = max(
            1,
            int(self.silence_seconds * self.sample_rate / block_size),
        )
        pre_roll_blocks = max(
            1,
            int(0.25 * self.sample_rate / block_size),
        )
        max_frames = int(self.max_recording_seconds * self.sample_rate)

        playback_started = time.monotonic()
        pre_roll: deque[np.ndarray] = deque(maxlen=pre_roll_blocks)
        audio_chunks: list[np.ndarray] = []

        speech_started = False
        consecutive_speech_blocks = 0
        silent_blocks = 0
        recorded_frames = 0
        speaker_baseline = 0.01

        print("JARVIS: You can interrupt me by speaking.")

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=block_size,
            ) as stream:
                while is_playing() or speech_started:
                    try:
                        block, overflowed = stream.read(block_size)
                    except (sd.PortAudioError, OSError) as exc:
                        raise RuntimeError(
                            f"Could not monitor the microphone during playback: {exc}"
                        ) from exc

                    if overflowed:
                        print(
                            "JARVIS: Microphone buffer overflow; continuing."
                        )

                    raw_int16 = np.asarray(block, dtype=np.int16).reshape(-1)
                    raw_block = raw_int16.astype(np.float32) / 32768.0
                    volume = float(np.sqrt(np.mean(raw_block * raw_block)))

                    if not speech_started:
                        pre_roll.append(raw_block)

                        now = time.monotonic()
                        if now - playback_started < startup_grace_seconds:
                            speaker_baseline = max(speaker_baseline, volume)
                            continue

                        # Dynamically track speaker energy picked up by mic
                        speaker_baseline = 0.90 * speaker_baseline + 0.10 * volume
                        interruption_threshold = max(
                            min_interruption_threshold,
                            speaker_baseline * 1.5 + 0.02,
                        )

                        if volume >= interruption_threshold:
                            consecutive_speech_blocks += 1
                        else:
                            consecutive_speech_blocks = 0

                        if consecutive_speech_blocks < required_speech_blocks:
                            continue

                        speech_started = True
                        audio_chunks.extend(pre_roll)
                        recorded_frames = sum(
                            len(chunk) for chunk in audio_chunks
                        )

                        print("JARVIS: Interruption detected.")
                        stop_playback()
                        continue

                    audio_chunks.append(raw_block)
                    recorded_frames += len(raw_block)

                    silence_threshold = max(
                        0.008,
                        min(self.volume_threshold, speaker_baseline * 0.8),
                    )
                    if volume < silence_threshold:
                        silent_blocks += 1
                    else:
                        silent_blocks = 0

                    if silent_blocks >= silence_blocks_needed:
                        break

                    if recorded_frames >= max_frames:
                        break

        except KeyboardInterrupt:
            print("\nJARVIS: Interruption listening cancelled.")
            raise

        except (sd.PortAudioError, OSError) as exc:
            raise RuntimeError(
                f"Could not monitor the microphone during playback: {exc}"
            ) from exc

        if not speech_started or not audio_chunks:
            return None

        audio = np.concatenate(audio_chunks).astype(
            np.float32, copy=False
        )

        if audio.size < self.sample_rate // 2:
            print("JARVIS: I didn't catch enough speech.")
            return ""

        # Suppress noise once on the complete captured utterance.
        filtered_audio = self._suppress_noise(audio)
        transcript = self._transcribe(filtered_audio)
        return transcript if transcript else None


    def listen(self) -> str:
        """Record manually until Enter is pressed a second time."""
        audio_chunks: list[np.ndarray] = []

        print("\nPress Enter to start recording.")
        input()
        print("JARVIS: Listening... Speak now.")
        print("Press Enter again to stop recording.")

        def capture_audio(
            audio: np.ndarray,
            frames: int,
            time_info: object,
            status: sd.CallbackFlags,
        ) -> None:
            if status:
                print(f"JARVIS audio warning: {status}")
            audio_chunks.append(audio.copy())

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=capture_audio,
            ):
                input()

        except KeyboardInterrupt:
            print("\nJARVIS: Manual recording interrupted.")
            raise

        except (sd.PortAudioError, OSError) as exc:
            raise RuntimeError(
                f"Could not record microphone audio: {exc}"
            ) from exc

        if not audio_chunks:
            print("JARVIS: No audio was recorded.")
            return ""

        audio = np.concatenate(audio_chunks, axis=0).reshape(-1)

        if len(audio) < self.sample_rate // 2:
            print("JARVIS: I didn't catch enough speech.")
            return ""

        filtered_audio = self._suppress_noise(audio)
        return self._transcribe(filtered_audio)
