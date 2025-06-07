import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Any

from config import StreamConfig

class ConfigDialog(tk.Toplevel):
    """Dialog window for editing StreamConfig."""

    def __init__(self, master: tk.Misc, config: StreamConfig, on_save: Callable[[], None] | None = None) -> None:
        super().__init__(master)
        self.title("Settings")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self._config = config
        self._on_save = on_save
        self._vars: Dict[str, Any] = {}
        self._build()

    def _build(self) -> None:
        fields = [
            ("Camera IP", "cam_ip"),
            ("Cam Video Port", "cam_video_port"),
            ("Cam Audio Port", "cam_audio_port"),
            ("Client Video Port", "client_video_port"),
            ("Client Audio Port", "client_audio_port"),
            ("Frame Buffer", "frame_buffer_size"),
            ("Header Bytes", "header_bytes"),
            ("Jitter Delay", "jitter_delay"),
        ]

        frame = ttk.Frame(self)
        frame.pack(padx=10, pady=10)

        for i, (label, field) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky="w")
            value = getattr(self._config, field)
            var = tk.StringVar(value=str(value))
            self._vars[field] = var
            ttk.Entry(frame, textvariable=var, width=15).grid(row=i, column=1, padx=5, pady=2)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=5)

        ttk.Button(btn_frame, text="Save", command=self._save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Restore Defaults", command=self._restore_defaults).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="right", padx=5)

    def _save(self) -> None:
        for field, var in self._vars.items():
            current_value = getattr(self._config, field)
            cast_type = type(current_value)
            setattr(self._config, field, cast_type(var.get()))
        self._config.save()
        if self._on_save:
            self._on_save()
        self.destroy()

    def _restore_defaults(self) -> None:
        defaults = StreamConfig()
        for field, var in self._vars.items():
            var.set(str(getattr(defaults, field)))


