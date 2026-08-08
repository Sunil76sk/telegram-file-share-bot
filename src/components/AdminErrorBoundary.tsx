import { useRouter } from "@tanstack/react-router";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function AdminErrorBoundary({ error, reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  console.error("[admin]", error);
  return (
    <div className="p-6">
      <Card className="p-6 border-destructive max-w-xl">
        <h2 className="font-semibold text-lg">Something went wrong</h2>
        <p className="text-sm text-muted-foreground mt-1 break-words">
          {error?.message ?? "Unknown error"}
        </p>
        <div className="flex gap-2 mt-4">
          <Button
            size="sm"
            onClick={() => {
              router.invalidate();
              reset();
            }}
          >
            Try again
          </Button>
          <Button size="sm" variant="outline" onClick={() => (window.location.href = "/admin")}>
            Back to dashboard
          </Button>
        </div>
      </Card>
    </div>
  );
}
