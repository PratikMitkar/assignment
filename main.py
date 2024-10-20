import os
import whisper
import requests
import json
from moviepy.editor import VideoFileClip, AudioFileClip
from pydub import AudioSegment, silence
import pyttsx3
import streamlit as st
import time
from tempfile import NamedTemporaryFile

# Hardcoded API key and endpoint
api_key = "22ec84421ec24230a3638d1b51e3a7dc"
endpoint = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

# Load Whisper model once to improve performance
whisper_model = whisper.load_model("base")

# Streamlit app title
st.title("Video to Adjusted Audio Sync with Silence Handling")

# Define a base output folder path
base_output_folder = "output"
os.makedirs(base_output_folder, exist_ok=True)

# Function to log errors
def log_error(message):
    st.error(message)  # Display error messages in Streamlit

# Step 1: Extract audio from the video
def extract_audio_from_video(video_path):
    try:
        with VideoFileClip(video_path) as video:
            audio_path = NamedTemporaryFile(delete=False, suffix=".mp3").name
            video.audio.write_audiofile(audio_path)
        return audio_path
    except Exception as e:
        log_error(f"Error extracting audio: {e}")
        return None

# Step 2: Transcribe audio with Whisper
def transcribe_audio(audio_file_path):
    try:
        result = whisper_model.transcribe(audio_file_path)
        transcription = result['text'].strip()

        transcription_file = NamedTemporaryFile(delete=False, suffix=".txt").name
        with open(transcription_file, 'w', encoding='utf-8') as f:
            f.write(transcription)
        return transcription_file
    except Exception as e:
        log_error(f"Error transcribing audio: {e}")
        return None

# Step 4: Correct transcription with GPT-4
def correct_transcription_with_gpt4(transcription_file, max_retries=3):
    try:
        with open(transcription_file, 'r', encoding='utf-8') as file:
            file_content = file.read()

        prompt = ("Correct the following text for punctuation, spelling, and grammar without changing its meaning:"
                  "\n\n" + file_content)

        headers = {
            "Content-Type": "application/json",
            "api-key": api_key,
        }

        data = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 2048,
            "temperature": 0.7,
        }

        for attempt in range(max_retries):
            try:
                response = requests.post(endpoint, headers=headers, json=data)
                if response.status_code == 200:
                    response_data = response.json()
                    gpt4_response = response_data['choices'][0]['message']['content'].strip()

                    corrected_file_path = NamedTemporaryFile(delete=False, suffix=".txt").name
                    with open(corrected_file_path, 'w', encoding='utf-8') as output_file:
                        output_file.write(gpt4_response)

                    return corrected_file_path
                else:
                    log_error(f"API Error: {response.status_code} - {response.text}")
                    return None
            except requests.exceptions.RequestException as e:
                log_error(f"Request failed: {e}. Retrying {attempt + 1}/{max_retries}...")
                time.sleep(2)

    except Exception as e:
        log_error(f"Error in GPT-4 correction: {e}")
        return None

# Detect silences in the original audio
def detect_silences(audio_path, silence_thresh=-50, min_silence_len=500):
    try:
        audio = AudioSegment.from_mp3(audio_path)
        silence_segments = silence.detect_silence(audio, min_silence_len=min_silence_len, silence_thresh=silence_thresh)

        # Convert the silence start and end times into milliseconds
        silence_segments = [(start, stop) for start, stop in silence_segments]
        return silence_segments
    except Exception as e:
        log_error(f"Error detecting silences: {e}")
        return None

# Step 5: Generate adjusted audio and incorporate silences
def generate_adjusted_audio_with_silences(corrected_transcription_file, original_audio_path, speech_rate=1.0):
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", int(170 * speech_rate))

        with open(corrected_transcription_file, 'r', encoding='utf-8') as f:
            text = f.read()

        # Generate TTS audio
        output_audio_path = NamedTemporaryFile(delete=False, suffix=".wav").name
        engine.save_to_file(text, output_audio_path)
        engine.runAndWait()

        # Detect silences from the original audio
        silence_segments = detect_silences(original_audio_path)

        if silence_segments:
            tts_audio = AudioSegment.from_wav(output_audio_path)

            # Insert silences into the generated audio
            for start, stop in silence_segments:
                silence_duration = stop - start
                silent_segment = AudioSegment.silent(duration=silence_duration)
                tts_audio = tts_audio[:start] + silent_segment + tts_audio[start:]

            return output_audio_path
        else:
            return output_audio_path

    except Exception as e:
        log_error(f"Error generating adjusted audio with silences: {e}")
        return None

# Step 6: Attach adjusted audio to the video
def attach_audio_to_video(video_path, adjusted_audio_path):
    try:
        with VideoFileClip(video_path) as video_clip:
            audio_clip = AudioFileClip(adjusted_audio_path)

            # Export adjusted audio
            final_adjusted_audio_path = NamedTemporaryFile(delete=False, suffix=".wav").name
            audio_clip.write_audiofile(final_adjusted_audio_path)

            # Attach the adjusted audio to the video
            final_video_path = NamedTemporaryFile(delete=False, suffix=".mp4").name
            final_video = video_clip.set_audio(AudioFileClip(final_adjusted_audio_path))
            final_video.write_videofile(final_video_path, codec="libx264", audio_codec="aac")

            return final_video_path
    except Exception as e:
        log_error(f"Error attaching audio to video: {e}")
        return None

# Main Streamlit logic
def main():
    video_file = st.file_uploader("Upload a video", type=["mp4", "mkv", "avi"])

    if st.button("Process Video") and video_file is not None:
        progress = st.progress(0)
        status_label = st.empty()  # Create an empty placeholder for status label

        video_path = os.path.join(base_output_folder, video_file.name)
        with open(video_path, "wb") as f:
            f.write(video_file.read())

        # Step 1: Extract audio
        status_label.text("Extracting audio from video...")
        output_audio_path = extract_audio_from_video(video_path)
        progress.progress(20)

        if output_audio_path:
            # Step 2: Transcribe audio
            status_label.text("Transcribing audio...")
            transcription_file = transcribe_audio(output_audio_path)
            progress.progress(40)

            if transcription_file:
                # Step 4: Correct transcription with GPT-4
                status_label.text("Correcting transcription with GPT-4...")
                corrected_transcription_file = correct_transcription_with_gpt4(transcription_file)
                progress.progress(80)

                if corrected_transcription_file:
                    # Step 5: Generate adjusted audio and incorporate silences
                    status_label.text("Generating adjusted audio...")
                    adjusted_audio_path = generate_adjusted_audio_with_silences(corrected_transcription_file, output_audio_path)
                    progress.progress(100)

                    if adjusted_audio_path:
                        # Step 6: Attach adjusted audio to video
                        status_label.text("Attaching adjusted audio to video...")
                        final_video_path = attach_audio_to_video(video_path, adjusted_audio_path)

                        if final_video_path:
                            st.success("Process completed successfully!")
                            st.video(final_video_path)
                        else:
                            log_error("Final video could not be created.")
                    else:
                        log_error("Adjusted audio could not be generated.")
                else:
                    log_error("Corrected transcription could not be obtained.")
            else:
                log_error("Audio transcription failed.")
        else:
            log_error("Audio extraction failed.")

# Run the main function
if __name__ == "__main__":
    main()
