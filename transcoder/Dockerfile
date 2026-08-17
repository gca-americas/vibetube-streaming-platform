FROM python:3.11-slim

# Install FFmpeg.
#
# --no-install-recommends matters more here than usual: this job is a Cloud Run
# *job*, so every execution is a cold start and pays the full image pull before
# Python runs at all. Measured on a 10s clip, the actual work (download, encode
# both renditions, thumbnail, upload) is ~8s while the execution takes ~180s --
# the rest is pulling the image. Debian's ffmpeg recommends pull in a large
# desktop dependency tree that nothing here uses; dropping them takes the image
# from 1.17GB to 864MB.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Python block-buffers stdout when it is not a TTY, so a whole run's output
# flushed at process exit and every log line landed on the same timestamp --
# which made it impossible to tell how long any phase actually took.
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "job.py"]
