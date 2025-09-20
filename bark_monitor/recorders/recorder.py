from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import time
import json
import pathlib
import pyaudio
import os
import subprocess

from bark_monitor.recorders.base_recorder import BaseRecorder
from bark_monitor.recorders.recording import Recording

def trunc_hour(t):
    return t.replace(second=0, microsecond=0, minute=0, hour=t.hour)

def scp(*, src : str, dst : str):
    try:
        subprocess.check_call(f"scp {src} {dst}", shell=True)
        print(f"Successfully transferred: {src} -> {dst}", flush=True)
    except subprocess.CalledProcessError as e:
        print(f"Ignoring error: {e} from scp {src} -> {dst}", flush=True)

class Data:
    def __init__(self, filename, remote_filename = None):
        self.filename = filename
        self.remote = remote_filename
        if self.remote:
            scp(src=self.remote,dst=self.filename)
        try:
            self.data = json.loads(self.filename.read_text(encoding="utf-8"))
            for d in self.data["barks"]:
                d["r"] = 5
            print(f"Successfully loaded {filename}", flush=True)
        except Exception as e:
            print(f"Ignoring error: {e} from {filename}", flush=True)
            self.data = { "barks":[]}
        self.save()

    def add_bark(self, time, intensity):
        self.data["barks"].append({"x": int(time.timestamp()), "y": int(intensity), "r": 5})

    def save(self):
        now = datetime.now()
        end = trunc_hour(now) + timedelta(hours=1)
        start = (now - timedelta(hours=48)).timestamp()
        self.data["min"] = int(start)
        self.data["max"] = int(end.timestamp())
        self.data["now"] = int(now.timestamp())
        self.data["barks"] = [
                d for d in self.data["barks"] if d["x"] > start]
        self.filename.write_text(json.dumps(self.data), encoding="utf-8")
        print(f"Saved {len(self.data['barks'])} points to {self.filename}", flush=True)
        if self.remote:
            scp(src=self.filename, dst=self.remote)

class RemoteLog:
    def __init__(self, dst):
        if dst is not None:
            assert ":" in str(dst)
            self.remote_output = pathlib.Path(dst)
            self.filename = pathlib.Path(self.remote_output.name)
        else:
            self.remote_output = None

    def print(self, s):
        print(s, flush=True)
        self.prepend(s)

    def prepend(self, s):
        if self.remote_output is None:
            return
        content = self.filename.read_text(encoding="utf-8") if self.filename.is_file() else ""
        now = f"[{datetime.now()}] "
        content = "\n".join(now + l for l in s.splitlines()) + "\n" + content[:200000]
        self.filename.write_text(content, encoding="utf-8")

    def save(self):
        if self.remote_output is None:
            return
        scp(src=self.filename, dst=self.remote_output)

class DataWindow:
    def __init__(self, rlog):
        self.num_points = 2400
        self.start = None
        self.max= 0
        self._n = 0
        self.rlog = rlog
        self.rlog.print(f"========= START ========")
        self.rlog.save()

    def add(self, time, intensity):
        if self._n == 0:
            self.max = intensity
            self.start = time
        elif intensity > self.max:
            self.max = intensity
        self._n += 1
        if self._n == self.num_points:
            since = time - self.start
            self.rlog.print(f"{time}: max {self.max} from the last {since}")
            self.rlog.save()
            self._n = 0


class Recorder(BaseRecorder):
    """A recorder using signal amplitude to detect dog barks."""

    def __init__(
        self,
        output_folder: str,
        audio_device: str | None = None,
        output_data_file: str | None = None,
        debug_print : bool = False,
    ) -> None:
        self._bark_level: int = 10000

        self.running = False
        self.is_paused = False

        self.debug = debug_print
        self.remote_output = None
        remote_log_file = None
        if output_data_file is not None:
            if ":" in output_data_file:
                self.remote_output = pathlib.Path(output_data_file)
                path = pathlib.Path(self.remote_output.name)
                remote_log_file = self.remote_output.with_suffix(".log")
            else:
                path = pathlib.Path(output_data_file)
        else:
            path = pathlib.Path("bark_data.json")

        if not path.is_absolute():
            path = pathlib.Path.cwd() / path

        self.rlog = RemoteLog(remote_log_file)
        self.json = Data(path, self.remote_output)
        self.live = DataWindow(self.rlog)
        self._last_callback = datetime.now()
        self._last_bark = datetime.now()
        super().__init__(output_folder,audio_device=audio_device)
        self.clean_up()

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
                if self.debug:
                    print(f"[debug] bark: {intensity}", flush=True)

                now = datetime.now()
                self._last_callback = now
                self.live.add(now, intensity)
                # Save data if dog is barking
                is_bark = self._is_bark(intensity)
                # If to update time and stop recording the bark
                if is_bark:
                    self._last_barking = now
                    self.json.add_bark(self._last_barking, intensity)

                    if self._barking_start is None:
                        self._barking_start = self._last_barking
                        print(f"Barking started {self._barking_start}", flush=True)
                        if self._chat_bot:
                            self._chat_bot.send_bark(intensity - self._bark_level)
                    print(f"bark: {intensity}", flush=True)

                if self._barking_start is not None:
                    self._frames.append(bytes(data))
                    print(f"Adding {datetime.now()} {intensity}", flush=True)

                    if (now - self._last_barking) > timedelta(
                        seconds=15
                    ):
                        self.json.save()
                        recording = Recording.read(self.output_folder)
                        duration = timedelta(
                            seconds=(len(self._frames) * self._chunk) / self._fs
                        )
                        print(f"Stopped barking timeout Bark start {self._barking_start}, Last bark {self._last_barking} / now {datetime.now()}, delta = {datetime.now()-self._last_barking} Duration {duration}", flush=True)
                        recording.add_time_barked(duration)

                        if self._chat_bot:
                            self._chat_bot.send_end_bark(duration)
                        self._save_recording(self._frames)
                        self.clean_up()
                        self._frames = []
                        self._barking_start = None
                    elif intensity > 5000:
                        print(f"[debug] bark: {intensity}", flush=True)
            return (data, pyaudio.paContinue)
        self._start_stream(callback)
        self._bark_logger.info("Recording started")

        assert self._stream is not None
        while self.running:
            time.sleep(1)
            if (datetime.now() - self._last_callback) > timedelta(
                seconds=59
            ):
                now = datetime.now()
                self._bark_logger.warning(f"Restarting stream {now}")
                self._stop_stream()
                self._start_stream(callback)
                self._last_callback = now

        self._stop_stream()
