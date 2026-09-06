type Props = {
  content: string;
};

export function UserMessage({ content }: Props) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] rounded-2xl bg-brand px-4 py-2.5 text-sm text-brand-foreground">
        {content}
      </div>
    </div>
  );
}
