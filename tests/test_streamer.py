import os
import sys
import queue
import time
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import StreamConfig
from streamer import FrameProcessor, CameraStreamer, start_dummy_camera


def test_streamer_receives_frame():
    config = StreamConfig(
        cam_ip="127.0.0.1",
        cam_video_port=9000,
        client_video_port=9001,
        frame_width=32,
        frame_height=32,
        channels=3,
        rows_per_chunk=16,
    )

    processor = FrameProcessor()
    streamer = CameraStreamer(config, processor)
    q = queue.Queue()
    streamer.start(q)

    img = Image.new("RGB", (config.frame_width, config.frame_height), "blue")
    sender = start_dummy_camera(config, img)
    try:
        received = False
        for _ in range(30):
            try:
                frame = q.get_nowait()
                received = True
                assert frame.size == img.size
                break
            except queue.Empty:
                time.sleep(0.1)
        assert received, "no frame received"
    finally:
        streamer.stop()
        sender.join(timeout=1)

