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

# Directly using the Azure API key and endpoint
api_key = "22ec84421ec24230a3638d1b51e3a7dc"
endpoint = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

# Streamlit app title
st.title("Video to Adjusted Audio Sync with Silence Handling")

# Function to log errors
def log_error(message):
    print(message)  # For debugging, can be changed to logging

# Step 1: Extract audio from the video
def extract_audio_from_video(video_file, output_audio_filename="audio.mp3"):
    try:
        video = VideoFileClip(video_file)
        audio = video.audio
        output_audio_path = os.path.join(tempfile.gettempdir(), output_audio_filename)
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
        return transcription, result['segments']
    except Exception as e:
        log_error(f"Error transcribing audio: {e}")
        return None, None

# Step 3: Correct transcription with Azure API
def correct_transcription_with_gpt4(transcription, max_retries=3):
    prompt = f"Correct the following text for punctuation, spelling, and grammar without changing its meaning:\n\n{transcription}"

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
                return response_data['choices'][0]['message']['content'].strip()
            else:
                print(f"API Error: {response.status_code} - {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}. Retrying {attempt + 1}/{max_retries}...")
            time.sleep(2)

    return None

# Step 4: Generate adjusted audio with silence handling
def generate_adjusted_audio_with_timestamps(text, segments, original_audio_path):
    try:
        # Generate TTS audio using gTTS
        tts = gTTS(text)
        output_audio_path = os.path.join(tempfile.gettempdir(), "generated_audio.wav")
        tts.save(output_audio_path)

        # Load the generated TTS audio as an AudioSegment
        tts_audio = AudioSegment.from_wav(output_audio_path)
        aligned_audio = AudioSegment.silent(duration=0)

        # Align the audio based on Whisper's timestamps
        for seg in segments:
            start_time = seg['start'] * 1000  # Convert to milliseconds
            end_time = seg['end'] * 1000
            aligned_audio += tts_audio[start_time:end_time] + AudioSegment.silent(duration=100)  # Short silence

        final_output_audio_path = os.path.join(tempfile.gettempdir(), "adjusted_audio_with_timestamps.wav")
        aligned_audio.export(final_output_audio_path, format="wav")
        return final_output_audio_path
    except Exception as e:
        log_error(f"Error generating adjusted audio: {e}")
        return None

# Step 5: Attach adjusted audio to the video
def attach_audio_to_video(video_file, adjusted_audio_path):
    try:
        video_clip = VideoFileClip(video_file)
        final_adjusted_audio_path = os.path.join(tempfile.gettempdir(), "final_video_with_audio.mp4")

        with st.spinner('Generating final video...'):
            video_clip.set_audio(AudioFileClip(adjusted_audio_path)).write_videofile(final_adjusted_audio_path, codec="libx264", audio_codec="aac")

        return final_adjusted_audio_path
    except Exception as e:
        log_error(f"Error attaching audio to video: {e}")
        return None

# Main Streamlit logic
def main():
    st.write("Upload a video to sync audio with silence handling.")
    video_file = st.file_uploader("Choose a video file", type=["mp4", "mkv", "avi"])

    if video_file is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video_file:
            temp_video_file.write(video_file.read())
            video_path = temp_video_file.name

        if st.button("Process Video"):
            progress_bar = st.progress(0)

            # Step 1: Extract audio
            output_audio_path = extract_audio_from_video(video_path)
            progress_bar.progress(20)

            if output_audio_path:
                # Step 2: Transcribe audio
                transcription, segments = transcribe_audio_with_timestamps(output_audio_path)
                progress_bar.progress(40)

                if transcription and segments:
                    # Step 3: Correct transcription
                    corrected_transcription = correct_transcription_with_gpt4(transcription)
                    progress_bar.progress(60)

                    if corrected_transcription:
                        # Step 4: Generate adjusted audio
                        generated_audio_path = generate_adjusted_audio_with_timestamps(corrected_transcription, segments, output_audio_path)
                        progress_bar.progress(80)

                        if generated_audio_path:
                            # Step 5: Attach audio to video
                            final_video_path = attach_audio_to_video(video_path, generated_audio_path)
                            progress_bar.progress(100)

                            if final_video_path:
                                st.success("Video processing complete!")
                                st.video(final_video_path)
                            else:
                                st.error("Error attaching audio to video.")
                        else:
                            st.error("Error generating adjusted audio.")
                    else:
                        st.error("Error correcting transcription.")
                else:
                    st.error("Error transcribing audio.")
            else:
                st.error("Error extracting audio from the video.")

if __name__ == "__main__":
    main()
