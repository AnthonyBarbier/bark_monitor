from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import time
import pyaudio

from bark_monitor.recorders.base_recorder import BaseRecorder
from bark_monitor.recorders.recording import Recording


class Recorder(BaseRecorder):
    """A recorder using signal amplitude to detect dog barks."""

    def __init__(
        self,
        output_folder: str,
    ) -> None:
        self._bark_level: int = 3500

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
        return value >= self._bark_level

    def _signal_to_intensity(self, signal: bytes) -> int:
        np_data = np.frombuffer(signal, dtype=np.int16)
        return np.amax(np_data)  # type: ignore

    def stop(self):
        self._bark_level = 0
        return super().stop()

    def _record_loop(self) -> None:
        def callback(data, frame_count, time_info, status):
            if not self.is_paused:
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
                    print(f"bark: {intensity}")

                if self._barking_start is not None:
                    self._frames.append(bytes(data))
                    print(f"Adding {datetime.now()} {intensity}")

                    if (datetime.now() - self._last_barking) > timedelta(
                        seconds=15
                    ):
                        recording = Recording.read(self.output_folder)
                        duration = timedelta(
                            seconds=(len(self._frames) * self._chunk) / self._fs
                        )
                        print(f"Stopped barking timeout Bark start {self._barking_start}, Last bark {self._last_barking} / now {datetime.now()}, delta = {datetime.now()-self._last_barking} Duration {duration}")
                        recording.add_time_barked(duration)

                        self._chat_bot.send_end_bark(duration)
                        self._save_recording(self._frames)
                        self._frames = []
                        self._barking_start = None
            return (data, pyaudio.paContinue)
        self._start_stream(callback)
        self._bark_logger.info("Recording started")

        assert self._stream is not None
        while self.running:
            time.sleep(1)

        self._stop_stream()
