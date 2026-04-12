export const ui = {
  card: "bg-slate-800/60 border border-slate-700/60 rounded-xl backdrop-blur-sm",
  cardHover: "hover:border-slate-600 hover:bg-slate-800/80 transition-all duration-200",
  badge: {
    created: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
    active: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
    ended: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
    processed: "bg-slate-500/10 text-slate-400 border border-slate-500/20",
  } as Record<string, string>,
  statCard: "bg-slate-900/60 rounded-lg p-4 border border-slate-700/40",
  sectionTitle: "text-lg font-semibold text-white",
  mutedText: "text-slate-400 text-sm",
};
