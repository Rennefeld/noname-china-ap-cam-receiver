import os
import time
import subprocess
import shutil
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np
from config import StreamConfig
from config_dialog import ConfigDialog
from streamer import FrameProcessor, CameraStreamer

OUTPUT_DIR = "recordings"


def ensure_output_dir():
    if not os.path.isdir(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)


def convert_to_mpg(path: str) -> str:
    """Convert an AVI recording to MPG using ffmpeg."""
    if shutil.which("ffmpeg") is None:
        return path
    base = os.path.splitext(path)[0]
    mpg_path = f"{base}.mpg"
    cmd = ["ffmpeg", "-y", "-i", path, mpg_path]
    try:
        subprocess.run(
            cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        os.remove(path)
        return mpg_path
    except Exception:
        return path


class CameraApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AP Camera Receiver")
        self.config = StreamConfig.load()
        self.processor = FrameProcessor()
        self.streamer = CameraStreamer(self.config, self.processor)

        self.mic_on = False
        self.recording = False
        self.current_frame = None
        self.tk_image = None
        self.video_writer = None
        self.record_indicator_state = False
        self.blink_job = None
        self.volume = tk.DoubleVar(value=50)
        self.prev_frame = None

        self._build_ui()
        self._show_off_message()

    # ----------------- UI SETUP -----------------
    def _build_ui(self):
        menu_bar = tk.Menu(self.root)
        self.root.config(menu=menu_bar)
        menu_bar.add_command(label="Settings", command=self.open_config_dialog)

        self.canvas = tk.Canvas(self.root, bg="black")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._display_current_frame())

        controls = ttk.Frame(self.root)
        controls.pack(fill="x", pady=5)

        self.stream_btn = ttk.Button(
            controls, text="Start Stream", command=self.toggle_stream
        )
        self.stream_btn.grid(row=0, column=0, padx=5)

        self.mic_btn = ttk.Button(controls, text="Mic Off", command=self.toggle_mic)
        self.mic_btn.grid(row=0, column=1, padx=5)

        self.flip_h_btn = ttk.Button(
            controls, text="Flip H", command=self.toggle_flip_h
        )
        self.flip_h_btn.grid(row=0, column=2, padx=5)

        self.flip_v_btn = ttk.Button(
            controls, text="Flip V", command=self.toggle_flip_v
        )
        self.flip_v_btn.grid(row=0, column=3, padx=5)

        self.rotate_btn = ttk.Button(
            controls, text="Rotate 90°", command=self.toggle_rotate
        )
        self.rotate_btn.grid(row=0, column=4, padx=5)

        self.bw_btn = ttk.Button(controls, text="B/W", command=self.toggle_bw)
        self.bw_btn.grid(row=0, column=5, padx=5)

        self.record_btn = ttk.Button(
            controls, text="Record", state="disabled", command=self.toggle_record
        )
        self.record_btn.grid(row=0, column=6, padx=5)

        self.snapshot_btn = ttk.Button(
            controls, text="\U0001f4f7", command=self.take_snapshot
        )
        self.snapshot_btn.grid(row=0, column=7, padx=5)

        ttk.Label(controls, text="Volume").grid(row=0, column=8, padx=5)
        self.volume_slider = ttk.Scale(
            controls,
            from_=0,
            to=100,
            variable=self.volume,
            command=self.on_volume_change,
        )
        self.volume_slider.grid(row=0, column=9, padx=5)

        self.offset_label = ttk.Label(controls, text="Offset: 0")
        self.offset_label.grid(row=0, column=10, padx=5)

        self.packets_label = ttk.Label(controls, text="Pkts: 0")
        self.packets_label.grid(row=0, column=11, padx=5)

    # ----------------- STREAM CONTROL -----------------
    def toggle_stream(self):
        if not self.streamer.running:
            self.streamer.start(self._on_frame)
            self.stream_btn.config(text="Stop Stream")
            self.record_btn.config(state="normal")
        else:
            if self.recording:
                self.toggle_record()
            self.streamer.stop()
            self.stream_btn.config(text="Start Stream")
            self.record_btn.config(state="disabled")
            self.current_frame = None
            self._show_off_message()

    # ----------------- FRAME HANDLING -----------------
    def _on_frame(self, img):
        self.packets_label.config(text=f"Pkts: {self.streamer.packets_in_frame()}")
        aligned, offset = self._align_frame(self.prev_frame, img)
        self.prev_frame = aligned.copy()
        self.current_frame = aligned
        self.offset_label.config(text=f"Offset: {offset}")
        if self.recording and self.video_writer:
            frame = cv2.cvtColor(np.array(aligned), cv2.COLOR_RGB2BGR)
            self.video_writer.write(frame)
        self._display_current_frame()

    def _display_current_frame(self):
        self.canvas.delete("all")
        if self.current_frame is None:
            self._show_off_message()
            return
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        img_w, img_h = self.current_frame.size
        scale = min(canvas_w / img_w, canvas_h / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        img = self.current_frame.resize((new_w, new_h), Image.LANCZOS)
        x = (canvas_w - new_w) // 2
        y = (canvas_h - new_h) // 2
        self.tk_image = ImageTk.PhotoImage(img)
        self.canvas.create_image(x, y, anchor=tk.NW, image=self.tk_image)
        if self.recording and self.record_indicator_state:
            self.canvas.create_oval(10, 10, 30, 30, fill="red", tags="record_indicator")

    def _align_frame(self, prev: Image.Image | None, curr: Image.Image, max_offset: int = 10) -> tuple[Image.Image, int]:
        if prev is None:
            return curr, 0
        prev_g = np.array(prev.convert("L"))
        curr_g = np.array(curr.convert("L"))
        h = min(prev_g.shape[0], curr_g.shape[0])
        w = min(prev_g.shape[1], curr_g.shape[1])
        template_h = min(80, h)
        template = prev_g[h - template_h : h, :w]
        search_top = min(curr_g.shape[0], template_h + max_offset * 2)
        search = curr_g[:search_top, :w]
        res = cv2.matchTemplate(search, template, cv2.TM_CCORR_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(res)
        offset = max_loc[1] - max_offset
        if offset == 0:
            return curr, 0
        curr_np = np.array(curr)
        aligned = np.zeros_like(curr_np)
        if offset > 0:
            aligned[:-offset] = curr_np[offset:]
        else:
            aligned[-offset:] = curr_np[: curr_np.shape[0] + offset]
        return Image.fromarray(aligned), offset

    def _show_off_message(self):
        self.canvas.delete("all")
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        self.canvas.create_text(
            canvas_w // 2,
            canvas_h // 2,
            text="Stream is off",
            fill="white",
            font=("Arial", 20),
        )

    # ----------------- BUTTON CALLBACKS -----------------
    def toggle_mic(self):
        self.mic_on = not self.mic_on
        self.mic_btn.config(text="Mic On" if self.mic_on else "Mic Off")

    def toggle_flip_h(self):
        self.processor.flip_h = not self.processor.flip_h

    def toggle_flip_v(self):
        self.processor.flip_v = not self.processor.flip_v

    def toggle_rotate(self):
        self.processor.rotate_90 = not self.processor.rotate_90

    def toggle_bw(self):
        self.processor.grayscale = not self.processor.grayscale

    def toggle_record(self):
        if not self.recording:
            self._start_record()
        else:
            self._stop_record()

    def _start_record(self):
        ensure_output_dir()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(OUTPUT_DIR, f"record_{timestamp}.avi")
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        if self.current_frame is not None:
            w, h = self.current_frame.size
        else:
            w = int(self.canvas.winfo_width()) or 640
            h = int(self.canvas.winfo_height()) or 480
        self.video_writer = cv2.VideoWriter(path, fourcc, 20.0, (w, h))
        if not self.video_writer.isOpened():
            messagebox.showerror("Recording", "Failed to open video writer")
            self.video_writer = None
            return
        self.record_file = path
        self.recording = True
        self.record_btn.config(text="Stop Recording")
        self._blink_record_indicator()

    def _stop_record(self):
        self.recording = False
        self.record_btn.config(text="Record")
        if self.blink_job:
            self.root.after_cancel(self.blink_job)
            self.blink_job = None
        self.canvas.delete("record_indicator")
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            final_path = convert_to_mpg(self.record_file)
            messagebox.showinfo("Recording", f"Saved to {final_path}")

    def _blink_record_indicator(self):
        if not self.recording:
            self.canvas.delete("record_indicator")
            return
        self.record_indicator_state = not self.record_indicator_state
        self._display_current_frame()
        self.blink_job = self.root.after(500, self._blink_record_indicator)

    def take_snapshot(self):
        if self.current_frame is None:
            return
        ensure_output_dir()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(OUTPUT_DIR, f"snapshot_{timestamp}.jpg")
        self.current_frame.save(path)
        messagebox.showinfo("Snapshot", f"Saved to {path}")

    def on_volume_change(self, _=None):
        # Placeholder for real volume control
        pass

    def on_align_change(self, _=None):
        self.config.alignment_threshold = int(float(self.align_threshold.get()))

    def open_config_dialog(self) -> None:
        ConfigDialog(self.root, self.config, on_save=self._on_config_saved)

    def _on_config_saved(self) -> None:
        was_running = self.streamer.running
        if was_running:
            self.streamer.stop()
        self.streamer = CameraStreamer(self.config, self.processor)
        if was_running:
            self.streamer.start(self._on_frame)
        self.align_threshold.set(self.config.alignment_threshold)
