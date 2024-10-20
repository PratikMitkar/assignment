import os
import threading
import requests
import time
import re
import whisper
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
import silence
import streamlit as st

# Configuration for API

API_KEY = "22ec84421ec24230a3638d1b51e3a7dc"
ENDPOINT = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

def extract_audio_from_video(video_path, output_audio_folder="output", output_audio_filename="audio.mp3"):
    if not os.path.exists(output_audio_folder):
        os.makedirs(output_audio_folder)
    output_audio_path = os.path.join(output_audio_folder, output_audio_filename)
    
    try:
        video = VideoFileClip(video_path)
        audio = video.audio
        audio.write_audiofile(output_audio_path)
        video.close()
        st.success(f"Audio extracted successfully: {output_audio_path}")
        return output_audio_path
    except Exception as e:
        st.error(f"An error occurred while extracting audio: {str(e)}")
        return None

def process_audio_with_whisper(audio_file_path):
    try:
        audio = AudioSegment.from_mp3(audio_file_path)
        silence_threshold = -50  
        min_silence_duration = 500 
        silence_intervals = silence.detect_silence(audio, min_silence_len=min_silence_duration, silence_thresh=silence_threshold)

        total_duration_seconds = len(audio) / 1000
        spoken_duration_seconds = total_duration_seconds - sum((end - start) for start, end in silence_intervals) / 1000

        model = whisper.load_model("base")
        result = model.transcribe(audio_file_path)
        transcription = result['text'].strip()

        word_count = len(transcription.split())
        spoken_minutes = spoken_duration_seconds / 60
        wpm = word_count / spoken_minutes if spoken_minutes > 0 else 0

        transcription_file = "transcription.txt"
        with open(transcription_file, 'w', encoding='utf-8') as f:
            f.write(transcription)
        
        analysis_output = {
            "word_count": word_count,
            "spoken_duration": spoken_minutes,
            "wpm": wpm
        }

        return transcription_file, analysis_output
    except Exception as e:
        st.error(f"An error occurred during audio processing: {str(e)}")
        return None, None

def correct_transcription_with_gpt4(transcription_file):
    try:
        with open(transcription_file, 'r', encoding='utf-8') as file:
            file_content = file.read()

        prompt = ("Correct the following text for punctuation, spelling, and grammar without changing its meaning. "
                  "Ensure the output contains only the corrected text.")

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

        response = requests.post(ENDPOINT, headers=headers, json=data)
        
        if response.status_code == 200:
            response_data = response.json()
            gpt4_response = response_data['choices'][0]['message']['content'].strip()

            corrected_file_path = 'transcription_corrected.txt'
            with open(corrected_file_path, 'w', encoding='utf-8') as output_file:
                output_file.write(gpt4_response)

            st.success(f"GPT-4 output saved to: {corrected_file_path}")
            return corrected_file_path

        else:
            st.error(f"API Error: {response.status_code} - {response.text}")

    except Exception as e:
        st.error(f"An error occurred during GPT-4 processing: {str(e)}")
        return None

def generate_adjusted_audio(analysis_output, corrected_transcription_file):
    try:
        with open(corrected_transcription_file, 'r', encoding='utf-8') as f:
            text = f.read()

        target_wpm = analysis_output['wpm']
        speech_rate = target_wpm / 170  # Adjust the rate based on your preference

        chunk_size = 1000
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        
        combined_audio = AudioSegment.empty()
        for i, chunk in enumerate(chunks):
            chunk_audio = generate_audio_chunk(chunk, speech_rate, i)
            if chunk_audio:
                combined_audio += chunk_audio
        
        output_path = "output_adjusted.wav"
        combined_audio.export(output_path, format="wav")

        st.success(f"Final adjusted audio saved as '{output_path}'")
        return output_path

    except Exception as e:
        st.error(f"An error occurred during audio generation: {str(e)}")

def generate_audio_chunk(chunk, speech_rate, chunk_index):
    import pyttsx3

    engine = pyttsx3.init()
    engine.setProperty('rate', 150 * speech_rate)  # Adjust speech rate
    engine.setProperty('voice', 'english+male')  # Set to male voice (may vary by system)

    chunk_path = f"chunk_adjusted_{chunk_index}.wav"
    engine.save_to_file(chunk, chunk_path)
    engine.runAndWait()

    return AudioSegment.from_wav(chunk_path)

def main():
    st.title("Video to Adjusted Audio Converter")

    video_file = st.file_uploader("Upload a Video File", type=["mp4"])
    
    if video_file is not None:
        video_path = "uploaded_video.mp4"
        with open(video_path, "wb") as f:
            f.write(video_file.read())

        st.write("Extracting audio...")
        extracted_audio = extract_audio_from_video(video_path)
        
        if extracted_audio:
            st.write("Processing audio with Whisper...")
            transcription_file, analysis_output = process_audio_with_whisper(extracted_audio)
            
            if transcription_file and analysis_output:
                st.write("Correcting transcription with GPT-4...")
                corrected_transcription_file = correct_transcription_with_gpt4(transcription_file)

                if corrected_transcription_file:
                    st.write("Generating adjusted audio...")
                    generate_adjusted_audio(analysis_output, corrected_transcription_file)

if __name__ == "__main__":
    main()
