from flask import Flask, request, render_template, redirect, url_for, session
from werkzeug.utils import secure_filename
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from PIL import Image
import os
from threading import Thread

# === Flask Setup ===
app = Flask(__name__)
app.secret_key = 'your-secret-key'  # Needed to store PIN in session

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'mp4', 'mov', 'avi'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# === Google Drive Setup ===
SERVICE_ACCOUNT_FILE = 'service_account.json'
SCOPES = ['https://www.googleapis.com/auth/drive.file']

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
drive_service = build('drive', 'v3', credentials=creds)
FOLDER_ID = '1Eum2pFA2Q2785D6tUZ2WJH0gHvy7YtLy'  # Replace with your own folder ID

PIN_CODE = '2025wedding'  # Customize your PIN

# === Helpers ===
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_image(filename):
    return filename.lower().endswith(('.jpg', '.jpeg', '.png'))

def is_video(filename):
    return filename.lower().endswith(('.mp4', '.mov', '.avi'))

def compress_image(input_path, output_path, quality=85):
    image = Image.open(input_path)
    image = image.convert("RGB")
    image.save(output_path, "JPEG", optimize=True, quality=quality)

def upload_to_drive(local_path, filename, folder_id=None):
    file_metadata = {'name': filename}
    if folder_id:
        file_metadata['parents'] = [folder_id]
    media = MediaFileUpload(local_path, resumable=False)
    uploaded_file = drive_service.files().create(
        body=file_metadata, media_body=media, fields='id'
    ).execute()
    return uploaded_file.get('id')

def background_upload_and_cleanup(files, folder_id):
    for local_path, filename in files:
        try:
            upload_to_drive(local_path, filename, folder_id)
            print(f"[UPLOAD] {filename} uploaded.")
        except Exception as e:
            print(f"[ERROR] Failed to upload {filename}: {e}")
            continue
        try:
            os.remove(local_path)
            print(f"[CLEANUP] Deleted {filename}")
        except Exception as e:
            print(f"[WARN] Could not delete {filename}: {e}")

# === Routes ===
@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    if request.method == 'POST':
        pin = request.form.get('pin')
        if pin == PIN_CODE:
            session['authenticated'] = True
            return redirect(url_for('upload'))
        else:
            error = "Incorrect PIN. Please try again."
    return render_template('pin.html', error=error)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if not session.get('authenticated'):
        return redirect(url_for('index'))

    if request.method == 'POST':
        files = request.files.getlist('file')
        saved_files = []

        if not files:
            return "No files uploaded"

        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                local_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(local_path)

                # Only compress if it's an image and larger than 2MB
                if is_image(filename) and os.path.getsize(local_path) > 2 * 1024 * 1024:
                    compressed_path = os.path.join(UPLOAD_FOLDER, f"compressed_{filename}")
                    compress_image(local_path, compressed_path)
                    os.remove(local_path)
                    os.rename(compressed_path, local_path)

                saved_files.append((local_path, filename))

        # Start background upload and cleanup
        Thread(target=background_upload_and_cleanup, args=(saved_files, FOLDER_ID)).start()

        return redirect(url_for('thank_you'))

    return render_template('upload.html')

@app.route('/thank-you')
def thank_you():
    return render_template('thank_you.html')

# === Run ===
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
