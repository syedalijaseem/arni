type ArniState = "idle" | "listening" | "processing" | "speaking";

interface ArniVisualizerProps {
  state: ArniState;
}

export default function ArniVisualizer({ state }: ArniVisualizerProps) {
  return (
    <div className="relative flex items-center justify-center w-full h-full bg-slate-900 rounded-lg overflow-hidden">
      {/* Ripple rings — speaking */}
      {state === "speaking" && (
        <>
          <div
            className="absolute rounded-full border-2 border-emerald-400 animate-ping opacity-75"
            style={{ width: "60%", height: "60%" }}
          />
          <div
            className="absolute rounded-full border-2 border-emerald-400 animate-ping opacity-50"
            style={{ width: "75%", height: "75%", animationDelay: "0.4s" }}
          />
          <div
            className="absolute rounded-full border-2 border-emerald-400 animate-ping opacity-25"
            style={{ width: "90%", height: "90%", animationDelay: "0.8s" }}
          />
        </>
      )}

      {/* Processing spinner ring */}
      {state === "processing" && (
        <div
          className="absolute rounded-full border-2 border-t-amber-400 border-transparent animate-spin"
          style={{ width: "65%", height: "65%" }}
        />
      )}

      {/* Idle/listening glow */}
      <div
        className={`absolute rounded-full transition-all duration-1000 blur-xl ${
          state === "listening"
            ? "opacity-30 scale-110 bg-sky-400"
            : state === "idle"
              ? "opacity-10 scale-100 bg-sky-400"
              : ""
        }`}
        style={{ width: "50%", height: "50%" }}
      />

      {/* Center circle */}
      <div
        className={`relative z-10 flex items-center justify-center rounded-full text-white font-bold text-2xl border-2 transition-colors duration-300 ${
          state === "speaking"
            ? "bg-emerald-600 border-emerald-400"
            : state === "processing"
              ? "bg-amber-600 border-amber-400"
              : "bg-sky-800 border-sky-400"
        }`}
        style={{ width: "40%", height: "40%" }}
      >
        A
      </div>

      {/* Waveform bars — speaking */}
      {state === "speaking" && (
        <div className="absolute bottom-6 flex gap-1 items-end">
          {[0.4, 0.7, 1.0, 0.8, 0.5, 0.9, 0.6].map((h, i) => (
            <div
              key={i}
              className="w-1 bg-emerald-400 rounded-full animate-bounce"
              style={{
                height: `${h * 24}px`,
                animationDelay: `${i * 0.1}s`,
                animationDuration: `${0.4 + i * 0.1}s`,
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
