import { readdir, readFile } from "node:fs/promises"
import { fileURLToPath } from "node:url"
import path from "node:path"

const localesDirectory = fileURLToPath(
    new URL("../public/locales/", import.meta.url)
)
const pluralSuffix = /_(zero|one|two|few|many|other)$/
const interpolationPattern = /{{\s*([^},\s]+)/g

function interpolationNames(value) {
    return [...value.matchAll(interpolationPattern)]
        .map((match) => match[1])
        .sort()
}

const localeNames = (await readdir(localesDirectory, { withFileTypes: true }))
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort()

if (!localeNames.includes("en")) {
    throw new Error("The English reference locale is missing.")
}

const translations = new Map()
for (const localeName of localeNames) {
    const filename = path.join(localesDirectory, localeName, "translation.json")
    translations.set(localeName, JSON.parse(await readFile(filename, "utf8")))
}

const reference = translations.get("en")
const referenceKeys = Object.keys(reference)
const failures = []

for (const [localeName, locale] of translations) {
    for (const [key, value] of Object.entries(locale)) {
        if (typeof value !== "string") {
            failures.push(`${localeName}: "${key}" must be a string`)
        }
    }

    for (const key of referenceKeys) {
        if (!(key in locale)) {
            failures.push(`${localeName}: missing "${key}"`)
            continue
        }
        const expectedNames = interpolationNames(reference[key])
        const actualNames = interpolationNames(locale[key])
        if (expectedNames.join("\0") !== actualNames.join("\0")) {
            failures.push(
                `${localeName}: "${key}" uses interpolation variables ` +
                    `${actualNames.join(", ") || "(none)"}; expected ` +
                    `${expectedNames.join(", ") || "(none)"}`
            )
        }
    }

    for (const key of Object.keys(locale)) {
        if (key in reference) continue
        const match = key.match(pluralSuffix)
        const base = match ? key.slice(0, -match[0].length) : key
        if (!match || !(`${base}_one` in reference)) {
            failures.push(`${localeName}: unexpected "${key}"`)
        }
    }
}

if (failures.length) {
    throw new Error(`Locale validation failed:\n- ${failures.join("\n- ")}`)
}

console.log(
    `Validated ${localeNames.length} locales against ` +
        `${referenceKeys.length} English keys.`
)
