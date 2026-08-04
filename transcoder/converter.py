import os
import shutil
import subprocess

# Resolution presets with recommended bitrates for streaming
RESOLUTIONS = {
    "480p": {"width": 854, "height": 480, "bitrate": "800k", "audio_bitrate": "128k"},
    "720p": {"width": 1280, "height": 720, "bitrate": "1500k", "audio_bitrate": "128k"},
    "1080p": {"width": 1920, "height": 1080, "bitrate": "3000k", "audio_bitrate": "192k"}
}

def check_ffmpeg() -> bool:
    """Check if ffmpeg is installed and available in the system path."""
    return shutil.which("ffmpeg") is not None

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
