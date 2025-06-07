import tkinter as tk
from tkinter import messagebox
import threading
import socket
import time
import os
from PIL import Image, ImageTk, UnidentifiedImageError
import io
import cv2
import numpy as np

# ============================
# ===== Konfiguration =======
# ============================
CAM_IP = "192.168.4.153"        # IP der Kamera im AP-Modus
KEEPALIVE_PORT = 8070           # Port, an den wir "0f" (Hex 30 66) senden
VIDEO_PORT = 8080               # Port, von dem die Kamera MJPEG über UDP schickt
REQUESTED_LOCAL_PORT = 53310    # Bevorzugter lokaler Port
KEEPALIVE_INTERVAL = 5          # Sekunden zwischen den Keep-Alive-Paketen
OUTPUT_DIR = "recordings"       # Ordner, in den Video abgespeichert werden

WINDOW_SIZE = 640               # Fenstermaße (640×640)
BG_COLOR = "#ffffff"            # Weißer Hintergrund
FG_COLOR = "#333333"            # Dunkelgraue Schrift

FIXED_FPS = 20                  # Gewünschte Bildrate (frames/sec)
FRAME_INTERVAL = 1.0 / FIXED_FPS

# ============================
# ===== Hilfsfunktionen =====
# ============================
def ensure_output_dir():
    """Legt den OUTPUT_DIR an, falls er nicht existiert."""
    if not os.path.isdir(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

# ============================
# ===== GUI-Anwendung =======
# ============================
class CameraApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MJPEG-UDP Streamer (Fixed FPS)")
        self.root.geometry(f"{WINDOW_SIZE}x{WINDOW_SIZE}")
        self.root.configure(bg=BG_COLOR)

        # Canvas zum Anzeigen der MJPEG-Frames
        self.canvas = tk.Canvas(root, width=WINDOW_SIZE, height=WINDOW_SIZE - 100, bg="black")
        self.canvas.pack(pady=10)

        # Frame für Buttons und Port-Label
        self.btn_frame = tk.Frame(root, bg=BG_COLOR)
        self.btn_frame.pack()

        # Start/Stop-Stream-Button
        self.stream_btn = tk.Button(
            self.btn_frame, text="Start Stream", command=self.toggle_stream,
            bg=BG_COLOR, fg=FG_COLOR, width=12
        )
        self.stream_btn.grid(row=0, column=0, padx=10)

        # Record-Button (wird aktiv, sobald Stream läuft)
        self.record_btn = tk.Button(
            self.btn_frame, text="Record", command=self.toggle_record,
            bg=BG_COLOR, fg=FG_COLOR, width=12, state="disabled"
        )
        self.record_btn.grid(row=0, column=1, padx=10)

        # Blinker: Kleiner Kreis, der während der Aufnahme rot blinkt
        self.record_indicator = tk.Canvas(
            self.btn_frame, width=20, height=20, bg=BG_COLOR, highlightthickness=0
        )
        self.record_indicator.grid(row=0, column=2, padx=10)
        self.record_dot = self.record_indicator.create_oval(4, 4, 16, 16, fill="", outline="")

        # Label, in dem wir den tatsächlich verwendeten lokalen Port anzeigen
        self.port_label = tk.Label(
            self.btn_frame, text="Local Port: N/A", bg=BG_COLOR, fg=FG_COLOR
        )
        self.port_label.grid(row=1, column=0, columnspan=3, pady=5)

        # Statusvariablen
        self.streaming = False
        self.recording = False

        # UDP-Socket (später gebunden)
        self.sock = None
        self.local_port = None

        # Threads
        self.sender_thread = None
        self.receiver_thread = None

        # Puffer für MJPEG-Zusammenbau
        self.jpeg_buffer = bytearray()

        # Referenz aufs aktuell angezeigte Tkinter-Bild
        self.current_image = None

        # Aufnahme-Variablen
        self.video_writer = None
        self.temp_video_file = None

        # Timing für feste FPS
        self.last_frame_time = 0.0

    def toggle_stream(self):
        """Schaltet zwischen Start und Stop des UDP-Streams um."""
        if not self.streaming:
            self.start_stream()
        else:
            self.stop_stream()

    def start_stream(self):
        """Erstellt Socket, Threads und UI, um den Stream zu starten."""
        ensure_output_dir()

        # UDP-Socket erstellen
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Versuche, an den SPECIFIED REQUESTED_LOCAL_PORT zu binden
            self.sock.bind(("", REQUESTED_LOCAL_PORT))
            self.local_port = REQUESTED_LOCAL_PORT
        except Exception:
            # Falls der Port belegt oder verweigert, wähle einen beliebigen freien Port
            self.sock.bind(("", 0))
            self.local_port = self.sock.getsockname()[1]

        # Anzeige des benutzten Ports im GUI
        self.port_label.config(text=f"Local Port: {self.local_port}")

        # Status umschalten
        self.streaming = True
        self.stream_btn.config(text="Stop Stream")
        self.record_btn.config(state="normal")

        # Threads starten
        self.sender_thread = threading.Thread(target=self.keepalive_sender, daemon=True)
        self.receiver_thread = threading.Thread(target=self.receive_frames, daemon=True)
        self.sender_thread.start()
        self.receiver_thread.start()

    def stop_stream(self):
        """Stoppt den Stream, schließt den Socket, setzt UI zurück."""
        self.streaming = False
        self.stream_btn.config(text="Start Stream")
        self.record_btn.config(state="disabled")
        if self.recording:
            self.toggle_record()

        if self.sock:
            self.sock.close()
            self.sock = None

        # Canvas und Puffer leeren
        self.canvas.delete("all")
        self.jpeg_buffer.clear()
        self.port_label.config(text="Local Port: N/A")

        # Timing zurücksetzen
        self.last_frame_time = 0.0

    def toggle_record(self):
        """Schaltet zwischen Start/Stop der Aufnahme um."""
        if not self.recording:
            self.start_record()
        else:
            self.stop_record()

    def start_record(self):
        """Initialisiert VideoWriter und Aufnahme-Dateien."""
        ensure_output_dir()
        self.recording = True
        self.record_btn.config(text="Stop Recording")
        self.blink_dot()  # Startet den roten Blinkpunkt

        # Erstelle einzigartige Dateinamen mit Zeitstempel
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.temp_video_file = os.path.join(OUTPUT_DIR, f"video_{timestamp}.avi")
        self.final_output = os.path.join(OUTPUT_DIR, f"recording_{timestamp}.mp4")

        # VideoWriter initialisieren: MJPG, 640×480, FIXED_FPS
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        self.video_writer = cv2.VideoWriter(self.temp_video_file, fourcc, FIXED_FPS, (640, 480))

    def stop_record(self):
        """Beendet Videoaufnahme."""
        self.recording = False
        self.record_btn.config(text="Record")
        self.record_indicator.itemconfig(self.record_dot, fill="")

        # VideoWriter freigeben
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None

        # Die AVI-Datei ist bereits final
        self.final_output = self.temp_video_file
        messagebox.showinfo("Aufnahme beendet", f"Aufnahme gespeichert als:\n{self.final_output}")

    def blink_dot(self):
        """Lässt den roten Punkt blinken, solange Aufnahme läuft."""
        if not self.recording:
            return
        current = self.record_indicator.itemcget(self.record_dot, "fill")
        new_color = "red" if current == "" else ""
        self.record_indicator.itemconfig(self.record_dot, fill=new_color)
        self.root.after(500, self.blink_dot)

    def keepalive_sender(self):
        """Sendet alle KEEP-ALIVE-Pakete im festen Intervall."""
        payload_8070 = b"0f"  # ASCII "0f" → Hex 30 66
        payload_8080 = b"Bv"   # ASCII "Bv" → Hex 42 76
        while self.streaming:
            try:
                self.sock.sendto(payload_8070, (CAM_IP, KEEPALIVE_PORT))
                self.sock.sendto(payload_8080, (CAM_IP, VIDEO_PORT))
            except Exception as e:
                # Ignoriere Fehler, wenn der Stream gerade gestoppt wurde
                print(f"Fehler beim Keep-Alive-Senden: {e}")
            time.sleep(KEEPALIVE_INTERVAL)

    def receive_frames(self):
        """
        Empfängt UDP-Pakete (MJPEG) von der Kamera (VIDEO_PORT),
        fügt sie in einen Buffer, extrahiert vollständige JPEGs (SOI/EOI),
        überprüft (verify()), zeigt sie im Canvas an und speichert sie
        in die AVI, falls Aufnahme läuft und der nächste Zeitpunkt für die feste FPS erreicht ist.
        """
        while self.streaming:
            try:
                data, addr = self.sock.recvfrom(2048)
            except:
                break  # Socket wurde geschlossen
            sender_ip, sender_port = addr
            if sender_ip == CAM_IP and sender_port == VIDEO_PORT:
                # Füge Daten ins Buffer
                self.jpeg_buffer += data

                # Extrahiere so lange Frames, wie komplette JPEGs im Buffer stecken
                while True:
                    soi = self.jpeg_buffer.find(b"\xff\xd8")
                    if soi < 0:
                        break
                    eoi = self.jpeg_buffer.find(b"\xff\xd9", soi + 2)
                    if eoi < 0:
                        break
                    jpeg_data = self.jpeg_buffer[soi:eoi+2]
                    del self.jpeg_buffer[:eoi+2]

                    # JPEG-Verifikation: nur wenn vollständig, weiter verarbeiten
                    try:
                        Image.open(io.BytesIO(jpeg_data)).verify()
                    except Exception:
                        # Unvollständiges/kaputtes JPEG überspringen
                        continue

                    # Timing: feste FPS erzwingen (z.B. 20 fps)
                    now = time.monotonic()
                    if now - self.last_frame_time < FRAME_INTERVAL:
                        # Zu früh: verwerfe diesen Frame, warte auf nächsten
                        continue
                    self.last_frame_time = now

                    # Frame anzeigen (PIL + Tkinter)
                    try:
                        self.display_frame(jpeg_data)
                    except (UnidentifiedImageError, OSError):
                        # Sollte fast nie vorkommen, da verify() bereits geprüft hat
                        continue

                    # Wenn Aufnahme läuft, in die AVI schreiben
                    if self.recording and self.video_writer:
                        nparr = np.frombuffer(jpeg_data, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if frame is not None:
                            try:
                                resized = cv2.resize(frame, (640, 480))
                                self.video_writer.write(resized)
                            except Exception:
                                pass

    def display_frame(self, jpeg_data):
        """Zeigt ein JPEG-Bild im Tkinter-Canvas an."""
        image = Image.open(io.BytesIO(jpeg_data))
        image = image.resize((640, 480), Image.LANCZOS)
        tk_image = ImageTk.PhotoImage(image)
        self.current_image = tk_image  # Referenz merken, sonst verschwindet's wieder
        self.canvas.create_image(0, 0, anchor=tk.NW, image=tk_image)

# ============================
# ===== Hauptprogramm =======
# ============================
if __name__ == "__main__":
    root = tk.Tk()
    app = CameraApp(root)
    root.mainloop()
