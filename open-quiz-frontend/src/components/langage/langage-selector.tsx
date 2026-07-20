import { Button } from "@/components/ui/button"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import { Languages } from "lucide-react"

import { useTranslation } from "react-i18next"
import { availableLangages } from "@/lib/i18n"

export function LanguageSelector() {
    const { i18n } = useTranslation()

    return (
        <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="outline" />}>
                <Languages />
            </DropdownMenuTrigger>
            <DropdownMenuContent>
                {availableLangages.map((value) => {
                    return (
                        <DropdownMenuItem
                            onClick={() => {
                                i18n.changeLanguage(value)
                            }}
                        >
                            {value}
                        </DropdownMenuItem>
                    )
                })}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
