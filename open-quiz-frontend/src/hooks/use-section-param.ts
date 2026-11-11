import { useCallback } from "react"
import { useSearchParams } from "react-router"

/**
 * The section of a dashboard, kept in the `section` query parameter so that
 * a reload stays on it, Back returns to the previous one and a link can open
 * it. An unknown or missing value falls back to the first section.
 */
export function useSectionParam<Section extends string>(
    sections: readonly [Section, ...Section[]]
): [Section, (section: Section) => void] {
    const [searchParams, setSearchParams] = useSearchParams()
    const requested = searchParams.get("section")
    const section =
        sections.find((candidate) => candidate === requested) ?? sections[0]
    const selectSection = useCallback(
        (next: Section) =>
            setSearchParams((current) => {
                const params = new URLSearchParams(current)
                params.set("section", next)
                return params
            }),
        [setSearchParams]
    )
    return [section, selectSection]
}
