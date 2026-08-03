import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import { Video } from "./VideoCard";

interface VideoPlayerModalProps {
  video: Video;
  onClose: () => void;
}

export const VideoPlayerModal = ({
  video,
  onClose
}: VideoPlayerModalProps) => {
  const videoRef = useRef<HTMLVideoElement>(null);

  // Auto-play the video when the source changes
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.load();
      videoRef.current.play().catch((err) => {
        console.log("Auto-play was prevented by browser policies:", err);
      });
    }
  }, [video]);

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
      <div className="relative w-full max-w-4xl bg-[#0d0d12]/90 border border-white/10 rounded-2xl overflow-hidden shadow-2xl z-10 flex flex-col max-h-[90vh]">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-20 p-2 rounded-full bg-black/60 hover:bg-black/85 text-gray-400 hover:text-white border border-white/5 cursor-pointer transition-colors duration-150"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Video Player & Details Scrollable Area */}
        <div className="flex-1 flex flex-col min-h-0 overflow-y-auto scrollbar-thin">
          {/* Aspect-video Wrapper */}
          <div className="relative aspect-video w-full bg-black">
            <video
              ref={videoRef}
              src={video.videoUrl}
              controls
              autoPlay
              className="w-full h-full object-contain"
            />
          </div>

          {/* Video Metadata */}
          <div className="p-5 md:p-6 flex-1 flex flex-col">
            <h2 className="text-xl md:text-2xl font-bold text-white mb-3">
              {video.title}
            </h2>

            {/* Video Stats */}
            <div className="flex items-center text-xs text-gray-400 mb-6 font-medium gap-2">
              <span>{video.views.toLocaleString()} views</span>
              <span className="w-1 h-1 bg-gray-600 rounded-full"></span>
              <span>Published {video.uploadedAt}</span>
            </div>

            <hr className="border-white/5 mb-6" />

            {/* Channel Info */}
            <div className="flex items-start gap-4">
              <img
                src={video.channelAvatar}
                alt={video.channelName}
                className="w-12 h-12 rounded-full object-cover border border-white/10"
              />
              <div className="min-w-0 flex-1">
                <h4 className="font-bold text-white text-sm mb-1">
                  {video.channelName}
                </h4>
                <p className="text-xs text-gray-400 font-medium">
                  {video.channelName} Creator Network
                </p>
                
                {/* Description */}
                <p className="text-sm text-gray-300 mt-4 leading-relaxed whitespace-pre-line bg-white/5 p-4 rounded-xl border border-white/5">
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
