import { usePublicInformation } from "@/hooks/use-public-information"
import { useTranslation } from "react-i18next"
import {
    LegalPage,
    LoadFailureNotice,
    ConfigValue,
    Definition,
    OfficialLink,
} from "./legal-page"

export function PrivacyPage() {
    const { t } = useTranslation()
    const { information, loadFailed } = usePublicInformation()
    const pending = !information && !loadFailed
    const quizDays = information?.privacy.quiz_result_retention_days
    const trainingDays = information?.privacy.training_result_retention_days
    const reportDays = information?.privacy.problem_report_retention_days

    return (
        <LegalPage
            titleKey="privacy-title"
            descriptionKey="privacy-description"
        >
            <LoadFailureNotice show={loadFailed} />

            <section>
                <h2>{t("privacy-controller-title")}</h2>
                <dl>
                    <Definition term={t("privacy-controller-name")}>
                        <ConfigValue
                            value={information?.privacy.controller_name}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("privacy-rights-contact")}>
                        <ConfigValue
                            value={information?.privacy.controller_contact}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("privacy-dpo-contact")}>
                        <ConfigValue
                            value={information?.privacy.dpo_contact}
                            pending={pending}
                        />
                    </Definition>
                </dl>
                <p className="mt-4 text-muted-foreground">
                    {t("privacy-controller-note")}
                </p>
            </section>

            <section>
                <h2>{t("privacy-purposes-title")}</h2>
                <p>{t("privacy-purposes-text")}</p>
            </section>

            <section>
                <h2>{t("privacy-legal-basis-title")}</h2>
                <ConfigValue
                    value={information?.privacy.legal_basis}
                    pending={pending}
                />
                <p className="mt-3 text-muted-foreground">
                    {t("privacy-legal-basis-note")}
                </p>
            </section>

            <section>
                <h2>{t("privacy-data-title")}</h2>
                <p>{t("privacy-data-text")}</p>
                <p className="mt-3">{t("privacy-data-source")}</p>
                <p className="mt-3 text-muted-foreground">
                    {t("privacy-data-obligation")}
                </p>
            </section>

            <section>
                <h2>{t("privacy-recipients-title")}</h2>
                <ConfigValue
                    value={information?.privacy.recipients}
                    pending={pending}
                />
                <p className="mt-3 text-muted-foreground">
                    {t("privacy-recipients-note")}
                </p>
            </section>

            <section>
                <h2>{t("privacy-transfers-title")}</h2>
                <p>{t("privacy-transfers-text")}</p>
            </section>

            <section>
                <h2>{t("privacy-retention-title")}</h2>
                <dl>
                    <Definition term={t("privacy-retention-quiz-label")}>
                        {quizDays === undefined ? (
                            <ConfigValue value="" pending={pending} />
                        ) : (
                            t("privacy-retention-quiz-value", {
                                count: quizDays,
                            })
                        )}
                    </Definition>
                    <Definition term={t("privacy-retention-training-label")}>
                        {trainingDays === undefined ? (
                            <ConfigValue value="" pending={pending} />
                        ) : (
                            t("privacy-retention-training-value", {
                                count: trainingDays,
                            })
                        )}
                    </Definition>
                    <Definition term={t("privacy-retention-teachers-label")}>
                        <ConfigValue
                            value={information?.privacy.teacher_data_retention}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("privacy-retention-students-label")}>
                        <ConfigValue
                            value={information?.privacy.student_data_retention}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("privacy-retention-security-label")}>
                        <ConfigValue
                            value={information?.privacy.security_log_retention}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term={t("privacy-retention-reports-label")}>
                        {reportDays === undefined ? (
                            <ConfigValue value="" pending={pending} />
                        ) : (
                            t("privacy-retention-reports-value", {
                                count: reportDays,
                            })
                        )}
                    </Definition>
                </dl>
                <p className="mt-4 text-muted-foreground">
                    {t("privacy-retention-deletion-note")}
                </p>
            </section>

            <section>
                <h2>{t("privacy-decisions-title")}</h2>
                <p>{t("privacy-decisions-text")}</p>
            </section>

            <section>
                <h2>{t("privacy-rights-title")}</h2>
                <p>{t("privacy-rights-text")}</p>
                <p className="mt-3">{t("privacy-rights-consent-text")}</p>
                <p className="mt-3">
                    {t("privacy-complaint-before-link")}{" "}
                    <OfficialLink href="https://www.cnil.fr/fr/plaintes">
                        {t("privacy-cnil-link")}
                    </OfficialLink>
                    {t("privacy-complaint-after-link")}
                </p>
            </section>

            <section>
                <h2>{t("privacy-education-title")}</h2>
                <p>{t("privacy-education-text")}</p>
            </section>
        </LegalPage>
    )
}
