import os
import requests
from moviepy.editor import VideoFileClip, AudioFileClip
from pydub import AudioSegment, silence
from gtts import gTTS
import streamlit as st
import tempfile
import whisper

# API configurations (replace with your own API key)
API_KEY = "22ec84421ec24230a3638d1b51e3a7dc"
ENDPOINT = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

# Streamlit app title
st.title("Video to Adjusted Audio Sync with Silence Handling")

# Function to log errors
def log_error(message):
    st.error(message)  # Log errors in the Streamlit app

# Step 1: Extract audio from the video
def extract_audio_from_video(video_path):
    try:
        video = VideoFileClip(video_path)
        audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
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
        return result['text'].strip()
    except Exception as e:
        log_error(f"Error transcribing audio: {e}")
        return None

# Step 3: Correct transcription with GPT-4
def correct_transcription_with_gpt4(transcription):
    try:
        prompt = ("Correct the following text for punctuation, spelling, and grammar without changing its meaning:\n\n" + transcription)

        headers = {
            "Content-Type": "application/json",
            "api-key": API_KEY,
        }

        data = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 2048,
            "temperature": 0.7,
        }

        response = requests.post(ENDPOINT, headers=headers, json=data)
        if response.status_code == 200:
            response_data = response.json()
            return response_data['choices'][0]['message']['content'].strip()
        else:
            log_error(f"API Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        log_error(f"Error correcting transcription: {e}")
        return None

# Step 4: Detect silences in the original audio
def detect_silences(audio_path, silence_thresh=-50, min_silence_len=500):
    try:
        audio = AudioSegment.from_mp3(audio_path)
        silence_segments = silence.detect_silence(audio, min_silence_len=min_silence_len, silence_thresh=silence_thresh)
        return [(start, stop) for start, stop in silence_segments]
    except Exception as e:
        log_error(f"Error detecting silences: {e}")
        return None

# Step 5: Generate adjusted audio and incorporate silences
def generate_adjusted_audio_with_silences(corrected_transcription, original_audio_path):
    try:
        # Generate TTS audio
        tts = gTTS(corrected_transcription, lang='en')
        tts_audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
        tts.save(tts_audio_path)

        # Detect silences from the original audio
        silence_segments = detect_silences(original_audio_path)

        if silence_segments:
            tts_audio = AudioSegment.from_mp3(tts_audio_path)

            # Insert silences into the generated audio
            for start, stop in silence_segments:
                silence_duration = stop - start
                silent_segment = AudioSegment.silent(duration=silence_duration)
                tts_audio = tts_audio[:start] + silent_segment + tts_audio[start:]

            final_output_audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
            tts_audio.export(final_output_audio_path, format="mp3")
            return final_output_audio_path
        else:
            return tts_audio_path

    except Exception as e:
        log_error(f"Error generating adjusted audio with silences: {e}")
        return None

# Step 6: Attach adjusted audio to video
def attach_audio_to_video(video_path, adjusted_audio_path):
    try:
        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(adjusted_audio_path)  # Use AudioFileClip instead of AudioSegment

        final_video_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
        final_video = video_clip.set_audio(audio_clip)
        final_video.write_videofile(final_video_path, codec="libx264", audio_codec="aac")

        video_clip.close()  # Close the video clip
        audio_clip.close()  # Close the audio clip
        final_video.close()  # Close the final video clip
        return final_video_path
    except Exception as e:
        log_error(f"Error attaching audio to video: {e}")
        return None

# Main Streamlit logic
def main():
    video_file = st.file_uploader("Upload a video", type=["mp4", "mkv", "avi"])

    if st.button("Process Video") and video_file is not None:
        video_path = tempfile.NamedTemporaryFile(delete=False).name
        with open(video_path, "wb") as f:
            f.write(video_file.read())

        # Step 1: Extract audio
        output_audio_path = extract_audio_from_video(video_path)

        if output_audio_path:
            # Step 2: Transcribe audio
            transcription = transcribe_audio(output_audio_path)

            if transcription:
                # Step 3: Correct transcription
                corrected_transcription = correct_transcription_with_gpt4(transcription)

                if corrected_transcription:
                    # Step 4: Generate adjusted audio with silences
                    adjusted_audio_path = generate_adjusted_audio_with_silences(corrected_transcription, output_audio_path)

                    if adjusted_audio_path:
                        # Step 5: Sync audio and attach to video
                        final_video_path = attach_audio_to_video(video_path, adjusted_audio_path)

                        if final_video_path:
                            st.success("Video processing complete!")
                            st.video(final_video_path)
                        else:
                            log_error("Failed to attach audio to video.")
                    else:
                        log_error("Failed to generate adjusted audio.")
                else:
                    log_error("Failed to correct transcription.")
            else:
                log_error("Failed to transcribe audio.")
        else:
            log_error("Failed to extract audio from video.")

if __name__ == "__main__":
    main()
