import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

// Merge class names; later Tailwind classes override earlier ones (e.g. "px-2" then "px-4").
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
