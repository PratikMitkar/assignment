import os
import whisper
import requests
import json
from moviepy.editor import VideoFileClip, AudioFileClip
from pydub import AudioSegment
from gtts import gTTS
import streamlit as st

# API configurations
api_key = "22ec84421ec24230a3638d1b51e3a7dc"
endpoint = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

# Streamlit app title
st.title("🎥 Video to Audio Sync with Speed Adjustment")

# Define a base output folder path
base_output_folder = "output"
os.makedirs(base_output_folder, exist_ok=True)

# Function to log errors
def log_error(message):
    st.error(message)

# Step 1: Extract audio from the video
def extract_audio_from_video(video_path):
    try:
        video = VideoFileClip(video_path)
        audio_path = os.path.join(base_output_folder, "audio.mp3")
        video.audio.write_audiofile(audio_path)
        video.close()
        return audio_path
    except Exception as e:
        log_error(f"Error extracting audio: {e}")
        return None

# Step 2: Transcribe audio with Whisper
def transcribe_audio(audio_file_path):
    try:
        model = whisper.load_model("base")
        result = model.transcribe(audio_file_path)
        transcription = result['text'].strip()
        return transcription
    except Exception as e:
        log_error(f"Error transcribing audio: {e}")
        return None

# Step 3: Correct transcription with GPT-4
def correct_transcription_with_gpt4(transcription):
    try:
        prompt = ("Correct the following text for punctuation, spelling, and grammar without changing its meaning:"
                  f"\n\n{transcription}")

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

        response = requests.post(endpoint, headers=headers, json=data)

        if response.status_code == 200:
            response_data = response.json()
            # Check if 'choices' key exists and contains a valid response
            if 'choices' in response_data and len(response_data['choices']) > 0:
                gpt4_response = response_data['choices'][0]['message']['content'].strip()
                return gpt4_response
            else:
                log_error("No valid 'choices' found in GPT-4 response.")
                return None
        else:
            log_error(f"GPT-4 API request failed with status code: {response.status_code}")
            return None

    except Exception as e:
        log_error(f"Error in GPT-4 correction: {e}")
        return None

# Step 4: Generate audio from corrected transcription
def generate_audio_from_text(text, output_path):
    try:
        tts = gTTS(text, lang='en')
        tts.save(output_path)
        return output_path
    except Exception as e:
        log_error(f"Error generating audio: {e}")
        return None

# Step 5: Adjust the speed of the generated audio to match video duration
def adjust_audio_speed_to_match_duration(audio_path, target_duration_ms):
    try:
        # Load the generated audio
        audio = AudioSegment.from_mp3(audio_path)
        audio_duration_ms = len(audio)

        # Calculate speed factor to adjust the duration
        speed_factor = target_duration_ms / audio_duration_ms

        # Adjust speed
        adjusted_audio = audio.speedup(playback_speed=speed_factor)

        # Save the adjusted audio
        adjusted_audio_path = os.path.join(base_output_folder, "adjusted_audio.mp3")
        adjusted_audio.export(adjusted_audio_path, format="mp3")

        return adjusted_audio_path
    except Exception as e:
        log_error(f"Error adjusting audio speed: {e}")
        return None

# Step 6: Attach adjusted audio to the video
def attach_audio_to_video(video_path, adjusted_audio_path):
    try:
        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(adjusted_audio_path)

        final_video = video_clip.set_audio(audio_clip)
        final_video_path = os.path.join(base_output_folder, "final_video_with_audio.mp4")
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
        status_label.text("🔊 Extracting audio from video...")
        output_audio_path = extract_audio_from_video(video_path)
        progress.progress(20)

        if output_audio_path:
            # Step 2: Transcribe audio
            status_label.text("📝 Transcribing audio...")
            transcription = transcribe_audio(output_audio_path)
            progress.progress(40)

            if transcription:
                # Step 3: Correct transcription
                status_label.text("✍️ Correcting transcription with GPT-4...")
                corrected_transcription = correct_transcription_with_gpt4(transcription)
                progress.progress(60)

                if corrected_transcription:
                    # Step 4: Generate audio from corrected transcription
                    status_label.text("🎶 Generating audio from corrected transcription...")
                    generated_audio_path = os.path.join(base_output_folder, "generated_audio.mp3")
                    generated_audio = generate_audio_from_text(corrected_transcription, generated_audio_path)
                    progress.progress(70)

                    if generated_audio:
                        # Step 5: Adjust audio speed to match video duration
                        status_label.text("🎚️ Adjusting audio speed to match video duration...")
                        video_duration = VideoFileClip(video_path).duration * 1000  # Convert to milliseconds
                        adjusted_audio_path = adjust_audio_speed_to_match_duration(generated_audio_path, video_duration)
                        progress.progress(85)

                        if adjusted_audio_path:
                            # Step 6: Sync audio and attach to video
                            status_label.text("📽️ Attaching adjusted audio to video...")
                            final_video_path = attach_audio_to_video(video_path, adjusted_audio_path)
                            progress.progress(100)

                            if final_video_path:
                                st.success("✅ Video processing complete!")
                                # Create two columns to display videos side by side
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.subheader("Original Video")
                                    st.video(video_path)
                                with col2:
                                    st.subheader("Generated Video")
                                    st.video(final_video_path)
                            else:
                                log_error("Final video generation failed.")
                        else:
                            log_error("Audio speed adjustment failed.")
                    else:
                        log_error("Generated audio creation failed.")
                else:
                    log_error("Transcription correction failed.")
            else:
                log_error("Audio transcription failed.")
        else:
            log_error("Audio extraction failed.")

if __name__ == "__main__":
    main()
