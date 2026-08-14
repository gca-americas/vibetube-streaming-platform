import { X, AlertTriangle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Video, initialsOf } from "./VideoCard";
import { ShareButtons } from "./ShareButtons";
import { formatUploadTime } from "../lib/api";
import { videoShareUrl } from "../lib/router";

interface VideoPlayerModalProps {
  video: Video;
  /** Showroom the video belongs to, needed to build its shareable link. */
  eventCode: string;
  onClose: () => void;
}

export const VideoPlayerModal = ({
  video,
  eventCode,
  onClose
}: VideoPlayerModalProps) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playbackFailed, setPlaybackFailed] = useState(false);

  // Keyed on the source rather than the whole video object: the object
  // identity changes on every poll-driven refresh, which would otherwise
  // re-run load() and restart playback for no reason.
  useEffect(() => {
    const videoElement = videoRef.current;
    if (!videoElement) return;

    setPlaybackFailed(false);
    let hlsInstance: any = null;

    // An undecodable file otherwise leaves a silent black rectangle with no
    // indication anything went wrong.
    const onError = () => setPlaybackFailed(true);
    videoElement.addEventListener("error", onError);

    if (video.videoUrl.endsWith(".m3u8")) {
      const Hls = (window as any).Hls;
      if (Hls && Hls.isSupported()) {
        hlsInstance = new Hls();
        hlsInstance.loadSource(video.videoUrl);
        hlsInstance.attachMedia(videoElement);
        // hls.js swallows media errors internally, so the element's own error
        // event never fires for a broken stream.
        hlsInstance.on(Hls.Events.ERROR, (_e: any, data: any) => {
          if (data?.fatal) setPlaybackFailed(true);
        });
        hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {
          videoElement.play().catch((err) => {
            console.log("Auto-play was prevented by browser policies:", err);
          });
        });
      } else if (videoElement.canPlayType("application/vnd.apple.mpegurl")) {
        // Native support (e.g. Safari)
        videoElement.src = video.videoUrl;
        videoElement.load();
        videoElement.play().catch((err) => {
          console.log("Auto-play was prevented by browser policies:", err);
        });
      }
    } else {
      // Standard video format (e.g., MP4)
      videoElement.src = video.videoUrl;
      videoElement.load();
      videoElement.play().catch((err) => {
        console.log("Auto-play was prevented by browser policies:", err);
      });
    }

    return () => {
      videoElement.removeEventListener("error", onError);
      if (hlsInstance) {
        hlsInstance.destroy();
      }
    };
  }, [video.videoUrl]);

  // Lock body scroll when modal is open
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "unset";
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-6 bg-black/80 backdrop-blur-md transition-opacity duration-300 animate-fade-in">
      {/* Click-away overlay */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* Modal Container */}
      <div className="relative w-full max-w-4xl bg-[#0d0d12]/90 border border-hairline rounded-2xl overflow-hidden shadow-2xl z-10 flex flex-col max-h-[90vh]">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-20 p-2 rounded-full bg-stage/60 hover:bg-stage/85 text-fg-muted hover:text-fg border border-hairline cursor-pointer transition-colors duration-150"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Video Player & Details Scrollable Area */}
        <div className="flex-1 flex flex-col min-h-0 overflow-y-auto scrollbar-thin">
          {/* Aspect-video Wrapper */}
          <div className="relative aspect-video w-full bg-black">
            <video
              ref={videoRef}
              controls
              autoPlay
              className="absolute inset-0 w-full h-full object-contain"
            />

            {playbackFailed && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/85 px-6 text-center">
                <AlertTriangle className="w-9 h-9 text-amber-400" />
                <p className="text-sm font-bold text-white">
                  This video can't be played
                </p>
                <p className="text-xs text-white/60 max-w-sm">
                  The file is missing or is not in a format your browser can
                  decode. Uploading it again usually fixes it.
                </p>
              </div>
            )}
          </div>

          {/* Video Metadata */}
          <div className="p-5 md:p-6 flex-1 flex flex-col">
            <h2 className="text-xl md:text-2xl font-bold text-fg mb-3">
              {video.title}
            </h2>

            <span className="text-xs text-fg-muted font-medium">
              Uploaded {formatUploadTime(video.createdAt)}
            </span>

            {/* Its own row: sharing competed with the timestamp for attention
                when both sat on one line. */}
            <div className="mt-4 mb-6 p-3 rounded-2xl bg-overlay border border-hairline">
              <ShareButtons
                url={videoShareUrl(eventCode, video.id)}
                title={video.title}
                authorName={video.channelName}
                seed={video.id}
              />
            </div>

            <hr className="border-hairline mb-6" />

            {/* Channel Info */}
            <div className="flex items-start gap-4">
              {video.channelAvatar && video.channelAvatar !== "?" ? (
                <img
                  src={video.channelAvatar}
                  alt={video.channelName}
                  className="w-12 h-12 rounded-full object-cover border border-hairline"
                />
              ) : (
                <div
                  className="w-12 h-12 rounded-full border border-hairline flex items-center justify-center bg-gradient-to-br from-vibe-red/25 to-vibe-purple/25 text-fg text-sm font-bold shrink-0 select-none"
                  title={video.channelName}
                >
                  {initialsOf(video.channelName)}
                </div>
              )}
              <div className="min-w-0 flex-1">
                <h4 className="font-bold text-fg text-sm mb-1">
                  {video.channelName}
                </h4>
                {video.projectId && (
                  <p className="text-xs text-fg-muted font-medium font-mono">
                    Project {video.projectId}
                  </p>
                )}
                
                {/* Description */}
                <p className="text-sm text-fg/90 mt-4 leading-relaxed whitespace-pre-line bg-overlay p-4 rounded-xl border border-hairline">
                  {video.description}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
