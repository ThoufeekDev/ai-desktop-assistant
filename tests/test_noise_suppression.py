"""Regression tests for RNNoise suppression."""

import unittest
import numpy as np

from jarvis.noise_suppression import RNNoiseSuppressor, NoiseSuppressionError


class NoiseSuppressionTests(unittest.TestCase):
    def test_rnnoise_initialization_and_frame_size(self) -> None:
        suppressor = RNNoiseSuppressor()
        try:
            self.assertEqual(suppressor.FRAME_SIZE, 480)
            self.assertEqual(suppressor.INPUT_RATE, 16000)
            self.assertEqual(suppressor.RNNOISE_RATE, 48000)
        finally:
            suppressor.close()

    def test_process_valid_16k_audio(self) -> None:
        with RNNoiseSuppressor() as suppressor:
            # 1 second of test audio (sine wave)
            t = np.linspace(0, 1.0, 16000, endpoint=False, dtype=np.float32)
            sine = 0.3 * np.sin(2 * np.pi * 440 * t)

            output = suppressor.process(sine)
            self.assertIsInstance(output, np.ndarray)
            self.assertEqual(output.dtype, np.float32)
            self.assertEqual(output.shape, (16000,))
            self.assertTrue(np.all(np.isfinite(output)))

    def test_process_empty_audio(self) -> None:
        with RNNoiseSuppressor() as suppressor:
            empty = np.array([], dtype=np.float32)
            output = suppressor.process(empty)
            self.assertEqual(output.size, 0)
            self.assertEqual(output.dtype, np.float32)

    def test_process_type_and_shape_validation(self) -> None:
        with RNNoiseSuppressor() as suppressor:
            with self.assertRaises(TypeError):
                suppressor.process([0.1, 0.2, 0.3])

            with self.assertRaises(ValueError):
                # 2D array
                suppressor.process(np.zeros((100, 2), dtype=np.float32))

            with self.assertRaises(TypeError):
                # int16 instead of float32
                suppressor.process(np.zeros(1000, dtype=np.int16))

            with self.assertRaises(ValueError):
                # Non-finite (NaN / inf)
                bad = np.zeros(1000, dtype=np.float32)
                bad[5] = np.nan
                suppressor.process(bad)

    def test_process_frame_validation(self) -> None:
        with RNNoiseSuppressor() as suppressor:
            # Exactly 160 samples expected
            with self.assertRaises(ValueError):
                suppressor.process_frame(np.zeros(100, dtype=np.float32))

            with self.assertRaises(TypeError):
                suppressor.process_frame(np.zeros(160, dtype=np.int16))

            with self.assertRaises(TypeError):
                suppressor.process_frame([0.0] * 160)

            # Valid 160 samples
            frame = np.zeros(160, dtype=np.float32)
            out = suppressor.process_frame(frame)
            self.assertEqual(out.shape, (160,))
            self.assertEqual(out.dtype, np.float32)

    def test_closed_state_error(self) -> None:
        suppressor = RNNoiseSuppressor()
        suppressor.close()
        # Closing multiple times is safe and idempotent
        suppressor.close()

        with self.assertRaises(RuntimeError):
            suppressor.process(np.zeros(1600, dtype=np.float32))

        with self.assertRaises(RuntimeError):
            suppressor.process_frame(np.zeros(160, dtype=np.float32))


if __name__ == "__main__":
    unittest.main()
