import { useState, useCallback, useRef } from "react";

interface DocumentInfo {
  id: string;
  filename: string;
  status: "processing" | "ready" | "error";
  chunk_count: number;
  file_size_bytes: number;
}

interface DocumentUploadProps {
  meetingId: string;
  token: string;
  onDocumentReady?: (doc: DocumentInfo) => void;
}

const ACCEPTED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
];

const ACCEPTED_EXTENSIONS = ".pdf,.docx,.txt";
const MAX_SIZE_MB = 20;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentUpload({ meetingId, token, onDocumentReady }: DocumentUploadProps) {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const uploadFile = useCallback(
    async (file: File) => {
      setError(null);

      if (!ACCEPTED_TYPES.includes(file.type)) {
        setError("Only PDF, DOCX, and TXT files are supported.");
        return;
      }

      if (file.size > MAX_SIZE_MB * 1024 * 1024) {
        setError(`File must be under ${MAX_SIZE_MB} MB.`);
        return;
      }

      setUploading(true);

      const formData = new FormData();
      formData.append("file", file);

      try {
        const response = await fetch(
          `/api/meetings/${meetingId}/documents`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          }
        );

        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail ?? `Upload failed (${response.status})`);
        }

        const doc: DocumentInfo = await response.json();

        setDocuments((prev) => [...prev, doc]);
        onDocumentReady?.(doc);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed.");
      } finally {
        setUploading(false);
      }
    },
    [meetingId, token, onDocumentReady]
  );

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files) return;
      Array.from(files).forEach(uploadFile);
    },
    [uploadFile]
  );

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  const onDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(true);
  };

  const onDragLeave = () => setDragging(false);

  const statusColor = (status: DocumentInfo["status"]) => {
    if (status === "ready") return "text-green-600 dark:text-green-400";
    if (status === "error") return "text-red-500";
    return "text-yellow-500";
  };

  return (
    <div className="space-y-3">
      {/* Drop Zone */}
      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => inputRef.current?.click()}
        className={[
          "cursor-pointer rounded-xl border-2 border-dashed p-6 text-center transition-colors",
          dragging
            ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
            : "border-neutral-300 dark:border-neutral-600 hover:border-blue-400",
        ].join(" ")}
        role="button"
        aria-label="Upload document"
      >
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          {uploading
            ? "Uploading..."
            : "Drag and drop a PDF, DOCX, or TXT file here, or click to browse"}
        </p>
        <p className="mt-1 text-xs text-neutral-400">Max {MAX_SIZE_MB} MB per file</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS}
          className="hidden"
          multiple
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {/* Error */}
      {error && (
        <p className="text-sm text-red-500" role="alert">
          {error}
        </p>
      )}

      {/* Document List */}
      {documents.length > 0 && (
        <ul className="space-y-1">
          {documents.map((doc) => (
            <li
              key={doc.id}
              className="flex items-center justify-between rounded-lg border border-neutral-200 dark:border-neutral-700 px-3 py-2 text-sm"
            >
              <span className="truncate font-medium">{doc.filename}</span>
              <span className="ml-3 shrink-0 space-x-2 text-xs">
                <span className="text-neutral-400">{formatBytes(doc.file_size_bytes)}</span>
                <span className={statusColor(doc.status)}>
                  {doc.status === "ready"
                    ? `Ready (${doc.chunk_count} chunks)`
                    : doc.status === "processing"
                    ? "Processing..."
                    : "Error"}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
