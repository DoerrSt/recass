"""Speech-to-text transcription with speaker diarization support."""

import os
import queue
import threading
from datetime import datetime
import numpy as np
import torch
import torchaudio
import torchaudio.transforms as T
import whisper
from pyannote.audio import Pipeline

from config import WHISPER_SAMPLE_RATE, load_user_settings
from ollama_analyzer import OllamaAnalyzer
import soundfile as sf
import config as cfg


class Transcriber(threading.Thread):
    """Handles audio transcription and optional speaker diarization."""

    def __init__(self, whisper_model, diarization_pipeline, audio_queue, text_callback=None, analysis_callback=None):
        super().__init__()
        self.audio_queue = audio_queue
        self.text_callback = text_callback
        self.analysis_callback = analysis_callback
        self.min_speakers = 0
        self.max_speakers = 0

        self.model = whisper_model
        self.diarization_pipeline = diarization_pipeline
        
        try:
            settings = load_user_settings()
            self.transcription_language = settings.get('transcription_language', 'en')
        except Exception:
            self.transcription_language = 'en'
        self.stop_event = threading.Event()
        # Only perform real-time transcription when recording is active.
        # This flag is set by the UI application when a recording session starts/stops.
        self.recording_enabled = False

        if self.diarization_pipeline:
            print("✓ Speaker Diarization ist AKTIV für LOOPBACK-Quelle")
        else:
            print("✗ Speaker Diarization ist DEAKTIVIERT - nur Standard-Transkription")

    def run(self):
        """Main transcription loop."""
        while not self.stop_event.is_set():
            try:
                audio_float, source = self.audio_queue.get(timeout=0.5)
                # If real-time recording is not enabled, skip processing incoming audio
                # and avoid printing to the console.
                if not getattr(self, 'recording_enabled', False):
                    self.audio_queue.task_done()
                    continue

                print(f"\n--- Transkribiere {source} ({len(audio_float)/WHISPER_SAMPLE_RATE:.1f}s) ---")

                if source == "LOOPBACK":
                    if self.diarization_pipeline:
                        print("✓ Nutze Diarization-Pipeline für LOOPBACK")
                        # Diarization für die Loopback-Quelle durchführen
                        self.diarize_and_transcribe(audio_float)
                    else:
                        print("⚠️  Diarization-Pipeline nicht verfügbar, nutze Standard-Transkription für LOOPBACK")
                        # Standard-Transkription für MIC oder wenn Diarization nicht verfügbar ist
                        self._transcribe_standard(audio_float, source)
                else:
                    # Standard-Transkription für MIC
                    self._transcribe_standard(audio_float, source)

                self.audio_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Fehler bei der Transkription: {e}")
                import traceback
                print(f"   Traceback: {traceback.format_exc()}")
                self.audio_queue.task_done()

    def _transcribe_standard(self, audio_float, source):
        """Perform standard transcription for mic or when diarization is unavailable."""
        if source == "MIC":
            # Energy-based VAD for mic input to filter out silence
            rms = np.sqrt(np.mean(audio_float**2))
            if rms < 0.001:  # Adjusted threshold from 0.01 to 0.003
                print(f"[{source}]: Stille erkannt (RMS: {rms:.4f}). Überspringe Transkription.")
                return

            # Use stricter parameters for mic input to prevent hallucinations on silence
            result = self.model.transcribe(
                audio_float,
                language="en",
                fp16=False,
                logprob_threshold=-0.8,
                no_speech_threshold=0.7
            )
        else:
            # Determine language parameter: None for auto detection
            lang = None if self.transcription_language == 'auto' else self.transcription_language
            result = self.model.transcribe(audio_float, language=lang, fp16=False)

        text = result['text'].strip()
        if text:
            prefix = "🎤 MIC: " if source == "MIC" else "🖥️ COMP: "
            print(f"{prefix}{text}")
            if self.text_callback:
                self.text_callback(text, source, None)
        else:
            print(f"[{source}]: Keine Sprache erkannt.")

    def diarize_and_transcribe(self, audio_float):
        """Perform speaker diarization and transcribe each speaker segment separately."""
        # Konvertiere Numpy-Array zu PyTorch-Tensor und füge eine Channel-Dimension hinzu
        audio_tensor = torch.from_numpy(audio_float).unsqueeze(0)
        
        try:
            print("🔍 Starte Diarization...")
            
            # HACK: Lower the VAD onset threshold to make it more sensitive to speech.
            # The default (0.83) is too high for some loopback audio levels.
            self.diarization_pipeline.segmentation.onset = 0.5

            diarization_params = {}
            if self.min_speakers > 0:
                diarization_params["min_speakers"] = self.min_speakers
            if self.max_speakers > 0:
                diarization_params["max_speakers"] = self.max_speakers

            print(f"📊 Diarization-Parameter: {diarization_params}")
            
            diarization_result = self.diarization_pipeline(
                {"waveform": audio_tensor, "sample_rate": WHISPER_SAMPLE_RATE},
                **diarization_params
            )
            
            print(f"✓ Diarization-Ergebnis Typ: {type(diarization_result)}")
            
            diarization = diarization_result
            
            print(f"✓ Speaker Diarization Typ: {type(diarization)}")
            print(f"✓ Speaker Diarization Länge: {len(diarization)}")

            # Check if diarization has any tracks
            num_tracks = 0
            for _ in diarization.itertracks():
                num_tracks += 1
            
            print(f"✓ Anzahl der Sprech-Segmente: {num_tracks}")

            if num_tracks == 0:
                print("[COMP]: Keine Sprache für Diarization erkannt (0 Segmente).")
                # Fallback zur Transkription des gesamten Chunks
                lang = None if self.transcription_language == 'auto' else self.transcription_language
                result = self.model.transcribe(audio_float, language=lang, fp16=False)
                text = result['text'].strip()
                if text:
                    print(f"🖥️ COMP: {text}")
                    if self.text_callback:
                        self.text_callback(text, "LOOPBACK", None)
                return

            print("🗣️ Sprechersegmente erkannt. Transkribiere einzeln...")
            
            # Iteriere über die Segmente und transkribiere sie
            for segment, track, speaker in diarization.itertracks(yield_label=True):
                start_frame = int(segment.start * WHISPER_SAMPLE_RATE)
                end_frame = int(segment.end * WHISPER_SAMPLE_RATE)
                
                segment_audio = audio_float[start_frame:end_frame].astype(np.float32).copy()
                segment_duration = len(segment_audio) / WHISPER_SAMPLE_RATE

                print(f"  📍 Segment [{speaker}]: {segment_duration:.2f}s ({start_frame}-{end_frame})")

                if len(segment_audio) < WHISPER_SAMPLE_RATE * 0.2:  # Ignoriere sehr kurze Segmente
                    print(f"     ⊘ Übersprungen (zu kurz: {segment_duration:.2f}s < 0.2s)")
                    continue

                try:
                    lang = None if self.transcription_language == 'auto' else self.transcription_language
                    result = self.model.transcribe(segment_audio, language=lang, fp16=False)
                    text = result['text'].strip()
                    if text:
                        print(f"🖥️ COMP [{speaker}]: {text}")
                        if self.text_callback:
                            self.text_callback(text, "LOOPBACK", speaker)
                    else:
                        print(f"     (keine Sprache erkannt)")
                except Exception as seg_error:
                    print(f"     ⚠️  Fehler beim Transkribieren dieses Segments: {seg_error}")
                    # Try with fallback method
                    try:
                        result = self.model.transcribe(
                            segment_audio,
                            language="en",
                            fp16=False,
                            task="transcribe"
                        )
                        text = result['text'].strip()
                        if text:
                            print(f"🖥️ COMP [{speaker}] (Fallback): {text}")
                            if self.text_callback:
                                self.text_callback(text, "LOOPBACK", speaker)
                    except Exception as fallback_error:
                        print(f"     ❌ Fallback auch fehlgeschlagen: {fallback_error}")

        except torch.OutOfMemoryError as e:
            print(f"❌ CUDA Out of Memory während der Diarization: {e}")
            print("   -> Fallback auf CPU-Verarbeitung für diese und zukünftige Transkriptionen.")

            # Move models to CPU
            try:
                if hasattr(self.model, 'device') and self.model.device.type == 'cuda':
                    self.model.to('cpu')
                    print("   ✓ Whisper-Modell auf CPU verschoben.")
                if self.diarization_pipeline is not None and hasattr(self.diarization_pipeline, 'device') and self.diarization_pipeline.device.type == 'cuda':
                    self.diarization_pipeline.to('cpu')
                    print("   ✓ Diarization-Pipeline auf CPU verschoben.")
            except Exception as move_e:
                print(f"   ❌ Kritischer Fehler beim Verschieben der Modelle auf CPU: {move_e}")
                return # Can't recover

            # Retry transcription on CPU
            print("   -> Wiederhole Transkription auf CPU...")
            try:
                lang = None if self.transcription_language == 'auto' else self.transcription_language
                result = self.model.transcribe(audio_float, language=lang, fp16=False)
                text = result['text'].strip()
                if text:
                    print(f"🖥️ COMP (CPU): {text}")
                    if self.text_callback:
                        self.text_callback(text, "LOOPBACK", None)
            except Exception as cpu_e:
                print(f"   ❌ Transkription auf CPU ist ebenfalls fehlgeschlagen: {cpu_e}")

        except Exception as e:
            import traceback
            print(f"❌ Fehler bei der Diarization: {e}")
            print(f"   Traceback: {traceback.format_exc()}")
            print("   Fallback zur Standard-Transkription für diesen Chunk.")
            lang = None if self.transcription_language == 'auto' else self.transcription_language
            result = self.model.transcribe(audio_float, language=lang, fp16=False)
            text = result['text'].strip()
            if text:
                print(f"🖥️ COMP: {text}")
                if self.text_callback:
                    self.text_callback(text, "LOOPBACK", None)

    def transcribe_recording_file(self, audio_file_path, output_filename=None, file_lock=None):
        """
        Perform full transcription of a recording file with speaker diarization.
        This is called when stopping to ensure accurate speaker detection on the complete recording.
        Saves results directly to output_filename if provided.
        """
        try:
            print(f"\n=== Re-Transkribiere vollständige Aufnahme: {audio_file_path} ===")
            
            # Load audio file
            data, sample_rate = sf.read(audio_file_path, dtype='float32')
            waveform = torch.from_numpy(data).T # sf.read gives (time, channels), torchaudio expects (channels, time)
            
            print(f"📁 Audiodatei geladen: {waveform.shape}, Sample Rate: {sample_rate}")
            
            # If stereo, use loopback (right channel)
            if waveform.shape[0] > 1:
                # Use loopback channel (right/channel 1) for diarization as it contains computer audio
                audio_channel = waveform[1, :].float()
                print(f"🖥️ Nutze Loopback-Kanal (rechts) für Diarization")
            else:
                audio_channel = waveform[0, :].float()
            
            # Resample to WHISPER_SAMPLE_RATE if needed
            if sample_rate != WHISPER_SAMPLE_RATE:
                resampler = T.Resample(orig_freq=sample_rate, new_freq=WHISPER_SAMPLE_RATE)
                audio_channel = resampler(audio_channel)
                print(f"🔄 Resampled zu {WHISPER_SAMPLE_RATE} Hz")
            
            # Ensure proper float32 format and clone to avoid reference issues
            audio_float = audio_channel.numpy().astype(np.float32).copy()
            
            # Temporarily replace text_callback to save to file instead
            original_callback = self.text_callback
            output_file = None
            
            if output_filename and file_lock:
                # Create output file for final transcription
                try:
                    output_file = open(output_filename, 'a', encoding='utf-8')
                    
                    def file_callback(text, source, speaker):
                        """Callback that writes to file instead of print."""
                        with file_lock:
                            if output_file and not output_file.closed:
                                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                speaker_str = f"/{speaker}" if speaker else ""
                                line = f"[{now}] [{source}{speaker_str}]: {text}\n"
                                try:
                                    output_file.write(line)
                                    output_file.flush()
                                except IOError as e:
                                    print(f"Fehler beim Schreiben in die Datei: {e}")
                    
                    self.text_callback = file_callback
                    output_file.write(f"\n=== Finale Transkription (mit Diarization) ===\n")
                    output_file.write(f"Start-Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    output_file.flush()
                    
                except IOError as e:
                    print(f"❌ Fehler beim Öffnen der Ausgabedatei: {e}")
                    output_file = None
            
            # Perform diarization and transcription on the full recording
            if self.diarization_pipeline:
                print("✓ Nutze Diarization-Pipeline für vollständige Aufnahme")
                self.diarize_and_transcribe(audio_float)
            else:
                print("⚠️  Diarization-Pipeline nicht verfügbar, nutze Standard-Transkription")
                self._transcribe_standard(audio_float, "LOOPBACK")
            
            # Restore original callback
            self.text_callback = original_callback
            
            if output_file and not output_file.closed:
                output_file.write(f"\n=== Transkription abgeschlossen ===\n")
                output_file.close()
                print(f"✅ Finale Transkription gespeichert in: {output_filename}")
            
            print("=== Vollständige Transkription abgeschlossen ===\n")
            
        except Exception as e:
            import traceback
            print(f"❌ Fehler bei der Transkription der Datei: {e}")
            print(f"   Traceback: {traceback.format_exc()}")

    def analyze_meeting_minutes(self, output_filename, send_screenshots_to_llm=True, final_inconsistencies_note: str = ""):
        """
        Analyze meeting minutes from transcription file using Ollama.
        
        Args:
            output_filename: Path to the transcription file to analyze
            send_screenshots_to_llm (bool): Whether to send screenshots to the LLM for analysis.
        """
        try:
            # Read the transcription from file
            with open(output_filename, 'r', encoding='utf-8') as f:
                meeting_minutes = f.read()
            
            if not meeting_minutes or not meeting_minutes.strip():
                print("❌ No meeting minutes found to analyze")
                return
            
            print("\n" + "="*60)
            print("🔍 STARTING MEETING MINUTES ANALYSIS")
            print("="*60)
            
            # Load Ollama settings from config
            try:
                settings = load_user_settings()
                base_url = settings.get('ollama_url', 'http://localhost:11434')
                model_name = settings.get('ollama_model_name', 'llama3')
            except Exception:
                base_url = 'http://localhost:11434'
                model_name = 'llama3'
                
            # Initialize Ollama analyzer with all settings
            analyzer = OllamaAnalyzer(
                base_url=base_url,
                model_name=model_name,
                language=self.transcription_language
            )
            
            # Extract meeting folder and conditionally load screenshots
            meeting_folder = os.path.dirname(output_filename)
            if meeting_folder and send_screenshots_to_llm: # Conditional check added here
                analyzer.load_screenshots_from_folder(meeting_folder)
            
            # Append final inconsistency note if present
            if final_inconsistencies_note:
                print(f"DEBUG: Appending final inconsistency note to meeting minutes. Length before: {len(meeting_minutes)}")
                meeting_minutes += f"\n{final_inconsistencies_note}"
                print(f"DEBUG: Length after appending note: {len(meeting_minutes)}")
                print(f"DEBUG: Last 500 chars of meeting_minutes before analysis:\n{meeting_minutes[-500:]}")

            # Perform analysis
            result = analyzer.analyze_minutes(meeting_minutes)
            
            if result['success']:
                analysis = result['analysis']
                
                # Save analysis to file with screenshots embedded
                analysis_filename = output_filename.replace('.txt', '-analysis.txt')
                analyzer.save_analysis_with_screenshots(analysis_filename, analysis)
                
                # Print analysis
                print("\n" + analysis)
                print("\n" + "="*60)
                
                # Call analysis callback if provided
                if self.analysis_callback:
                    self.analysis_callback(analysis, final_inconsistencies_note)
                # Optionally add the final analysis document to ChromaDB if user enabled the setting
                try:
                    settings = load_user_settings()
                    ai_enabled = bool(settings.get('ai_record_meeting', True))
                except Exception:
                    ai_enabled = True

                if ai_enabled:
                    try:
                        try:
                            import chromadb
                            from chromadb.config import Settings
                        except Exception as e:
                            print(f"⚠️ ChromaDB not available; skipping DB insert: {e}")
                            chromadb = None

                        if chromadb is not None:
                            chroma_dir = os.path.join(os.getcwd(), "chromadb")
                            os.makedirs(chroma_dir, exist_ok=True)
                            # Use PersistentClient for actual file-based storage
                            try:
                                client = chromadb.PersistentClient(path=chroma_dir)
                            except Exception:
                                # Fallback for older chromadb versions
                                try:
                                    from chromadb.config import Settings
                                    settings = Settings(persist_directory=chroma_dir, chroma_db_impl="duckdb+parquet")
                                    client = chromadb.Client(settings)
                                except Exception as e:
                                    print(f"⚠️ Failed to create Chroma client: {e}")
                                    client = None
                            try:
                                collection = client.get_or_create_collection("recass_meetings")
                            except Exception:
                                try:
                                    collection = client.create_collection("recass_meetings")
                                except Exception:
                                    collection = None

                            if collection is not None:
                                doc_id = os.path.basename(analysis_filename)
                                metadata = {
                                    'meeting_folder': meeting_folder,
                                    'transcript_file': output_filename,
                                    'analysis_file': analysis_filename,
                                    'language': self.transcription_language,
                                    'timestamp': datetime.now().isoformat()
                                }
                                try:
                                    collection.add(ids=[doc_id], documents=[analysis], metadatas=[metadata])
                                    # Try to persist if the client supports it
                                    try:
                                        client.persist()
                                    except Exception:
                                        pass
                                    # Print contents of chromadb folder to verify DB file creation
                                    db_files = os.listdir(chroma_dir)
                                    print(f"✅ Added analysis to ChromaDB as id={doc_id}")
                                    print(f"ChromaDB folder contents: {db_files}")
                                except Exception as e:
                                    print(f"⚠️ Failed to add document to ChromaDB: {e}")
                    except Exception as e:
                        print(f"⚠️ Unexpected error while inserting into ChromaDB: {e}")
            else:
                print(f"❌ Analysis failed: {result.get('error', 'Unknown error')}")
                
        except FileNotFoundError:
            print(f"❌ Transcription file not found: {output_filename}")
        except Exception as e:
            import traceback
            print(f"❌ Error analyzing meeting minutes: {e}")
            print(f"   Traceback: {traceback.format_exc()}")

    def stop(self):
        """Signal the transcriber thread to stop."""
        self.stop_event.set()
