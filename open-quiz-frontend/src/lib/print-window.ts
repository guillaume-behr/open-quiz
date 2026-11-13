/**
 * Opens a blank window, lets `write` fill it, then opens the print dialog.
 * The window is opened before anything is awaited, so that the browser ties
 * it to the click that asked for it, and it cannot reach back to this page.
 * It is closed again when `write` fails. Resolves to false, without calling
 * `write`, when the browser blocked the pop-up.
 */
export async function withPrintWindow(
    write: (printWindow: Window) => Promise<void> | void
): Promise<boolean> {
    const printWindow = window.open("", "_blank")
    if (!printWindow) return false
    printWindow.opener = null
    try {
        await write(printWindow)
    } catch (caught) {
        printWindow.close()
        throw caught
    }
    printWindow.focus()
    printWindow.setTimeout(() => printWindow.print(), 100)
    return true
}
