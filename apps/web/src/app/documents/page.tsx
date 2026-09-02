"use client";

import { useCallback, useState } from "react";

import { DocumentList } from "@/components/documents/document-list";
import { UploadDialog } from "@/components/documents/upload-dialog";

export default function DocumentsPage() {
  const [refreshToken, setRefreshToken] = useState(0);
  const handleUploaded = useCallback(() => setRefreshToken((count) => count + 1), []);

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-6 px-6 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Documents</h1>
        <UploadDialog onUploaded={handleUploaded} />
      </div>
      <DocumentList refreshToken={refreshToken} />
    </div>
  );
}
