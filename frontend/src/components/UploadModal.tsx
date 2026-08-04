import React, { useState } from "react";
import { X } from "lucide-react";

interface UploadModalProps {
  onClose: () => void;
  onUploadSuccess: () => void;
}

export const UploadModal = ({ onClose, onUploadSuccess }: UploadModalProps) => {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [duration, setDuration] = useState("0:52");
  const [channelName, setChannelName] = useState("Me");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setVideoFile(e.target.files[0]);
      // Auto-populate title if empty
      if (!title) {
        const baseName = e.target.files[0].name.replace(/\.[^/.]+$/, ""); // strip extension
        setTitle(baseName);
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title || !videoFile) return;

    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append("title", title);
    formData.append("description", description);
    formData.append("duration", duration);
    formData.append("channelName", channelName);
    formData.append("videoFile", videoFile);

    try {
      const res = await fetch("/api/videos", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Failed to upload video file");
      }

      onUploadSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-6 bg-black/80 backdrop-blur-md transition-opacity duration-300 animate-fade-in">
      {/* Click-away overlay */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* Form Container */}
      <div className="relative w-full max-w-lg bg-[#0d0d12]/95 border border-hairline rounded-2xl p-6 shadow-2xl z-10 text-fg">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-fg-muted hover:text-fg cursor-pointer p-1.5 rounded-full hover:bg-overlay transition-colors"
          type="button"
          aria-label="Close upload modal"
        >
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-xl font-bold mb-4 font-display bg-gradient-to-r from-vibe-red to-vibe-purple bg-clip-text text-transparent">
          Publish a New Stream
        </h2>

        {error && (
          <p className="text-xs text-red-500 mb-4 bg-red-500/10 p-3 rounded-lg border border-red-500/20">
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] uppercase font-bold tracking-wider text-fg-muted">Video File *</label>
            <input
              required
              type="file"
              accept="video/*"
              onChange={handleFileChange}
              className="bg-input border border-hairline rounded-xl px-4 py-2.5 text-sm text-fg focus:outline-none focus:border-vibe-purple transition-colors cursor-pointer"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] uppercase font-bold tracking-wider text-fg-muted">Title *</label>
            <input
              required
              placeholder="e.g. Synthwave Chill Drive"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="bg-input border border-hairline rounded-xl px-4 py-2.5 text-sm text-fg focus:outline-none focus:border-vibe-purple transition-colors"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] uppercase font-bold tracking-wider text-fg-muted">Description</label>
            <textarea
              placeholder="Tell your viewers about the vibe..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="bg-input border border-hairline rounded-xl px-4 py-2.5 text-sm text-fg focus:outline-none focus:border-vibe-purple h-24 resize-none transition-colors"
            />
          </div>

          <div className="flex gap-4">
            <div className="flex-1 flex flex-col gap-1.5">
              <label className="text-[10px] uppercase font-bold tracking-wider text-fg-muted">Duration</label>
              <input
                placeholder="e.g. 15:40"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                className="bg-input border border-hairline rounded-xl px-4 py-2.5 text-sm text-fg focus:outline-none focus:border-vibe-purple transition-colors"
              />
            </div>
            <div className="flex-1 flex flex-col gap-1.5">
              <label className="text-[10px] uppercase font-bold tracking-wider text-fg-muted">Creator Name</label>
              <input
                placeholder="e.g. VibeCreator"
                value={channelName}
                onChange={(e) => setChannelName(e.target.value)}
                className="bg-input border border-hairline rounded-xl px-4 py-2.5 text-sm text-fg focus:outline-none focus:border-vibe-purple transition-colors"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-3 rounded-xl bg-gradient-to-r from-vibe-red to-vibe-purple hover:scale-[1.01] text-white text-sm font-bold shadow-lg shadow-vibe-red/20 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Publishing Vibe..." : "Publish Vibe"}
          </button>
        </form>
      </div>
    </div>
  );
};
