import type { ReactNode } from "react"
import { createPortal } from "react-dom"
import { useOutletContext } from "react-router"

type MainLayoutOutletContext = {
    navbarActionTarget: HTMLDivElement | null
}

export function NavbarAction({ children }: { children: ReactNode }) {
    const { navbarActionTarget } = useOutletContext<MainLayoutOutletContext>()

    return navbarActionTarget
        ? createPortal(children, navbarActionTarget)
        : null
}
