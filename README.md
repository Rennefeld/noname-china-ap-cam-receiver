# noname-china-ap-cam-receiver

![image](https://github.com/user-attachments/assets/a5ab85a1-102d-4f0f-a91e-450537760f3d)
![image](https://github.com/user-attachments/assets/e0b32b87-d101-4292-b5d3-7774b4c4668e)
![image](https://github.com/user-attachments/assets/ab484e62-75b2-4369-8a6d-e5ad57c945eb)


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
\n## Reliability improvements
Each chunk now carries a CRC16 checksum in the header. Damaged chunks are
discarded and a small NACK message is sent to request a resend. Incoming frames
are buffered in a double queue so that GUI updates never clash with the
receiver thread.

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
