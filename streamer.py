import socket
import threading
import time
import io
from typing import Callable, Optional
from PIL import Image, ImageOps, UnidentifiedImageError, ImageFile

# Allow loading frames even if the JPEG data is slightly truncated.
ImageFile.LOAD_TRUNCATED_IMAGES = True
import numpy as np
import cv2
from config import StreamConfig

class FrameProcessor:
    def __init__(self):
        self.flip_h = False
        self.flip_v = False
        self.rotate_90 = False
        self.grayscale = False

    def process(self, img: Image.Image) -> Image.Image:
        if self.flip_h:
            img = ImageOps.mirror(img)
        if self.flip_v:
            img = ImageOps.flip(img)
        if self.rotate_90:
            img = img.rotate(-90, expand=True)
        if self.grayscale:
            img = ImageOps.grayscale(img).convert("RGB")
        return img

class CameraStreamer:
    def __init__(self, config: StreamConfig, processor: FrameProcessor):
        self.config = config
        self.processor = processor
        self.running = False
        self.sock: Optional[socket.socket] = None
        self.keepalive_thread: Optional[threading.Thread] = None
        self.receiver_thread: Optional[threading.Thread] = None
        self.jpeg_buffer = bytearray()
        self.last_frame_time = 0.0
        self.frame_callback: Optional[Callable[[Image.Image], None]] = None

    def start(self, callback: Callable[[Image.Image], None]):
        if self.running:
            return
        self.frame_callback = callback
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(("", self.config.client_video_port))
        except Exception:
            self.sock.bind(("", 0))
        self.running = True
        self.keepalive_thread = threading.Thread(target=self._send_keepalive, daemon=True)
        self.receiver_thread = threading.Thread(target=self._recv_frames, daemon=True)
        self.keepalive_thread.start()
        self.receiver_thread.start()

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None
        self.jpeg_buffer.clear()
        self.last_frame_time = 0.0

    def _send_keepalive(self):
        payload_8070 = b"0f"
        payload_8080 = b"Bv"
        while self.running:
            try:
                if self.sock:
                    self.sock.sendto(payload_8070, (self.config.cam_ip, self.config.cam_audio_port))
                    self.sock.sendto(payload_8080, (self.config.cam_ip, self.config.cam_video_port))
            except Exception:
                pass
            time.sleep(self.config.keepalive_interval)

    def _recv_frames(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(self.config.frame_buffer_size)
            except Exception:
                break
            if addr[0] != self.config.cam_ip:
                continue
            self.jpeg_buffer += data
            while True:
                soi = self.jpeg_buffer.find(b"\xff\xd8")
                if soi < 0:
                    break
                eoi = self.jpeg_buffer.find(b"\xff\xd9", soi + 2)
                if eoi < 0:
                    break
                jpeg_data = self.jpeg_buffer[soi:eoi+2]
                del self.jpeg_buffer[:eoi+2]
                try:
                    Image.open(io.BytesIO(jpeg_data)).verify()
                except Exception:
                    continue
                now = time.monotonic()
                if now - self.last_frame_time < 0.05:
                    continue
                self.last_frame_time = now
                try:
                    img = Image.open(io.BytesIO(jpeg_data))
                    img.load()  # ensure data is read before processing
                    img = self.processor.process(img)
                except (UnidentifiedImageError, OSError):
                    continue
                if self.frame_callback:
                    self.frame_callback(img)
                if self.config.jitter_delay:
                    time.sleep(self.config.jitter_delay / 1000.0)

