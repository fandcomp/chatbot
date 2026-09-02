"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";
import { documentsApi, type KnowledgeSpace } from "@/lib/documents-api";
import { uploadSchema } from "@/lib/documents-schemas";

type Props = {
  onUploaded: () => void;
};

export function UploadDialog({ onUploaded }: Props) {
  const [open, setOpen] = useState(false);
  const [spaces, setSpaces] = useState<KnowledgeSpace[]>([]);
  const [knowledgeSpaceId, setKnowledgeSpaceId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    documentsApi
      .listKnowledgeSpaces()
      .then((result) => {
        setSpaces(result);
        setKnowledgeSpaceId((current) => current || result[0]?.id || "");
      })
      .catch(() => setFormError("Could not load knowledge spaces"));
  }, [open]);

  function reset() {
    setFile(null);
    setFieldError(null);
    setFormError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const result = uploadSchema.safeParse({ knowledgeSpaceId, file });
    if (!result.success) {
      setFieldError(result.error.flatten().fieldErrors.file?.[0] ?? "Invalid upload");
      return;
    }
    setFieldError(null);

    setIsSubmitting(true);
    try {
      await documentsApi.upload(result.data.knowledgeSpaceId, result.data.file);
      setOpen(false);
      reset();
      onUploaded();
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : "Upload failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (!nextOpen) reset();
      }}
    >
      <DialogTrigger render={<Button />}>Upload document</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload document</DialogTitle>
          <DialogDescription>PDF or DOCX, up to 50MB.</DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="knowledge-space">Knowledge space</Label>
            <select
              id="knowledge-space"
              value={knowledgeSpaceId}
              onChange={(event) => setKnowledgeSpaceId(event.target.value)}
              className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
            >
              {spaces.map((space) => (
                <option key={space.id} value={space.id}>
                  {space.name}
                </option>
              ))}
            </select>
          </div>
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setIsDragging(false);
              const dropped = event.dataTransfer.files[0];
              if (dropped) setFile(dropped);
            }}
            className={`flex flex-col items-center gap-2 rounded-md border border-dashed p-6 text-center text-sm ${
              isDragging ? "border-primary bg-muted/50" : "border-input"
            }`}
          >
            <p className="text-muted-foreground">Drop document here, or</p>
            <Label htmlFor="file-input" className="cursor-pointer text-primary underline-offset-4 hover:underline">
              Browse files
            </Label>
            <input
              id="file-input"
              type="file"
              accept=".pdf,.docx"
              className="sr-only"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            {file && <p className="text-xs text-muted-foreground">{file.name}</p>}
            {fieldError && <p className="text-xs text-destructive">{fieldError}</p>}
          </div>
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <DialogFooter>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Uploading…" : "Upload"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
