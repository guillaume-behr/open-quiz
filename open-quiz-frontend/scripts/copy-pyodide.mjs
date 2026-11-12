// The Python runner loads Pyodide from /pyodide/<version>/
// (python-runner.worker.ts, vite.config.ts),
// which Vite serves from public/. The loader itself is served from there too
// instead of being bundled. These files come from the pyodide package pinned
// in package.json, so the loader and the runtime always match; they are
// copied on every dev start and build rather than committed.
import { copyFile, mkdir, readFile, rm } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const frontend = fileURLToPath(new URL("../", import.meta.url))
const source = path.join(frontend, "node_modules/pyodide")
const { version } = JSON.parse(
    await readFile(path.join(source, "package.json"), "utf8")
)
const publicDirectory = path.join(frontend, "public/pyodide")
const target = path.join(publicDirectory, version)
const files = [
    "pyodide-lock.json",
    "pyodide.asm.mjs",
    "pyodide.asm.wasm",
    "pyodide.mjs",
    "python_stdlib.zip",
]

// Only the current version: an older copy would ship in the build too.
await rm(publicDirectory, { recursive: true, force: true })
await mkdir(target, { recursive: true })
await Promise.all(
    files.map((file) =>
        copyFile(path.join(source, file), path.join(target, file))
    )
)
console.log(
    `Copied ${files.length} Pyodide files to public/pyodide/${version}.`
)
