# noname-china-ap-cam-receiver

Simple GUI application to receive MJPEG streams from the noname AP camera.
The app allows configuring connection parameters and manipulating the video in
real time. It supports recording, snapshots and basic image transformations.
Open the settings dialog via the **Settings** menu to adjust connection
options. Changes are persisted to `config.json`.
The preview canvas keeps a 1:1 aspect ratio and shows a message if the stream
is not running.
The config also allows setting **frame dimensions** and **rows per chunk**.
`rows_per_chunk` is used to calculate the UDP `chunk_size` so that each packet
contains an exact number of image rows. The previously used **Packets per
Frame** setting now reflects how many unique chunks were received for the last
frame.
An additional slider on the main window sets the **Alignment Threshold** for
checking horizontal drift between frames.
Run with:
```bash
pip install -r requirements.txt
python main.py
```

## Packaging

### Windows executable
Install [PyInstaller](https://pyinstaller.org) and build the single file binary:

```bash
pip install pyinstaller
pyinstaller --onefile main.py
```

### Android APK with Buildozer
Install the toolchain and dependencies (requires Linux):

```bash
sudo apt update
sudo apt install -y build-essential git python3 python3-pip openjdk-17-jdk ffmpeg
pip install buildozer
```

Initialize Buildozer and create the APK:

```bash
buildozer init  # creates buildozer.spec
buildozer -v android debug
```

`ffmpeg` is needed so recordings can be automatically converted from AVI to MPG.
