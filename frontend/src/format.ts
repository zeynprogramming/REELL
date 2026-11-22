export const dateLabel = (value: string | null) => (value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—");

export const durationLabel = (seconds: number | null) => {
  if (seconds == null) return "—";
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
  return [h, m, s].map(v => String(v).padStart(2, "0")).join(":");
};

export const bytesLabel = (bytes: number | null | undefined) => {
  if (bytes == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes, i = 0;
  while (value >= 1024 && i < units.length - 1) { value /= 1024; i++; }
  return `${value >= 100 || i === 0 ? Math.round(value) : value.toFixed(1)} ${units[i]}`;
};

export const statusTone = (status: string) => {
  const s = status.toLowerCase();
  if (["ready", "uploaded", "completed", "published", "done", "connected", "allowed", "active"].includes(s)) return "green";
  if (["processing", "running", "uploading"].includes(s)) return "blue";
  if (["failed", "error", "denied", "deactivated"].includes(s)) return "orange";
  if (s === "cancelled") return "gray";
  return "purple";
};
