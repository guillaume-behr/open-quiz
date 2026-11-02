// The Python runner loads Pyodide from /pyodide/ (python-runner.worker.ts),
// which Vite serves from public/. These files come from the pyodide package
// pinned in package.json, so they always match the JavaScript loader that
// imports them; they are copied on every dev start and build rather than
// committed.
import { copyFile, mkdir } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const frontend = fileURLToPath(new URL("../", import.meta.url))
const source = path.join(frontend, "node_modules/pyodide")
const target = path.join(frontend, "public/pyodide")
const files = [
    "pyodide-lock.json",
    "pyodide.asm.mjs",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
]

await mkdir(target, { recursive: true })
await Promise.all(
    files.map((file) =>
        copyFile(path.join(source, file), path.join(target, file))
    )
)
console.log(`Copied ${files.length} Pyodide files to public/pyodide.`)
