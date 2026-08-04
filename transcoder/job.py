import os
import sys
import requests
from google.cloud import storage
from converter import transcode_to_hls, generate_master_playlist, extract_thumbnail

def parse_gcs_uri(gcs_uri: str):
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    parts = gcs_uri[5:].split("/", 1)
    bucket_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""
    return bucket_name, blob_name

def upload_folder_to_gcs(local_dir: str, bucket_name: str, gcs_prefix: str):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    
    custom_types = {
        ".m3u8": "application/x-mpegURL",
        ".ts": "video/MP2T",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".mp4": "video/mp4"
    }
    
    for root, _, files in os.walk(local_dir):
        for file in files:
            local_file_path = os.path.join(root, file)
            rel_path = os.path.relpath(local_file_path, local_dir)
            blob_name = os.path.join(gcs_prefix, rel_path)
            
            blob = bucket.blob(blob_name)
            
            ext = os.path.splitext(file)[1].lower()
            content_type = custom_types.get(ext)
            
            if content_type:
                blob.upload_from_filename(local_file_path, content_type=content_type)
            else:
                blob.upload_from_filename(local_file_path)

def main():
    input_uri = os.getenv("INPUT_GCS_URI")
    output_dir_uri = os.getenv("OUTPUT_GCS_DIR")
    video_id = os.getenv("VIDEO_ID")
    backend_url = os.getenv("BACKEND_URL")
    secret_token = os.getenv("TRANSCODER_SECRET_TOKEN")
    
    if not input_uri or not output_dir_uri or not video_id:
        print("Missing required environment variables (INPUT_GCS_URI, OUTPUT_GCS_DIR, VIDEO_ID)")
        sys.exit(1)
        
    print(f"Starting transcode job for Video {video_id}")
    print(f"Input URI: {input_uri}")
    print(f"Output URI: {output_dir_uri}")
    
    # 1. Download raw file from GCS
    try:
        raw_bucket, raw_blob = parse_gcs_uri(input_uri)
        storage_client = storage.Client()
        bucket = storage_client.bucket(raw_bucket)
        blob = bucket.blob(raw_blob)
        
        local_input = "/tmp/input.mp4"
        blob.download_to_filename(local_input)
        print("Raw video downloaded successfully.")
    except Exception as e:
        print(f"Error downloading video: {e}")
        sys.exit(1)
        
    # 2. Run transcoding locally in container
    local_output_dir = "/tmp/transcoded"
    os.makedirs(local_output_dir, exist_ok=True)
    
    resolutions = ["480p", "720p", "1080p"]
    success_resolutions = []
    
    for res in resolutions:
        try:
            print(f"Processing resolution {res}...")
            transcode_to_hls(local_input, local_output_dir, res)
            success_resolutions.append(res)
        except Exception as e:
            print(f"Failed processing resolution {res}: {e}")
            
    if not success_resolutions:
        print("All resolutions failed. Exiting.")
        sys.exit(1)
        
    # Generate master playlist
    try:
        generate_master_playlist(local_output_dir, success_resolutions)
        print("Master playlist generated.")
    except Exception as e:
        print(f"Failed to generate master playlist: {e}")
        sys.exit(1)
        
    # Extract thumbnail (using mid-point calculation built inside converter.py)
    try:
        print("Extracting thumbnail...")
        extract_thumbnail(local_input, local_output_dir)
        print("Thumbnail extracted.")
    except Exception as e:
        print(f"Failed to extract thumbnail: {e}")
        sys.exit(1)
        
    # 3. Upload outputs back to GCS
    try:
        out_bucket, out_prefix = parse_gcs_uri(output_dir_uri)
        upload_folder_to_gcs(local_output_dir, out_bucket, out_prefix)
        print("Transcoded files uploaded to GCS successfully.")
    except Exception as e:
        print(f"Failed to upload output to GCS: {e}")
        sys.exit(1)
        
    # 4. Notify backend
    if backend_url:
        callback_url = f"{backend_url.rstrip('/')}/api/videos/{video_id}/transcode-complete"
        # Standard GCS URL syntax
        video_url = f"https://storage.googleapis.com/{out_bucket}/{out_prefix.rstrip('/')}/master.m3u8"
        thumbnail_url = f"https://storage.googleapis.com/{out_bucket}/{out_prefix.rstrip('/')}/thumbnail.jpg"
        
        headers = {}
        if secret_token:
            headers["X-Transcoder-Token"] = secret_token
            
        payload = {
            "videoUrl": video_url,
            "thumbnailUrl": thumbnail_url
        }
        
        try:
            print(f"Sending callback to backend at {callback_url}")
            res = requests.post(callback_url, json=payload, headers=headers)
            res.raise_for_status()
            print("Backend callback successful.")
        except Exception as e:
            print(f"Failed to notify backend: {e}")
            sys.exit(1)
            
    print("Transcoding job completed successfully!")

if __name__ == "__main__":
    main()
