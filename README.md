# noname-china-ap-cam-receiver

Simple GUI application to receive MJPEG streams from the noname AP camera.
The app allows configuring connection parameters and manipulating the video in
real time. It supports recording, snapshots and basic image transformations.
Open the settings dialog via the **Settings** menu to adjust connection
options. Changes are persisted to `config.json`.
The preview canvas keeps a 1:1 aspect ratio and shows a message if the stream
is not running.
The config also allows setting **Packets per Frame** which controls how many
network packets are collected before a JPEG frame is processed. Frames are
automatically aligned to reduce visible jitter between packets.
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

## Test Environment

A fake camera utility is provided to replay the captured network traffic from
`docs/PCAPdroid_log.pcap`. This allows testing the receiver without the actual
hardware. The tool requires root privileges because it replays raw packets with
Scapy.

Run the simulator:

```bash
pip install -r requirements.txt
sudo python tests/fake_camera.py docs/PCAPdroid_log.pcap --iface eth0
```

Use `--client-ip`, `--camera-ip` and `--client-port` to override addresses from
the capture if your network setup differs.
