import { toast } from "sonner";

export function useToast() {
  return {
    success: (message) => toast.success(message),
    error:   (message) => toast.error(message),
    info:    (message) => toast.info(message),
  };
}
