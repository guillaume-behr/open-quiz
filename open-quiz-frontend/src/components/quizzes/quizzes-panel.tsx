import { getAllStudentClasses } from "@/api/classes"
import { ApiError, getLiveAccessToken } from "@/api/client"
import {
    getAllQuestionBanks,
    getChoiceImage,
    getQuestionImage,
    getQuestions,
} from "@/api/question-banks"
import {
    cancelQuizSession,
    createQuiz,
    deleteQuiz,
    deleteQuizSession,
    getAllQuizzes,
    getQuizzes,
    launchQuiz,
    pauseQuizSession,
    previewQuiz,
    resumeQuizSession,
    startQuizSession,
    updateQuiz,
} from "@/api/quizzes"
import type {
    GradeLevel,
    Question,
    QuestionBank,
    Quiz,
    QuizSession,
    StudentClass,
} from "@/api/types"
import { ActiveQuizSessionDialog } from "@/components/quizzes/active-quiz-session-dialog"
import { QuizFormDialog } from "@/components/quizzes/quiz-form-dialog"
import {
    LaunchQuizDialog,
    PrintQuizDialog,
    QuizPreviewDialog,
    SessionActionDialog,
} from "@/components/quizzes/quiz-secondary-dialogs"
import { QuizzesList } from "@/components/quizzes/quizzes-list"
import { isActiveSessionStatus } from "@/lib/session-status"
import { connectLiveUpdates } from "@/lib/live-updates"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { FieldError } from "@/components/ui/field"
import { type FormEvent, useEffect, useRef, useState } from "react"
import { LoaderCircle, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { pageContaining } from "@/lib/utils"

type QuizzesPanelProps = {
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
    gradeLevels: GradeLevel[]
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
}

const difficultyKeys = ["easy", "medium", "hard"] as const
const PAGE_SIZE = 8
const PRINT_IMAGE_LOAD_CONCURRENCY = 6

function isActiveSession(session: QuizSession): boolean {
    return isActiveSessionStatus(session.status)
}

type Difficulty = (typeof difficultyKeys)[number]
type DifficultyCounts = Record<Difficulty, number>

function availableQuestionCounts(
    banks: QuestionBank[],
    selectedBankIds: number[]
): DifficultyCounts {
    const selectedBanks = banks.filter((bank) =>
        selectedBankIds.includes(bank.id)
    )
    return difficultyKeys.reduce(
        (result, difficulty) => {
            result[difficulty] = selectedBanks.reduce(
                (total, bank) => total + bank[`${difficulty}_question_count`],
                0
            )
            return result
        },
        { easy: 0, medium: 0, hard: 0 } as DifficultyCounts
    )
}

export function QuizzesPanel({
    isCreateDialogOpen,
    onCreateDialogOpenChange,
    gradeLevels,
    onDeleteGradeLevel,
}: QuizzesPanelProps) {
    const { t, i18n } = useTranslation()
    const [quizzes, setQuizzes] = useState<Quiz[]>([])
    const [page, setPage] = useState(1)
    const [totalPages, setTotalPages] = useState(1)
    const [reloadKey, setReloadKey] = useState(0)
    const [sessions, setSessions] = useState<QuizSession[]>([])
    const [banks, setBanks] = useState<QuestionBank[]>([])
    const [classes, setClasses] = useState<StudentClass[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [supportLoadFailed, setSupportLoadFailed] = useState(false)
    const [quizListLoadFailed, setQuizListLoadFailed] = useState(false)
    const [liveSessionsLoadFailed, setLiveSessionsLoadFailed] = useState(false)
    const [title, setTitle] = useState("")
    const [quizGradeLevel, setQuizGradeLevel] = useState("")
    const [selectedBankIds, setSelectedBankIds] = useState<number[]>([])
    const [durationMinutes, setDurationMinutes] = useState(15)
    const [allowPreviousQuestions, setAllowPreviousQuestions] = useState(false)
    const [allowNegativePoints, setAllowNegativePoints] = useState(false)
    const [sameQuestionsForAll, setSameQuestionsForAll] = useState(false)
    const [difficultyCounts, setDifficultyCounts] = useState({
        easy: 0,
        medium: 0,
        hard: 0,
    })
    const [isCreating, setIsCreating] = useState(false)
    const [createError, setCreateError] = useState<string | null>(null)
    const [editingQuiz, setEditingQuiz] = useState<Quiz | null>(null)
    const [previewedQuiz, setPreviewedQuiz] = useState<Quiz | null>(null)
    const [previewQuestions, setPreviewQuestions] = useState<Question[]>([])
    const [isPreviewLoading, setIsPreviewLoading] = useState(false)
    const [previewError, setPreviewError] = useState<string | null>(null)
    const [quizToLaunch, setQuizToLaunch] = useState<Quiz | null>(null)
    const [selectedClassId, setSelectedClassId] = useState("")
    const [isLaunching, setIsLaunching] = useState(false)
    const [launchError, setLaunchError] = useState<string | null>(null)
    const [quizToPrint, setQuizToPrint] = useState<Quiz | null>(null)
    const [printClassId, setPrintClassId] = useState("")
    const [isPrinting, setIsPrinting] = useState(false)
    const [printError, setPrintError] = useState<string | null>(null)
    const [activeSession, setActiveSession] = useState<QuizSession | null>(null)
    const [activeSessionError, setActiveSessionError] = useState<string | null>(
        null
    )
    const [isStarting, setIsStarting] = useState(false)
    const [sessionAction, setSessionAction] = useState<
        "pause" | "resume" | "cancel" | "delete" | null
    >(null)
    const [sessionActionToConfirm, setSessionActionToConfirm] = useState<
        "cancel" | "delete" | null
    >(null)
    const [quizFilter, setQuizFilter] = useState("")
    const [gradeLevelFilter, setGradeLevelFilter] = useState("")
    const [quizToDelete, setQuizToDelete] = useState<Quiz | null>(null)
    const [isDeleting, setIsDeleting] = useState(false)
    const [deleteError, setDeleteError] = useState<string | null>(null)
    const previewRequestVersion = useRef(0)
    const activeSessionId = activeSession?.id

    useEffect(() => {
        let isActive = true
        Promise.all([getAllQuestionBanks(), getAllStudentClasses()])
            .then(([loadedBanks, loadedClasses]) => {
                if (!isActive) return
                setBanks(loadedBanks)
                setClasses(loadedClasses)
                setSupportLoadFailed(false)
            })
            .catch(() => {
                if (isActive) setSupportLoadFailed(true)
            })
            .finally(() => {
                if (isActive) setIsLoading(false)
            })
        return () => {
            isActive = false
        }
    }, [])

    useEffect(() => {
        let isActive = true
        getQuizzes(page, quizFilter.trim(), gradeLevelFilter, 8)
            .then((result) => {
                if (!isActive) return
                setQuizzes(result.items)
                setTotalPages(result.totalPages)
                setQuizListLoadFailed(false)
                if (result.page > result.totalPages) setPage(result.totalPages)
            })
            .catch(() => {
                if (isActive) setQuizListLoadFailed(true)
            })
            .finally(() => {
                if (isActive) setIsLoading(false)
            })
        return () => {
            isActive = false
        }
    }, [gradeLevelFilter, page, quizFilter, reloadKey])

    useEffect(
        () =>
            connectLiveUpdates<QuizSession[]>({
                path: "/api/quizzes/live/teacher/sessions",
                getToken: getLiveAccessToken,
                onData: (updatedSessions) => {
                    const activeSessions =
                        updatedSessions.filter(isActiveSession)
                    setSessions(activeSessions)
                    setActiveSession((current) => {
                        if (!current) return null
                        return (
                            activeSessions.find(
                                (session) => session.id === current.id
                            ) ?? current
                        )
                    })
                    setLiveSessionsLoadFailed(false)
                },
                onUnavailable: () => setLiveSessionsLoadFailed(true),
            }),
        []
    )

    useEffect(() => {
        if (!activeSessionId) return
        // Keep one subscription for the lifetime of the dialog. Reconnecting
        // around every Start/Pause/Resume request creates a gap exactly while
        // the backend publishes the corresponding state change.
        return connectLiveUpdates<QuizSession>({
            path: `/api/quizzes/live/teacher/sessions/${activeSessionId}`,
            getToken: getLiveAccessToken,
            onData: (session) => {
                setActiveSessionError(null)
                setActiveSession(session)
                setSessions((current) =>
                    isActiveSession(session)
                        ? current.map((item) =>
                              item.id === session.id ? session : item
                          )
                        : current.filter((item) => item.id !== session.id)
                )
            },
            onDeleted: () => {
                setSessions((current) =>
                    current.filter((item) => item.id !== activeSessionId)
                )
                setActiveSession(null)
            },
            onUnavailable: () =>
                setActiveSessionError(t("quiz-session-refresh-error")),
        })
    }, [activeSessionId, t])

    const availableByDifficulty = availableQuestionCounts(
        banks,
        selectedBankIds
    )
    const questionCount = Object.values(difficultyCounts).reduce(
        (total, count) => total + count,
        0
    )
    const quizGradeLevels = gradeLevels
    const loadError =
        supportLoadFailed || quizListLoadFailed || liveSessionsLoadFailed
            ? t("quizzes-load-error")
            : null

    function handleSelectedBankIdsChange(ids: number[]): void {
        setSelectedBankIds(ids)
        const available = availableQuestionCounts(banks, ids)
        setDifficultyCounts((current) => ({
            easy: Math.min(current.easy, available.easy),
            medium: Math.min(current.medium, available.medium),
            hard: Math.min(current.hard, available.hard),
        }))
    }

    function handleDifficultyCountsChange(
        values: Record<Difficulty, number>
    ): void {
        setDifficultyCounts(values)
    }

    function resetCreationForm(): void {
        setTitle("")
        setQuizGradeLevel("")
        setSelectedBankIds([])
        setDurationMinutes(15)
        setAllowPreviousQuestions(false)
        setAllowNegativePoints(false)
        setSameQuestionsForAll(false)
        setDifficultyCounts({ easy: 0, medium: 0, hard: 0 })
        setCreateError(null)
        setEditingQuiz(null)
    }

    function handleQuizGradeLevelChange(level: string): void {
        setQuizGradeLevel(level)
        setSelectedBankIds([])
        setDifficultyCounts({ easy: 0, medium: 0, hard: 0 })
    }

    function openQuizEditor(quiz: Quiz): void {
        setEditingQuiz(quiz)
        setTitle(quiz.title)
        setQuizGradeLevel(quiz.question_banks[0]?.grade_level ?? "")
        setSelectedBankIds(quiz.question_banks.map((bank) => bank.id))
        setDurationMinutes(quiz.duration_seconds / 60)
        setAllowPreviousQuestions(quiz.allow_previous_questions)
        setAllowNegativePoints(quiz.allow_negative_points)
        setSameQuestionsForAll(quiz.same_questions_for_all)
        setDifficultyCounts({
            easy: quiz.easy_question_count,
            medium: quiz.medium_question_count,
            hard: quiz.hard_question_count,
        })
        setCreateError(null)
    }

    async function printExamSubjects(
        quiz: Quiz,
        studentClass: StudentClass,
        printWindow: Window
    ) {
        printWindow.opener = null
        const questionGroups = await Promise.all(
            quiz.question_banks.map((bank) => getQuestions(bank.id))
        )
        const questions = questionGroups.flat()
        const seeded = (seed: number) => () => {
            seed |= 0
            seed = (seed + 0x6d2b79f5) | 0
            let value = Math.imul(seed ^ (seed >>> 15), 1 | seed)
            value =
                (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value
            return ((value ^ (value >>> 14)) >>> 0) / 4294967296
        }
        const shuffle = <T,>(items: T[], random: () => number) => {
            const result = [...items]
            for (let index = result.length - 1; index > 0; index--) {
                const target = Math.floor(random() * (index + 1))
                ;[result[index], result[target]] = [
                    result[target],
                    result[index],
                ]
            }
            return result
        }
        const copies = studentClass.students.map((_, copyIndex) => {
            const random = seeded(
                quiz.id * 1000003 + studentClass.id * 1009 + copyIndex
            )
            const selected = difficultyKeys.flatMap((difficulty) =>
                shuffle(
                    questions.filter(
                        (question) => question.difficulty === difficulty
                    ),
                    random
                ).slice(0, quiz[`${difficulty}_question_count`])
            )
            return shuffle(selected, random).map((question) => ({
                question,
                choices:
                    question.answer_mode === "written"
                        ? []
                        : shuffle(question.choices, random),
            }))
        })
        const printedQuestions = copies.flatMap((copy) =>
            copy.map(({ question }) => question)
        )
        const questionImageIds = [
            ...new Set(
                printedQuestions
                    .filter((question) => question.has_image)
                    .map((question) => question.id)
            ),
        ]
        const choiceImageIds = [
            ...new Set(
                printedQuestions.flatMap((question) =>
                    question.choices
                        .filter((choice) => choice.has_image)
                        .map((choice) => choice.id)
                )
            ),
        ]
        const objectUrls: string[] = []
        let urlsReleased = false
        let imageLoadFailed = false
        const releaseObjectUrls = () => {
            if (urlsReleased) return
            urlsReleased = true
            objectUrls.forEach((url) => URL.revokeObjectURL(url))
        }
        const loadImages = async (
            ids: number[],
            loader: (id: number) => Promise<Blob>
        ) => {
            const entries = new Array<readonly [number, string]>(ids.length)
            let nextIndex = 0
            const loadNext = async (): Promise<void> => {
                while (!imageLoadFailed && nextIndex < ids.length) {
                    const index = nextIndex
                    nextIndex += 1
                    const id = ids[index]
                    let blob: Blob
                    try {
                        blob = await loader(id)
                    } catch (error) {
                        imageLoadFailed = true
                        throw error
                    }
                    if (imageLoadFailed) return
                    const url = URL.createObjectURL(blob)
                    objectUrls.push(url)
                    entries[index] = [id, url]
                }
            }
            await Promise.all(
                Array.from(
                    {
                        length: Math.min(
                            ids.length,
                            PRINT_IMAGE_LOAD_CONCURRENCY
                        ),
                    },
                    () => loadNext()
                )
            )
            return new Map(entries)
        }
        let questionImages: Map<number, string>
        let choiceImages: Map<number, string>
        try {
            ;[questionImages, choiceImages] = await Promise.all([
                loadImages(questionImageIds, getQuestionImage),
                loadImages(choiceImageIds, getChoiceImage),
            ])
        } catch (error) {
            imageLoadFailed = true
            releaseObjectUrls()
            throw error
        }
        const doc = printWindow.document
        doc.documentElement.lang = i18n.resolvedLanguage ?? "fr"
        doc.title = quiz.title
        const style = doc.createElement("style")
        style.textContent = `@page{size:A4;margin:0}*{box-sizing:border-box}body{font-family:Arial,sans-serif;color:#111;margin:0}.subject{width:210mm;min-height:297mm;padding:15mm;break-after:page}.subject:last-child{break-after:auto}header{position:relative;min-height:27mm;border-bottom:2px solid #111;margin-bottom:8mm;padding:1mm 0 4mm 75mm}h1{font-size:20pt;margin:0 0 3mm}.class-name{font-size:10pt;margin:0}.identity{position:absolute;top:0;left:0;width:68mm;border:1.5px solid #111;padding:3mm;font-size:10pt}.identity-line{display:flex;align-items:flex-end;gap:2mm;height:8mm}.identity-blank{flex:1;border-bottom:1px solid #111}.question{break-inside:avoid;margin:0 0 8mm}.question h2{font-size:12pt;margin:0 0 3mm}.question-image{display:block;max-width:100%;max-height:65mm;object-fit:contain;margin:3mm 0}.choice{margin:2mm 0}.choice-content{display:inline}.choice-image{display:block;max-width:85%;max-height:45mm;object-fit:contain;margin:2mm 0 3mm 6mm}.box{display:inline-block;width:4mm;height:4mm;border:1px solid;margin-right:2mm;vertical-align:middle}pre{white-space:pre-wrap;overflow-wrap:anywhere;border:1px solid #bbb;border-radius:2mm;background:#f5f5f5;padding:3mm;margin:3mm 0;font:9pt/1.35 monospace}.code-language{display:block;color:#555;font:8pt Arial,sans-serif;margin-bottom:1mm}.writing{height:35mm;border-bottom:1px dotted #777;background:repeating-linear-gradient(transparent,transparent 8mm,#ddd 8.2mm)}@media print{button,nav{display:none!important}}`
        doc.head.append(style)
        const appendCode = (
            parent: HTMLElement,
            content: string | null,
            language: string | null
        ) => {
            if (!content) return
            const pre = doc.createElement("pre")
            if (language) {
                const label = doc.createElement("span")
                label.className = "code-language"
                label.textContent = language
                pre.append(label)
            }
            const code = doc.createElement("code")
            code.textContent = content
            pre.append(code)
            parent.append(pre)
        }
        copies.forEach((copy) => {
            const section = doc.createElement("section")
            section.className = "subject"
            const header = doc.createElement("header")
            const title = doc.createElement("h1")
            title.textContent = quiz.title
            header.append(title)
            const className = doc.createElement("p")
            className.className = "class-name"
            className.textContent = `${t("class-name")} : ${studentClass.grade_level} ${studentClass.name}`
            header.append(className)
            const identity = doc.createElement("div")
            identity.className = "identity"
            for (const label of [t("last-name"), t("first-name")]) {
                const line = doc.createElement("div")
                line.className = "identity-line"
                const text = doc.createElement("span")
                text.textContent = `${label} :`
                const blank = doc.createElement("span")
                blank.className = "identity-blank"
                line.append(text, blank)
                identity.append(line)
            }
            header.append(identity)
            section.append(header)
            copy.forEach(({ question, choices }, index) => {
                const article = doc.createElement("article")
                article.className = "question"
                const heading = doc.createElement("h2")
                heading.textContent = `${index + 1}. ${question.prompt}`
                article.append(heading)
                const questionImageUrl = questionImages.get(question.id)
                if (questionImageUrl) {
                    const image = doc.createElement("img")
                    image.className = "question-image"
                    image.src = questionImageUrl
                    image.alt = ""
                    article.append(image)
                }
                appendCode(
                    article,
                    question.code_content,
                    question.code_language
                )
                if (question.answer_mode === "written") {
                    const writing = doc.createElement("div")
                    writing.className = "writing"
                    article.append(writing)
                } else
                    choices.forEach((choice) => {
                        const row = doc.createElement("div")
                        row.className = "choice"
                        const box = doc.createElement("span")
                        box.className = "box"
                        const content = doc.createElement("span")
                        content.className = "choice-content"
                        content.textContent = choice.label
                        row.append(box, content)
                        const choiceImageUrl = choiceImages.get(choice.id)
                        if (choiceImageUrl) {
                            const image = doc.createElement("img")
                            image.className = "choice-image"
                            image.src = choiceImageUrl
                            image.alt = ""
                            row.append(image)
                        }
                        appendCode(
                            row,
                            choice.code_content,
                            choice.code_language
                        )
                        article.append(row)
                    })
                section.append(article)
            })
            doc.body.append(section)
        })
        doc.close()
        await Promise.all(
            Array.from(doc.images).map(
                (image) =>
                    new Promise<void>((resolve) => {
                        if (image.complete) return resolve()
                        image.addEventListener("load", () => resolve(), {
                            once: true,
                        })
                        image.addEventListener("error", () => resolve(), {
                            once: true,
                        })
                    })
            )
        )
        printWindow.addEventListener("afterprint", releaseObjectUrls, {
            once: true,
        })
        printWindow.setTimeout(releaseObjectUrls, 120_000)
        printWindow.focus()
        printWindow.setTimeout(() => printWindow.print(), 100)
    }

    async function handlePrint(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!quizToPrint) return
        const studentClass = classes.find(
            (item) => String(item.id) === printClassId
        )
        if (!studentClass || studentClass.students.length === 0) return
        const printWindow = window.open("", "_blank")
        if (!printWindow) {
            setPrintError(t("quiz-print-popup-error"))
            return
        }
        printWindow.opener = null
        setPrintError(null)
        setIsPrinting(true)
        try {
            await printExamSubjects(quizToPrint, studentClass, printWindow)
            setQuizToPrint(null)
            setPrintClassId("")
        } catch {
            printWindow.close()
            setPrintError(t("quiz-print-error"))
        } finally {
            setIsPrinting(false)
        }
    }

    async function handleCreate(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (questionCount === 0 || selectedBankIds.length === 0)
            return setCreateError(null)
        setIsCreating(true)
        try {
            const payload = {
                mode: "exam" as const,
                title: title.trim(),
                source_language:
                    editingQuiz?.source_language ??
                    i18n.resolvedLanguage ??
                    "fr",
                question_bank_ids: selectedBankIds,
                duration_seconds: durationMinutes * 60,
                allow_previous_questions: allowPreviousQuestions,
                allow_negative_points: allowNegativePoints,
                same_questions_for_all: sameQuestionsForAll,
                easy_question_count: difficultyCounts.easy,
                medium_question_count: difficultyCounts.medium,
                hard_question_count: difficultyCounts.hard,
            }
            const isEditing = editingQuiz !== null
            const quiz = isEditing
                ? await updateQuiz(editingQuiz.id, payload)
                : await createQuiz(payload)
            if (isEditing) {
                setQuizzes((current) =>
                    current.map((item) => (item.id === quiz.id ? quiz : item))
                )
            }
            onCreateDialogOpenChange(false)
            resetCreationForm()
            if (!isEditing) {
                setQuizFilter("")
                setGradeLevelFilter("")
                const allQuizzes = await getAllQuizzes().catch(() => [])
                setPage(pageContaining(allQuizzes, quiz.id, PAGE_SIZE))
            }
            setReloadKey((current) => current + 1)
        } catch {
            setCreateError(
                t(editingQuiz ? "quiz-update-error" : "quiz-create-error")
            )
        } finally {
            setIsCreating(false)
        }
    }

    async function openPreview(quiz: Quiz): Promise<void> {
        const requestVersion = ++previewRequestVersion.current
        setPreviewedQuiz(quiz)
        setPreviewQuestions([])
        setPreviewError(null)
        setIsPreviewLoading(true)
        try {
            const questions = await previewQuiz(quiz.id)
            if (requestVersion === previewRequestVersion.current)
                setPreviewQuestions(questions)
        } catch {
            if (requestVersion === previewRequestVersion.current)
                setPreviewError(t("quiz-preview-error"))
        } finally {
            if (requestVersion === previewRequestVersion.current)
                setIsPreviewLoading(false)
        }
    }

    function closePreview(): void {
        previewRequestVersion.current += 1
        setPreviewedQuiz(null)
        setIsPreviewLoading(false)
    }

    async function handleLaunch(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!quizToLaunch) return
        setLaunchError(null)
        setIsLaunching(true)
        try {
            const session = await launchQuiz(
                quizToLaunch.id,
                Number(selectedClassId)
            )
            setSessions((current) =>
                current.some((item) => item.id === session.id)
                    ? current.map((item) =>
                          item.id === session.id ? session : item
                      )
                    : [session, ...current]
            )
            setQuizToLaunch(null)
            setSelectedClassId("")
            setActiveSessionError(null)
            setActiveSession(session)
        } catch {
            setLaunchError(t("quiz-launch-error"))
        } finally {
            setIsLaunching(false)
        }
    }

    async function handleStart(): Promise<void> {
        if (!activeSession) return
        setActiveSessionError(null)
        setIsStarting(true)
        try {
            const started = await startQuizSession(activeSession.id)
            setActiveSession(started)
            setSessions((current) =>
                current.map((session) =>
                    session.id === started.id ? started : session
                )
            )
        } catch {
            setActiveSessionError(t("quiz-start-error"))
        } finally {
            setIsStarting(false)
        }
    }

    function updateSession(updated: QuizSession): void {
        setActiveSession(updated)
        setSessions((current) =>
            current.map((session) =>
                session.id === updated.id ? updated : session
            )
        )
    }

    async function handleSessionAction(
        action: "pause" | "resume" | "cancel"
    ): Promise<void> {
        if (!activeSession) return
        setActiveSessionError(null)
        setSessionAction(action)
        try {
            if (action === "cancel") {
                await cancelQuizSession(activeSession.id)
                setSessions((current) =>
                    current.filter((item) => item.id !== activeSession.id)
                )
                setActiveSession(null)
            } else {
                const updated =
                    action === "pause"
                        ? await pauseQuizSession(activeSession.id)
                        : await resumeQuizSession(activeSession.id)
                updateSession(updated)
            }
            setSessionActionToConfirm(null)
        } catch (caught) {
            setActiveSessionError(
                caught instanceof ApiError && caught.status === 409
                    ? action === "cancel"
                        ? t("quiz-cancel-with-answers-error")
                        : t("quiz-session-action-error")
                    : t("quiz-session-action-error")
            )
        } finally {
            setSessionAction(null)
        }
    }

    async function handleDeleteSession(): Promise<void> {
        if (!activeSession) return
        setActiveSessionError(null)
        setSessionAction("delete")
        try {
            await deleteQuizSession(activeSession.id)
            setSessions((current) =>
                current.filter((session) => session.id !== activeSession.id)
            )
            setSessionActionToConfirm(null)
            setActiveSession(null)
        } catch {
            setActiveSessionError(t("quiz-session-delete-error"))
        } finally {
            setSessionAction(null)
        }
    }

    async function handleDeleteQuiz(): Promise<void> {
        if (!quizToDelete) return
        setDeleteError(null)
        setIsDeleting(true)
        try {
            await deleteQuiz(quizToDelete.id)
            setQuizToDelete(null)
            setReloadKey((k) => k + 1)
        } catch (caught) {
            setDeleteError(
                caught instanceof ApiError && caught.status === 409
                    ? t("quiz-delete-error")
                    : t("quiz-delete-error")
            )
        } finally {
            setIsDeleting(false)
        }
    }

    return (
        <div className="mt-6">
            <QuizzesList
                quizzes={quizzes}
                sessions={sessions}
                gradeLevels={quizGradeLevels}
                isLoading={isLoading}
                loadError={loadError}
                quizFilter={quizFilter}
                gradeLevelFilter={gradeLevelFilter}
                onQuizFilterChange={(value) => {
                    setQuizFilter(value)
                    setPage(1)
                }}
                onGradeLevelFilterChange={(value) => {
                    setGradeLevelFilter(value)
                    setPage(1)
                }}
                onDeleteGradeLevel={onDeleteGradeLevel}
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                onEdit={openQuizEditor}
                onPreview={(quiz) => void openPreview(quiz)}
                onLaunch={(quiz) => {
                    setLaunchError(null)
                    setQuizToLaunch(quiz)
                }}
                onDelete={(quiz) => {
                    setDeleteError(null)
                    setQuizToDelete(quiz)
                }}
                onPrint={(quiz) => {
                    setPrintError(null)
                    setPrintClassId("")
                    setQuizToPrint(quiz)
                }}
                onOpenSession={(quizSession) => {
                    setActiveSessionError(null)
                    setActiveSession(quizSession)
                }}
            />

            <QuizFormDialog
                open={isCreateDialogOpen || editingQuiz !== null}
                editingQuiz={editingQuiz}
                banks={banks}
                gradeLevels={quizGradeLevels}
                quizGradeLevel={quizGradeLevel}
                title={title}
                durationMinutes={durationMinutes}
                selectedBankIds={selectedBankIds}
                allowPreviousQuestions={allowPreviousQuestions}
                allowNegativePoints={allowNegativePoints}
                sameQuestionsForAll={sameQuestionsForAll}
                difficultyCounts={difficultyCounts}
                availableByDifficulty={availableByDifficulty}
                isBusy={isCreating}
                error={createError}
                onTitleChange={setTitle}
                onDurationChange={setDurationMinutes}
                onQuizGradeLevelChange={handleQuizGradeLevelChange}
                onDeleteGradeLevel={onDeleteGradeLevel}
                onSelectedBankIdsChange={handleSelectedBankIdsChange}
                onAllowPreviousQuestionsChange={setAllowPreviousQuestions}
                onAllowNegativePointsChange={setAllowNegativePoints}
                onSameQuestionsForAllChange={setSameQuestionsForAll}
                onDifficultyCountsChange={handleDifficultyCountsChange}
                onClose={() => {
                    onCreateDialogOpenChange(false)
                    resetCreationForm()
                }}
                onSubmit={handleCreate}
            />

            <QuizPreviewDialog
                quiz={previewedQuiz}
                questions={previewQuestions}
                isLoading={isPreviewLoading}
                error={previewError}
                onClose={closePreview}
                onRefresh={(quiz) => void openPreview(quiz)}
            />

            <LaunchQuizDialog
                quiz={quizToLaunch}
                classes={classes}
                selectedClassId={selectedClassId}
                isBusy={isLaunching}
                error={launchError}
                onSelectedClassIdChange={setSelectedClassId}
                onClose={() => setQuizToLaunch(null)}
                onSubmit={handleLaunch}
            />

            <PrintQuizDialog
                quiz={quizToPrint}
                classes={classes}
                selectedClassId={printClassId}
                isBusy={isPrinting}
                error={printError}
                onSelectedClassIdChange={setPrintClassId}
                onClose={() => {
                    setQuizToPrint(null)
                    setPrintClassId("")
                    setPrintError(null)
                }}
                onSubmit={(event) => void handlePrint(event)}
            />

            <ActiveQuizSessionDialog
                session={activeSession}
                error={activeSessionError}
                isStarting={isStarting}
                action={sessionAction}
                onClose={() => {
                    setActiveSession(null)
                    setActiveSessionError(null)
                }}
                onStart={() => void handleStart()}
                onPause={() => void handleSessionAction("pause")}
                onResume={() => void handleSessionAction("resume")}
                onConfirmCancel={() => {
                    setActiveSessionError(null)
                    setSessionActionToConfirm("cancel")
                }}
                onConfirmDelete={() => {
                    setActiveSessionError(null)
                    setSessionActionToConfirm("delete")
                }}
            />

            <SessionActionDialog
                actionToConfirm={sessionActionToConfirm}
                currentAction={sessionAction}
                error={activeSessionError}
                onClose={() => setSessionActionToConfirm(null)}
                onConfirm={(action) =>
                    action === "delete"
                        ? void handleDeleteSession()
                        : void handleSessionAction("cancel")
                }
            />

            <Dialog
                open={quizToDelete !== null}
                onOpenChange={(open) => {
                    if (!open && !isDeleting) setQuizToDelete(null)
                }}
                title={t("delete-quiz")}
                description={t("delete-quiz-help", {
                    title: quizToDelete?.title ?? "",
                })}
                size="sm"
            >
                {deleteError && (
                    <FieldError className="mb-4">{deleteError}</FieldError>
                )}
                <div className="flex justify-end gap-2">
                    <Button
                        variant="outline"
                        disabled={isDeleting}
                        onClick={() => setQuizToDelete(null)}
                    >
                        {t("cancel")}
                    </Button>
                    <Button
                        variant="destructive"
                        disabled={isDeleting}
                        onClick={() => void handleDeleteQuiz()}
                    >
                        {isDeleting ? (
                            <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                        ) : (
                            <Trash2 />
                        )}
                        {t("delete")}
                    </Button>
                </div>
            </Dialog>
        </div>
    )
}
