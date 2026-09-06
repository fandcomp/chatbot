import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Props = {
  label: string;
  value: string;
  sublabel?: string;
  size?: "default" | "hero";
  tone?: "default" | "destructive";
};

export function StatCard({ label, value, sublabel, size = "default", tone = "default" }: Props) {
  return (
    <Card className={cn(size === "hero" && "bg-muted/40")}>
      <CardContent className="flex flex-col gap-1">
        <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {label}
        </span>
        <span
          className={cn(
            "font-heading font-semibold tabular-nums",
            size === "hero" ? "text-5xl" : "text-3xl",
            tone === "destructive" && "text-destructive"
          )}
        >
          {value}
        </span>
        {sublabel && <span className="text-xs text-muted-foreground">{sublabel}</span>}
      </CardContent>
    </Card>
  );
}
