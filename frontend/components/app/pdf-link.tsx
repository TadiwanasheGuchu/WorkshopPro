import { FileDown } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Opens a server-generated PDF (same origin, session cookie) in a new tab. */
export function PdfLink({ href, label = "PDF" }: { href: string; label?: string }) {
  return (
    <Button asChild size="sm">
      <a href={`/api/v1${href}`} target="_blank" rel="noopener">
        <FileDown className="size-4" aria-hidden /> {label}
      </a>
    </Button>
  );
}
