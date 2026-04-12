export const ui = {
  card: "bg-card/60 border border-border/60 rounded-xl backdrop-blur-sm",
  cardHover: "hover:border-border hover:bg-card/80 transition-all duration-200",
  badge: {
    created: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20",
    active: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20",
    ended: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20",
    processed: "bg-muted text-muted-foreground border border-border",
  } as Record<string, string>,
  statCard: "bg-muted/60 rounded-lg p-4 border border-border/40",
  sectionTitle: "text-lg font-semibold text-foreground",
  mutedText: "text-muted-foreground text-sm",
};
