// The backend answers errors with stable codes (auth_error() in
// open-quiz-backend/app/routers/auth.py, ErrorCode in app/errors.py) and the
// interface translates them through API_ERROR_TRANSLATION_KEYS in
// src/lib/errors.ts. A code missing there falls back to a generic message,
// so every backend code must have a key, every key a translation, and the
// table no code the backend has stopped sending.
import { readdir, readFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const frontend = fileURLToPath(new URL("../", import.meta.url))
const backendApp = path.join(frontend, "../open-quiz-backend/app")

async function pythonFiles(directory) {
    const entries = await readdir(directory, { withFileTypes: true })
    const files = await Promise.all(
        entries.map((entry) => {
            const entryPath = path.join(directory, entry.name)
            if (entry.isDirectory()) return pythonFiles(entryPath)
            return entry.name.endsWith(".py") ? [entryPath] : []
        })
    )
    return files.flat()
}

const backendCodes = new Set()
for (const file of await pythonFiles(backendApp)) {
    const source = await readFile(file, "utf8")
    for (const match of source.matchAll(/auth_error\(\s*"([A-Z0-9_]+)"/g))
        backendCodes.add(match[1])
    if (path.basename(file) === "errors.py") {
        for (const match of source.matchAll(
            /^\s+([A-Z0-9_]+) = "\1"(?:\s+#.*)?$/gm
        ))
            backendCodes.add(match[1])
    }
}
if (backendCodes.size === 0) {
    throw new Error(`No error codes found under ${backendApp}`)
}

const table = await readFile(path.join(frontend, "src/lib/errors.ts"), "utf8")
const translationKeys = new Map(
    [...table.matchAll(/^\s+([A-Z0-9_]+): "([a-z0-9-]+)",$/gm)].map((match) => [
        match[1],
        match[2],
    ])
)
const catalog = JSON.parse(
    await readFile(
        path.join(frontend, "public/locales/en/translation.json"),
        "utf8"
    )
)

const failures = []
for (const code of [...backendCodes].sort()) {
    if (!translationKeys.has(code))
        failures.push(`${code} has no entry in API_ERROR_TRANSLATION_KEYS`)
}
for (const [code, key] of translationKeys) {
    if (!backendCodes.has(code))
        failures.push(`${code} is translated but the backend never sends it`)
    if (!(key in catalog))
        failures.push(`${code} maps to "${key}", missing from the catalogs`)
}

if (failures.length) {
    throw new Error(`Error code validation failed:\n- ${failures.join("\n- ")}`)
}

console.log(`Validated ${backendCodes.size} backend error codes.`)
