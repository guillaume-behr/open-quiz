// Fails the build when the JavaScript and CSS every visitor downloads before
// the first page renders grow past their budget. Run after `pnpm build`.
//
// "Initial" is what dist/index.html loads: its entry script, the chunks it
// modulepreloads and its stylesheets. Lazy pages and fonts are not counted.
// The budgets sit about 10 % above the sizes measured when they were set:
// raise one deliberately, in the same change that needs it.
import { readFileSync } from "node:fs"
import { gzipSync } from "node:zlib"

const budgets = {
    js: { raw: 560_000, gzip: 185_000 },
    css: { raw: 85_000, gzip: 15_000 },
}

const dist = new URL("../dist/", import.meta.url)
const html = readFileSync(new URL("index.html", dist), "utf8")

/** The /assets/ files a tag of the given pattern references. */
function referenced(pattern) {
    return [...html.matchAll(pattern)].map((match) => match[1])
}

const files = {
    js: [
        ...referenced(/<script[^>]+type="module"[^>]+src="\/([^"]+\.js)"/g),
        ...referenced(
            /<link[^>]+rel="modulepreload"[^>]+href="\/([^"]+\.js)"/g
        ),
    ],
    css: referenced(/<link[^>]+rel="stylesheet"[^>]+href="\/([^"]+\.css)"/g),
}

let failed = false
for (const [kind, paths] of Object.entries(files)) {
    if (paths.length === 0) {
        console.error(`No initial ${kind} found in dist/index.html.`)
        failed = true
        continue
    }
    let raw = 0
    let gzip = 0
    for (const path of new Set(paths)) {
        const content = readFileSync(new URL(path, dist))
        raw += content.length
        gzip += gzipSync(content, { level: 9 }).length
    }
    const budget = budgets[kind]
    const over = raw > budget.raw || gzip > budget.gzip
    failed ||= over
    console.log(
        `${over ? "OVER" : "ok  "} initial ${kind}: ${(raw / 1000).toFixed(1)} kB` +
            ` (budget ${budget.raw / 1000} kB), gzip ${(gzip / 1000).toFixed(1)} kB` +
            ` (budget ${budget.gzip / 1000} kB), ${new Set(paths).size} files`
    )
}

if (failed) {
    console.error(
        "Initial bundle over budget: see scripts/check-bundle-size.mjs."
    )
    process.exit(1)
}
