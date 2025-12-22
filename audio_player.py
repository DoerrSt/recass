import sounddevice as sd
import numpy as np
import numpy.typing as npt
import torchaudio
import torch

def load_audio(audio_path: str):
    audio_wav, sr = torchaudio.load(audio_path)
    # Resample if necessary
    if sr != 24000:
        resampler = torchaudio.transforms.Resample(sr, 24000)
        audio_wav = resampler(audio_wav)
    audio_wav = audio_wav.mean(dim=0, keepdim=True)
    # Convert to int16
    audio_wav = (audio_wav * 32767).to(torch.int16)
    return audio_wav.squeeze().numpy(), 24000


class AudioPlayer:
    def __init__(self, samplerate=24000):
        self.stream = sd.OutputStream(samplerate=samplerate, channels=1, dtype=np.int16)
        self.stream.start()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stream.stop()
        self.stream.close()

    def add_audio(self, audio_data: npt.NDArray[np.int16]):
        self.stream.write(audio_data)

    def close(self):
        self.stream.stop()
        self.stream.close()
