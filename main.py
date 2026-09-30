from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import yt_dlp
import os
import tempfile
import uuid
import re

app = FastAPI(title="MediaDown In-House Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = os.path.join(tempfile.gettempdir(), "mediadown_files")
os.makedirs(TEMP_DIR, exist_ok=True)

def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    return cleaned.strip()[:80] or "MediaDown_Media"

@app.get("/")
def home():
    return {
        "service": "MediaDown Dedicated Conversion Engine",
        "status": "online",
        "version": "1.0.0"
    }

@app.get("/api/info")
def get_info(url: str = Query(..., description="Target video URL")):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extractor_args': {'youtube': {'player_client': ['visionos', 'android_vr', 'tv_embedded', 'ios']}}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", "Video"),
                "uploader": info.get("uploader", ""),
                "thumbnail": info.get("thumbnail", ""),
                "duration": info.get("duration", 0),
                "extractor": info.get("extractor", ""),
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo extraer información: {str(e)}")

@app.get("/api/download")
def download_media(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="Target video URL"),
    format: str = Query("mp4", regex="^(mp4|mp3)$"),
    quality: str = Query("1080")
):
    req_id = str(uuid.uuid4())[:8]
    output_template = os.path.join(TEMP_DIR, f"{req_id}_%(title)s.%(ext)s")

    if format == "mp3":
        ydl_opts = {
            'format': 'ba/b',
            'outtmpl': output_template,
            'extractor_args': {'youtube': {'player_client': ['visionos', 'android_vr', 'tv_embedded', 'ios']}},
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality if quality in ["128", "192", "256", "320"] else "320",
            }],
            'quiet': True,
            'no_warnings': True,
        }
    else:
        # MP4 video
        ydl_opts = {
            'format': f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best',
            'outtmpl': output_template,
            'extractor_args': {'youtube': {'player_client': ['visionos', 'android_vr', 'tv_embedded', 'ios']}},
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = sanitize_filename(info.get("title", "MediaDown_Download"))

            # Find created file in temp dir
            ext = "mp3" if format == "mp3" else "mp4"
            expected_prefix = f"{req_id}_"
            target_path = None

            for f in os.listdir(TEMP_DIR):
                if f.startswith(expected_prefix) and f.endswith(f".{ext}"):
                    target_path = os.path.join(TEMP_DIR, f)
                    break

            if not target_path or not os.path.exists(target_path):
                raise HTTPException(status_code=500, detail="Error al compilar el archivo multimedia.")

            def cleanup():
                try:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                except Exception:
                    pass

            background_tasks.add_task(cleanup)

            return FileResponse(
                path=target_path,
                filename=f"{title}.{ext}",
                media_type="audio/mpeg" if format == "mp3" else "video/mp4"
            )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en la extracción: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
