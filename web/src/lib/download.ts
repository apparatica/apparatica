// Files the page makes or reads itself, saved by the browser as a download.

/** Saves `file` under `name`. */
export function saveFile(file: Blob, name: string): void {
  const url = URL.createObjectURL(file);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  // The download has the file by the next task.
  setTimeout(() => URL.revokeObjectURL(url));
}
