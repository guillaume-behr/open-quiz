import { Button } from "@/components/ui/button"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuRadioGroup,
    DropdownMenuRadioItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import { Languages } from "lucide-react"

import { useTranslation } from "react-i18next"
import { availableLanguages } from "@/lib/i18n"

export function LanguageSelector({ className }: React.ComponentProps<"div">) {
    const { i18n, t } = useTranslation()
    const currentLanguage = i18n.resolvedLanguage ?? i18n.language

    return (
        <div className={className}>
            <DropdownMenu>
                <DropdownMenuTrigger
                    render={<Button variant="outline" size="icon" />}
                >
                    <Languages />
                    <span className="sr-only">{t("language")}</span>
                </DropdownMenuTrigger>
                <DropdownMenuContent side="top">
                    <DropdownMenuRadioGroup
                        value={currentLanguage}
                        onValueChange={(code: string) => {
                            void i18n.changeLanguage(code)
                        }}
                    >
                        {availableLanguages.map(({ code, label }) => (
                            <DropdownMenuRadioItem key={code} value={code}>
                                <span lang={code}>{label}</span>
                            </DropdownMenuRadioItem>
                        ))}
                    </DropdownMenuRadioGroup>
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    )
}
