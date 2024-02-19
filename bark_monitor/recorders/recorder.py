from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from bark_monitor.recorders.base_recorder import BaseRecorder
from bark_monitor.recorders.recording import Recording


class Recorder(BaseRecorder):
    """A recorder using signal amplitude to detect dog barks."""

    def __init__(
        self,
        output_folder: str,
    ) -> None:
        self._bark_level: int = 0

        self.running = False
        self.is_paused = False

        self._last_bark = datetime.now()
        super().__init__(output_folder)

    @property
    def bark_level(self) -> Optional[int]:
        return self._bark_level

    def _init(self):
        super()._init()
        self._barking_start = None
        self._last_barking = None

    def _is_bark(self, value: int) -> bool:
        if self._bark_level == 0:
            return False
        return value >= self._bark_level

    def _signal_to_intensity(self, signal: bytes) -> int:
        np_data = np.frombuffer(signal, dtype=np.int16)
        return np.amax(np_data)  # type: ignore

    def stop(self):
        self._bark_level = 0
        return super().stop()

    def _set_bark_level(self, range_measurements: int = 100) -> None:
        assert self._stream is not None
        self._bark_level = 0
        for _ in range(range_measurements):
            data = self._stream.read(self._chunk, exception_on_overflow=False)
            self._bark_level = max(self._bark_level, self._signal_to_intensity(data))
        self._bark_level *= 2

    def _record_loop(self) -> None:
        self._start_stream()
        self._bark_logger.info("Recording started")

        assert self._stream is not None
        self._set_bark_level()

        while self.running:
            if self.is_paused:
                continue

            data = self._stream.read(self._chunk, exception_on_overflow=False)
            intensity = self._signal_to_intensity(data)

            # Save data if dog is barking
            is_bark = self._is_bark(intensity)
            # If to update time and stop recording the bark
            if is_bark:
                self._last_barking = datetime.now()
                if self._barking_start is None:
                    self._barking_start = self._last_barking
                    print(f"Barking started {self._barking_start}")
                    self._chat_bot.send_bark(intensity - self._bark_level)

            if self._barking_start is not None:
                self._frames.append(data)

                if (datetime.now() - self._last_barking) > timedelta(
                    seconds=10
                ):
                    print(f"Stopped barking timeout Bark start {self._barking_start}, Last bark {self._last_barking} / now {datetime.now()}, delta = {datetime.now()-self._last_barking}")
                    recording = Recording.read(self.output_folder)
                    duration = timedelta(
                        seconds=(len(self._frames) * self._chunk) / self._fs
                    )
                    recording.add_time_barked(duration)

                    self._chat_bot.send_end_bark(duration)
                    self._save_recording(self._frames)
                    self._frames = []
                    self._barking_start = None

        self._stop_stream()
