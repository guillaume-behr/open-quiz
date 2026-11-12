// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { Pagination } from "./pagination"

describe("Pagination", () => {
    it("renders nothing for a single page", () => {
        const { container } = render(
            <Pagination currentPage={1} totalPages={1} onPageChange={vi.fn()} />
        )
        expect(container).toBeEmptyDOMElement()
    })

    it("moves between pages and disables the ends", async () => {
        const onPageChange = vi.fn()
        const { rerender } = render(
            <Pagination
                currentPage={1}
                totalPages={3}
                onPageChange={onPageChange}
            />
        )
        expect(
            screen.getByRole("button", { name: "previous-page" })
        ).toBeDisabled()
        expect(
            screen.getByText('pagination-status {"current":1,"total":3}')
        ).toBeVisible()
        await userEvent.click(screen.getByRole("button", { name: "next-page" }))
        expect(onPageChange).toHaveBeenLastCalledWith(2)

        rerender(
            <Pagination
                currentPage={3}
                totalPages={3}
                onPageChange={onPageChange}
            />
        )
        expect(screen.getByRole("button", { name: "next-page" })).toBeDisabled()
        await userEvent.click(
            screen.getByRole("button", { name: "previous-page" })
        )
        expect(onPageChange).toHaveBeenLastCalledWith(2)
    })
})
