import { usePublicInformation } from "@/hooks/use-public-information"
import { useTranslation } from "react-i18next"
import { UPDATED_AT } from "./updated-at"
import {
    LegalPage,
    LoadFailureNotice,
    ConfigValue,
    Definition,
    OfficialLink,
} from "./legal-page"

export function AccessibilityPage() {
    const { t, i18n } = useTranslation()
    const { information, loadFailed } = usePublicInformation()
    const pending = !information && !loadFailed
    const updatedAt = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
        dateStyle: "long",
    }).format(UPDATED_AT)

    return (
        <LegalPage
            titleKey="accessibility-title"
            descriptionKey="accessibility-description"
        >
            <LoadFailureNotice show={loadFailed} />

            <section className="rounded-lg border-2 border-destructive/40 bg-destructive/5 p-5">
                <h2>{t("accessibility-status-title")}</h2>
                <p className="text-lg font-bold">{t("accessibility-status")}</p>
                <p className="mt-2">{t("accessibility-status-text")}</p>
            </section>

            <section>
                <h2>{t("accessibility-tests-title")}</h2>
                <p>{t("accessibility-tests-text")}</p>
            </section>

            <section>
                <h2>{t("accessibility-statement-title")}</h2>
                <p>{t("accessibility-statement-text", { date: updatedAt })}</p>
                <p className="mt-3">{t("accessibility-technologies-text")}</p>
            </section>

            <section>
                <h2>{t("accessibility-plan-title")}</h2>
                <dl>
                    <Definition term={t("accessibility-scheme-label")}>
                        {information?.accessibility.scheme_url ? (
                            <OfficialLink
                                href={information.accessibility.scheme_url}
                            >
                                {t("accessibility-scheme-link")}
                            </OfficialLink>
                        ) : (
                            <ConfigValue value="" pending={pending} />
                        )}
                    </Definition>
                    <Definition term={t("accessibility-action-label")}>
                        {information?.accessibility.action_plan_url ? (
                            <OfficialLink
                                href={information.accessibility.action_plan_url}
                            >
                                {t("accessibility-action-link")}
                            </OfficialLink>
                        ) : (
                            <ConfigValue value="" pending={pending} />
                        )}
                    </Definition>
                </dl>
            </section>

            <section id="contact" tabIndex={-1} className="outline-none">
                <h2>{t("accessibility-contact-title")}</h2>
                <p>{t("accessibility-contact-text")}</p>
                <p className="mt-3 font-semibold">
                    <ConfigValue
                        value={information?.accessibility.contact}
                        pending={pending}
                    />
                </p>
            </section>

            <section>
                <h2>{t("accessibility-remedies-title")}</h2>
                <p>
                    {t("accessibility-remedies-before-link")}{" "}
                    <OfficialLink href="https://formulaire.defenseurdesdroits.fr/">
                        {t("accessibility-remedies-link")}
                    </OfficialLink>
                    {t("accessibility-remedies-after-link")}
                </p>
            </section>
        </LegalPage>
    )
}
