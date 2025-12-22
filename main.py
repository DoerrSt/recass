# [file name]: main.py
#!/usr/bin/env python3
"""
recass - Real-time Conference Audio Transcription and Speaker Separation

Main entry point for the application. Handles device detection and configuration.
"""

import sounddevice as sd
import platform
import os
import config
from ui_application import Application


def detect_device_type(device_name):
    """Classify audio device by name."""
    dev_name_lower = device_name.lower()
    
    if '.monitor' in dev_name_lower:
        return "Loopback/Monitor"
    elif any(x in dev_name_lower for x in ['brave', 'spotify', 'firefox', 'chrome']):
        return "Anwendung"
    elif any(x in dev_name_lower for x in ['mic', 'headset', 'webcam', 'plantronics', 'camera']):
        return "Mikrofon"
    elif 'hdmi' in dev_name_lower or 'displayport' in dev_name_lower:
        return "Display Audio"
    elif any(x in dev_name_lower for x in ['controller', 'jack', 'pulse', 'pipewire']):
        return "System/Virtuell"
    else:
        return "Unbekannt"


def list_audio_devices():
    """List all available audio input devices."""
    print("\n--- Audio-Geräte-Setup ---")
    print("Unten sehen Sie eine Liste der von Ihrem System erkannten Audio-Eingabegeräte.")
    print("Bitte wählen Sie die numerischen IDs für Ihr Mikrofon und die Audio-Quelle des Computers aus.")
    
    try:
        devices = sd.query_devices()
        valid_devices = []
        
        for dev in devices:
            if dev['max_input_channels'] > 0:
                device_type = detect_device_type(dev['name'])
                valid_devices.append(dev)
                print(f"  ID {dev['index']:<3} | Typ: {device_type:<17} | Name: {dev['name']}")
        
        return valid_devices
    except Exception as e:
        print(f"Konnte keine Geräte mit 'sounddevice' auflisten: {e}")
        raise


def print_setup_instructions():
    """Print helpful instructions for loopback setup."""
    print("-" * 50)
    print("HINWEIS FÜR COMPUTER-AUDIO (LOOPBACK):")
    print("Ihr System (dank PipeWire) listet möglicherweise eine Audio-Quelle direkt für Ihre Anwendung auf (z.B. 'Brave', 'Spotify').")
    print("Wenn Sie eine solche Quelle sehen, ist deren ID die beste Wahl für die 'Loopback-Quelle'.")
    print("Andernfalls suchen Sie nach einer Quelle mit 'Monitor' im Namen.")
    print("-" * 50)


def get_device_selection():
    """Prompt user to select microphone and loopback devices."""
    print_setup_instructions()
    
    try:
        mic_input = input("Geben Sie die ID für das Mikrofon ein: ").strip()
        loopback_input = input("Geben Sie die ID für die Loopback-Quelle (z.B. 'Brave') ein: ").strip()

        if not mic_input or not loopback_input:
            print("\n❌ Fehler: Beide Geräte-IDs sind erforderlich. Programm wird beendet.")
            return None, None
            
        return int(mic_input), int(loopback_input)
    except (ValueError, TypeError):
        print("\n❌ Ungültige Eingabe. Bitte geben Sie eine numerische ID ein.")
        return None, None


def check_dependencies():
    """Check for Linux-specific dependencies."""
    if platform.system() == "Linux":
        try:
            import gi
            gi.require_version('AppIndicator3', '0.1')
        except (ImportError, ValueError):
            print("---")
            print("⚠️  WARNUNG: Das pystray-Backend 'AppIndicator' wurde nicht gefunden.")
            print("   Das Taskleisten-Icon funktioniert möglicherweise nicht wie erwartet.")
            print("   Für eine korrekte Funktion unter Linux (besonders KDE/Gnome) installieren Sie bitte die Abhängigkeiten:")
            print("   Debian/Ubuntu: sudo apt install libappindicator3-1 python3-gi")
            print("   Arch Linux:    sudo pacman -S libappindicator-gtk3")
            print("   Fedora:        sudo dnf install libappindicator-gtk3")
            print("---\n")


def main():
    """Main application entry point."""
    # If Hugging Face token is not in env, try to load from config file
    if not os.environ.get("HUGGING_FACE_TOKEN"):
        print("HUGGING_FACE_TOKEN not found in environment, checking config file...")
        settings = config.load_user_settings()
        hf_token = settings.get('hf_token')
        if hf_token:
            os.environ["HUGGING_FACE_TOKEN"] = hf_token
            print("Loaded HUGGING_FACE_TOKEN from config file.")

    check_dependencies()
    
    app = Application()

    try:
        app.run()
        
    except KeyboardInterrupt:
        print("\n👋 Programm wird beendet...")
        if app.system_tray.icon and app.system_tray.icon.visible:
            app.quit_action(app.system_tray.icon, None)
    except Exception as e:
        print(f"\nEin unerwarteter Fehler ist aufgetreten: {e}")
    finally:
        print("✅ Programm vollständig beendet.")


if __name__ == "__main__":
    main()