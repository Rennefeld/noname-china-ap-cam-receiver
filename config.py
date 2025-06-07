from dataclasses import dataclass

@dataclass
class StreamConfig:
    cam_ip: str = "192.168.4.153"
    cam_video_port: int = 8080
    cam_audio_port: int = 8082
    client_video_port: int = 53310
    client_audio_port: int = 53311
    frame_buffer_size: int = 2048
    header_bytes: int = 0
    jitter_delay: int = 0
