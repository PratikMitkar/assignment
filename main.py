import os
import re
import requests
import whisper
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
import pydub.silence as silence
import streamlit as st
from tempfile import NamedTemporaryFile
from TTS.api import TTS  # Import the TTS API

# Constants for API access
API_KEY = "22ec84421ec24230a3638d1b51e3a7dc"  
ENDPOINT = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

# Function to extract audio from video
def extract_audio_from_video(video_path):
    output_audio_path = "output/extracted_audio.mp3"
    try:
        if not os.path.exists("output"):
            os.makedirs("output")
        video = VideoFileClip(video_path)
        audio = video.audio
        audio.write_audiofile(output_audio_path)
        video.close()
        return output_audio_path
    except Exception as e:
        st.error(f"Error extracting audio: {str(e)}")
        return None

# Function to process audio with Whisper and Pydub
def process_audio_with_whisper_and_pydub(audio_file_path):
    try:
        audio = AudioSegment.from_mp3(audio_file_path)
        silence_threshold = -50  # in dB
        min_silence_duration = 500  # in ms
        silence_intervals = silence.detect_silence(audio, min_silence_len=min_silence_duration, silence_thresh=silence_threshold)
        
        total_duration_seconds = len(audio) / 1000
        spoken_duration_seconds = total_duration_seconds - sum((end - start) for start, end in silence_intervals) / 1000
        
        model = whisper.load_model("base")
        result = model.transcribe(audio_file_path)
        transcription = result['text'].strip()
        word_count = len(transcription.split())
        spoken_minutes = spoken_duration_seconds / 60
        wpm = word_count / spoken_minutes if spoken_minutes > 0 else 0

        transcription_file = os.path.join("output", 'transcription.txt')
        with open(transcription_file, 'w', encoding='utf-8') as f:
            f.write(transcription)

        analysis_output = (f"Transcription saved to: {transcription_file}\n"
                           f"Word count: {word_count}\n"
                           f"Spoken duration (minutes): {spoken_minutes:.2f}\n"
                           f"Words per minute (WPM): {wpm:.2f}")

        analysis_file = os.path.join("output", 'audio_analysis_output.txt')
        with open(analysis_file, 'w', encoding='utf-8') as f:
            f.write(analysis_output)

        return transcription_file, analysis_file
    except Exception as e:
        st.error(f"Error processing audio: {str(e)}")
        return None, None

# Function to correct transcription with GPT-4
def correct_transcription_with_gpt4(transcription_file):
    try:
        with open(transcription_file, 'r', encoding='utf-8') as file:
            file_content = file.read()

        prompt = ("Correct the following text for punctuation, spelling, and grammar without changing its meaning. "
                  "Ensure the output contains only the corrected text, with no additional words or commentary.")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }

        data = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": f"{prompt}\n\n{file_content}"}
            ],
            "max_tokens": 2048,
            "temperature": 0.7,
        }

        response = requests.post(ENDPOINT, headers=headers, json=data)
        response_data = response.json()
        
        if response.status_code == 200:
            gpt4_response = response_data['choices'][0]['message']['content'].strip()
            corrected_file_path = os.path.join("output", 'transcription_corrected.txt')
            with open(corrected_file_path, 'w', encoding='utf-8') as output_file:
                output_file.write(gpt4_response)
            return corrected_file_path
        else:
            st.error(f"API Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        st.error(f"Error during GPT-4 processing: {str(e)}")
        return None

# Function to generate adjusted audio
def generate_adjusted_audio(analysis_file, corrected_transcription_file):
    try:
        with open(analysis_file, 'r') as f:
            analysis_output = f.read()

        word_count = int(re.search(r'Word count: (\d+)', analysis_output).group(1))
        spoken_duration = float(re.search(r'Spoken duration \(minutes\): ([\d.]+)', analysis_output).group(1))
        target_wpm = float(re.search(r'Words per minute \(WPM\): ([\d.]+)', analysis_output).group(1))

        with open(corrected_transcription_file, 'r', encoding='utf-8') as f:
            text = f.read()

        # Setup TTS engine
        tts = TTS(model_name="tts_models/en/ljspeech/tacotron2", progress_bar=True)

        # Generate the audio from text
        output_path = os.path.join("output", "output_adjusted.wav")
        tts.tts_to_file(text=text, file_path=output_path)
        
        st.success(f"Final adjusted audio saved as '{output_path}'")
    except Exception as e:
        st.error(f"Error during audio generation: {str(e)}")

# Streamlit app
st.title("Video to Adjusted Audio Converter")

uploaded_file = st.file_uploader("Choose a video file...", type=["mp4"])

if uploaded_file:
    with NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(uploaded_file.read())
        video_path = tmp_file.name

    st.write("Extracting audio from the video...")
    extracted_audio_path = extract_audio_from_video(video_path)
    
    if extracted_audio_path:
        st.write("Processing audio with Whisper and Pydub...")
        transcription_file, analysis_file = process_audio_with_whisper_and_pydub(extracted_audio_path)

        if transcription_file and analysis_file:
            st.write("Correcting transcription with GPT-4...")
            corrected_transcription_file = correct_transcription_with_gpt4(transcription_file)
            
            if corrected_transcription_file:
                st.write("Generating adjusted audio...")
                generate_adjusted_audio(analysis_file, corrected_transcription_file)
