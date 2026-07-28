import { Button } from "@/components/ui/button"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import { Check, Languages } from "lucide-react"

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
                    {availableLanguages.map(({ code, label }) => {
                        return (
                            <DropdownMenuItem
                                key={code}
                                aria-current={
                                    currentLanguage === code
                                        ? "true"
                                        : undefined
                                }
                                onClick={() => {
                                    void i18n.changeLanguage(code)
                                }}
                            >
                                {label}
                                {currentLanguage === code && (
                                    <Check className="ms-auto" />
                                )}
                            </DropdownMenuItem>
                        )
                    })}
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    )
}
