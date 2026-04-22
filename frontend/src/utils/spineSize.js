export function getSpineDimensions(book) {
  const MM_TO_PX = 0.6;

  const heightPx = book.height_mm
    ? Math.min(220, Math.max(140, book.height_mm * MM_TO_PX))
    : 160;

  const widthPx = book.pages
    ? Math.min(55, Math.max(18, book.pages * 0.065 * MM_TO_PX))
    : 20;

  return { heightPx, widthPx };
}