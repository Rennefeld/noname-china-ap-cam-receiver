import socket
import threading
import time
import io
import binascii
import logging
import queue
from typing import Callable, Optional
from PIL import Image, ImageOps, UnidentifiedImageError, ImageFile

# Allow loading frames even if the JPEG data is slightly truncated.
ImageFile.LOAD_TRUNCATED_IMAGES = True
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
        self.keepalive_sock: Optional[socket.socket] = None
        self.keepalive_thread: Optional[threading.Thread] = None
        self.receiver_thread: Optional[threading.Thread] = None
        self.jpeg_buffer = bytearray()
        self.last_frame_time = 0.0
        self.current_packet_count = 0
        self.last_packet_count = 0
        self.frame_queue: Optional[queue.Queue] = None
        self._recv_buffer = bytearray(self.config.chunk_size + self.config.header_bytes)

    def packets_in_frame(self) -> int:
        """Return number of packets used to assemble the last frame."""
        return self.last_packet_count
    def start(self, frame_queue: queue.Queue):
        if self.running:
            return
        self.frame_queue = frame_queue
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.config.frame_buffer_size)
        self.keepalive_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.keepalive_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.config.frame_buffer_size)
        try:
            self.sock.bind(("", self.config.client_video_port))
            logging.debug("bound video socket to %s", self.sock.getsockname())
        except Exception:
            self.sock.bind(("", 0))
            logging.warning(
                "failed to bind to configured port %d, using %d",
                self.config.client_video_port,
                self.sock.getsockname()[1],
            )
        self.running = True
        self.keepalive_thread = threading.Thread(target=self._send_keepalive, daemon=True)
        self.receiver_thread = threading.Thread(target=self._recv_frames, daemon=True)
        self.keepalive_thread.start()
        self.receiver_thread.start()
        logging.debug("streamer started")
        # reset counters for consistent behaviour after restarts
        self.current_packet_count = 0
        self.last_packet_count = 0

    def stop(self):
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
        self.jpeg_buffer.clear()
        self.last_frame_time = 0.0
        self.current_packet_count = 0
        self.last_packet_count = 0
        self.frame_queue = None
        logging.debug("streamer stopped")

    def _send_keepalive(self):
        payload_8070 = b"0f"
        payload_8080 = b"Bv"
        while self.running:
            try:
                if self.sock:
                    self.sock.sendto(payload_8070, (self.config.cam_ip, self.config.cam_audio_port))
                    self.sock.sendto(payload_8080, (self.config.cam_ip, self.config.cam_video_port))
            except Exception:
                logging.exception("keepalive send failed")
            time.sleep(self.config.keepalive_interval)

    def _send_nack(self, seq: int) -> None:
        """Request retransmission for a missing or corrupted sequence."""
        if not self.keepalive_sock:
            return
        msg = b"NACK" + seq.to_bytes(3, "big")
        try:
            self.keepalive_sock.sendto(
                msg, (self.config.cam_ip, self.config.cam_video_port)
            )
        except Exception:
            logging.exception("failed to send NACK")

    def _recv_frames(self):
        buffer = memoryview(self._recv_buffer)
        header = self.config.header_bytes
        while self.running:
            try:
                nbytes, addr = self.sock.recvfrom_into(buffer)
            except Exception:
                break
            if addr[0] != self.config.cam_ip:
                continue
            if nbytes <= header:
                continue
            seq = int.from_bytes(buffer[:3], "big")
            crc_recv = int.from_bytes(buffer[3:5], "big")
            payload = buffer[header:nbytes].tobytes()
            if binascii.crc_hqx(payload, 0xFFFF) != crc_recv:
                self._send_nack(seq)
                continue
            self.current_packet_count += 1
            self.jpeg_buffer.extend(payload)
            self._extract_frames()
            if self.config.jitter_delay:
                time.sleep(self.config.jitter_delay / 1000.0)

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
                continue
            if self.frame_queue is not None:
                try:
                    self.frame_queue.put_nowait(img)
                except queue.Full:
                    pass
            self.last_packet_count = self.current_packet_count
            self.current_packet_count = 0
            logging.debug("frame assembled with %d packets", self.last_packet_count)
            if self.config.jitter_delay:
                time.sleep(self.config.jitter_delay / 1000.0)

    def check_connection(self, timeout: float = 2.0) -> bool:
        """Return True if packets arrive within `timeout` seconds."""
        start = time.monotonic()
        last = self.last_frame_time
        while time.monotonic() - start < timeout:
            if self.last_frame_time != last:
                return True
            time.sleep(0.1)
        logging.error("no packets received within %.1fs", timeout)
        if self.sock and self.sock.getsockname()[1] != self.config.client_video_port:
            logging.error(
                "socket bound to %d instead of %d",
                self.sock.getsockname()[1],
                self.config.client_video_port,
            )
        return False


def start_dummy_camera(config: StreamConfig, frame: Image.Image, count: int = 1) -> threading.Thread:
    """Send `count` JPEG frames to the client using an 8 byte header."""

    def _run() -> None:
        video_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        audio_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            video_sock.bind((config.cam_ip, 8080))
            audio_sock.bind((config.cam_ip, 8070))
        except Exception:
            video_sock.bind((config.cam_ip, 0))
            audio_sock.bind((config.cam_ip, 0))
        buf = io.BytesIO()
        frame.save(buf, format="JPEG", quality=95)
        payload = buf.getvalue()
        chunk_size = config.chunk_size or 1024
        for _ in range(count):
            seq = 0
            for offset in range(0, len(payload), chunk_size):
                chunk = payload[offset : offset + chunk_size]
                crc = binascii.crc_hqx(chunk, 0xFFFF)
                header = seq.to_bytes(3, "big") + crc.to_bytes(2, "big") + b"\x00\x00\x00"
                pkt = header + chunk
                video_sock.sendto(pkt, ("127.0.0.1", config.client_video_port))
                seq += 1
            time.sleep(0.05)
        video_sock.close()
        audio_sock.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t

