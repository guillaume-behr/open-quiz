import {
    getChoiceImage,
    getQuestionImage,
    getQuestions,
} from "@/api/question-banks"
import type { Quiz, StudentClass } from "@/api/types"
import { difficultyKeys } from "@/components/quizzes/quiz-form-state"
import type { TFunction } from "i18next"

const PRINT_IMAGE_LOAD_CONCURRENCY = 6

/**
 * Writes one paper copy of the exam per student of the class into
 * printWindow, then opens the print dialog. Each copy draws and orders its
 * questions and choices from a seed, so printing again gives the same copies.
 */
export async function printExamSubjects(
    quiz: Quiz,
    studentClass: StudentClass,
    printWindow: Window,
    t: TFunction,
    language: string
): Promise<void> {
    printWindow.opener = null
    const questionGroups = await Promise.all(
        quiz.question_banks.map((bank) => getQuestions(bank.id))
    )
    const questions = questionGroups.flat()
    const seeded = (seed: number) => () => {
        seed |= 0
        seed = (seed + 0x6d2b79f5) | 0
        let value = Math.imul(seed ^ (seed >>> 15), 1 | seed)
        value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value
        return ((value ^ (value >>> 14)) >>> 0) / 4294967296
    }
    const shuffle = <T>(items: T[], random: () => number) => {
        const result = [...items]
        for (let index = result.length - 1; index > 0; index--) {
            const target = Math.floor(random() * (index + 1))
            ;[result[index], result[target]] = [result[target], result[index]]
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
                    length: Math.min(ids.length, PRINT_IMAGE_LOAD_CONCURRENCY),
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
    doc.documentElement.lang = language
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
            appendCode(article, question.code_content, question.code_language)
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
                    appendCode(row, choice.code_content, choice.code_language)
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
