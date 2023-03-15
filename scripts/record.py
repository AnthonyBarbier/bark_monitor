from datetime import datetime
from pathlib import Path

from dog_bark.recorder import Recorder


def main():
    now = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
    filepath = Path("recordings", now + ".wav")

    with Recorder(filename=str(filepath), bark_level=1000) as rec:
        rec.record()


if __name__ == "__main__":
    main()
