"use client";
import { useState } from "react";
import { ArrowRight, Link2, Loader2 } from "lucide-react";

interface Props {
  onSubmit: (url: string) => void;
  loading: boolean;
}

export default function UrlInput({ onSubmit, loading }: Props) {
  const [url, setUrl] = useState("");

  const handle = (e: React.FormEvent) => {
    e.preventDefault();
    if (url.trim()) onSubmit(url.trim());
  };

  const isValid = url.includes("instagram.com") || url.includes("reel");

  return (
    <form onSubmit={handle} className="w-full max-w-2xl mx-auto">
      <div className="relative group">
        <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-purple-500/20 to-pink-500/20 blur-xl opacity-0 group-focus-within:opacity-100 transition-opacity duration-500" />
        <div className="relative flex items-center glass rounded-2xl p-1.5 gap-2">
          <div className="flex items-center gap-2 pl-3 text-[var(--text-muted)] shrink-0">
            <Link2 size={16} />
          </div>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste any Instagram Reel URL..."
            className="flex-1 bg-transparent text-[var(--text)] placeholder:text-[var(--text-muted)] outline-none text-sm py-3 pr-2"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={!url.trim() || loading}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
            style={{
              background: "linear-gradient(135deg, #c084fc, #f472b6)",
              color: "white",
            }}
          >
            {loading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <>
                Analyze Style
                <ArrowRight size={14} />
              </>
            )}
          </button>
        </div>
      </div>
      <p className="text-center text-xs text-[var(--text-muted)] mt-3">
        Works with public Instagram Reels · No login required
      </p>
    </form>
  );
}
