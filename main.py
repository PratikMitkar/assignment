import os
import requests
import threading
import whisper
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
from pydub.silence import detect_silence
import streamlit as st

# Constants for API

API_KEY = "22ec84421ec24230a3638d1b51e3a7dc"
ENDPOINT = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"


def extract_audio_from_video(video_path, output_audio_folder="output", output_audio_filename="audio.mp3"):
    try:
        if not os.path.exists(output_audio_folder):
            os.makedirs(output_audio_folder)
        output_audio_path = os.path.join(output_audio_folder, output_audio_filename)
        video = VideoFileClip(video_path)
        audio = video.audio
        audio.write_audiofile(output_audio_path)
        video.close()
        return output_audio_path
    except Exception as e:
        st.error(f"An error occurred while extracting audio: {str(e)}")
        return None

def process_audio_with_whisper(audio_file_path):
    try:
        audio = AudioSegment.from_mp3(audio_file_path)
        silence_threshold = -50  # Threshold in dBFS
        min_silence_duration = 500  # Minimum silence duration in milliseconds
        silence_intervals = detect_silence(audio, min_silence_len=min_silence_duration, silence_thresh=silence_threshold)

        total_duration_seconds = len(audio) / 1000
        spoken_duration_seconds = total_duration_seconds - sum((end - start) for start, end in silence_intervals) / 1000
        
        model = whisper.load_model("base")
        result = model.transcribe(audio_file_path)
        transcription = result['text'].strip()
        word_count = len(transcription.split())
        spoken_minutes = spoken_duration_seconds / 60
        wpm = word_count / spoken_minutes if spoken_minutes > 0 else 0
        
        analysis_output = {
            'transcription': transcription,
            'word_count': word_count,
            'spoken_duration': spoken_duration_seconds,
            'wpm': wpm
        }
        
        return analysis_output
    except Exception as e:
        st.error(f"An error occurred during audio processing: {str(e)}")
        return None

def correct_transcription_with_gpt4(transcription):
    try:
        prompt = ("Correct the following text for punctuation, spelling, and grammar without changing its meaning: ")
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
            corrected_transcription = response_data['choices'][0]['message']['content'].strip()
            return corrected_transcription
        else:
            st.error(f"API Error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        st.error(f"An error occurred during GPT-4 processing: {str(e)}")
        return None

def generate_adjusted_audio(corrected_transcription, spoken_duration, output_audio_folder="output"):
    try:
        speech_rate = spoken_duration / len(corrected_transcription.split()) * 170  # Calculate speech rate

        engine = pyttsx3.init()
        engine.setProperty('rate', int(speech_rate))  # Set speech rate
        engine.setProperty('voice', 'english+male')  # Set voice

        # Save the adjusted audio
        adjusted_audio_path = os.path.join(output_audio_folder, "output_adjusted.wav")
        engine.save_to_file(corrected_transcription, adjusted_audio_path)
        engine.runAndWait()

        return adjusted_audio_path

    except Exception as e:
        st.error(f"An error occurred during audio generation: {str(e)}")
        return None

# Streamlit UI
st.title("Video to Adjusted Audio Converter")
uploaded_file = st.file_uploader("Upload a Video File", type=["mp4"])

if uploaded_file is not None:
    # Save uploaded video file
    video_path = os.path.join("temp", uploaded_file.name)
    with open(video_path, "wb") as f:
        f.write(uploaded_file.read())

    st.write("Extracting audio from video...")
    audio_file = extract_audio_from_video(video_path)

    if audio_file:
        st.write("Processing audio with Whisper...")
        analysis = process_audio_with_whisper(audio_file)

        if analysis:
            st.write("Correcting transcription with GPT-4...")
            corrected_transcription = correct_transcription_with_gpt4(analysis['transcription'])

            if corrected_transcription:
                st.write("Generating adjusted audio...")
                adjusted_audio_path = generate_adjusted_audio(corrected_transcription, analysis['spoken_duration'])

                if adjusted_audio_path:
                    st.success("Adjusted audio generated successfully!")
                    st.audio(adjusted_audio_path)

# Clean up temporary files if needed
