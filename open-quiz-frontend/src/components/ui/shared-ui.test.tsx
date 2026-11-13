// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AnimatedGrid } from "@/components/ui/animated-grid"
import { FilterSidebar } from "@/components/ui/filter-sidebar"
import { LoadingState } from "@/components/ui/loading-state"

describe("LoadingState", () => {
    it("announces the loading and sizes its box", () => {
        render(<LoadingState className="min-h-64" size={8} />)
        const status = screen.getByRole("status", { name: "page-loading" })
        expect(status).toHaveClass("flex", "min-h-64")
        expect(status.querySelector("svg")).toHaveClass("size-8")
    })
})

describe("AnimatedGrid", () => {
    it("replays its animation when the items shown change", () => {
        const { container, rerender } = render(
            <AnimatedGrid ids={[1, 2]} as="ul" className="gap-4">
                <li>one</li>
            </AnimatedGrid>
        )
        const first = container.firstElementChild
        expect(first?.tagName).toBe("UL")
        expect(first).toHaveClass("grid", "animate-in", "gap-4")

        rerender(
            <AnimatedGrid ids={[1, 2]} as="ul" className="gap-4">
                <li>one</li>
            </AnimatedGrid>
        )
        expect(container.firstElementChild).toBe(first)

        rerender(
            <AnimatedGrid ids={[3]} as="ul" className="gap-4">
                <li>three</li>
            </AnimatedGrid>
        )
        expect(container.firstElementChild).not.toBe(first)
    })
})

describe("FilterSidebar", () => {
    it("offers to clear the filters only once one is set", () => {
        const onClear = vi.fn()
        const { rerender } = render(
            <FilterSidebar hasFilters={false} onClear={onClear}>
                <input aria-label="search" />
            </FilterSidebar>
        )
        expect(screen.getByRole("heading", { name: "filters" })).toBeVisible()
        expect(screen.getByLabelText("search")).toBeVisible()
        expect(screen.queryByRole("button")).toBeNull()

        rerender(
            <FilterSidebar hasFilters onClear={onClear}>
                <input aria-label="search" />
            </FilterSidebar>
        )
        fireEvent.click(screen.getByRole("button", { name: "clear-filters" }))
        expect(onClear).toHaveBeenCalledWith()
    })
})
