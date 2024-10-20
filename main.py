import os
import whisper
import requests
import json
import tempfile
from moviepy.editor import VideoFileClip, AudioFileClip
from pydub import AudioSegment, silence
from gtts import gTTS
import streamlit as st
import time

# API configurations (replace with your own API key)
api_key = "22ec84421ec24230a3638d1b51e3a7dc"
endpoint = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

# Streamlit app title
st.title("Video to Adjusted Audio Sync with Silence Handling")

# Use temporary directory for storing files
temp_dir = tempfile.TemporaryDirectory()

# Function to log errors
def log_error(message):
    print(message)  # You can replace this with logging to a file or other logging mechanisms

# Step 1: Extract audio from the video
def extract_audio_from_video(video_path, output_audio_filename="audio.mp3"):
    try:
        output_audio_path = os.path.join(temp_dir.name, output_audio_filename)
        video = VideoFileClip(video_path)
        audio = video.audio
        audio.write_audiofile(output_audio_path)
        video.close()
        return output_audio_path
    except Exception as e:
        log_error(f"Error extracting audio: {e}")
        return None

# Step 2: Transcribe audio with Whisper and get timestamps
def transcribe_audio_with_timestamps(audio_file_path):
    try:
        model = whisper.load_model("tiny", device="cpu")
        result = model.transcribe(audio_file_path, word_timestamps=True)
        transcription = result['text'].strip()

        # Save transcription and timestamps
        transcription_file = os.path.join(temp_dir.name, 'transcription.txt')
        with open(transcription_file, 'w', encoding='utf-8') as f:
            f.write(transcription)

        return transcription_file, result['segments']
    except Exception as e:
        log_error(f"Error transcribing audio: {e}")
        return None, None

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

                    corrected_file_path = os.path.join(temp_dir.name, 'transcription_corrected.txt')
                    with open(corrected_file_path, 'w', encoding='utf-8') as output_file:
                        output_file.write(gpt4_response)

                    return corrected_file_path
                else:
                    print(f"API Error: {response.status_code} - {response.text}")
            except requests.exceptions.RequestException as e:
                print(f"Request failed: {e}. Retrying {attempt + 1}/{max_retries}...")
                time.sleep(2)

        return None
    except Exception as e:
        log_error(f"Error in GPT-4 correction: {e}")
        return None

# Step 5: Generate adjusted audio with silence handling and timestamps
def generate_adjusted_audio_with_timestamps(corrected_transcription_file, segments, original_audio_path):
    try:
        with open(corrected_transcription_file, 'r', encoding='utf-8') as f:
            text = f.read()

        # Generate TTS audio using gTTS
        tts = gTTS(text)
        output_audio_path = os.path.join(temp_dir.name, "generated_audio.wav")
        tts.save(output_audio_path)

        # Align the audio based on the timestamps from Whisper's result
        silence_segments = detect_silences(original_audio_path)

        tts_audio = AudioSegment.from_wav(output_audio_path)
        aligned_audio = tts_audio

        # Apply silences from original audio to the synthesized speech based on word-level timestamps
        for seg in segments:
            start_time = seg['start'] * 1000  # Convert to milliseconds
            end_time = seg['end'] * 1000

            if silence_segments:
                for start, stop in silence_segments:
                    silence_duration = stop - start
                    silent_segment = AudioSegment.silent(duration=silence_duration)
                    aligned_audio = aligned_audio[:start_time] + silent_segment + aligned_audio[end_time:]

        final_output_audio_path = os.path.join(temp_dir.name, "adjusted_audio_with_timestamps.wav")
        aligned_audio.export(final_output_audio_path, format="wav")
        return final_output_audio_path

    except Exception as e:
        log_error(f"Error generating adjusted audio with timestamps: {e}")
        return None

# Step 6: Attach adjusted audio to the video
def attach_audio_to_video(video_path, adjusted_audio_path):
    try:
        video_clip = VideoFileClip(video_path)
        final_adjusted_audio_path = os.path.join(temp_dir.name, "final_video_with_audio.mp4")

        # Set progress bar increment during video generation
        with st.spinner('Generating final video...'):
            for i in range(1, 101, 10):  # Simulate gradual progress
                time.sleep(0.5)
                st.progress(i / 100.0)  # Update progress bar
            video_clip.set_audio(AudioFileClip(adjusted_audio_path)).write_videofile(final_adjusted_audio_path, codec="libx264", audio_codec="aac")
        
        return final_adjusted_audio_path
    except Exception as e:
        log_error(f"Error attaching audio to video: {e}")
        return None

# Main Streamlit logic
def main():
    video_file = st.file_uploader("Upload a video", type=["mp4", "mkv", "avi"])
    
    if st.button("Process Video") and video_file is not None:
        progress_bar = st.progress(0)

        video_path = os.path.join(temp_dir.name, video_file.name)
        with open(video_path, "wb") as f:
            f.write(video_file.read())

        # Step 1: Extract audio
        with st.spinner('Extracting audio from the video...'):
            output_audio_path = extract_audio_from_video(video_path)
        progress_bar.progress(20)

        if output_audio_path:
            # Step 2: Transcribe audio with timestamps
            with st.spinner('Transcribing audio...'):
                transcription_file, segments = transcribe_audio_with_timestamps(output_audio_path)
            progress_bar.progress(40)

            if transcription_file and segments:
                # Step 4: Correct transcription
                with st.spinner('Correcting transcription with GPT-4...'):
                    corrected_transcription_file = correct_transcription_with_gpt4(transcription_file)
                progress_bar.progress(60)

                if corrected_transcription_file:
                    # Step 5: Generate adjusted audio with silences and timestamps
                    with st.spinner('Generating adjusted audio with timestamps...'):
                        generated_audio_path = generate_adjusted_audio_with_timestamps(corrected_transcription_file, segments, output_audio_path)
                    progress_bar.progress(80)

                    if generated_audio_path:
                        # Step 6: Sync audio and attach to video
                        with st.spinner('Syncing audio and attaching it to the video...'):
                            final_video_path = attach_audio_to_video(video_path, generated_audio_path)
                        progress_bar.progress(100)

                        if final_video_path:
                            st.success("Video processing complete!")
                            st.video(final_video_path)

if __name__ == "__main__":
    main()
