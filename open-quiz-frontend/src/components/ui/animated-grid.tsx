import { cn } from "@/lib/utils"
import type { ReactNode } from "react"

/**
 * A grid that fades its items in, again each time the set of items shown
 * changes (another page, other filters), identified by `ids`.
 */
export function AnimatedGrid({
    ids,
    as: Element = "div",
    className,
    children,
}: {
    ids: readonly (number | string)[]
    as?: "div" | "ul"
    className?: string
    children: ReactNode
}) {
    return (
        <Element
            key={ids.join(",")}
            className={cn(
                "grid animate-in duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none",
                className
            )}
        >
            {children}
        </Element>
    )
}
