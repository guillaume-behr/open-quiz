import { usePublicInformation } from "@/hooks/use-public-information"
import { CircleAlert } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router"
import {
    LegalPage,
    LoadFailureNotice,
    ConfigValue,
    Definition,
    OfficialLink,
} from "./legal-page"

export function LegalNoticesPage() {
    const { t } = useTranslation()
    const { information, loadFailed } = usePublicInformation()
    const pending = !information && !loadFailed
    const hostInformationMissing =
        information !== null &&
        (!information.host.name.trim() ||
            !information.host.address.trim() ||
            !information.host.phone?.trim())

    return (
        <LegalPage
            titleKey="legal-notice-title"
            descriptionKey="legal-notice-description"
        >
            <LoadFailureNotice show={loadFailed} />
            {hostInformationMissing ? (
                <div
                    className="flex gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4"
                    role="alert"
                >
                    <CircleAlert
                        className="mt-0.5 size-5 shrink-0 text-destructive"
                        aria-hidden="true"
                    />
                    <p>{t("legal-notice-host-warning")}</p>
                </div>
            ) : null}

            <section>
                <h2>{t("legal-notice-non-professional-title")}</h2>
                <p>{t("legal-notice-non-professional-text")}</p>
            </section>

            <section>
                <h2>{t("legal-notice-hosting-title")}</h2>
                <dl>
                    <Definition term={t("legal-notice-host-name")}>
                        <ConfigValue
                            value={information?.host.name}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("legal-notice-host-address")}>
                        <ConfigValue
                            value={information?.host.address}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("legal-notice-host-phone")}>
                        <ConfigValue
                            value={information?.host.phone}
                            pending={pending}
                        />
                    </Definition>
                </dl>
            </section>

            <section>
                <h2>{t("legal-notice-software-title")}</h2>
                <p>
                    {t("legal-notice-software-before-link")}{" "}
                    <OfficialLink href="https://github.com/guillaume-behr/open-quiz">
                        {t("legal-notice-repository-link")}
                    </OfficialLink>
                    {t("legal-notice-software-after-link")}
                </p>
                <p className="mt-3">{t("legal-notice-educational-content")}</p>
            </section>

            <section>
                <h2>{t("legal-notice-related-title")}</h2>
                <p>{t("legal-notice-related-intro")}</p>
                <ul className="mt-2 list-disc space-y-2 ps-6">
                    <li>
                        <Link to="/privacy">{t("privacy-title")}</Link>
                    </li>
                    <li>
                        <Link to="/accessibility">
                            {t("accessibility-title")}
                        </Link>
                    </li>
                </ul>
            </section>
        </LegalPage>
    )
}
