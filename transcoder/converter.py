import json
import os
import shutil
import subprocess

# Resolution presets with recommended bitrates for streaming.
# Ordered smallest first: select_resolutions relies on that to pick a fallback.
RESOLUTIONS = {
    "480p": {"width": 854, "height": 480, "bitrate": "800k", "audio_bitrate": "128k"},
    "720p": {"width": 1280, "height": 720, "bitrate": "1500k", "audio_bitrate": "128k"},
    "1080p": {"width": 1920, "height": 1080, "bitrate": "3000k", "audio_bitrate": "192k"}
}

# x264 speed/size trade. The default is "medium"; "fast" encodes roughly twice
# as quickly for about 5% larger segments, which at these bitrates is not
# visible. Encoding is what the job spends nearly all its wall time on, so this
# is the single biggest lever after not upscaling.
X264_PRESET = os.getenv("X264_PRESET", "fast")


def check_ffmpeg() -> bool:
    """Check if ffmpeg is installed and available in the system path."""
    return shutil.which("ffmpeg") is not None


def probe_height(input_path: str) -> int:
    """Height of the source video in pixels, or 0 if it cannot be determined."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height", "-of", "json", input_path],
            check=True, capture_output=True, text=True,
        ).stdout
        streams = json.loads(out).get("streams") or []
        return int(streams[0].get("height") or 0)
    except Exception:
        # Unknown height means "encode the full ladder", which is the old
        # behaviour -- wasteful but never worse than failing outright.
        return 0


def select_resolutions(input_path: str) -> list:
    """Ladder entries worth encoding for this source, smallest first.

    Renditions taller than the source are dropped. Upscaling cannot add detail,
    so a 1080p rendition of a 720p master is bytes and CPU spent to deliver the
    same picture -- and it is the most expensive encode in the ladder, since
    cost scales with pixel count. For a 720p source that alone is ~61% of the
    total work.

    Falls back to the smallest entry when the source is shorter than every
    rung, so a tiny input still produces something playable rather than an
    empty ladder and a failed job.
    """
    height = probe_height(input_path)
    if not height:
        return list(RESOLUTIONS)

    keep = [key for key, res in RESOLUTIONS.items() if res["height"] <= height]
    return keep or [next(iter(RESOLUTIONS))]

def transcode_to_mp4(input_path: str, output_dir: str, resolution_key: str) -> str:
    """
    Transcodes the input video to a single MP4 file at the specified resolution.
    Returns the path to the generated MP4 file.
    """
    if resolution_key not in RESOLUTIONS:
        raise ValueError(f"Unknown resolution: {resolution_key}")

    os.makedirs(output_dir, exist_ok=True)
    res = RESOLUTIONS[resolution_key]
    
    # Get base filename without extension
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_filename = f"{base_name}_{resolution_key}.mp4"
    output_path = os.path.join(output_dir, output_filename)
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"scale=-2:{res['height']}",
        "-c:v", "libx264",
        "-preset", X264_PRESET,
        "-b:v", res["bitrate"],
        "-c:a", "aac",
        "-b:a", res["audio_bitrate"],
        "-movflags", "+faststart",  # Move metadata to start for faster web playback
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg failed with exit code {e.returncode}.\nError details:\n{e.stderr}")

def transcode_to_hls(input_path: str, output_dir: str, resolution_key: str) -> str:
    """
    Transcodes the input video to HLS (m3u8 playlist + ts segments) at the specified resolution.
    The output is stored in a subdirectory named after the resolution inside output_dir.
    Returns the path to the playlist.m3u8 file.
    """
    if resolution_key not in RESOLUTIONS:
        raise ValueError(f"Unknown resolution: {resolution_key}")

    res_dir = os.path.join(output_dir, resolution_key)
    os.makedirs(res_dir, exist_ok=True)
    
    res = RESOLUTIONS[resolution_key]
    playlist_path = os.path.join(res_dir, "playlist.m3u8")
    segment_pattern = os.path.join(res_dir, "segment_%03d.ts")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"scale=-2:{res['height']}",
        "-c:v", "libx264",
        "-preset", X264_PRESET,
        "-b:v", res["bitrate"],
        "-c:a", "aac",
        "-b:a", res["audio_bitrate"],
        "-hls_time", "10",
        "-hls_playlist_type", "vod",
        "-hls_list_size", "0",
        "-hls_segment_filename", segment_pattern,
        playlist_path
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return playlist_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg failed with exit code {e.returncode}.\nError details:\n{e.stderr}")

def generate_master_playlist(output_dir: str, processed_resolutions: list[str]) -> str:
    """
    Generates a master.m3u8 HLS playlist that references the individual resolution playlists.
    Returns the path to the master playlist.
    """
    master_path = os.path.join(output_dir, "master.m3u8")
    
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3"
    ]
    
    for res_key in sorted(processed_resolutions, key=lambda r: RESOLUTIONS[r]["height"]):
        res = RESOLUTIONS[res_key]
        # Standard bandwidth mapping (combines target video bitrate and audio bitrate in bits per second)
        # e.g., "800k" video + "128k" audio = 928,000 bps
        v_bit = int(res["bitrate"].replace("k", "")) * 1000
        a_bit = int(res["audio_bitrate"].replace("k", "")) * 1000
        bandwidth = v_bit + a_bit
        
        resolution_str = f"{res['width']}x{res['height']}"
        
        lines.append(f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={resolution_str}')
        # Path must be relative to the master playlist location
        lines.append(f"{res_key}/playlist.m3u8")
        
    with open(master_path, "w") as f:
        f.write("\n".join(lines) + "\n")
        
    return master_path

def get_video_duration(input_path: str) -> float:
    """Returns the duration of the video in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path
    ]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except Exception:
        # Fallback to 0 if ffprobe fails or is not present
        return 0.0

def extract_thumbnail(input_path: str, output_dir: str) -> str:
    """
    Extracts a frame from the input video as a thumbnail image.
    Uses the calculated middle of the video.
    Returns the path to the generated thumbnail JPEG.
    """
    os.makedirs(output_dir, exist_ok=True)
    thumbnail_path = os.path.join(output_dir, "thumbnail.jpg")
    
    duration = get_video_duration(input_path)
    # Use midpoint if duration is valid; fallback to 1.0 second
    timestamp = str(duration / 2.0) if duration > 0 else "1.0"
    
    cmd = [
        "ffmpeg", "-y",
        "-ss", timestamp,
        "-i", input_path,
        "-vframes", "1",
        "-q:v", "2",
        thumbnail_path
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return thumbnail_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg thumbnail extraction failed with exit code {e.returncode}.\nError details:\n{e.stderr}")
