"""Audio recording and streaming management for recass."""

import threading
import numpy as np
import torch
import torchaudio
import torchaudio.transforms as T
import sounddevice as sd

from config import WHISPER_SAMPLE_RATE, CHUNK_SECONDS, MIX_SAMPLE_RATE


class AudioRecorder:
    """Handles audio capture from microphone and loopback sources."""

    def __init__(self, mic_id, loopback_id, transcription_queue, level_callback=None):
        self.mic_id = mic_id
        self.loopback_id = loopback_id
        self.transcription_queue = transcription_queue
        self.level_callback = level_callback
        
        self.mic_buffer = []
        self.loopback_buffer = []
        self.mic_buffer_size = 0
        self.loopback_buffer_size = 0
        
        self.lock = threading.Lock()
        self.loopback_silence_warning_shown = False
        
        self.mic_stream = None
        self.loopback_stream = None
        
        self.mic_samplerate = None
        self.loopback_samplerate = None
        self.mic_resampler = None
        self.loopback_resampler = None

        self.mic_file_buffer = []
        self.loopback_file_buffer = []
        self.is_writing_audio = False
        self.mixed_audio_path = None

    def mic_callback(self, indata, frames, time, status):
        # print(f"DEBUG: Mic callback triggered.")
#        if status:
#            print(f"Mic Status: {status}")
#        if indata.any():
#            print(f"DEBUG: Mic indata.any() is True. Mean abs: {np.abs(indata).mean():.2f}")
#        else:
#            print(f"DEBUG: Mic indata.any() is False (silence). Mean abs: {np.abs(indata).mean():.2f}")
        self._process_data(indata, "MIC")

    def loopback_callback(self, indata, frames, time, status):
        # print(f"DEBUG: Loopback callback triggered.")
#        if status:
#            print(f"Loopback Status: {status}")
#        if indata.any():
#            print(f"DEBUG: Loopback indata.any() is True. Mean abs: {np.abs(indata).mean():.2f}")
#        else:
#            print(f"DEBUG: Loopback indata.any() is False (silence). Mean abs: {np.abs(indata).mean():.2f}")
        self._process_data(indata, "LOOPBACK")

    def _process_data(self, indata, source_name):
        """Process incoming audio data from either mic or loopback source."""
        if self.level_callback:
            audio_float = indata.flatten().astype(np.float32) / 32768.0
            rms = np.sqrt(np.mean(audio_float**2))
            self.level_callback(source_name, rms)

        with self.lock:
            if self.is_writing_audio:
                if source_name == "MIC":
                    self.mic_file_buffer.append(indata.copy())
                else:  # LOOPBACK
                    self.loopback_file_buffer.append(indata.copy())

            if source_name == "MIC":
                buffer_list = self.mic_buffer
                buffer_size = self.mic_buffer_size
                samplerate = self.mic_samplerate
                resampler = self.mic_resampler
                buffer_list_attr = "mic_buffer"
                buffer_size_attr = "mic_buffer_size"
            else:  # LOOPBACK
                buffer_list = self.loopback_buffer
                buffer_size = self.loopback_buffer_size
                samplerate = self.loopback_samplerate
                resampler = self.loopback_resampler
                buffer_list_attr = "loopback_buffer"
                buffer_size_attr = "loopback_buffer_size"
                
                if not self.loopback_silence_warning_shown:
                    mean_abs = np.abs(indata).mean()
                    if mean_abs < 100:
                        print(
                            f"\n⚠️  WARNUNG: Loopback-Stream scheint leise "
                            f"(Amplitude: {mean_abs:.2f}). Audio wird abgespielt?"
                        )
                        self.loopback_silence_warning_shown = True

            new_data = indata.flatten()
            buffer_list.append(new_data)
            buffer_size += new_data.size
            
            frames_per_chunk = int(samplerate * CHUNK_SECONDS)

            if buffer_size >= frames_per_chunk:
                full_audio = np.concatenate(buffer_list)
                chunk = full_audio[:frames_per_chunk]
                remainder = full_audio[frames_per_chunk:]

                buffer_list.clear()
                if remainder.size > 0:
                    buffer_list.append(remainder)
                    buffer_size = remainder.size
                else:
                    buffer_size = 0
                
                # Konvertiere zu Float32 für die Weiterverarbeitung
                audio_float = chunk.astype(np.float32) / 32768.0

                # Resample, falls notwendig
                if resampler:
                    audio_torch = torch.from_numpy(audio_float)
                    audio_resampled = resampler(audio_torch)
                    audio_final = audio_resampled.numpy()
                else:
                    audio_final = audio_float
                
                self.transcription_queue.put((audio_final, source_name))

            setattr(self, buffer_size_attr, buffer_size)

    def start_audio_file_writing(self, mixed_path):
        """Start capturing audio to file buffers."""
        with self.lock:
            self.mixed_audio_path = mixed_path
            self.mic_file_buffer.clear()
            self.loopback_file_buffer.clear()
            self.is_writing_audio = True

    def stop_audio_file_writing(self):
        """Stop capturing audio and save mixed audio file. Returns the path to the saved file."""
        with self.lock:
            self.is_writing_audio = False
            mic_buffer_copy = list(self.mic_file_buffer)
            loopback_buffer_copy = list(self.loopback_file_buffer)
            self.mic_file_buffer.clear()
            self.loopback_file_buffer.clear()

        print(f"🔍 DEBUG: mic_buffer_copy length: {len(mic_buffer_copy)}, loopback_buffer_copy length: {len(loopback_buffer_copy)}, path: {self.mixed_audio_path}")
        
        if not self.mixed_audio_path:
            print("⚠️  Warning: mixed_audio_path not set")
            return None
        
        if not mic_buffer_copy and not loopback_buffer_copy:
            print("⚠️  Warning: Both audio buffers are empty")
            return None

        # Process mic audio
        if mic_buffer_copy:
            mic_audio_int16 = np.concatenate(mic_buffer_copy, axis=0)
            mic_audio_float32 = mic_audio_int16.astype(np.float32) / 32768.0
            mic_tensor = torch.from_numpy(mic_audio_float32.flatten())
            if self.mic_samplerate != MIX_SAMPLE_RATE:
                resampler = T.Resample(orig_freq=self.mic_samplerate, new_freq=MIX_SAMPLE_RATE)
                mic_tensor = resampler(mic_tensor)
        else:
            mic_tensor = torch.tensor([], dtype=torch.float32)

        # Process loopback audio
        if loopback_buffer_copy:
            loopback_audio_int16 = np.concatenate(loopback_buffer_copy, axis=0)
            loopback_audio_float32 = loopback_audio_int16.astype(np.float32) / 32768.0
            loopback_tensor = torch.from_numpy(loopback_audio_float32.flatten())
            if self.loopback_samplerate != MIX_SAMPLE_RATE:
                resampler = T.Resample(
                    orig_freq=self.loopback_samplerate, new_freq=MIX_SAMPLE_RATE
                )
                loopback_tensor = resampler(loopback_tensor)
        else:
            loopback_tensor = torch.tensor([], dtype=torch.float32)

        mic_len = mic_tensor.shape[0]
        loopback_len = loopback_tensor.shape[0]
        max_len = max(mic_len, loopback_len)

        if max_len > 0:
            # Padding
            mic_padded = torch.nn.functional.pad(mic_tensor, (0, max_len - mic_len))
            loopback_padded = torch.nn.functional.pad(loopback_tensor, (0, max_len - loopback_len))

            # Create stereo audio and save (mic on left, loopback on right)
            mixed_tensor = torch.stack([mic_padded, loopback_padded], dim=0)

            try:
                torchaudio.save(self.mixed_audio_path, mixed_tensor, MIX_SAMPLE_RATE, backend="soundfile")
                print(f"🎤+🖥️ Gemischtes Audio gespeichert in: {self.mixed_audio_path}")
                return self.mixed_audio_path
            except Exception as e:
                print(f"❌ Fehler beim Speichern des gemischten Audios: {e}")
                return None
        
        return None

    def start_recording(self):
        """Initialize and start audio streams."""
        # Öffne Streams ohne feste Samplerate, um die Standardrate des Geräts zu verwenden
        self.mic_stream = sd.InputStream(
            device=self.mic_id, channels=1, dtype='int16', callback=self.mic_callback, blocksize=1024
        )
        self.loopback_stream = sd.InputStream(
            device=self.loopback_id, channels=1, dtype='int16', callback=self.loopback_callback, blocksize=1024
        )

        # Hole die tatsächliche Samplerate von den Streams
        self.mic_samplerate = int(self.mic_stream.samplerate)
        self.loopback_samplerate = int(self.loopback_stream.samplerate)

        mic_resample_status = 'aktiviert' if self.mic_samplerate != WHISPER_SAMPLE_RATE else 'übersprungen'
        loopback_resample_status = 'aktiviert' if self.loopback_samplerate != WHISPER_SAMPLE_RATE else 'übersprungen'
        
        print(f"🎤 Mic-Stream:      Gerät nutzt {self.mic_samplerate} Hz. Resampling nach {WHISPER_SAMPLE_RATE} Hz wird {mic_resample_status}.")
        print(f"🖥️ Loopback-Stream: Gerät nutzt {self.loopback_samplerate} Hz. Resampling nach {WHISPER_SAMPLE_RATE} Hz wird {loopback_resample_status}.")

        # Erstelle Resampler-Objekte, falls die Raten nicht übereinstimmen
        if self.mic_samplerate != WHISPER_SAMPLE_RATE:
            self.mic_resampler = T.Resample(
                orig_freq=self.mic_samplerate, new_freq=WHISPER_SAMPLE_RATE
            )
        
        if self.loopback_samplerate != WHISPER_SAMPLE_RATE:
            self.loopback_resampler = T.Resample(
                orig_freq=self.loopback_samplerate, new_freq=WHISPER_SAMPLE_RATE
            )

        # Starte die Streams
        self.mic_stream.start()
        self.loopback_stream.start()
        print(f"🎙️ Aufnahme gestartet: Mic ('{self.mic_id}') und Loopback ('{self.loopback_id}')")

    def stop_recording(self):
        """Stop and close audio streams."""
        if self.mic_stream:
            self.mic_stream.stop()
            self.mic_stream.close()
        if self.loopback_stream:
            self.loopback_stream.stop()
            self.loopback_stream.close()
