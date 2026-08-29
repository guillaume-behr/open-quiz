// formatClassName duplicates format_class_name from
// open-quiz-backend/app/class_names.py. The two build the label shown on
// results and written into session snapshots, so a difference between them
// makes the interface disagree with the API it renders. This table is the one
// in test_class_labels_are_built_without_repeating_the_level; keep them equal.
import { formatClassName } from "../src/lib/utils.ts"

const cases = [
    // The level is prepended when the name does not already carry it.
    ["Tle", "TG1", "Tle TG1"],
    ["Tle", "Tle TG1", "Tle TG1"],
    // A name equal to the level stays as written.
    ["Tle", "Tle", "Tle"],
    ["Tle", "tle", "tle"],
    // Either side missing leaves the other untouched.
    [null, "TG1", "TG1"],
    ["", "TG1", "TG1"],
    ["Tle", "", "Tle"],
    // A level repeated around a separator is folded back into the prefix,
    // for each separator teachers actually type.
    ["Tle", "TG1 - Tle", "Tle TG1"],
    ["Tle", "TG1 — Tle", "Tle TG1"],
    ["Tle", "TG1 · Tle", "Tle TG1"],
    ["Tle", "Tle - TG1", "Tle TG1"],
    ["Tle", "Tle — TG1", "Tle TG1"],
    ["Tle", "Tle · TG1", "Tle TG1"],
    // Matching ignores case on both sides.
    ["Tle", "tle - TG1", "Tle TG1"],
    ["Tle", "TG1 - TLE", "Tle TG1"],
    // Surrounding and repeated whitespace is collapsed.
    ["Tle", "  TG1   B  ", "Tle TG1 B"],
    ["  Tle  ", "TG1", "Tle TG1"],
    // A level that merely starts the name is not a separator match.
    ["1ere", "1ere-A", "1ere 1ere-A"],
]

const failures = []
for (const [gradeLevel, className, expected] of cases) {
    const actual = formatClassName(gradeLevel, className)
    if (actual !== expected) {
        failures.push(
            `formatClassName(${JSON.stringify(gradeLevel)}, ` +
                `${JSON.stringify(className)}) returned ` +
                `${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`
        )
    }
}

if (failures.length) {
    throw new Error(
        `Class label validation failed:\n- ${failures.join("\n- ")}`
    )
}

console.log(`Validated ${cases.length} class labels against the API format.`)
