from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import re
import sys
import time
import uuid
import threading
import subprocess
import webbrowser
import urllib.request
import urllib.error
import traceback

app = Flask(__name__)

# ---------------- SETTINGS ----------------

DOWNLOAD_FOLDER = "downloads"

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

download_progress = {}

# If ffmpeg is not on your system PATH, set the full path to its folder here.
# Example: r"C:\ffmpeg\bin"
FFMPEG_LOCATION = None  # e.g. r"C:\ffmpeg\bin"

# Full path to cloudflared.exe (matches what start_server.bat used to launch directly)
CLOUDFLARED_PATH = r"C:\cloudflared\cloudflared.exe"

# ---------------- CLOUDFLARE TUNNEL MANAGEMENT ----------------
# app.py now owns the cloudflared process (instead of the .bat file spawning
# it in a separate window). This lets the page ask "what's my public URL
# right now" and lets the /restart button relaunch the tunnel and pick up
# the new randomly-generated trycloudflare.com link.
#
# IMPORTANT LIMITATION: quick tunnels (no Cloudflare account/named tunnel)
# get a brand new random subdomain every time cloudflared starts. A browser
# tab that is CURRENTLY viewing the site through the old tunnel URL has no
# way to learn the new URL once that tunnel is killed — the connection it
# would use to ask "what's the new link?" is the same one being torn down.
# Auto-redirect only works reliably for a tab open on http://localhost:5000.

cloudflared_process = None
tunnel_state = {"url": None, "version": 0}
tunnel_lock = threading.Lock()
last_opened_url = None

TUNNEL_URL_PATTERN = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


def wait_for_tunnel_then_open(url, max_wait_seconds=30):
    """
    cloudflared prints the URL before the subdomain is actually resolvable
    (DNS + edge registration takes a few extra seconds). Opening the browser
    immediately races that and shows "can't reach this page" / NXDOMAIN.
    So poll the URL until we get ANY response - even an HTTP error counts,
    since that means DNS resolved and the tunnel accepted the connection -
    then open the browser.
    """
    deadline = time.time() + max_wait_seconds

    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=3)
            webbrowser.open(url)
            return
        except urllib.error.HTTPError:
            webbrowser.open(url)  # tunnel is reachable, just returned a non-200 - fine
            return
        except Exception:
            time.sleep(1)  # DNS not ready / connection refused yet - retry

    print(
        f"[tunnel] WARNING: {url} did not become reachable within "
        f"{max_wait_seconds}s. Opening it anyway, but if it still 404s/fails "
        f"to load, check: (1) cloudflared is still running (look above for "
        f"crash/error lines), (2) your firewall/antivirus isn't blocking it, "
        f"(3) your internet connection is up."
    )
    webbrowser.open(url)


def start_cloudflared():
    """Launch cloudflared and watch its output for the public URL."""
    global cloudflared_process

    with tunnel_lock:
        tunnel_state["url"] = None

    try:
        cloudflared_process = subprocess.Popen(
            [CLOUDFLARED_PATH, "tunnel", "--url", "http://localhost:5000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        print(
            f"[tunnel] Could not find cloudflared at {CLOUDFLARED_PATH}. "
            f"Update CLOUDFLARED_PATH at the top of app.py."
        )
        return

    def watch_output():
        global last_opened_url

        for line in cloudflared_process.stdout:
            print(f"[cloudflared] {line}", end="")
            match = TUNNEL_URL_PATTERN.search(line)
            if match:
                url = match.group(0)

                with tunnel_lock:
                    tunnel_state["url"] = url
                    tunnel_state["version"] += 1

                print(f"[tunnel] Public URL: {url}")

                if url != last_opened_url:
                    last_opened_url = url
                    threading.Thread(
                        target=wait_for_tunnel_then_open,
                        args=(url,),
                        daemon=True
                    ).start()

    threading.Thread(target=watch_output, daemon=True).start()

# ---------------- HOME PAGE ----------------

@app.route("/")
def home():
    return render_template("index.html")

# ---------------- DOWNLOAD API ----------------

@app.route("/download", methods=["POST"])
def download():

    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({
            "success": False,
            "error": "No URL provided"
        })

    download_id = str(uuid.uuid4())

    download_progress[download_id] = {
        "progress": 0,
        "status": "Starting...",
        "filename": "",
        "title": ""
    }

    thread = threading.Thread(
        target=download_audio,
        args=(url, download_id)
    )

    thread.start()

    return jsonify({
        "success": True,
        "download_id": download_id
    })

# ---------------- DOWNLOAD FUNCTION ----------------

def download_audio(url, download_id):

    def progress_hook(d):

        if d['status'] == 'downloading':

            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)

            if total:

                percent = int(downloaded / total * 100)

                download_progress[download_id]["progress"] = percent

                download_progress[download_id]["status"] = (
                    f"Downloading... {percent}%"
                )

        elif d['status'] == 'finished':

            download_progress[download_id]["progress"] = 100

            download_progress[download_id]["status"] = (
                "Converting to MP3..."
            )

    try:

        # ---------------- GET TITLE FIRST ----------------

        with yt_dlp.YoutubeDL({
            'quiet': True,
            'extractor_args': {
                'youtube': {'player_client': ['android', 'web', 'tv']}
            },
        }) as ydl:

            info = ydl.extract_info(url, download=False)

            title = info.get("title", "Unknown Song")

            download_progress[download_id]["title"] = title

        # ---------------- DOWNLOAD ----------------

        output_template = os.path.join(
            DOWNLOAD_FOLDER,
            '%(title)s [%(id)s].%(ext)s'
        )

        ydl_opts = {

            'format': 'bestaudio/best',

            'outtmpl': output_template,

            'progress_hooks': [progress_hook],

            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],

            'quiet': False,
            'no_warnings': False,

            'geo_bypass': True,

            'ignoreerrors': False,

            # YouTube periodically blocks the default web client with 403s.
            # Falling back through android -> web -> tv clients works around
            # most of these without needing cookies. If this stops helping,
            # the fix is almost always: pip install -U yt-dlp
            'extractor_args': {
                'youtube': {'player_client': ['android', 'web', 'tv']}
            },
        }

        if FFMPEG_LOCATION:
            ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(url, download=True)

            if info is None:
                raise RuntimeError("yt-dlp returned no info — download failed.")

            original_file = ydl.prepare_filename(info)

            mp3_file = (
                os.path.splitext(original_file)[0]
                + ".mp3"
            )

            if not os.path.exists(mp3_file):
                raise RuntimeError(
                    f"MP3 file was not created at expected path: {mp3_file}. "
                    f"This usually means ffmpeg is not installed or not on PATH. "
                    f"Set FFMPEG_LOCATION at the top of this file to your ffmpeg "
                    f"bin folder if it's installed but not on PATH."
                )

            download_progress[download_id]["filename"] = mp3_file

        download_progress[download_id]["status"] = "Completed"

    except Exception as e:

        traceback.print_exc()

        download_progress[download_id]["status"] = (
            f"Error: {str(e)}"
        )

# ---------------- PROGRESS API ----------------

@app.route("/progress/<download_id>")
def progress(download_id):

    return jsonify(
        download_progress.get(download_id, {})
    )

# ---------------- FILE DOWNLOAD ----------------

@app.route("/file/<download_id>")
def get_file(download_id):

    data = download_progress.get(download_id)

    if not data:
        return "Invalid download ID"

    file_path = data.get("filename")

    if not file_path:
        return "File not ready"

    if not os.path.exists(file_path):
        return "File not found"

    return send_file(
        file_path,
        mimetype="audio/mpeg",
        as_attachment=True,
        download_name=os.path.basename(file_path)
    )

# ---------------- TUNNEL STATUS API ----------------

@app.route("/tunnel_status")
def tunnel_status():
    with tunnel_lock:
        return jsonify(dict(tunnel_state))

# ---------------- RESTART API ----------------

@app.route("/restart", methods=["POST"])
def restart():
    """
    Restarts cloudflared (new public URL) and then the Flask process itself.
    The Flask process exits and relies on start_server.bat's restart loop to
    relaunch python app.py. Any in-progress downloads will be interrupted.
    """

    def do_restart():
        time.sleep(0.5)  # let this response actually reach the client first

        global cloudflared_process
        if cloudflared_process:
            try:
                cloudflared_process.terminate()
            except Exception:
                pass

        os._exit(0)

    threading.Thread(target=do_restart).start()

    return jsonify({"success": True})

# ---------------- RUN SERVER ----------------

if __name__ == "__main__":

    start_cloudflared()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False  # we manage our own restart via /restart + the .bat loop
    )