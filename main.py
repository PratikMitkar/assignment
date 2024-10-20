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

# API configurations (replace with your own API key)
api_key = "22ec84421ec24230a3638d1b51e3a7dc"
endpoint = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

# Streamlit app title
st.title("Video to Adjusted Audio Sync")

# Define a base output folder path
base_output_folder = "output"
os.makedirs(base_output_folder, exist_ok=True)

# Step 1: Extract audio from the video
def extract_audio_from_video(video_path, output_audio_folder=base_output_folder, output_audio_filename="audio.mp3"):
    try:
        output_audio_path = os.path.join(output_audio_folder, output_audio_filename)
        video = VideoFileClip(video_path)
        audio = video.audio
        audio.write_audiofile(output_audio_path)
        video.close()
        return output_audio_path
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return None

# Step 2: Transcribe audio with Whisper
def transcribe_audio(audio_file_path, output_folder=base_output_folder):
    try:
        model = whisper.load_model("base")
        result = model.transcribe(audio_file_path)
        transcription = result['text'].strip()

        transcription_file = os.path.join(output_folder, 'transcription.txt')
        with open(transcription_file, 'w', encoding='utf-8') as f:
            f.write(transcription)
        return transcription_file
    except Exception as e:
        print(f"Error transcribing audio: {e}")
        return None

# Step 3: Correct transcription with GPT-4
def correct_transcription_with_gpt4(transcription_file, output_folder=base_output_folder, max_retries=3):
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

                    corrected_file_path = os.path.join(output_folder, 'transcription_corrected.txt')
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
        print(f"Error in GPT-4 correction: {e}")
        return None

# Step 4: Generate adjusted audio
def generate_adjusted_audio(corrected_transcription_file, speech_rate=1.0, output_folder=base_output_folder):
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", int(170 * speech_rate))

        with open(corrected_transcription_file, 'r', encoding='utf-8') as f:
            text = f.read()

        output_audio_path = os.path.join(output_folder, "generated_audio.wav")
        engine.save_to_file(text, output_audio_path)
        engine.runAndWait()
        return output_audio_path
    except Exception as e:
        print(f"Error generating adjusted audio: {e}")
        return None

# Step 5: Adjust audio duration to sync with the video
def adjust_audio_duration_with_speech_rate(audio_clip, video_duration):
    audio_duration = len(audio_clip) / 1000  # Audio duration in seconds
    duration_difference = video_duration - audio_duration

    if abs(duration_difference) < 0.1:  # If the difference is minimal (e.g., < 100 ms), add silence
        if duration_difference > 0:
            silence_clip = AudioSegment.silent(duration=duration_difference * 1000)
            audio_clip = audio_clip + silence_clip
        elif duration_difference < 0:
            audio_clip = audio_clip[:int(video_duration * 1000)]
    else:
        target_speed = audio_duration / video_duration
        audio_clip = audio_clip.speedup(playback_speed=target_speed)

    return audio_clip

# Step 6: Attach adjusted audio to the video
def attach_audio_to_video(video_path, adjusted_audio_path, output_folder=base_output_folder):
    try:
        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(adjusted_audio_path)

        adjusted_audio_clip = adjust_audio_duration_with_speech_rate(AudioSegment.from_wav(adjusted_audio_path),
                                                                     video_clip.duration)

        # Export adjusted audio
        final_adjusted_audio_path = os.path.join(output_folder, "adjusted_audio.wav")
        adjusted_audio_clip.export(final_adjusted_audio_path, format="wav")

        # Attach the adjusted audio to the video
        final_video = video_clip.set_audio(AudioFileClip(final_adjusted_audio_path))
        final_video_path = os.path.join(output_folder, "final_video_with_audio.mp4")
        final_video.write_videofile(final_video_path, codec="libx264", audio_codec="aac")

        return final_video_path
    except Exception as e:
        print(f"Error attaching audio to video: {e}")
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
                # Step 3: Correct transcription
                status_label.text("Correcting transcription with GPT-4...")
                corrected_transcription_file = correct_transcription_with_gpt4(transcription_file)
                progress.progress(60)

                if corrected_transcription_file:
                    # Step 4: Generate adjusted audio
                    status_label.text("Generating adjusted audio...")
                    generated_audio_path = generate_adjusted_audio(corrected_transcription_file)
                    progress.progress(80)

                    if generated_audio_path:
                        # Step 5 & 6: Sync audio and attach to video
                        status_label.text("Attaching adjusted audio to video...")
                        final_video_path = attach_audio_to_video(video_path, generated_audio_path)
                        progress.progress(100)
                        if final_video_path:
                            st.success("Processing complete!")

                            # Display original and final videos side by side
                            col1, col2 = st.columns(2)
                            with col1:
                                st.subheader("Original Video")
                                st.video(video_path)
                            with col2:
                                st.subheader("Final Video with Adjusted Audio")
                                st.video(final_video_path)

                            status_label.text("Complete")
                        else:
                            st.error("Error generating final video with synced audio.")
                            status_label.text("Error during final video generation")
    else:
        st.error("Please upload a video file.")

if __name__ == "__main__":
    main()
