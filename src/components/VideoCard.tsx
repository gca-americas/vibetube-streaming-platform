import { Play } from "lucide-react";

export interface Video {
  id: string;
  title: string;
  description: string;
  thumbnailUrl: string;
  videoUrl: string;
  duration: string;
  views: number;
  uploadedAt: string;
  channelName: string;
  channelAvatar: string;
}

interface VideoCardProps {
  video: Video;
  onClick?: (video: Video) => void;
}

const formatViews = (views: number): string => {
  if (views >= 1000000) {
    return `${(views / 1000000).toFixed(1).replace(/\.0$/, "")}M views`;
  }
  if (views >= 1000) {
    return `${(views / 1000).toFixed(0)}K views`;
  }
  return `${views} views`;
};

export const VideoCard = ({ video, onClick }: VideoCardProps) => {
  return (
    <div
      onClick={() => onClick?.(video)}
      className="group relative flex flex-col bg-card hover:bg-card-hover rounded-2xl overflow-hidden border border-white/5 shadow-lg hover:shadow-2xl hover:-translate-y-1.5 transition-all duration-300 cursor-pointer"
    >
      {/* Thumbnail section */}
      <div className="relative aspect-video w-full overflow-hidden bg-black/40">
        <img
          src={video.thumbnailUrl}
          alt={video.title}
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          loading="lazy"
        />
        
        {/* Hover overlay with Play button */}
        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity duration-300">
          <div className="p-3.5 bg-vibe-red rounded-full text-white shadow-lg shadow-vibe-red/30 transform scale-75 group-hover:scale-100 transition-transform duration-300">
            <Play className="w-6 h-6 fill-current" />
          </div>
        </div>

        {/* Video Duration Badge */}
        <span className="absolute bottom-3 right-3 px-2 py-0.5 bg-black/75 backdrop-blur-sm text-xs font-semibold text-white tracking-wide rounded-md border border-white/5">
          {video.duration}
        </span>
      </div>

      {/* Info Section */}
      <div className="flex gap-3 p-4 flex-1">
        {/* Channel Avatar */}
        <div className="flex-shrink-0">
          <img
            src={video.channelAvatar}
            alt={video.channelName}
            className="w-10 h-10 rounded-full object-cover border border-white/10"
          />
        </div>

        {/* Title / Channel / Stats */}
        <div className="flex flex-col min-w-0 flex-1">
          <h3 className="text-sm font-semibold leading-snug text-white line-clamp-2 group-hover:text-vibe-red transition-colors duration-200" title={video.title}>
            {video.title}
          </h3>
          
          <p className="text-xs text-gray-400 mt-1.5 font-medium truncate">
            {video.channelName}
          </p>
          
          <div className="flex items-center text-xs text-gray-500 mt-1 font-medium gap-1.5">
            <span>{formatViews(video.views)}</span>
            <span className="w-1 h-1 bg-gray-600 rounded-full"></span>
            <span>{video.uploadedAt}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
