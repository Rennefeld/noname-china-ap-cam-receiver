import argparse
import logging
import tkinter as tk
from gui import CameraApp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AP Camera Receiver")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable verbose logging",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    root = tk.Tk()
    app = CameraApp(root)
    root.mainloop()
