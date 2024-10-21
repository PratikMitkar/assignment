import os
import whisper
import requests
import json
from moviepy.editor import VideoFileClip, AudioFileClip
from pydub import AudioSegment, silence
from TTS.api import TTS  # For text-to-speech using TTS library
import streamlit as st

# API configurations
api_key = "22ec84421ec24230a3638d1b51e3a7dc"
endpoint = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

# Streamlit app title
st.title("🎥 Video to Adjusted Audio Sync with Silence Handling")

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

# Detect silences in the original audio
def detect_silences(audio_path, silence_thresh=-50, min_silence_len=500):
    try:
        audio = AudioSegment.from_mp3(audio_path)
        silence_segments = silence.detect_silence(audio, min_silence_len=min_silence_len, silence_thresh=silence_thresh)
        return [(start, stop) for start, stop in silence_segments]
    except Exception as e:
        log_error(f"Error detecting silences: {e}")
        return []

# Step 4: Generate adjusted audio and incorporate silences using Streamlit-TTS
def generate_adjusted_audio_with_silences(corrected_transcription, original_audio_path):
    try:
        # Initialize TTS model
        tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False, gpu=False)

        # Generate audio from the corrected transcription using TTS
        tts_output_path = os.path.join(base_output_folder, "generated_audio.wav")
        tts.tts_to_file(text=corrected_transcription, file_path=tts_output_path)

        # Detect silences from the original audio
        silence_segments = detect_silences(original_audio_path)

        if silence_segments:
            generated_audio = AudioSegment.from_wav(tts_output_path)

            # Insert silences into the generated audio
            for start, stop in silence_segments:
                silence_duration = stop - start
                silent_segment = AudioSegment.silent(duration=silence_duration)
                generated_audio = generated_audio[:start] + silent_segment + generated_audio[start:]

            # Save the final adjusted audio with silences
            final_output_audio_path = os.path.join(base_output_folder, "adjusted_audio_with_silences.wav")
            generated_audio.export(final_output_audio_path, format="wav")
            return final_output_audio_path
        else:
            return tts_output_path
    except Exception as e:
        log_error(f"Error generating adjusted audio with silences: {e}")
        return None

# Step 5: Attach adjusted audio to the video
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
        status_label = st.empty()

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
                    # Step 4: Generate adjusted audio with silences
                    status_label.text("🎶 Generating adjusted audio with silences...")
                    generated_audio_path = generate_adjusted_audio_with_silences(corrected_transcription, output_audio_path)
                    progress.progress(80)

                    if generated_audio_path:
                        # Step 5: Sync audio and attach to video
                        status_label.text("📽️ Attaching adjusted audio to video...")
                        final_video_path = attach_audio_to_video(video_path, generated_audio_path)

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
                        log_error("Adjusted audio generation failed.")
                else:
                    log_error("Transcription correction failed.")
            else:
                log_error("Audio transcription failed.")
        else:
            log_error("Audio extraction failed.")

if __name__ == "__main__":
    main()
