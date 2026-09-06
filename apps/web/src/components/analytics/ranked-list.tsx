type Item = {
  key: string;
  label: string;
  count: number;
  meta?: string;
};

type Props = {
  title: string;
  items: Item[];
  emptyMessage: string;
  countLabel: string;
};

export function RankedList({ title, items, emptyMessage, countLabel }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{emptyMessage}</p>
      ) : (
        <ol className="flex flex-col gap-1">
          {items.map((item, index) => (
            <li
              key={item.key}
              className="flex items-center gap-3 rounded-md border border-transparent px-2 py-2 hover:border-border"
            >
              <span className="w-5 shrink-0 text-right text-xs text-muted-foreground tabular-nums">
                {index + 1}
              </span>
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-sm">{item.label}</span>
                {item.meta && <span className="text-xs text-muted-foreground">{item.meta}</span>}
              </div>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                {item.count} {countLabel}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
