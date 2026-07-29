import { logout } from "@/api/auth"
import {
    getPublicInformation,
    type PublicInformation,
} from "@/api/public-information"
import { Button } from "@/components/ui/button"
import { CircleAlert, ExternalLink, Trash2 } from "lucide-react"
import { type ReactNode, useEffect, useId, useState } from "react"
import { Link } from "react-router"

const UPDATED_AT = "29 juillet 2026"

function usePublicInformation() {
    const [information, setInformation] = useState<PublicInformation | null>(
        null
    )
    const [loadFailed, setLoadFailed] = useState(false)

    useEffect(() => {
        let active = true
        getPublicInformation()
            .then((result) => {
                if (active) setInformation(result)
            })
            .catch(() => {
                if (active) setLoadFailed(true)
            })
        return () => {
            active = false
        }
    }, [])

    return { information, loadFailed }
}

function usePageTitle(title: string) {
    useEffect(() => {
        const previousTitle = document.title
        document.title = `${title} — Open Quiz`
        return () => {
            document.title = previousTitle
        }
    }, [title])
}

function LegalPage({
    title,
    description,
    children,
}: {
    title: string
    description: string
    children: ReactNode
}) {
    usePageTitle(title)

    return (
        <article
            lang="fr"
            className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-8 sm:py-12"
        >
            <header className="mb-10 border-b pb-8">
                <p className="mb-2 text-sm font-semibold text-primary">
                    Information de l’instance
                </p>
                <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
                    {title}
                </h1>
                <p className="mt-4 max-w-3xl text-base leading-7 text-muted-foreground">
                    {description}
                </p>
                <p className="mt-3 text-sm text-muted-foreground">
                    Dernière mise à jour : {UPDATED_AT}
                </p>
            </header>
            <div className="space-y-10 [&_a]:font-medium [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4 [&_h2]:mb-3 [&_h2]:text-2xl [&_h2]:font-bold [&_h3]:mb-2 [&_h3]:text-lg [&_h3]:font-bold [&_li]:leading-7 [&_p]:leading-7">
                {children}
            </div>
        </article>
    )
}

function LoadFailureNotice({ show }: { show: boolean }) {
    if (!show) return null
    return (
        <div
            className="flex gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4"
            role="alert"
        >
            <CircleAlert
                className="mt-0.5 size-5 shrink-0 text-destructive"
                aria-hidden="true"
            />
            <p>
                Les informations propres à cette instance ne sont pas
                disponibles. Contactez son exploitant avant de lui confier des
                données personnelles.
            </p>
        </div>
    )
}

function ConfigValue({
    value,
    pending,
}: {
    value: string | undefined
    pending: boolean
}) {
    if (pending) {
        return <span aria-busy="true">Chargement…</span>
    }
    if (!value) {
        return (
            <strong className="text-destructive">
                Non renseigné — information à compléter
            </strong>
        )
    }
    return <span className="whitespace-pre-line">{value}</span>
}

function Definition({ term, children }: { term: string; children: ReactNode }) {
    return (
        <div className="grid gap-1 border-b py-4 last:border-b-0 sm:grid-cols-[13rem_1fr] sm:gap-6">
            <dt className="font-semibold">{term}</dt>
            <dd className="min-w-0 text-muted-foreground">{children}</dd>
        </div>
    )
}

function OfficialLink({
    href,
    children,
}: {
    href: string
    children: ReactNode
}) {
    return (
        <a href={href} target="_blank" rel="noreferrer">
            {children}
            <ExternalLink className="ms-1 inline size-3.5" aria-hidden="true" />
        </a>
    )
}

export function LegalNoticesPage() {
    const { information, loadFailed } = usePublicInformation()
    const pending = !information && !loadFailed
    const hostInformationMissing =
        information !== null &&
        (!information.host.name.trim() || !information.host.address.trim())

    return (
        <LegalPage
            title="Mentions légales"
            description="Informations publiées dans le cadre d’une édition non professionnelle préservant l’anonymat de l’éditeur."
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
                    <p>
                        Les informations de l’hébergeur ne sont pas configurées.
                        Ces mentions légales sont incomplètes et doivent être
                        renseignées par l’exploitant de cette instance.
                    </p>
                </div>
            ) : null}

            <section>
                <h2>Édition non professionnelle</h2>
                <p>
                    L’éditeur de cette instance conserve son anonymat
                    conformément à l’article 1-1, II, de la loi n° 2004-575 du
                    21 juin 2004. Ce régime suppose que ses éléments
                    d’identification personnelle soient communiqués à
                    l’hébergeur ; ils ne sont pas demandés ni publiés par ce
                    service.
                </p>
            </section>

            <section>
                <h2>Hébergement</h2>
                <dl>
                    <Definition term="Hébergeur">
                        <ConfigValue
                            value={information?.host.name}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term="Adresse">
                        <ConfigValue
                            value={information?.host.address}
                            pending={pending}
                        />
                    </Definition>
                </dl>
            </section>

            <section>
                <h2>Logiciel et propriété intellectuelle</h2>
                <p>
                    Cette instance utilise Open Quiz, logiciel libre distribué
                    sous licence MIT. Le code source et le texte de la licence
                    sont publiés sur{" "}
                    <OfficialLink href="https://github.com/guillaume-behr/open-quiz">
                        le dépôt officiel du projet
                    </OfficialLink>
                    . Le projet logiciel et l’organisme qui exploite cette
                    instance sont deux entités distinctes.
                </p>
                <p className="mt-3">
                    Les contenus pédagogiques ajoutés par les utilisateurs
                    restent soumis aux droits et autorisations qui leur sont
                    applicables. Open Quiz ne leur attribue pas automatiquement
                    une licence.
                </p>
            </section>

            <section>
                <h2>Données et accessibilité</h2>
                <p>
                    Les modalités relatives aux traitements sont décrites dans
                    la page{" "}
                    <Link to="/donnees-personnelles">Données personnelles</Link>
                    . L’état d’accessibilité est publié dans la page{" "}
                    <Link to="/accessibilite">Accessibilité</Link>.
                </p>
            </section>
        </LegalPage>
    )
}

export function PrivacyPage() {
    const { information, loadFailed } = usePublicInformation()
    const pending = !information && !loadFailed
    const retentionDays = information?.privacy.quiz_result_retention_days

    return (
        <LegalPage
            title="Données personnelles"
            description="Information destinée aux enseignants, personnels, élèves et représentants légaux concernés par l’utilisation de cette instance."
        >
            <LoadFailureNotice show={loadFailed} />

            <section>
                <h2>Qui est responsable du traitement ?</h2>
                <dl>
                    <Definition term="Responsable du traitement">
                        <ConfigValue
                            value={information?.privacy.controller_name}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term="Exercer vos droits">
                        <ConfigValue
                            value={information?.privacy.controller_contact}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term="Délégué à la protection des données">
                        <ConfigValue
                            value={information?.privacy.dpo_contact}
                            pending={pending}
                        />
                    </Definition>
                </dl>
                <p className="mt-4 text-muted-foreground">
                    Dans l’enseignement public, la qualité de responsable du
                    traitement dépend de l’initiative du déploiement et du degré
                    d’enseignement. Elle doit être déterminée avant la mise en
                    service avec le DPO compétent ; elle n’est pas attribuée
                    automatiquement aux auteurs du logiciel.
                </p>
            </section>

            <section>
                <h2>Pourquoi les données sont-elles traitées ?</h2>
                <ul className="list-disc space-y-2 ps-6">
                    <li>
                        administrer et sécuriser les comptes des enseignants et
                        administrateurs ;
                    </li>
                    <li>
                        créer les classes, listes d’élèves, banques de questions
                        et quiz nécessaires à l’activité pédagogique ;
                    </li>
                    <li>
                        permettre aux élèves de rejoindre un quiz, enregistrer
                        leurs réponses, calculer les scores des questions
                        objectives et permettre la correction des réponses
                        écrites ;
                    </li>
                    <li>
                        signaler à l’enseignant les sorties du plein écran, de
                        la fenêtre ou de l’onglet pendant un quiz surveillé ;
                    </li>
                    <li>
                        protéger le service par l’authentification à deux
                        facteurs, la limitation des tentatives et des journaux
                        de sécurité.
                    </li>
                </ul>
            </section>

            <section>
                <h2>Fondement juridique</h2>
                <p>
                    <ConfigValue
                        value={information?.privacy.legal_basis}
                        pending={pending}
                    />
                </p>
                <p className="mt-3 text-muted-foreground">
                    Pour une autorité publique, une mission d’intérêt public ne
                    peut être retenue que si le traitement est nécessaire à une
                    mission définie par le droit. Le consentement de l’élève ne
                    doit donc pas être indiqué par défaut.
                </p>
            </section>

            <section>
                <h2>Quelles données ?</h2>
                <ul className="list-disc space-y-2 ps-6">
                    <li>
                        <strong>Enseignants et administrateurs :</strong>{" "}
                        identifiant, nom affiché, empreinte du mot de passe,
                        secret de double authentification chiffré, état et dates
                        du compte, sessions de connexion.
                    </li>
                    <li>
                        <strong>Élèves :</strong> identifiant choisi par
                        l’établissement, nom affiché, classe et niveau.
                    </li>
                    <li>
                        <strong>Activité pédagogique :</strong> participation,
                        réponses, scores, état de correction et dates.
                    </li>
                    <li>
                        <strong>Surveillance du quiz :</strong> nombre, type et
                        date du dernier événement détecté (plein écran quitté,
                        pointeur sorti, fenêtre quittée ou onglet masqué).
                    </li>
                    <li>
                        <strong>Sécurité :</strong> adresse IP dans les journaux
                        d’authentification, identifiants techniques hachés,
                        tentatives et dates d’expiration.
                    </li>
                    <li>
                        <strong>Signalements :</strong> message libre, page
                        concernée et date d’envoi. Le formulaire ne demande ni
                        nom, ni adresse, ni compte utilisateur.
                    </li>
                </ul>
                <p className="mt-3">
                    Les données proviennent de l’administrateur, de l’enseignant
                    et de l’élève lors de l’utilisation du service. Le code
                    fourni n’intègre ni publicité, ni outil de profilage, ni
                    mesure d’audience.
                </p>
            </section>

            <section>
                <h2>Qui peut y accéder ?</h2>
                <p>
                    <ConfigValue
                        value={information?.privacy.recipients}
                        pending={pending}
                    />
                </p>
                <p className="mt-3 text-muted-foreground">
                    Dans l’application, l’administrateur gère les comptes ;
                    chaque enseignant accède aux classes, quiz et résultats dont
                    il est propriétaire ; l’élève accède uniquement à sa session
                    au moyen du code et de son jeton temporaire. Tout hébergeur
                    ou prestataire ayant un accès technique doit être encadré
                    par l’exploitant.
                </p>
            </section>

            <section>
                <h2>Combien de temps ?</h2>
                <dl>
                    <Definition term="Résultats de quiz terminés">
                        {retentionDays === undefined ? (
                            <ConfigValue value="" pending={pending} />
                        ) : (
                            <>
                                Suppression automatique après {retentionDays}{" "}
                                jour{retentionDays > 1 ? "s" : ""}, avec
                                suppression anticipée possible par l’enseignant.
                            </>
                        )}
                    </Definition>
                    <Definition term="Comptes enseignants">
                        <ConfigValue
                            value={information?.privacy.teacher_data_retention}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term="Classes et données élèves">
                        <ConfigValue
                            value={information?.privacy.student_data_retention}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term="Journaux de sécurité">
                        <ConfigValue
                            value={information?.privacy.security_log_retention}
                            pending={pending}
                        />
                    </Definition>
                    <Definition term="Signalements de problèmes">
                        {information?.privacy.problem_report_retention_days ===
                        undefined ? (
                            <ConfigValue value="" pending={pending} />
                        ) : (
                            <>
                                Suppression par l’administrateur ou
                                automatiquement après{" "}
                                {
                                    information.privacy
                                        .problem_report_retention_days
                                }{" "}
                                jours au maximum.
                            </>
                        )}
                    </Definition>
                </dl>
            </section>

            <section>
                <h2>Décisions et surveillance</h2>
                <p>
                    Les scores des questions à choix sont calculés à partir du
                    barème défini par l’enseignant. Les réponses écrites
                    nécessitent une correction humaine. Les événements de
                    surveillance sont des alertes factuelles présentées à
                    l’enseignant : le logiciel ne prononce aucune sanction et ne
                    prend aucune décision automatique à leur sujet.
                </p>
            </section>

            <section>
                <h2>Vos droits</h2>
                <p>
                    Selon le fondement et la situation, vous pouvez demander
                    l’accès, la rectification, l’effacement ou la limitation des
                    données, et vous opposer au traitement pour des raisons
                    tenant à votre situation particulière. Adressez votre
                    demande au responsable du traitement ou à son DPO indiqués
                    plus haut. Une preuve d’identité peut être demandée
                    uniquement si un doute raisonnable existe.
                </p>
                <p className="mt-3">
                    Si la réponse ne vous satisfait pas, vous pouvez introduire
                    une réclamation auprès de la{" "}
                    <OfficialLink href="https://www.cnil.fr/fr/plaintes">
                        Commission nationale de l’informatique et des libertés
                    </OfficialLink>
                    .
                </p>
            </section>

            <section>
                <h2>Avant un usage dans l’Éducation nationale</h2>
                <p>
                    Le responsable du traitement doit notamment consulter son
                    DPO, inscrire le traitement au registre, vérifier la
                    nécessité et la proportionnalité des données — en
                    particulier la surveillance —, encadrer les sous-traitants
                    et informer les élèves et leurs représentants dans un
                    langage adapté. La mise à disposition du code ne constitue
                    ni une homologation, ni une certification ministérielle.
                </p>
            </section>
        </LegalPage>
    )
}

export function AccessibilityPage() {
    const { information, loadFailed } = usePublicInformation()
    const pending = !information && !loadFailed

    return (
        <LegalPage
            title="Déclaration d’accessibilité"
            description="L’exploitant de cette instance s’engage à rendre son service accessible conformément à l’article 47 de la loi n° 2005-102."
        >
            <LoadFailureNotice show={loadFailed} />

            <section className="rounded-lg border-2 border-destructive/40 bg-destructive/5 p-5">
                <h2>État de conformité</h2>
                <p className="text-lg font-bold">
                    Accessibilité : non conforme
                </p>
                <p className="mt-2">
                    Aucun audit RGAA complet et en cours de validité n’est
                    fourni avec le logiciel. En l’absence d’un tel résultat,
                    aucun taux de conformité ne peut être annoncé.
                </p>
            </section>

            <section>
                <h2>Résultats des tests</h2>
                <p>
                    Aucun audit de conformité au RGAA 4.1.2 n’a encore été
                    réalisé ou publié pour cette instance. Les contenus non
                    accessibles, dérogations et alternatives ne peuvent donc pas
                    être listés de manière fiable à ce stade.
                </p>
            </section>

            <section>
                <h2>Établissement de cette déclaration</h2>
                <p>
                    Cette déclaration a été établie le {UPDATED_AT} à partir de
                    l’état connu du logiciel. Elle doit être révisée par
                    l’exploitant après un audit représentatif de l’instance, de
                    ses contenus et de sa configuration.
                </p>
                <p className="mt-3">
                    Technologies utilisées : HTML, CSS, JavaScript, WAI-ARIA et
                    WebAssembly pour l’exécution locale facultative de code
                    Python dans les questions.
                </p>
            </section>

            <section>
                <h2>Schéma et plan d’action</h2>
                <dl>
                    <Definition term="Schéma pluriannuel">
                        {information?.accessibility.scheme_url ? (
                            <OfficialLink
                                href={information.accessibility.scheme_url}
                            >
                                Consulter le schéma pluriannuel
                            </OfficialLink>
                        ) : (
                            <ConfigValue value="" pending={pending} />
                        )}
                    </Definition>
                    <Definition term="Plan d’action en cours">
                        {information?.accessibility.action_plan_url ? (
                            <OfficialLink
                                href={information.accessibility.action_plan_url}
                            >
                                Consulter le plan d’action
                            </OfficialLink>
                        ) : (
                            <ConfigValue value="" pending={pending} />
                        )}
                    </Definition>
                </dl>
            </section>

            <section id="contact" tabIndex={-1}>
                <h2>Retour d’information et contact</h2>
                <p>
                    Si vous ne parvenez pas à accéder à un contenu ou à un
                    service, contactez l’exploitant afin d’être orienté vers une
                    alternative accessible :
                </p>
                <p className="mt-3 font-semibold">
                    <ConfigValue
                        value={information?.accessibility.contact}
                        pending={pending}
                    />
                </p>
            </section>

            <section>
                <h2>Voies de recours</h2>
                <p>
                    Si vous avez signalé un défaut d’accessibilité qui vous
                    empêche d’accéder à un contenu ou à une fonctionnalité et
                    que vous n’avez pas obtenu de réponse satisfaisante, vous
                    pouvez saisir gratuitement le{" "}
                    <OfficialLink href="https://formulaire.defenseurdesdroits.fr/">
                        Défenseur des droits
                    </OfficialLink>
                    , contacter son délégué dans votre région ou appeler le 09
                    69 39 00 00.
                </p>
            </section>
        </LegalPage>
    )
}

const LOCAL_STORAGE_KEYS = ["i18nextLng", "vite-ui-theme"]
const SESSION_STORAGE_KEYS = ["open-quiz-student-session"]

export function CookiesPage() {
    const { information, loadFailed } = usePublicInformation()
    const [cleared, setCleared] = useState(false)
    const statusId = useId()
    const maxAge = information?.cookies.authentication_max_age_days

    async function clearLocalData() {
        await logout().catch(() => undefined)
        try {
            for (const key of LOCAL_STORAGE_KEYS) {
                localStorage.removeItem(key)
            }
            for (const key of SESSION_STORAGE_KEYS) {
                sessionStorage.removeItem(key)
            }
        } catch {
            // The server-side session is still revoked when browser storage is disabled.
        }
        setCleared(true)
    }

    return (
        <LegalPage
            title="Gestion des cookies"
            description="Inventaire des cookies et autres stockages utilisés par Open Quiz, avec un contrôle permettant de supprimer les données conservées sur cet appareil."
        >
            <LoadFailureNotice show={loadFailed} />

            <section>
                <h2>Aucun traceur publicitaire ou de mesure d’audience</h2>
                <p>
                    Le code fourni n’installe aucun outil publicitaire, bouton
                    de réseau social, outil de profilage ou mesure d’audience.
                    Il n’émet que les données techniques strictement nécessaires
                    à l’authentification et aux choix demandés par
                    l’utilisateur. Aucun bandeau de consentement n’est donc
                    affiché.
                </p>
            </section>

            <section>
                <h2>Cookie strictement nécessaire</h2>
                <div className="overflow-x-auto">
                    <table className="w-full min-w-[42rem] border-collapse text-left">
                        <caption className="sr-only">
                            Cookie d’authentification utilisé par Open Quiz
                        </caption>
                        <thead>
                            <tr className="border-b">
                                <th className="p-3">Nom</th>
                                <th className="p-3">Finalité</th>
                                <th className="p-3">Durée</th>
                                <th className="p-3">Protection</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr className="border-b align-top">
                                <td className="p-3 font-mono text-sm">
                                    open_quiz_refresh
                                </td>
                                <td className="p-3">
                                    Maintenir et renouveler la session d’un
                                    enseignant ou administrateur authentifié.
                                </td>
                                <td className="p-3">
                                    {maxAge === undefined ? (
                                        <ConfigValue
                                            value=""
                                            pending={!loadFailed}
                                        />
                                    ) : (
                                        `${maxAge} jour${maxAge > 1 ? "s" : ""} au maximum, ou jusqu’à la déconnexion.`
                                    )}
                                </td>
                                <td className="p-3">
                                    HttpOnly, SameSite=Strict, Secure en
                                    production, limité au chemin
                                    d’authentification et renouvelé pendant la
                                    session.
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </section>

            <section>
                <h2>Stockages locaux nécessaires ou demandés</h2>
                <div className="overflow-x-auto">
                    <table className="w-full min-w-[48rem] border-collapse text-left">
                        <caption className="sr-only">
                            Stockages locaux utilisés par Open Quiz
                        </caption>
                        <thead>
                            <tr className="border-b">
                                <th className="p-3">Nom</th>
                                <th className="p-3">Type</th>
                                <th className="p-3">Contenu et finalité</th>
                                <th className="p-3">Durée</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr className="border-b align-top">
                                <td className="p-3 font-mono text-sm">
                                    i18nextLng
                                </td>
                                <td className="p-3">Stockage local</td>
                                <td className="p-3">
                                    Langue choisie pour l’interface.
                                </td>
                                <td className="p-3">
                                    Jusqu’à sa suppression sur cet appareil.
                                </td>
                            </tr>
                            <tr className="border-b align-top">
                                <td className="p-3 font-mono text-sm">
                                    vite-ui-theme
                                </td>
                                <td className="p-3">Stockage local</td>
                                <td className="p-3">
                                    Thème clair, sombre ou système choisi.
                                </td>
                                <td className="p-3">
                                    Jusqu’à sa suppression sur cet appareil.
                                </td>
                            </tr>
                            <tr className="border-b align-top">
                                <td className="p-3 font-mono text-sm">
                                    open-quiz-student-session
                                </td>
                                <td className="p-3">Stockage de session</td>
                                <td className="p-3">
                                    Code du quiz, identifiant de l’élève et
                                    jeton participant permettant de reprendre le
                                    quiz dans le même onglet.
                                </td>
                                <td className="p-3">
                                    Jusqu’à la fermeture de l’onglet, le départ
                                    volontaire du quiz ou la suppression
                                    ci-dessous.
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </section>

            <section>
                <h2>Supprimer les données de cet appareil</h2>
                <p>
                    Cette action déconnecte la session enseignant ou
                    administrateur, oublie la session élève de cet onglet et
                    efface les préférences de langue et de thème. Elle ne
                    supprime pas les réponses et résultats conservés sur le
                    serveur ; pour ceux-ci, consultez la page{" "}
                    <Link to="/donnees-personnelles">Données personnelles</Link>
                    .
                </p>
                <Button
                    className="mt-4"
                    variant="outline"
                    onClick={() => void clearLocalData()}
                    aria-describedby={statusId}
                >
                    <Trash2 aria-hidden="true" />
                    Effacer et me déconnecter
                </Button>
                <p
                    id={statusId}
                    className="mt-3 text-sm font-medium"
                    role="status"
                >
                    {cleared
                        ? "Les données locales et la session de connexion ont été supprimées."
                        : ""}
                </p>
            </section>

            <section>
                <h2>Évolution du service</h2>
                <p>
                    Si l’exploitant ajoute ultérieurement un traceur non
                    strictement nécessaire, il devra mettre à jour cette page,
                    empêcher son dépôt avant le choix de l’utilisateur et
                    proposer d’accepter ou de refuser avec la même facilité.
                </p>
            </section>
        </LegalPage>
    )
}
