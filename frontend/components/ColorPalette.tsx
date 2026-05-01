"use client";

interface Props {
  palette: string[];
  gradeStyle: string;
  warmth: number;
  saturation: number;
  brightness: number;
  shadowCast: string;
  highlightCast: string;
}

const GRADE_LABELS: Record<string, string> = {
  vibrant_warm: "Vibrant & Warm",
  vibrant_cool: "Vibrant & Cool",
  desaturated_moody: "Desaturated Moody",
  faded_film: "Faded Film",
  bright_airy: "Bright & Airy",
  dark_moody: "Dark & Moody",
  high_contrast_punchy: "High Contrast",
  golden_warm: "Golden Hour",
  cool_teal: "Cool Teal",
  natural_balanced: "Natural Balanced",
};

export default function ColorPalette({ palette, gradeStyle, warmth, saturation, brightness, shadowCast, highlightCast }: Props) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Color Story</h3>
        <span
          className="text-xs px-2 py-0.5 rounded-full"
          style={{ background: "rgba(192,132,252,0.15)", color: "#c084fc" }}
        >
          {GRADE_LABELS[gradeStyle] || gradeStyle}
        </span>
      </div>

      {/* Palette swatches */}
      {palette.length > 0 && (
        <div className="flex gap-1.5 h-10">
          {palette.map((hex, i) => (
            <div
              key={i}
              className="flex-1 rounded-lg transition-transform hover:scale-105 cursor-default"
              style={{ background: hex }}
              title={hex}
            />
          ))}
        </div>
      )}

      {/* Meters */}
      <div className="space-y-2.5">
        {[
          { label: "Warmth", value: (warmth + 0.2) / 0.4, left: "Cool", right: "Warm" },
          { label: "Saturation", value: saturation, left: "Muted", right: "Vivid" },
          { label: "Brightness", value: brightness, left: "Dark", right: "Bright" },
        ].map(({ label, value, left, right }) => (
          <div key={label}>
            <div className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
              <span>{label}</span>
              <span className="flex gap-3">
                <span>{left}</span>
                <span>|</span>
                <span>{right}</span>
              </span>
            </div>
            <div className="relative h-1.5 bg-[var(--surface-2)] rounded-full">
              <div
                className="absolute top-0 h-full w-1.5 rounded-full -translate-x-1/2"
                style={{
                  left: `${Math.min(100, Math.max(0, value * 100))}%`,
                  background: "linear-gradient(135deg, #c084fc, #f472b6)",
                }}
              />
              <div
                className="absolute top-0 h-full rounded-full opacity-20"
                style={{
                  width: `${Math.min(100, Math.max(0, value * 100))}%`,
                  background: "linear-gradient(90deg, #c084fc, #f472b6)",
                }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Shadow / Highlight cast */}
      <div className="flex gap-2">
        {[
          { label: "Shadows", value: shadowCast },
          { label: "Highlights", value: highlightCast },
        ].map(({ label, value }) => (
          <div key={label} className="flex-1 glass rounded-xl p-2.5">
            <p className="text-xs text-[var(--text-muted)]">{label}</p>
            <p className="text-sm font-medium capitalize mt-0.5">{value.replace("_", " ")}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
