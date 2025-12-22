# recass - Real-time Meeting Assistant (Transcription, Analysis, and Consistency Check)

**recass** (Real-time Context-Aware Speech/Screen Assistant) is a powerful desktop application designed to enhance your meeting experience by providing real-time transcription, intelligent analysis, and proactive consistency checks. Leveraging local AI models (Whisper, Pyannote, Ollama), recass keeps a vigilant eye on your discussions, ensuring you stay on track and informed.

## ✨ Features

*   **Real-time Audio Transcription**: Accurately transcribes spoken words from both your microphone and computer audio (loopback), providing a comprehensive record of your meeting.
*   **Speaker Diarization**: Identifies different speakers in real-time for computer audio, making it easier to follow who said what.
*   **Live Screenshot Capture**: Periodically captures screenshots of your selected screen(s) during recordings, offering visual context for discussions.
*   **AI-Powered Meeting Analysis**: Integrates with local Ollama LLMs to generate summaries, action items, and detailed insights from your transcriptions and screenshots.
*   **Real-time Consistency Check**:
    *   When enabled, `recass` continuously monitors the ongoing discussion.
    *   It compares the current meeting's dialogue with past meeting data (from its ChromaDB knowledge base).
    *   Identifies potential inconsistencies, contradictions, or unacknowledged changes in decisions or plans.
    *   Adds automated notes to the meeting minutes and final analysis if discrepancies are found.
*   **Rolling Transcription History**: Efficiently maintains a buffer of the last 5 minutes of transcription for quick contextual queries and suggestions.
*   **Joplin Integration**: Seamlessly syncs meeting analysis, including consistency check notes, to your Joplin note-taking application.
*   **Local AI/LLM Support**: Utilizes local installations of Whisper, Pyannote, and Ollama, ensuring data privacy and offline functionality.
*   **Configurable Settings**: Customize audio devices, transcription language, screenshot intervals, AI models, and Joplin synchronization settings via a user-friendly GTK UI.
*   **Meeting & Chat Browser**: Easily browse through past meeting records and chat sessions.

## 🚀 Installation

### Prerequisites

*   **Python 3.8+**: [Download Python](https://www.python.org/downloads/)
*   **Git**: [Download Git](https://git-scm.com/downloads)
*   **Ollama**: Install Ollama for local LLM inference. [Get Ollama](https://ollama.ai/)
    *   After installation, pull a model, e.g., `ollama pull llama3`.
*   **Joplin Desktop Application** (Optional, for Joplin sync): [Get Joplin](https://joplinapp.org/)
*   **Hugging Face Account & Token** (Optional, for Pyannote Diarization):
    *   Create an account on [Hugging Face](https://huggingface.co/).
    *   Accept the user conditions for `pyannote/speaker-diarization-3.1` on its model page.
    *   Generate a User Access Token (read access is sufficient) from your Hugging Face settings.

### Setup Steps

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/your-username/recass.git
    cd recass
    ```

2.  **Create a Virtual Environment & Install Dependencies**:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Configure Hugging Face Token (Optional, but recommended for diarization)**:
    Set your Hugging Face token as an environment variable:
    ```bash
    export HUGGING_FACE_TOKEN="hf_YOUR_TOKEN_HERE"
    ```
    Alternatively, you can add it directly to `config.py` or enter it via the UI.

## 🏃‍♀️ Usage

1.  **Activate your virtual environment**:
    ```bash
    source .venv/bin/activate
    ```

2.  **Run the application**:
    ```bash
    python3 main.py
    ```

3.  **Configure in UI**:
    *   Upon first launch, a system tray icon will appear. Click it and select "Open Settings".
    *   **Select Audio Devices**: Choose your microphone and computer audio (loopback) devices. Ensure you have a loopback device configured on your system (e.g., PulseAudio "Monitor of").
    *   **AI Settings**:
        *   Enter your Ollama URL (default: `http://localhost:11434`) and model name (e.g., `llama3`).
        *   Enable "AI: Record meeting" to activate intelligent analysis.
        *   Enable "Send screenshots to LLM for analysis" if desired.
    *   **Consistency Check**: Toggle "Consistency check" to enable real-time detection of contradictions with past meetings.
    *   **Joplin Settings**: If using Joplin, enter your API key and desired destination folder.
    *   **Whisper Model**: Select your preferred Whisper model (e.g., `base`, `small`, `medium`).
    *   **Start Recording**: Click "Aufnahme starten" (Start Recording) to begin. The system will transcribe, capture screenshots, and perform real-time analysis in the background.

## ⚙️ Configuration

Settings are primarily managed through the GTK UI. Configuration values are stored in a `user_settings.json` file.

## 🤝 Contributing

Contributions are welcome! Please feel free to open issues or submit pull requests.

## 📄 License

This project is licensed under the MIT License.