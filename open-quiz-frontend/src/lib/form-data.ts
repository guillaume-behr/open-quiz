/** A text field of a submitted form; "" when it is missing or a file. */
export function formText(form: FormData, name: string): string {
    const value = form.get(name)
    return typeof value === "string" ? value : ""
}
