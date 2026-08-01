import {
    ThemeProviderContext,
    type Theme,
} from "@/components/theme/theme-context"
import { useEffect, useState } from "react"

type ThemeProviderProps = {
    children: React.ReactNode
    defaultTheme?: Theme
    storageKey?: string
}

const themes = new Set<Theme>(["dark", "light", "system"])

function storedTheme(storageKey: string, fallback: Theme): Theme {
    try {
        const value = localStorage.getItem(storageKey)
        return value && themes.has(value as Theme) ? (value as Theme) : fallback
    } catch {
        return fallback
    }
}

export function ThemeProvider({
    children,
    defaultTheme = "system",
    storageKey = "vite-ui-theme",
    ...props
}: ThemeProviderProps) {
    const [theme, setTheme] = useState<Theme>(() =>
        storedTheme(storageKey, defaultTheme)
    )

    useEffect(() => {
        const root = window.document.documentElement
        root.classList.remove("light", "dark")
        root.style.removeProperty("background-color")

        if (theme !== "system") {
            root.classList.add(theme)
            root.style.colorScheme = theme
            return undefined
        }

        const media = window.matchMedia("(prefers-color-scheme: dark)")
        const applySystemTheme = () => {
            root.classList.toggle("dark", media.matches)
            root.classList.toggle("light", !media.matches)
            root.style.colorScheme = media.matches ? "dark" : "light"
        }
        applySystemTheme()
        media.addEventListener("change", applySystemTheme)
        return () => media.removeEventListener("change", applySystemTheme)
    }, [theme])

    const value = {
        theme,
        setTheme: (theme: Theme) => {
            try {
                localStorage.setItem(storageKey, theme)
            } catch {
                // Theme switching still works when storage is unavailable.
            }
            setTheme(theme)
        },
    }

    return (
        <ThemeProviderContext.Provider {...props} value={value}>
            {children}
        </ThemeProviderContext.Provider>
    )
}
