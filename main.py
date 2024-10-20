import os
import whisper
import requests
import json
from moviepy.editor import VideoFileClip, AudioFileClip
from pydub import AudioSegment, silence
from gtts import gTTS
import pyttsx3
import streamlit as st
import re
import time
from tempfile import NamedTemporaryFile

# API configurations (replace with your own API key)
api_key = "22ec84421ec24230a3638d1b51e3a7dc"
endpoint = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

# Streamlit app title
st.title("Video to Adjusted Audio Sync")

# Cache Whisper model loading to prevent reloading it each time
@st.cache_resource
def load_whisper_model():
    return whisper.load_model("base")

# Extract audio from the video and handle temporary files
def extract_audio_from_video(video_path):
    try:
        video = VideoFileClip(video_path)
        audio = video.audio
        
        # Use a temporary file for audio
        with NamedTemporaryFile(suffix=".mp3", delete=False) as temp_audio:
            audio.write_audiofile(temp_audio.name)
            video.close()
            return temp_audio.name
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return None

# Transcribe audio with Whisper
@st.cache_data
def transcribe_audio(audio_file_path):
    try:
        model = load_whisper_model()
        result = model.transcribe(audio_file_path)
        return result['text'].strip()
    except Exception as e:
        print(f"Error transcribing audio: {e}")
        return None

# Correct transcription with GPT-4
async def correct_transcription_with_gpt4(transcription):
    prompt = ("Correct the following text for punctuation, spelling, and grammar without changing its meaning:"
              "\n\n" + transcription)

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

    try:
        response = requests.post(endpoint, headers=headers, json=data)
        response_data = response.json()
        return response_data['choices'][0]['message']['content'].strip() if response.status_code == 200 else None
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None

# Generate adjusted audio
def generate_adjusted_audio(corrected_transcription):
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 170)

        # Use a temporary file for generated audio
        with NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
            engine.save_to_file(corrected_transcription, temp_audio.name)
            engine.runAndWait()
            return temp_audio.name
    except Exception as e:
        print(f"Error generating adjusted audio: {e}")
        return None

# Attach audio to video
def attach_audio_to_video(video_path, adjusted_audio_path):
    try:
        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(adjusted_audio_path)

        # Use a temporary file for final video
        with NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
            final_video = video_clip.set_audio(audio_clip)
            final_video.write_videofile(temp_video.name, codec="libx264", audio_codec="aac")
            return temp_video.name
    except Exception as e:
        print(f"Error attaching audio to video: {e}")
        return None

# Main Streamlit logic
def main():
    video_file = st.file_uploader("Upload a video", type=["mp4", "mkv", "avi"])

    if st.button("Process Video") and video_file is not None:
        progress = st.progress(0)
        status_label = st.empty()  # Create an empty placeholder for status label

        # Save uploaded video to a temporary file
        with NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
            temp_video.write(video_file.read())
            video_path = temp_video.name

        # Step 1: Extract audio
        status_label.text("Extracting audio from video...")
        output_audio_path = extract_audio_from_video(video_path)
        progress.progress(20)

        if output_audio_path:
            # Step 2: Transcribe audio
            status_label.text("Transcribing audio...")
            transcription = transcribe_audio(output_audio_path)
            progress.progress(40)

            if transcription:
                # Step 3: Correct transcription with GPT-4
                status_label.text("Correcting transcription with GPT-4...")
                corrected_transcription = correct_transcription_with_gpt4(transcription)
                progress.progress(60)

                if corrected_transcription:
                    # Step 4: Generate adjusted audio
                    status_label.text("Generating adjusted audio...")
                    generated_audio_path = generate_adjusted_audio(corrected_transcription)
                    progress.progress(80)

                    if generated_audio_path:
                        # Step 5: Attach adjusted audio to video
                        status_label.text("Attaching adjusted audio to video...")
                        final_video_path = attach_audio_to_video(video_path, generated_audio_path)
                        progress.progress(100)

                        if final_video_path:
                            st.success("Processing complete!")
                            st.video(final_video_path)
                        else:
                            st.error("Error generating final video with synced audio.")
                            status_label.text("Error during final video generation")
    else:
        st.error("Please upload a video file.")

if __name__ == "__main__":
    main()
