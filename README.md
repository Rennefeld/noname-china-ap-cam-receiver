# noname-china-ap-cam-receiver

Simple GUI application to receive MJPEG streams from the noname AP camera.
The app allows configuring connection parameters and manipulating the video in
real time. It supports recording, snapshots and basic image transformations.
Open the settings dialog via the **Settings** menu to adjust connection
options. Changes are persisted to `config.json`.
The preview canvas keeps a 1:1 aspect ratio and shows a message if the stream
is not running.
The config also allows setting **Packets per Frame** which controls how many
network packets are collected before a JPEG frame is processed.
Run with:
```bash
pip install -r requirements.txt
python main.py
```

## Packaging

To create a standalone executable for Windows, install PyInstaller and run:

```bash
pip install pyinstaller
pyinstaller --onefile main.py
```

For an Android APK, the project can be packaged with [BeeWare](https://beeware.org/) or
[Buildozer](https://github.com/kivy/buildozer). Set up the chosen toolchain and execute
the build command on a machine with the required Android SDK/NDK installed.
