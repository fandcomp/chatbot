import { z } from "zod";

const ALLOWED_EXTENSIONS = [".pdf", ".docx"];
const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;

function hasAllowedExtension(file: File): boolean {
  const name = file.name.toLowerCase();
  return ALLOWED_EXTENSIONS.some((extension) => name.endsWith(extension));
}

export const uploadSchema = z.object({
  knowledgeSpaceId: z.string().min(1, "Choose a knowledge space"),
  file: z
    .instanceof(File, { message: "Choose a file" })
    .refine(hasAllowedExtension, "Only PDF or DOCX files are allowed")
    .refine((file) => file.size <= MAX_FILE_SIZE_BYTES, "File must be 50MB or smaller"),
});

export type UploadInput = z.infer<typeof uploadSchema>;
