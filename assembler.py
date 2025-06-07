class ChunkedFrameBuffer:
    def __init__(self, width: int, height: int, channels: int, rows_per_chunk: int):
        self.width = width
        self.height = height
        self.channels = channels
        self.rows_per_chunk = rows_per_chunk
        self.row_bytes = self.width * self.channels
        self.chunk_size = self.row_bytes * self.rows_per_chunk
        self.frame_size = self.row_bytes * self.height
        # ensure frame size aligns to chunk size
        self.num_chunks = self.frame_size // self.chunk_size
        if self.frame_size % self.chunk_size != 0:
            self.num_chunks += 1
        self.buffer = bytearray(self.frame_size)
        self.received = set()

    def reset(self):
        self.received.clear()
        self.buffer[:] = b'\x00' * self.frame_size

    def add(self, seq: int, payload: bytes) -> bool:
        if seq in self.received:
            return False
        start = seq * self.chunk_size
        end = start + len(payload)
        if end > len(self.buffer):
            return False
        self.buffer[start:end] = payload
        self.received.add(seq)
        return len(self.received) == self.num_chunks

    def to_image(self):
        import numpy as np
        from PIL import Image

        frame = np.frombuffer(self.buffer, dtype=np.uint8)
        frame = frame.reshape((self.height, self.width, self.channels))
        return Image.fromarray(frame, 'RGB')
