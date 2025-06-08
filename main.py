import argparse
import logging
import tkinter as tk
from gui import CameraApp

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AP Camera Receiver")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    root = tk.Tk()
    app = CameraApp(root)
    root.mainloop()
