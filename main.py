import os
import requests
import whisper
from pydub import AudioSegment
from pydub.silence import detect_silence
from moviepy.editor import VideoFileClip
import streamlit as st
import time
import threading

# Streamlit Configuration
st.title("Video to Adjusted Audio Converter")
st.write("Upload a video file to extract and adjust audio.")

# Input for video file
video_file = st.file_uploader("Choose a video file", type=["mp4"])

# Configuration for API
API_KEY = "22ec84421ec24230a3638d1b51e3a7dc"   # Replace with your actual API key
ENDPOINT = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"  # Replace with your actual endpoint

# Function to extract audio from video
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

# Function to process audio with Whisper
def process_audio_with_whisper(audio_file_path, output_folder="output"):
    try:
        audio = AudioSegment.from_mp3(audio_file_path)
        silence_threshold = -50  # in dBFS
        min_silence_duration = 500  # in milliseconds
        silence_intervals = detect_silence(audio, min_silence_len=min_silence_duration, silence_thresh=silence_threshold)

        total_duration_seconds = len(audio) / 1000
        spoken_duration_seconds = total_duration_seconds - sum((end - start) for start, end in silence_intervals) / 1000
        model = whisper.load_model("base")
        result = model.transcribe(audio_file_path)
        transcription = result['text'].strip()
        word_count = len(transcription.split())
        spoken_minutes = spoken_duration_seconds / 60
        wpm = word_count / spoken_minutes if spoken_minutes > 0 else 0

        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        transcription_file = os.path.join(output_folder, 'transcription.txt')
        with open(transcription_file, 'w', encoding='utf-8') as f:
            f.write(transcription)

        analysis_file = os.path.join(output_folder, 'audio_analysis_output.txt')
        output = f"""Transcription saved to: {transcription_file}
Word count: {word_count}
Spoken duration (minutes): {spoken_minutes:.2f}
Words per minute (WPM): {wpm:.2f}"""
        
        with open(analysis_file, 'w') as f:
            f.write(output)
        
        return transcription_file, analysis_file
    except Exception as e:
        st.error(f"An error occurred during audio processing: {str(e)}")
        return None, None

# Function to correct transcription with GPT-4
def correct_transcription_with_gpt4(transcription_file, output_folder="output", max_retries=3):
    try:
        with open(transcription_file, 'r', encoding='utf-8') as file:
            file_content = file.read()

        prompt = ("Correct the following text for punctuation, spelling, and grammar without changing its meaning. "
                  "Ensure the output contains only the corrected text, with no additional words or commentary.")

        headers = {
            "Content-Type": "application/json",
            "api-key": API_KEY,
        }

        data = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": f"{prompt}\n\n{file_content}"}
            ],
            "max_tokens": 2048,
            "temperature": 0.7,
        }

        for attempt in range(max_retries):
            try:
                response = requests.post(ENDPOINT, headers=headers, json=data)

                if response.status_code == 200:
                    response_data = response.json()
                    gpt4_response = response_data['choices'][0]['message']['content'].strip()

                    corrected_file_path = os.path.join(output_folder, 'transcription_corrected.txt')
                    with open(corrected_file_path, 'w', encoding='utf-8') as output_file:
                        output_file.write(gpt4_response)

                    return corrected_file_path

                else:
                    st.error(f"API Error: {response.status_code} - {response.text}")

            except requests.exceptions.RequestException as e:
                st.error(f"Request failed: {e}. Retrying {attempt + 1}/{max_retries}...")

        st.error(f"Failed after {max_retries} attempts.")
        return None

    except Exception as e:
        st.error(f"An error occurred during GPT-4 processing: {str(e)}")
        return None

# Function to generate adjusted audio
def generate_adjusted_audio(analysis_file, corrected_transcription_file, original_video_path):
    try:
        with open(analysis_file, 'r') as f:
            analysis_output = f.read()

        word_count = int(re.search(r'Word count: (\d+)', analysis_output).group(1))
        spoken_duration = float(re.search(r'Spoken duration \(minutes\): ([\d.]+)', analysis_output).group(1))
        target_wpm = float(re.search(r'Words per minute \(WPM\): ([\d.]+)', analysis_output).group(1))

        with open(corrected_transcription_file, 'r', encoding='utf-8') as f:
            text = f.read()

        speech_rate = target_wpm / 170
        chunk_size = 1000
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

        combined_audio = AudioSegment.empty()
        for i, chunk in enumerate(chunks):
            try:
                chunk_audio = AudioSegment.silent(duration=1000)  # Replace with TTS logic
                combined_audio += chunk_audio
            except Exception as e:
                st.error(f"Error processing chunk {i}: {str(e)}")

        output_path = os.path.join("output", "output_adjusted.wav")
        combined_audio.export(output_path, format="wav")

        if original_video_path:
            video_clip = VideoFileClip(original_video_path)
            audio_clip = AudioSegment.from_wav(output_path)
            final_video = video_clip.set_audio(audio_clip)
            final_video_path = os.path.join("output", "final_video_with_audio.mp4")
            final_video.write_videofile(final_video_path, codec="libx264", audio_codec="aac")
            st.success(f"Final video with adjusted audio saved as '{final_video_path}'")

    except Exception as e:
        st.error(f"An error occurred during audio generation: {str(e)}")

# Main processing function
def process_files(video_file):
    if video_file is not None:
        video_path = video_file.name
        with open(video_path, 'wb') as f:
            f.write(video_file.getbuffer())

        st.write("Extracting audio from video...")
        extracted_audio = extract_audio_from_video(video_path)

        if extracted_audio:
            st.write("Processing audio with Whisper...")
            transcription_file, analysis_file = process_audio_with_whisper(extracted_audio)

            if transcription_file and analysis_file:
                st.write("Correcting transcription with GPT-4...")
                corrected_transcription_file = correct_transcription_with_gpt4(transcription_file)

                if corrected_transcription_file:
                    st.write("Generating adjusted audio...")
                    generate_adjusted_audio(analysis_file, corrected_transcription_file, video_path)

# Run the processing function on button click
if st.button("Start Processing"):
    process_files(video_file)

