import socket
import threading
import time
import io
import queue
import logging
from typing import Callable, Optional
from PIL import Image, ImageOps, UnidentifiedImageError, ImageFile, ImageEnhance

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
        self.brightness = 1.0
        self.contrast = 1.0
        self.saturation = 1.0
        self.hue = 0.0
        self.gamma = 1.0
        self.target_size: tuple[int, int] | None = None

    def process(self, img: Image.Image) -> Image.Image:
        if self.flip_h:
            img = ImageOps.mirror(img)
        if self.flip_v:
            img = ImageOps.flip(img)
        if self.rotate_90:
            img = img.rotate(-90, expand=True)
        if self.grayscale:
            img = ImageOps.grayscale(img).convert("RGB")
        if self.brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(self.brightness)
        if self.contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(self.contrast)
        if self.saturation != 1.0:
            img = ImageEnhance.Color(img).enhance(self.saturation)
        if self.hue != 0.0:
            hsv = np.array(img.convert("HSV"), dtype=np.uint8)
            hsv[..., 0] = (hsv[..., 0].astype(int) + int(self.hue * 255)) % 256
            img = Image.fromarray(hsv, "HSV").convert("RGB")
        if self.gamma != 1.0:
            inv = 1.0 / max(self.gamma, 0.01)
            table = [int((i / 255.0) ** inv * 255) for i in range(256)]
            img = img.point(table * len(img.getbands()))
        if self.target_size:
            img = img.resize(self.target_size, Image.LANCZOS)
        return img

class CameraStreamer:
    def __init__(self, config: StreamConfig, processor: FrameProcessor):
        self.config = config
        self.processor = processor
        self.running = False
        self.sock: Optional[socket.socket] = None
        self.keepalive_sock: Optional[socket.socket] = None
        self.keepalive_thread: Optional[threading.Thread] = None
        self.receiver_thread: Optional[threading.Thread] = None
        self.dispatch_thread: Optional[threading.Thread] = None
        self.jpeg_buffer = bytearray()
        self.last_frame_time = 0.0
        self.current_packet_count = 0
        self.last_packet_count = 0
        self.frame_callback: Optional[Callable[[Image.Image], None]] = None
        self._recv_buffer = bytearray(self.config.frame_buffer_size)
        self.frame_queue: queue.Queue[Image.Image] = queue.Queue(maxsize=2)

    def packets_in_frame(self) -> int:
        """Return number of packets used to assemble the last frame."""
        return self.last_packet_count
    def start(self, callback: Callable[[Image.Image], None]):
        if self.running:
            return
        self.frame_callback = callback
        logging.debug("Starting streamer")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.config.frame_buffer_size)
        self.keepalive_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.keepalive_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.config.frame_buffer_size)
        try:
            self.sock.bind(("", self.config.client_video_port))
        except Exception:
            self.sock.bind(("", 0))
        self.running = True
        while not self.frame_queue.empty():
            self.frame_queue.get_nowait()
        self.keepalive_thread = threading.Thread(target=self._send_keepalive, daemon=True)
        self.receiver_thread = threading.Thread(target=self._recv_frames, daemon=True)
        self.dispatch_thread = threading.Thread(target=self._dispatch_frames, daemon=True)
        self.keepalive_thread.start()
        self.receiver_thread.start()
        self.dispatch_thread.start()
        # reset counters for consistent behaviour after restarts
        self.current_packet_count = 0
        self.last_packet_count = 0

    def stop(self):
        logging.debug("Stopping streamer")
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None
        if self.keepalive_sock:
            try:
                self.keepalive_sock.close()
            finally:
                self.keepalive_sock = None
        if self.dispatch_thread and self.dispatch_thread.is_alive():
            self.dispatch_thread.join(timeout=0.1)
        self.jpeg_buffer.clear()
        self.last_frame_time = 0.0
        self.current_packet_count = 0
        self.last_packet_count = 0

    def _send_keepalive(self):
        payload_8070 = b"0f"
        payload_8080 = b"Bv"
        while self.running:
            try:
                if self.sock:
                    self.sock.sendto(payload_8070, (self.config.cam_ip, self.config.cam_audio_port))
                    self.sock.sendto(payload_8080, (self.config.cam_ip, self.config.cam_video_port))
            except Exception:
                logging.exception("Keepalive failed")
            time.sleep(self.config.keepalive_interval)

    def _recv_frames(self):
        buffer = memoryview(self._recv_buffer)
        while self.running:
            try:
                nbytes, addr = self.sock.recvfrom_into(buffer)
            except Exception:
                logging.exception("recvfrom failed")
                break
            if addr[0] != self.config.cam_ip:
                continue
            self.jpeg_buffer.extend(buffer[:nbytes])
            self.current_packet_count += 1
            if self.current_packet_count < self.config.packets_per_frame:
                continue
            self.last_packet_count = self.current_packet_count
            self.current_packet_count = 0
            self._extract_frames()

    def _extract_frames(self) -> None:
        """Parse buffered JPEG data into frames and dispatch them."""
        while True:
            soi = self.jpeg_buffer.find(b"\xff\xd8")
            if soi < 0:
                break
            eoi = self.jpeg_buffer.find(b"\xff\xd9", soi + 2)
            if eoi < 0:
                break
            jpeg_data = self.jpeg_buffer[soi:eoi + 2]
            del self.jpeg_buffer[:eoi + 2]
            now = time.monotonic()
            if now - self.last_frame_time < 0.05:
                continue
            self.last_frame_time = now
            try:
                img = Image.open(io.BytesIO(jpeg_data))
                img.load()
                img = self.processor.process(img)
            except (UnidentifiedImageError, OSError):
                logging.debug("Dropped corrupted frame")
                continue
            try:
                self.frame_queue.put_nowait(img)
            except queue.Full:
                logging.debug("Frame queue full, dropping frame")
            if self.config.jitter_delay:
                time.sleep(self.config.jitter_delay / 1000.0)

    def _dispatch_frames(self) -> None:
        """Send complete frames to the callback from a dedicated thread."""
        while self.running:
            try:
                img = self.frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if self.frame_callback:
                try:
                    self.frame_callback(img)
                except Exception:
                    logging.exception("Frame callback failed")

