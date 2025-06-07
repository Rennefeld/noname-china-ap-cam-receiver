import json
import os
from dataclasses import dataclass, asdict

CONFIG_PATH = "config.json"

@dataclass
class StreamConfig:
    cam_ip: str = "192.168.4.153"
    cam_video_port: int = 8080
    cam_audio_port: int = 8082
    client_video_port: int = 53310
    client_audio_port: int = 53311
    frame_buffer_size: int = 65536
    header_bytes: int = 0
    jitter_delay: int = 0
    packets_per_frame: int = 1
    keepalive_interval: float = 2.0

    def save(self, path: str = CONFIG_PATH) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)

    @classmethod
    def load(cls, path: str = CONFIG_PATH) -> "StreamConfig":
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return cls(**data)
        return cls()

    def restore_defaults(self) -> None:
        defaults = type(self)()
        self.__dict__.update(asdict(defaults))
