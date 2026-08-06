/**
 * Copy text in both normal browser pages and the restricted iframe used by
 * the OA plugin. Clipboard permissions are not guaranteed in the latter.
 */
export async function copyText(text: string): Promise<boolean> {
  if (!text || typeof document === "undefined") return false;

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Permissions Policy can reject navigator.clipboard in an iframe.
  }

  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    return copied;
  } catch {
    return false;
  }
}
