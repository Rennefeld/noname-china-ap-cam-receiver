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
            ("Packets per Frame", "packets_per_frame"),
            ("Keepalive Interval", "keepalive_interval"),
        ]

        frame = ttk.Frame(self)
        frame.pack(padx=10, pady=10)

        buffer_values = [2 ** i for i in range(10, 31)]

        for i, (label, field) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky="w")
            value = getattr(self._config, field)
            if field == "frame_buffer_size":
                idx = buffer_values.index(value) if value in buffer_values else 0
                var = tk.IntVar(value=buffer_values[idx])
                self._vars[field] = var
                label_var = tk.StringVar(value=str(var.get()))

                def update(val, v=var, l=label_var):
                    choice = buffer_values[int(float(val))]
                    v.set(choice)
                    l.set(str(choice))

                scale = tk.Scale(
                    frame,
                    from_=0,
                    to=len(buffer_values) - 1,
                    orient="horizontal",
                    showvalue=False,
                    command=update,
                )
                scale.set(idx)
                scale.grid(row=i, column=1, padx=5, pady=2)
                ttk.Label(frame, textvariable=label_var).grid(row=i, column=2, sticky="w")
                self._vars[field + "_label"] = label_var
                self._vars[field + "_scale"] = scale
            else:
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
            if field.endswith("_label") or field.endswith("_scale"):
                continue
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
            if field.endswith("_label") or field.endswith("_scale"):
                continue
            var.set(str(getattr(defaults, field)))
            if field == "frame_buffer_size":
                label = self._vars.get(field + "_label")
                scale = self._vars.get(field + "_scale")
                if label and scale:
                    label.set(str(getattr(defaults, field)))
                    buffer_values = [2 ** i for i in range(10, 31)]
                    idx = buffer_values.index(getattr(defaults, field))
                    scale.set(idx)


