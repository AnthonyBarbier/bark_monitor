import threading
import wave
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pyaudio

from bark_monitor.recorders.recorder_base import RecorderBase


class Recorder(RecorderBase):
    def __init__(
        self,
        bark_level: int,
        bark_func: Optional[Callable[[int], None]] = None,
        stop_bark_func: Optional[Callable[[timedelta], None]] = None,
    ) -> None:
        super().__init__(
            bark_level=bark_level, bark_func=bark_func, stop_bark_func=stop_bark_func
        )

        self._chunk = 1024  # Record in chunks of 1024 samples
        self._sample_format = pyaudio.paInt16  # 16 bits per sample
        self._channels = 1
        self._fs = 44100

        self._frames = []  # Initialize array to store frames

        self._t: Optional[threading.Thread] = None

        self._last_bark = datetime.now()
        self.total_time_barking = timedelta(seconds=0)
        self._pyaudio_interface = None

    @staticmethod
    def _filename() -> str:
        now = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
        filename = str(Path("recordings", now + ".wav"))
        if not Path(filename).parent.exists():
            Path(filename).parent.mkdir()
        return filename

    def _save_recording(self) -> None:
        # Save the recorded data as a WAV file
        assert self._pyaudio_interface is not None
        wf = wave.open(self._filename(), "wb")
        wf.setnchannels(self._channels)
        wf.setsampwidth(self._pyaudio_interface.get_sample_size(self._sample_format))
        wf.setframerate(self._fs)
        wf.writeframes(b"".join(self._frames))
        wf.close()

    def _signal_to_intensity(self, signal: bytes) -> int:
        np_data = np.frombuffer(signal, dtype=np.int16)
        return np.amax(np_data)

    def _record(self) -> None:
        self._t = threading.Thread(target=self._record_loop)
        self._t.start()

    def _stop(self) -> None:
        if self._t is None:
            return
        self._t.join()

    def _start_stream(self) -> tuple[pyaudio.PyAudio, pyaudio.Stream]:
        pyaudio_interface = pyaudio.PyAudio()  # Create an interface to PortAudio
        stream = pyaudio_interface.open(
            format=self._sample_format,
            channels=self._channels,
            rate=self._fs,
            frames_per_buffer=self._chunk,
            input=True,
        )
        return pyaudio_interface, stream

    def _stop_stream(
        self, pyaudio_interface: pyaudio.PyAudio, stream: pyaudio.Stream
    ) -> None:
        # Stop and close the stream
        stream.stop_stream()
        stream.close()
        # Terminate the PortAudio interface
        pyaudio_interface.terminate()

    def _record_loop(self) -> None:
        self._pyaudio_interface, stream = self._start_stream()
        print("Recording started")

        while self.running:
            if self.is_paused:
                continue

            data = stream.read(self._chunk)
            intensity = self._signal_to_intensity(data)

            # Save data if dog is barking
            is_bark = self._is_bark(intensity)
            if is_bark or (datetime.now() - self._barking_at) < timedelta(seconds=1):
                self._frames.append(data)

            self._intensity_decision(intensity)

        self._stop_stream(self._pyaudio_interface, stream)
        self._pyaudio_interface = None