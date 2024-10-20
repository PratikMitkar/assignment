import os
import whisper
import requests
import json
from moviepy.editor import VideoFileClip, AudioFileClip
from pydub import AudioSegment, silence
import streamlit as st
from gtts import gTTS

# API configurations
api_key = "22ec84421ec24230a3638d1b51e3a7dc"
endpoint = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

# Streamlit app title
st.title("Video to Adjusted Audio Sync with Silence Handling")

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
        # Load audio and get its duration
        audio = AudioSegment.from_mp3(audio_file_path)
        original_duration = len(audio) / 1000  # duration in seconds
        
        model = whisper.load_model("base")
        result = model.transcribe(audio_file_path)
        transcription = result['text'].strip()
        
        # Save the transcription to a text file
        transcription_file = os.path.join(base_output_folder, 'transcription.txt')
        with open(transcription_file, 'w', encoding='utf-8') as f:
            f.write(transcription)
        
        return transcription_file, original_duration  # Return transcription file and duration
    except Exception as e:
        log_error(f"Error transcribing audio: {e}")
        return None, None

# Step 3: Correct transcription with GPT-4
def correct_transcription_with_gpt4(transcription_file):
    try:
        with open(transcription_file, 'r', encoding='utf-8') as file:
            file_content = file.read()

        prompt = ("Correct the following text for punctuation, spelling, and grammar without changing its meaning:"
                  f"\n\n{file_content}")

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
        response_data = response.json()
        gpt4_response = response_data['choices'][0]['message']['content'].strip()

        corrected_file_path = os.path.join(base_output_folder, 'transcription_corrected.txt')
        with open(corrected_file_path, 'w', encoding='utf-8') as output_file:
            output_file.write(gpt4_response)

        return corrected_file_path
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

# Step 4: Generate adjusted audio and incorporate silences
def generate_adjusted_audio_with_silences(corrected_transcription_file, original_audio_path, original_duration):
    try:
        with open(corrected_transcription_file, 'r', encoding='utf-8') as f:
            text = f.read()

        # Use gTTS for generating audio from text
        tts = gTTS(text, lang='en')
        tts_output_path = os.path.join(base_output_folder, "generated_audio.mp3")
        tts.save(tts_output_path)

        # Detect silences from the original audio
        silence_segments = detect_silences(original_audio_path)

        generated_audio = AudioSegment.from_mp3(tts_output_path)

        # Adjust playback speed based on original duration and text length
        words_count = len(text.split())
        playback_speed = original_duration / (words_count / 2.0)  # Adjust speed per your requirements
        generated_audio = generated_audio.speedup(playback_speed)

        # Insert silences into the generated audio
        for start, stop in silence_segments:
            silence_duration = stop - start
            silent_segment = AudioSegment.silent(duration=silence_duration)
            generated_audio = generated_audio[:start] + silent_segment + generated_audio[start:]

        # Save the final adjusted audio with silences
        final_output_audio_path = os.path.join(base_output_folder, "adjusted_audio_with_silences.mp3")
        generated_audio.export(final_output_audio_path, format="mp3")
        return final_output_audio_path
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
            transcription_file, original_duration = transcribe_audio(output_audio_path)
            progress.progress(40)

            if transcription_file:
                # Step 3: Correct transcription
                status_label.text("Correcting transcription with GPT-4...")
                corrected_transcription_file = correct_transcription_with_gpt4(transcription_file)
                progress.progress(60)

                if corrected_transcription_file:
                    # Step 4: Generate adjusted audio with silences
                    status_label.text("Generating adjusted audio with silences...")
                    generated_audio_path = generate_adjusted_audio_with_silences(corrected_transcription_file, output_audio_path, original_duration)
                    progress.progress(80)

                    if generated_audio_path:
                        # Step 5: Sync audio and attach to video
                        status_label.text("Attaching adjusted audio to video...")
                        final_video_path = attach_audio_to_video(video_path, generated_audio_path)

                        if final_video_path:
                            st.success("Video processing complete!")
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
