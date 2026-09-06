type Props = {
  label: string;
  fraction: number;
  description?: string;
};

export function RateBar({ label, fraction, description }: Props) {
  const percent = Math.round(Math.min(Math.max(fraction, 0), 1) * 100);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-sm font-semibold tabular-nums">{percent}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-foreground/70 transition-[width]"
          style={{ width: `${percent}%` }}
        />
      </div>
      {description && <span className="text-xs text-muted-foreground">{description}</span>}
    </div>
  );
}
