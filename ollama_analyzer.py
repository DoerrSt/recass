"Integration with Ollama for meeting minutes analysis."

import requests
import json
import os
import base64
import glob
from datetime import datetime


class OllamaAnalyzer:
    """Connects to Ollama and analyzes meeting minutes."""

    def __init__(self, base_url="http://localhost:11434", model_name="llama3", language="en"):
        """
        Initialize the Ollama analyzer.
        
        Args:
            base_url: URL where Ollama is running
            model_name: Model name to use for analysis
            language: Language code for analysis output (e.g., 'en', 'de', 'es', 'auto')
        """
        self.base_url = base_url
        self.model = model_name
        self.endpoint = f"{base_url}/api/generate"
        self.screenshots = []  # Store screenshot paths
        self.language = language  # Language for analysis output

    def _check_connection(self):
        """Check if Ollama is running and accessible."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Ollama connection failed: {e}")
            return False

    def _check_model_available(self):
        """Check if the specified model is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                if any(self.model in name for name in model_names):
                    return True
                print(f"❌ Model '{self.model}' not found in Ollama. Available models: {model_names}")
                return False
        except Exception as e:
            print(f"❌ Error checking available models: {e}")
        return False

    def load_screenshots_from_folder(self, folder_path):
        """
        Load all screenshots from the meeting folder.
        
        Args:
            folder_path: Path to the meeting folder containing screenshots
        """
        self.screenshots = []
        if not folder_path or not os.path.isdir(folder_path):
            return
        
        # Find all screenshot files
        screenshot_patterns = ['screenshot-*.png', 'screenshot-*.jpg', 'screenshot-*.jpeg']
        for pattern in screenshot_patterns:
            screenshot_files = glob.glob(os.path.join(folder_path, pattern))
            self.screenshots.extend(sorted(screenshot_files))
        
        if self.screenshots:
            print(f"📸 Found {len(self.screenshots)} screenshots for context")
        return self.screenshots

    def _encode_screenshot_to_base64(self, image_path):
        """Convert image file to base64 string."""
        try:
            with open(image_path, 'rb') as img_file:
                return base64.b64encode(img_file.read()).decode('utf-8')
        except Exception as e:
            print(f"⚠️  Could not encode screenshot {image_path}: {e}")
            return None

    def analyze_minutes(self, meeting_minutes):
        """
        Analyze meeting minutes using Ollama, with optional screenshot analysis.
        
        Args:
            meeting_minutes: String containing the full meeting transcription
            
        Returns:
            dict with keys: 'success', 'analysis' (the LLM response), and optional 'error'
        """
        if not meeting_minutes or not meeting_minutes.strip():
            return {
                'success': False,
                'error': 'Meeting minutes are empty'
            }

        # Check connection
        if not self._check_connection():
            return {
                'success': False,
                'error': f'Cannot connect to Ollama at {self.base_url}'
            }

        # Check model availability
        if not self._check_model_available():
            return {
                'success': False,
                'error': f'Model {self.model} is not available'
            }

        # Prepare images if available
        encoded_images = []
        if self.screenshots:
            print(f"🖼️ Encoding {len(self.screenshots)} screenshots for analysis...")
            for img_path in self.screenshots:
                encoded = self._encode_screenshot_to_base64(img_path)
                if encoded:
                    encoded_images.append(encoded)
        
        # Prepare the prompt, indicating if screenshots are included
        prompt = self._prepare_prompt(meeting_minutes, self.language, with_screenshots=bool(encoded_images))

        # Prepare the payload for Ollama
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "temperature": 0.7,
        }
        if encoded_images:
            payload["images"] = encoded_images

        try:
            lang_display = self.language if self.language != 'auto' else 'auto-detect'
            screenshot_msg = f"with {len(encoded_images)} screenshots" if encoded_images else ""
            print(f"\n🤖 Sending meeting minutes to Ollama ({self.model}) for analysis in {lang_display} {screenshot_msg}...")
            
            # Call Ollama API
            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=3600  # 1 hour timeout for analysis
            )

            if response.status_code == 200:
                result = response.json()
                analysis = result.get("response", "").strip()
                
                if analysis:
                    print("✅ Analysis completed successfully")
                    return {
                        'success': True,
                        'analysis': analysis
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Empty response from Ollama'
                    }
            else:
                return {
                    'success': False,
                    'error': f'Ollama API returned status {response.status_code}: {response.text}'
                }

        except requests.Timeout:
            return {
                'success': False,
                'error': 'Request to Ollama timed out (analysis took too long)'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error communicating with Ollama: {str(e)}'
            }

    def _prepare_prompt(self, meeting_minutes, language="en", with_screenshots=False):
        """
        Prepare the analysis prompt for the LLM.
        
        Args:
            meeting_minutes: String containing the full meeting transcription.
            language: Language code for analysis output.
            with_screenshots: Boolean indicating if screenshots are attached.
        """
        
        # Screenshot context in the header
        screenshot_context = ""
        if self.screenshots:
            screenshot_context = f"\n\nNOTE: {len(self.screenshots)} screenshots were captured during this meeting and are attached. These must be analyzed as part of the instructions."

        # Language instruction
        language_instruction = ""
        if language and language != 'auto':
            lang_names = {
                'en': 'English', 'de': 'Deutsch (German)', 'es': 'Español (Spanish)', 'fr': 'Français (French)',
                'it': 'Italiano (Italian)', 'pt': 'Português (Portuguese)', 'nl': 'Nederlands (Dutch)', 'zh': 'Chinese (中文)',
                'ja': 'Japanese (日本語)', 'ko': 'Korean (한국어)', 'ru': 'Русский (Russian)', 'ar': 'العربية (Arabic)',
                'hi': 'हिन्दी (Hindi)', 'tr': 'Türkçe (Turkish)', 'pl': 'Polski (Polish)', 'sv': 'Svenska (Swedish)',
                'no': 'Norsk (Norwegian)', 'da': 'Dansk (Danish)', 'fi': 'Suomi (Finnish)', 'cs': 'Čeština (Czech)',
                'el': 'Ελληνικά (Greek)', 'hu': 'Magyar (Hungarian)', 'ro': 'Română (Romanian)', 'uk': 'Українська (Ukrainian)',
                'id': 'Bahasa Indonesia', 'ms': 'Bahasa Melayu', 'vi': 'Tiếng Việt (Vietnamese)',
            }
            lang_name = lang_names.get(language, language)
            language_instruction = f"\n\n🌐 IMPORTANT: Provide your entire analysis in {lang_name}. All output must be in {lang_name}."

        # Check if consistency notes are present and add specific instructions
        consistency_instruction = ""
        if "[CONSISTENCY CHECK NOTE]" in meeting_minutes or "[FINAL CONSISTENCY CHECK NOTE]" in meeting_minutes:
            consistency_instruction = """
IMPORTANT: The provided meeting minutes may contain a '[FINAL CONSISTENCY CHECK NOTE]' or '[CONSISTENCY CHECK NOTE]' section. These sections highlight potential inconsistencies or contradictions with past discussions or decisions. You MUST carefully review these notes and integrate their implications into your summary, key decisions, and overall analysis. If a contradiction is noted, ensure your summary reflects this discrepancy and its significance. Do NOT simply list the note; explain its impact on the meeting's content and outcomes."""

        screenshot_analysis_instructions = ""
        if with_screenshots:
            screenshot_analysis_instructions = """
---
ADDITIONAL TASK: SCREENSHOT ANALYSIS

{language_instruction}

You are an expert in screen analysis and digital observation. Your task is to thoroughly examine the attached screenshot(s) and provide a comprehensive report. Your report should cover the following areas for EACH screenshot:

1.  **Application Identification:** Identify the primary application displayed in the screenshot. Specify the version if possible.
2.  **User Activity:** Describe precisely what the user is doing within the application. Is the user presenting, participating in a discussion, sending a message, editing a document, or performing another action? Provide as much detail as you can infer.
3.  **Personnel Identification:** List all visible names and titles of individuals present in the screenshot. Note their roles if indicated.
4.  **Communication Details:** Analyze any chat windows, message threads, or video feeds. Transcribe any visible messages or snippets of conversation.
5.  **System Status:** Identify any visible error messages, notifications, or status indicators. Transcribe these exactly.
6.  **UI Elements:** Briefly describe the prominent UI elements and controls visible within the application.
7.  **Contextual Clues:** Based on the visual information, suggest any potential context related to the meeting or activity. (e.g., project name, agenda topic)

Integrate findings from this analysis into the main summary and to-do list where relevant.
"""
        
        output_format_extension = ""
        if with_screenshots:
            output_format_extension = """
🖼️ Screenshot Analysis:
[Your detailed analysis of each screenshot here, following the 7 points for each. Start with 'Screenshot 1:', then 'Screenshot 2:', etc.]
"""
        
        prompt = f"""Role: You are a highly precise business analysis and minute-taking assistant. Your task is to capture the essence of the meeting and provide clear, actionable next steps.

Important Note on Source Material:
Please Note: Speaker identification in the minutes may be inaccurate or faulty. Do not blindly assume the assigned person is correct. Evaluate the context of the statement to determine the most likely person for an action item. The entire transcription must be considered as a unified context to improve the analysis and identify the correct decisions/To-Dos.{screenshot_context}{language_instruction}{consistency_instruction}

Instruction: Completely analyze the following meeting minutes and any attached screenshots. Execute all tasks below and present the results in the format specified afterwards.

1. Summary
Purpose: Create a concise, high-level summary covering the main topics, decisions, and overall progress of the meeting.
Focus: Concentrate on "What has been discussed?", "What was decided?" and "What are the next milestones?"

2. Smart Chapters
Create an automatically generated outline of the meeting with timestamps and titles for the main topics discussed (e.g., “Project Update,” “Budget Planning,” “Next Steps”). This allows for quick navigation.


3. Extracted To-Do List (Action Items)
Purpose: Extract all explicit and implicit action items (To-Dos) that were assigned during the meeting.
Format: Create a table with three columns: To-Do Description, Assigned Person, and Deadline (if mentioned or implied).
Important: Use the overall context to validate or correct the assigned person. If no deadline was mentioned, write "TBD" (To Be Determined). If no person was mentioned, write "Team/Open".

4. Key Quotes (Optional, but Helpful)
Purpose: <Extract key quotes or major decisions directly from the text that reflect the tone or a critical decision.
{screenshot_analysis_instructions}
[MEETING MINUTES]
{meeting_minutes}
[END MEETING MINUTES]

Desired Output Format:
📊 High-Level Summary: [Your summary here]

✅ Next Steps (To-Do List):
| To-Do Description | Assigned Person | Deadline |
|---|---|---|
| [Action Point 1] | [Person's Name (Based on Context Check)] | [Date/TBD] |
| [Action Point 2] | [Person's Name (Based on Context Check)] | [Date/TBD] |
| [Action Point 3] | [Person's Name (Based on Context Check)] | [Date/TBD] |

💡 Key Decisions/Quotes:
"[Quote 1]"
"[Quote 2]"
"[Quote 3]"{output_format_extension}"""
        return prompt

    def save_analysis_with_screenshots(self, analysis_filename, analysis_text):
        """
        Save analysis with embedded screenshots as base64 in the file.
        
        Args:
            analysis_filename: Path to save the analysis file
            analysis_text: The analysis text from Ollama
        """
        try:
            with open(analysis_filename, 'w', encoding='utf-8') as f:
                f.write("MEETING ANALYSIS\n")
                f.write("="*60 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("="*60 + "\n\n")
                f.write(analysis_text)
                f.write("\n\n" + "="*60 + "\n")
                
                # Add screenshot references and data
                if self.screenshots:
                    f.write("\n📸 SCREENSHOTS CAPTURED DURING MEETING\n")
                    f.write("="*60 + "\n\n")
                    
                    for idx, screenshot_path in enumerate(self.screenshots, 1):
                        f.write(f"Screenshot {idx}: {os.path.basename(screenshot_path)}\n")                       
                        f.write(f"Reference: {screenshot_path}\n\n")                 
            
            print(f"✅ Analysis with {len(self.screenshots)} screenshot(s) saved to: {analysis_filename}")
            
        except IOError as e:
            print(f"⚠️  Could not save analysis to file: {e}")
            return False
        
        return True

    def chat(self, user_message, context_docs=None, temperature=0.7):
        """
        Simple chat helper sending a user message to Ollama with optional context documents.

        Args:
            user_message: The user's chat message (string).
            context_docs: Optional list of strings providing context (documents/snippets).
            temperature: Sampling temperature.

        Returns:
            dict with keys: 'success', 'response' or 'error'
        """
        if not user_message or not user_message.strip():
            return {'success': False, 'error': 'Empty message'}

        if not self._check_connection():
            return {'success': False, 'error': f'Cannot connect to Ollama at {self.base_url}'}

        if not self._check_model_available():
            return {'success': False, 'error': f'Model {self.model} is not available'}

        # Build a prompt that encourages using both context and general knowledge
        prompt_parts = [
            "You are a helpful assistant. Answer the user's question based on your general knowledge "
            "and the provided context documents. If the context is relevant, use it to inform your answer, "
            "but do not limit your response to only the information in the context."
        ]
        if context_docs:
            context_str = "\n---\n".join(context_docs)
            prompt_parts.append(f"Here is some context that might be relevant:\n{context_str}")

        prompt_parts.append(f"User's question: {user_message}")
        prompt = "\n\n".join(prompt_parts)

        try:
            response = requests.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": temperature,
                },
                timeout=120,
            )

            if response.status_code == 200:
                result = response.json()
                text = result.get("response", "").strip()
                if text:
                    return {'success': True, 'response': text}
                return {'success': False, 'error': 'Empty response from Ollama'}
            else:
                return {'success': False, 'error': f'Ollama API returned status {response.status_code}: {response.text}'}
        except Exception as e:
            return {'success': False, 'error': f'Error communicating with Ollama: {str(e)}'}

    def get_suggestion(self, history, mode="respond"):
        """
        Get a suggestion from Ollama based on the conversation history.

        Args:
            history: The conversation history (string).
            mode: "respond" or "details".

        Returns:
            dict with keys: 'success', 'response' or 'error'
        """
        if not history or not history.strip():
            return {'success': False, 'error': 'Empty history'}

        if not self._check_connection():
            return {'success': False, 'error': f'Cannot connect to Ollama at {self.base_url}'}

        if not self._check_model_available():
            return {'success': False, 'error': f'Model {self.model} is not available'}

        prompt = ""
        if mode == "respond":
            prompt = f"Based on the following conversation, suggest a concise and professional response. The response should be in the same language as the conversation.\n\nConversation:\n{history}\n\nSuggested response:"
        elif mode == "details":
            prompt = f"Based on the following conversation, provide a more detailed explanation of the last topic discussed. The response should be in the same language as the conversation.\n\nConversation:\n{history}\n\nDetailed explanation:"
        else:
            return {'success': False, 'error': 'Invalid mode specified'}

        try:
            response = requests.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.7,
                },
                timeout=120,
            )

            if response.status_code == 200:
                result = response.json()
                text = result.get("response", "").strip()
                if text:
                    return {'success': True, 'response': text}
                return {'success': False, 'error': 'Empty response from Ollama'}
            else:
                return {'success': False, 'error': f'Ollama API returned status {response.status_code}: {response.text}'}
        except Exception as e:
            return {'success': False, 'error': f'Error communicating with Ollama: {str(e)}'}

    def get_summary(self, history):
        """
        Get a summary from Ollama based on the conversation history.

        Args:
            history: The conversation history (string).

        Returns:
            dict with keys: 'success', 'response' or 'error'
        """
        if not history or not history.strip():
            return {'success': False, 'error': 'Empty history'}

        if not self._check_connection():
            return {'success': False, 'error': f'Cannot connect to Ollama at {self.base_url}'}

        if not self._check_model_available():
            return {'success': False, 'error': f'Model {self.model} is not available'}

        prompt = f"Based on the following conversation, provide a concise summary of the discussion. The summary should be in the same language as the conversation.\n\nConversation:\n{history}\n\nSummary:"

        try:
            response = requests.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.7,
                },
                timeout=120,
            )

            if response.status_code == 200:
                result = response.json()
                text = result.get("response", "").strip()
                if text:
                    return {'success': True, 'response': text}
                return {'success': False, 'error': 'Empty response from Ollama'}
            else:
                return {'success': False, 'error': f'Ollama API returned status {response.status_code}: {response.text}'}
        except Exception as e:
            return {'success': False, 'error': f'Error communicating with Ollama: {str(e)}'}

    def find_inconsistencies(self, current_meeting_history: str, previous_meeting_context: str):
        """
        Asks Ollama to find inconsistencies or contradictions.

        Args:
            current_meeting_history: The current meeting's transcription history (last 5 minutes).
            previous_meeting_context: Relevant information from past meetings (e.g., summaries, decisions).

        Returns:
            A string containing identified inconsistencies, or an empty string if none found or an error occurred.
        """
        if not current_meeting_history.strip() or not previous_meeting_context.strip():
            return ""

        if not self._check_connection() or not self._check_model_available():
            return "Error: Ollama connection or model not available for inconsistency check."

        prompt = f"""You are an AI assistant tasked with identifying inconsistencies and contradictions.

Here is the current ongoing meeting's recent transcription:
--- CURRENT MEETING HISTORY ---
{current_meeting_history}
--- END CURRENT MEETING HISTORY ---

Here is relevant context from previous meetings, including past decisions and discussions:
--- PREVIOUS MEETING CONTEXT ---
{previous_meeting_context}
--- END PREVIOUS MEETING CONTEXT ---

Please carefully compare the CURRENT MEETING HISTORY with the PREVIOUS MEETING CONTEXT.
Your task is to identify any:
1.  **Direct contradictions:** Where a statement or decision in the current meeting directly opposes a previous decision or established fact from past meetings.
2.  **Significant inconsistencies:** Where new information or discussions in the current meeting don't align with, or diverge from, previously understood plans, facts, or agreements without clear explanation.
3.  **Key changes without explicit acknowledgment:** If there's a shift in direction, scope, or understanding in the current meeting that seems to disregard prior discussions.

If you find any inconsistencies, contradictions, or unacknowledged changes, describe them clearly and concisely.
If no such issues are found, respond with "No inconsistencies found."

IMPORTANT: Your response should be in the same language as CURRENT MEETING HISTORY content.
"""
        try:
            response = requests.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3, # Lower temperature for more factual responses
                },
                timeout=180, # Increased timeout for potentially longer analysis
            )

            if response.status_code == 200:
                result = response.json()
                inconsistencies = result.get("response", "").strip()
                if inconsistencies.lower() == "no inconsistencies found.":
                    return "" # Return empty string if LLM explicitly says none
                return inconsistencies
            else:
                print(f"Error finding inconsistencies: Ollama returned status {response.status_code}: {response.text}")
                return ""
        except Exception as e:
            print(f"Error communicating with Ollama for inconsistency check: {e}")
            return ""

    def suggest_title(self, meeting_minutes):
        """
        Suggest a meeting title using Ollama based on the transcript.
        
        Args:
            meeting_minutes: String containing the full meeting transcription.
            
        Returns:
            A string containing the suggested title, or an empty string on failure.
        """
        if not meeting_minutes or not meeting_minutes.strip():
            return ""

        if not self._check_connection() or not self._check_model_available():
            return ""

        prompt = f"Based on the following meeting transcript, suggest one concise and descriptive title of no more than 10 words,just the title, do not comment or add other text. The title should be in the same language as the transcript.\n\nTranscript:\n{meeting_minutes}\n\nSuggested title:"

        try:
            response = requests.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.7,
                },
                timeout=60,
            )

            if response.status_code == 200:
                result = response.json()
                title = result.get("response", "").strip().replace('"', '')
                return title
            else:
                print(f"Error suggesting title: Ollama returned status {response.status_code}")
                return ""
        except Exception as e:
            print(f"Error communicating with Ollama for title suggestion: {e}")
            return ""

    def repurpose_content(self, text, template):
        """
        Repurposes meeting content into a different format using a template.

        Args:
            text (str): The full text of the meeting (transcript + analysis).
            template (str): The name of the template to use (e.g., "Executive Summary").

        Returns:
            dict: with keys 'success' and 'response' or 'error'.
        """
        if not text or not text.strip():
            return {'success': False, 'error': 'Content to repurpose is empty'}

        if not self._check_connection() or not self._check_model_available():
            return {'success': False, 'error': 'Ollama connection or model not available'}

        PROMPTS = {
            "Executive Summary": "You are a senior business analyst. From the provided meeting minutes, generate a concise, high-level executive summary suitable for a C-level audience. Focus on key decisions, strategic outcomes, and major action items. Omit granular details.",
            "Technical Log": "You are a lead software engineer. From the provided meeting minutes, generate a detailed technical log. Extract all technical decisions, code-related discussions, API changes, architecture proposals, and specific developer action items. Format the output clearly with sections.",
            "Blog Post Draft": "You are a content marketer. From the provided brainstorming meeting, create a structured blog post draft. Use markdown for formatting. Include a catchy title, a brief introduction, several paragraphs expanding on the main ideas, and a concluding paragraph. The tone should be engaging and informative for a public audience."
        }

        base_prompt = PROMPTS.get(template)
        if not base_prompt:
            return {'success': False, 'error': f"Unknown template: {template}"}

        full_prompt = f"{base_prompt}\n\nHere are the meeting minutes to work from:\n\n---\n\n{text}"

        try:
            print(f"Repurposing content for template: '{template}'...")
            response = requests.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": False,
                    "temperature": 0.5,
                },
                timeout=300, # 5 minute timeout
            )

            if response.status_code == 200:
                result = response.json()
                content = result.get("response", "").strip()
                if content:
                    return {'success': True, 'response': content}
                else:
                    return {'success': False, 'error': 'Empty response from Ollama'}
            else:
                return {'success': False, 'error': f'Ollama API returned status {response.status_code}: {response.text}'}
        except Exception as e:
            return {'success': False, 'error': f'Error communicating with Ollama: {str(e)}'}