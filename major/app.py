from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import os
from pytube import YouTube
from moviepy.editor import VideoFileClip, AudioFileClip
from gtts import gTTS
import speech_recognition as sr
from deep_translator import GoogleTranslator
from transformers import pipeline
import textwrap
from pydub import AudioSegment  

app = Flask(__name__)
app.secret_key = '3b80953aa858437a4c0c31f2a99fa75d'
app.config['UPLOAD_FOLDER'] = 'uploads'  

def extract_video(youtube_link):
    try:
        yt = YouTube(youtube_link)
        stream = yt.streams.get_highest_resolution()

        output_path = "static"
        output_filename = "video.mp4"

        stream.download(output_path=output_path, filename=output_filename)
        return os.path.join(output_path, output_filename)

    except Exception as e:
        print("An error occurred while extracting video:", str(e))
        return None

def extract_audio(video_path, audio_output_path):
    try:
        video_clip = VideoFileClip(video_path)
        audio_clip = video_clip.audio
        audio_clip.write_audiofile(audio_output_path)
        audio_clip.close()
        video_clip.close()

    except Exception as e:
        print("An error occurred while extracting audio:", str(e))

def split_text_by_words(text, max_words_per_chunk):
    words = text.split()
    chunks = []
    current_chunk = []

    for word in words:
        if len(' '.join(current_chunk)) + len(word) <= max_words_per_chunk:
            current_chunk.append(word)
        else:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]

    if current_chunk:
        chunks.append(' '.join(current_chunk))

    return chunks

def translate_and_combine(input_text, target_language, max_words_per_chunk):
    try:
        text_chunks = split_text_by_words(input_text, max_words_per_chunk)
        translated_chunks = []

        for chunk in text_chunks:
            translation = GoogleTranslator(source='auto', target=target_language).translate(chunk)
            translated_chunks.append(translation)

        translated_text = ' '.join(translated_chunks)

        return translated_text
    except Exception as e:
        print("An error occurred:", str(e))

def text_to_audio(input_text_file, output_audio_file, language='gu'):
    try:
        with open(input_text_file, 'r', encoding='utf-8') as file:
            gujarati_text = file.read()

        tts = gTTS(text=gujarati_text, lang=language)
        tts.save(output_audio_file)

        print(f"Audio saved to {output_audio_file}")
    except Exception as e:
        print("An error occurred:", str(e))

def sync_audio_with_video(original_video_path, dubbed_audio_path, output_video_path):
    try:
        video_clip = VideoFileClip(original_video_path)
        audio_clip = AudioFileClip(dubbed_audio_path)
        video_clip = video_clip.set_audio(audio_clip)
        video_clip.write_videofile(output_video_path, codec='libx264', audio_codec='aac')

        print(f"Synchronized video saved to {output_video_path}")
    except Exception as e:
        print("An error occurred:", str(e))

def save_uploaded_file(file):
    if file:
        
        file_extension = os.path.splitext(file.filename)[1]
        uploaded_filename = "uploaded_video" + file_extension

        file.save(os.path.join(app.config['UPLOAD_FOLDER'], uploaded_filename))
        return os.path.join(app.config['UPLOAD_FOLDER'], uploaded_filename)
    else:
        return None

def summarize_and_translate(input_text, target_language):
    try:
        
        summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")
        
        max_chunk_length = 1000  
        chunks = textwrap.wrap(input_text, width=max_chunk_length)

        combined_summary = ""

        for chunk in chunks:
            summary = summarizer(chunk, max_length=50, min_length=10, do_sample=False)[0]['summary_text']
            combined_summary += summary + "\n"

        with open('summary.txt', 'w', encoding='utf-8') as file:
            file.write(combined_summary)

        translated_summary = GoogleTranslator(source='auto', target=target_language).translate(combined_summary)

        return translated_summary

    except Exception as e:
        print("An error occurred:", str(e))

def transcribe_audio_segments(audio_file_path, output_folder):

    recognizer = sr.Recognizer()

    audio = AudioSegment.from_file(audio_file_path)

    segment_duration_ms = 5000  

    num_segments = len(audio) // segment_duration_ms + 1

    os.makedirs(output_folder, exist_ok=True)

    segment_transcriptions = []

    for i in range(num_segments):
        start_time = i * segment_duration_ms
        end_time = (i + 1) * segment_duration_ms

        segment = audio[start_time:end_time]

        try:
            temp_audio_file = os.path.join(output_folder, f"segment_{i}.wav")
            segment.export(temp_audio_file, format="wav")

            with sr.AudioFile(temp_audio_file) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data)

            segment_transcriptions.append(text)

            print(f"Segment {i + 1} transcription saved")

        except sr.UnknownValueError:
            print(f"Segment {i + 1}: Google Web Speech API could not understand the audio")
        except sr.RequestError as e:
            print(f"Segment {i + 1}: Could not request results from Google Web Speech API; {e}")

    combined_text = "\n".join(segment_transcriptions)
    combined_output_file = os.path.join(output_folder, "combined_transcription.txt")

    with open(combined_output_file, 'w') as txt_file:
        txt_file.write(combined_text)

    print(f"Combined transcription saved to {combined_output_file}")

@app.route('/', methods=['GET', 'POST'])
def index():
    youtube_link = None
    uploaded_file = None
    translated_summary = None  

    if request.method == 'POST':
        input_method = request.form['input_method']

        if input_method == "youtube_link":
            youtube_link = request.form['youtube_link']
            video_path = extract_video(youtube_link)
        elif input_method == "file_upload":
            uploaded_file = request.files['file']
            video_path = save_uploaded_file(uploaded_file)
        else:
            flash("Invalid input method selected", "danger")
            return redirect(url_for('index'))

        if video_path is not None:
            try:
                audio_output_path = os.path.join('static', 'output.wav')
                extract_audio(video_path, audio_output_path)

                transcription_output_folder = os.path.join('static', 'output_segments')
                transcribe_audio_segments(audio_output_path, transcription_output_folder)

                target_language = request.form['target_language']  

                with open(os.path.join(transcription_output_folder, 'combined_transcription.txt'), 'r', encoding='utf-8') as input_file:
                    input_text = input_file.read()

                input_text = ' '.join(input_text.split())
                translated_summary = summarize_and_translate(input_text, target_language)

                with open('translated_summary.txt', 'w', encoding='utf-8') as translated_file:
                    translated_file.write(translated_summary)

                print("Translated summary saved to translated_summary.txt")

                text_to_audio('translated_summary.txt', 'static/output2.wav', target_language)

                sync_audio_with_video(video_path, 'static/output2.wav', 'static/output_video.mp4')

                flash("Tasks completed successfully!", "success")

            except Exception as e:
                flash(f"Error: {str(e)}", "danger")

    return render_template('index.html', youtube_link=youtube_link, uploaded_file=uploaded_file, translated_summary=translated_summary)

@app.route('/download')
def download():
    return send_file('static/output_video.mp4', as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
