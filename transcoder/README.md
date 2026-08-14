# Vibetube Video Transcoder CLI

A Python Click CLI application to transcode video files into streaming-friendly formats (HLS and MP4) at multiple resolutions (480p, 720p, 1080p).

## Prerequisites

1. **Python 3.8+**
2. **FFmpeg**: The command-line utility `ffmpeg` must be installed and available in your system path.
   - **macOS**: `brew install ffmpeg`
   - **Ubuntu/Debian**: `sudo apt install ffmpeg`
   - **Windows**: Install via scoop/choco or download binaries and add to PATH.

## Installation

1. Navigate to the `transcoder` directory:
   ```bash
   cd transcoder
   ```

2. Create a virtual environment and install the required dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Usage

You can run the transcoder CLI by calling the Python file directly:

```bash
python3 cli.py <input_video_path> [options]
```

### Arguments

* `input_video_path`: Path to the source video file (e.g. `myvideo.mp4`).

### Options

* `-o, --output-dir PATH`: Directory to store the transcoded output. If not provided, a directory named `<input_name>_transcoded` is created in the same folder as the input file.
* `-f, --format [hls|mp4|all]`: Target output format.
  - `hls`: (Default) Generates HLS playlist files (`.m3u8`) and media segments (`.ts`). Also creates a `master.m3u8` playlist referencing the individual resolutions.
  - `mp4`: Generates standard `.mp4` video files.
  - `all`: Generates both HLS and MP4 formats.
* `-r, --resolution [480p|720p|1080p|all]`: Target resolution(s).
  - `480p` (854x480)
  - `720p` (1280x720)
  - `1080p` (1920x1080)
  - `all`: (Default) Transcodes to all three resolutions.

### Examples

1. **Transcode a video to HLS at all resolutions (Default)**:
   ```bash
   python3 cli.py sample.mp4
   ```
   *Creates a `sample_transcoded/` directory next to the video containing `master.m3u8`, along with subdirectories for `480p`, `720p`, and `1080p` HLS playlists.*

2. **Transcode a video to a specific directory in MP4 format at 720p only**:
   ```bash
   python3 cli.py sample.mp4 -f mp4 -r 720p -o /tmp/custom_output/
   ```

3. **Transcode to all formats (HLS + MP4) at all resolutions**:
   ```bash
   python3 cli.py sample.mp4 -f all -r all -o ./transcoded_library/
   ```
