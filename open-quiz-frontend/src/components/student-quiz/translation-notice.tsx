import { Button } from "@/components/ui/button"
import { Collapsible as CollapsiblePrimitive } from "@base-ui/react/collapsible"
import {
    ChevronDown,
    Languages,
    LoaderCircle,
    TriangleAlert,
} from "lucide-react"
import { useTranslation } from "react-i18next"

export type TranslationViewState = {
    offered: boolean
    active: boolean
    hasError: boolean
    isTranslating: boolean
    isDownloading: boolean
}

/** Local translation banner shared by the exam and the training pages. */
export function TranslationNotice({
    translation,
    onToggle,
}: {
    translation: TranslationViewState
    onToggle: () => void
}) {
    const { t } = useTranslation()

    return (
        <CollapsiblePrimitive.Root className="w-full max-w-xl self-center overflow-hidden rounded-xl border border-warning/40 bg-warning/10">
            <CollapsiblePrimitive.Trigger className="group flex w-full items-center gap-2 px-3 py-2 text-start text-sm font-bold transition-colors select-none hover:bg-warning/10 focus-visible:ring-3 focus-visible:ring-warning/50 focus-visible:outline-none focus-visible:ring-inset sm:px-4">
                <TriangleAlert
                    className="size-4 shrink-0 text-warning"
                    aria-hidden="true"
                />
                <span>{t("automatic-translation-title")}</span>
                <ChevronDown className="ms-auto size-4 shrink-0 text-warning transition-transform duration-200 ease-out group-data-panel-open:rotate-180 motion-reduce:transition-none" />
            </CollapsiblePrimitive.Trigger>
            <CollapsiblePrimitive.Panel className="h-[var(--collapsible-panel-height)] overflow-hidden opacity-100 transition-[height,opacity] duration-200 ease-out data-ending-style:h-0 data-ending-style:opacity-0 data-starting-style:h-0 data-starting-style:opacity-0 motion-reduce:transition-none [&[hidden]:not([hidden='until-found'])]:hidden">
                <div className="border-t border-warning/40 px-3 py-3 sm:px-4">
                    <p className="text-xs leading-5 sm:text-sm">
                        {t("automatic-translation-warning")}
                    </p>
                    {translation.hasError && (
                        <p
                            className="mt-2 text-xs text-destructive sm:text-sm"
                            role="alert"
                        >
                            {t("automatic-translation-unavailable")}
                        </p>
                    )}
                    <Button
                        className="mt-2 h-9"
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={translation.isTranslating}
                        onClick={onToggle}
                    >
                        {translation.isTranslating ? (
                            <LoaderCircle
                                className="animate-spin motion-reduce:animate-none"
                                aria-hidden="true"
                            />
                        ) : (
                            <Languages aria-hidden="true" />
                        )}
                        {translation.isDownloading
                            ? t("automatic-translation-downloading")
                            : translation.isTranslating
                              ? t("automatic-translation-progress")
                              : translation.active
                                ? t("automatic-translation-original")
                                : t("automatic-translation-enable")}
                    </Button>
                </div>
            </CollapsiblePrimitive.Panel>
        </CollapsiblePrimitive.Root>
    )
}
