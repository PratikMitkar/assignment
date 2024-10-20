import os
import requests
import streamlit as st
from moviepy.editor import VideoFileClip
from pydub import AudioSegment, silence
import whisper
import pyttsx3

# Constants for Azure GPT-4 API
API_KEY = "22ec84421ec24230a3638d1b51e3a7dc"
ENDPOINT = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

# Function to extract audio from video
def extract_audio_from_video(video_path, output_audio_folder="output"):
    if not os.path.exists(output_audio_folder):
        os.makedirs(output_audio_folder)
    output_audio_path = os.path.join(output_audio_folder, "audio.mp3")
    video = VideoFileClip(video_path)
    audio = video.audio
    audio.write_audiofile(output_audio_path)
    video.close()
    return output_audio_path

# Function to process audio and transcribe using Whisper
def process_audio_with_whisper(audio_file_path):
    audio = AudioSegment.from_mp3(audio_file_path)
    silence_threshold = -50  # dBFS
    min_silence_duration = 500  # ms
    silence_intervals = silence.detect_silence(audio, min_silence_len=min_silence_duration, silence_thresh=silence_threshold)

    total_duration_seconds = len(audio) / 1000
    spoken_duration_seconds = total_duration_seconds - sum((end - start) for start, end in silence_intervals) / 1000

    model = whisper.load_model("base")
    result = model.transcribe(audio_file_path)
    transcription = result["text"].strip()
    return transcription, spoken_duration_seconds

# Function to correct transcription using GPT-4
def correct_transcription_with_gpt4(transcription):
    prompt = ("Correct the following text for punctuation, spelling, and grammar without changing its meaning. "
              "Ensure the output contains only the corrected text, with no additional words or commentary. "
              "Do not alter the overall structure or style unnecessarily:")

    headers = {
        "Content-Type": "application/json",
        "api-key": API_KEY,
    }

    data = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"{prompt}\n\n{transcription}"}
        ],
        "max_tokens": 2048,
        "temperature": 0.7,
    }

    response = requests.post(ENDPOINT, headers=headers, json=data)

    if response.status_code == 200:
        response_data = response.json()
        return response_data["choices"][0]["message"]["content"].strip()
    else:
        st.error(f"API Error: {response.status_code} - {response.text}")
        return None

# Function to generate adjusted audio
def generate_adjusted_audio(corrected_transcription):
    engine = pyttsx3.init()
    engine.setProperty("rate", 170)  # Adjust speech rate

    # Split text into manageable chunks
    chunks = [corrected_transcription[i:i + 1000] for i in range(0, len(corrected_transcription), 1000)]

    combined_audio = AudioSegment.empty()
    for chunk in chunks:
        temp_audio_path = "temp_audio.wav"
        engine.save_to_file(chunk, temp_audio_path)
        engine.runAndWait()
        chunk_audio = AudioSegment.from_wav(temp_audio_path)
        combined_audio += chunk_audio
        os.remove(temp_audio_path)  # Cleanup temporary audio files

    output_path = os.path.join("output", "output_adjusted.wav")
    combined_audio.export(output_path, format="wav")

    return output_path

# Streamlit application
st.title("Video to Adjusted Audio Converter")

# Initialize paths
video_path = None
audio_path = None

# File uploader for video
uploaded_file = st.file_uploader("Upload a Video File", type=["mp4"])
if uploaded_file:
    video_path = os.path.join("temp", uploaded_file.name)
    with open(video_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.video(video_path)  # Display the original video

    # Button to start processing
    if st.button("Process Video"):
        # Extract audio
        audio_path = extract_audio_from_video(video_path)
        st.success("Audio extracted successfully!")

        # Process audio
        transcription, spoken_duration = process_audio_with_whisper(audio_path)
        st.success("Audio processed and transcribed successfully!")

        # Correct transcription
        corrected_transcription = correct_transcription_with_gpt4(transcription)
        if corrected_transcription:
            st.success("Transcription corrected successfully!")

            # Generate adjusted audio
            generated_audio_path = generate_adjusted_audio(corrected_transcription)
            st.success("Adjusted audio generated successfully!")

            # Display the generated audio
            st.audio(generated_audio_path)

# Clean up temporary files only if they were defined
if video_path and os.path.exists(video_path):
    os.remove(video_path)
if audio_path and os.path.exists(audio_path):
    os.remove(audio_path)
