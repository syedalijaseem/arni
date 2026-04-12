type ArniState = "idle" | "listening" | "processing" | "speaking";

interface ArniVisualizerProps {
  state: ArniState;
}

const ORB_GRADIENT =
  "radial-gradient(circle at 35% 35%, rgba(255,255,255,0.9) 0%, rgba(125,211,252,0.8) 20%, rgba(56,189,248,0.7) 40%, rgba(14,165,233,0.6) 60%, rgba(2,132,199,0.4) 80%, rgba(12,74,110,0.2) 100%)";

const ORB_GRADIENT_BRIGHT =
  "radial-gradient(circle at 35% 35%, rgba(255,255,255,1) 0%, rgba(165,243,252,0.9) 20%, rgba(34,211,238,0.8) 40%, rgba(56,189,248,0.7) 60%, rgba(14,165,233,0.5) 80%, rgba(12,74,110,0.3) 100%)";

function glowShadow(state: ArniState): string {
  switch (state) {
    case "speaking":
      return "0 0 40px 10px rgba(52,211,153,0.5), 0 0 80px 20px rgba(52,211,153,0.2), inset 0 0 30px rgba(255,255,255,0.15)";
    case "processing":
      return "0 0 35px 8px rgba(56,189,248,0.6), 0 0 70px 15px rgba(56,189,248,0.25), inset 0 0 30px rgba(255,255,255,0.15)";
    case "listening":
      return "0 0 40px 10px rgba(56,189,248,0.4), 0 0 70px 15px rgba(56,189,248,0.2), inset 0 0 30px rgba(255,255,255,0.1)";
    default:
      return "0 0 30px 5px rgba(56,189,248,0.3), 0 0 60px 10px rgba(56,189,248,0.15), inset 0 0 30px rgba(255,255,255,0.1)";
  }
}

function orbAnimation(state: ArniState): string {
  switch (state) {
    case "speaking":
      return "arni-pulse 1.5s ease-in-out infinite";
    case "processing":
      return "arni-pulse 1.5s ease-in-out infinite";
    case "listening":
      return "arni-breathe 4s ease-in-out infinite";
    default:
      return "arni-breathe 4s ease-in-out infinite";
  }
}

export default function ArniVisualizer({ state }: ArniVisualizerProps) {
  return (
    <div className="relative flex items-center justify-center w-full h-full bg-slate-900 overflow-hidden">
      <style>{`
        @keyframes arni-breathe {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.03); }
        }
        @keyframes arni-pulse {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.06); }
        }
        @keyframes arni-ring {
          0% { transform: scale(0.6); opacity: 0.7; }
          100% { transform: scale(1.8); opacity: 0; }
        }
      `}</style>

      {/* Expanding ring halos — speaking */}
      {state === "speaking" && (
        <>
          {[0, 0.5, 1.0].map((delay, i) => (
            <div
              key={i}
              className="absolute rounded-full border border-emerald-400/60"
              style={{
                width: 160,
                height: 160,
                animation: `arni-ring 1.5s ease-out ${delay}s infinite`,
              }}
            />
          ))}
        </>
      )}

      {/* Processing shimmer ring */}
      {state === "processing" && (
        <div
          className="absolute rounded-full border-2 border-t-cyan-300 border-r-sky-400/30 border-b-transparent border-l-transparent animate-spin"
          style={{ width: 180, height: 180 }}
        />
      )}

      {/* The orb */}
      <div
        style={{
          width: 160,
          height: 160,
          borderRadius: "50%",
          background: state === "speaking" || state === "processing" ? ORB_GRADIENT_BRIGHT : ORB_GRADIENT,
          boxShadow: glowShadow(state),
          animation: orbAnimation(state),
        }}
      />
    </div>
  );
}
