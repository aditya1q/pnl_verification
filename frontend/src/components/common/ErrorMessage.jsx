import { AlertCircle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function ErrorMessage({ children }) {
  if (!children) return null;
  return (
    <Alert variant="destructive" className="border-destructive/30 bg-destructive/5 py-2.5">
      <AlertCircle />
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}
