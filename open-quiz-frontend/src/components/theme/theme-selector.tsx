import { Moon, Sun } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuRadioGroup,
    DropdownMenuRadioItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { type Theme, useTheme } from "@/components/theme/theme-context"
import { useTranslation } from "react-i18next"

export function ThemeSelector({ className }: React.ComponentProps<"div">) {
    const { theme, setTheme } = useTheme()

    const { t } = useTranslation()

    return (
        <div className={className}>
            <DropdownMenu>
                <DropdownMenuTrigger
                    render={<Button variant="outline" size="icon" />}
                >
                    <Sun className="h-[1.2rem] w-[1.2rem] scale-100 rotate-0 transition-all dark:scale-0 dark:-rotate-90" />
                    <Moon className="absolute h-[1.2rem] w-[1.2rem] scale-0 rotate-90 transition-all dark:scale-100 dark:rotate-0" />
                    <span className="sr-only">{t("theme")}</span>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                    <DropdownMenuRadioGroup
                        value={theme}
                        onValueChange={(value: Theme) => setTheme(value)}
                    >
                        <DropdownMenuRadioItem value="light">
                            {t("light")}
                        </DropdownMenuRadioItem>
                        <DropdownMenuRadioItem value="dark">
                            {t("dark")}
                        </DropdownMenuRadioItem>
                        <DropdownMenuRadioItem value="system">
                            {t("system")}
                        </DropdownMenuRadioItem>
                    </DropdownMenuRadioGroup>
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    )
}
