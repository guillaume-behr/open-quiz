import type { StudentClass, StudentCredential } from "@/api/types"
import { formatClassName } from "@/lib/utils"
import type { TFunction } from "i18next"

/** Writes one cut-out card of sign-in credentials per student of the class. */
export function writeCredentialCards(
    document: Document,
    studentClass: StudentClass,
    credentials: StudentCredential[],
    t: TFunction,
    language: string,
    direction: "ltr" | "rtl"
): void {
    document.title = t("student-credentials-print-title", {
        className: formatClassName(studentClass.grade_level, studentClass.name),
    })
    document.documentElement.lang = language
    document.documentElement.dir = direction
    const style = document.createElement("style")
    style.textContent = `
        @page { size: A4 portrait; margin: 0; }
        * { box-sizing: border-box; }
        body { margin: 0; color: #111; font-family: Arial, sans-serif; }
        main { display: grid; width: 210mm; min-height: 297mm; padding: 6mm; grid-template-columns: repeat(3, minmax(0, 1fr)); align-content: start; gap: 2mm; }
        article { min-width: 0; min-height: 31mm; padding: 3mm; border: 1px dashed #777; break-inside: avoid; }
        .class { margin: 0 0 1.5mm; color: #555; font-size: 8pt; }
        .name { margin: 0 0 2mm; font-size: 11pt; font-weight: 700; overflow-wrap: anywhere; }
        dl { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 1mm 2mm; margin: 0; font-size: 8.5pt; }
        dt { color: #555; }
        dd { margin: 0; font-family: monospace; font-size: 9pt; font-weight: 700; overflow-wrap: anywhere; }
        .empty { grid-column: 1 / -1; padding: 10mm; text-align: center; }
    `
    document.head.append(style)
    const main = document.createElement("main")
    if (credentials.length === 0) {
        const empty = document.createElement("p")
        empty.className = "empty"
        empty.textContent = t("no-student-in-class")
        main.append(empty)
    }
    for (const credential of credentials) {
        const card = document.createElement("article")
        const classLabel = document.createElement("p")
        classLabel.className = "class"
        classLabel.textContent = formatClassName(
            studentClass.grade_level,
            studentClass.name
        )
        const name = document.createElement("p")
        name.className = "name"
        name.textContent = credential.display_name
        const details = document.createElement("dl")
        for (const [label, value] of [
            [t("student-id"), credential.identifier],
            [
                t("login-password"),
                credential.password ?? t("password-unavailable"),
            ],
        ]) {
            const term = document.createElement("dt")
            term.textContent = label
            const description = document.createElement("dd")
            description.textContent = value
            details.append(term, description)
        }
        card.append(classLabel, name, details)
        main.append(card)
    }
    document.body.append(main)
}
