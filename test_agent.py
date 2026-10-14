#!/usr/bin/env python3
print("Agent gestartet")
# Schreibe eine Datei nach /work
with open("/work/output.txt", "w") as f:
    f.write("Hello from agent!")
print("Datei geschrieben")
# Lese die Datei zurück
with open("/work/output.txt", "r") as f:
    content = f.read()
print(f"Gelesen: {content}")
print("Agent beendet")