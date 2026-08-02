import type { CodeLanguage } from "@/api/types"
import { Button } from "@/components/ui/button"
import { runPython as executePython } from "@/components/question-banks/python-runner"
import { LoaderCircle, Play } from "lucide-react"
import { Highlight, themes } from "prism-react-renderer"
import {
    type KeyboardEvent,
    type UIEvent,
    useEffect,
    useRef,
    useState,
} from "react"
import { useTranslation } from "react-i18next"

let pythonExecutionQueue: Promise<void> = Promise.resolve()

function serializePythonExecution<T>(task: () => Promise<T>): Promise<T> {
    const execution = pythonExecutionQueue.then(task, task)
    pythonExecutionQueue = execution.then(
        () => undefined,
        () => undefined
    )
    return execution
}

type CodeBlockProps = {
    code: string
    language: CodeLanguage
    runnable?: boolean
    editable?: boolean
    onCodeChange?: (code: string) => void
    onCodeKeyDown?: (event: KeyboardEvent<HTMLTextAreaElement>) => void
    editorClassName?: string
    maxLength?: number
    required?: boolean
}

export function CodeBlock({
    code,
    language,
    runnable = false,
    editable = false,
    onCodeChange,
    onCodeKeyDown,
    editorClassName = "min-h-40",
    maxLength = 20000,
    required = false,
}: CodeBlockProps) {
    const { t } = useTranslation()
    const [isRunning, setIsRunning] = useState(false)
    const [result, setResult] = useState<string | null>(null)
    const highlightedCodeRef = useRef<HTMLPreElement>(null)
    const currentCodeRef = useRef(code)
    const mountedRef = useRef(true)

    useEffect(() => {
        currentCodeRef.current = code
    }, [code])

    useEffect(() => {
        return () => {
            mountedRef.current = false
        }
    }, [])

    const canRun = runnable && language === "python"

    function syncCodeScroll(event: UIEvent<HTMLTextAreaElement>) {
        const highlightedCode = highlightedCodeRef.current
        if (!highlightedCode) return
        highlightedCode.scrollTop = event.currentTarget.scrollTop
        highlightedCode.scrollLeft = event.currentTarget.scrollLeft
    }

    async function runPython() {
        const source = code
        setIsRunning(true)
        setResult(null)
        try {
            const output = await serializePythonExecution(async () => {
                return (await executePython(source)) || t("python-no-output")
            })
            if (mountedRef.current && currentCodeRef.current === source)
                setResult(output)
        } catch (error) {
            if (mountedRef.current && currentCodeRef.current === source) {
                setResult(
                    `${t("python-run-error")}\n${
                        error instanceof Error ? error.message : String(error)
                    }`
                )
            }
        } finally {
            if (mountedRef.current) setIsRunning(false)
        }
    }

    function changeCode(value: string) {
        currentCodeRef.current = value
        setResult(null)
        onCodeChange?.(value)
    }

    return (
        <div className="overflow-hidden rounded-xl border">
            <Highlight theme={themes.vsDark} code={code} language={language}>
                {({
                    className,
                    style,
                    tokens,
                    getLineProps,
                    getTokenProps,
                }) => (
                    <div className="relative" dir="ltr">
                        {canRun && (
                            <Button
                                type="button"
                                size="sm"
                                variant="secondary"
                                className="absolute top-2 right-2 z-20"
                                onClick={() => void runPython()}
                                disabled={isRunning}
                            >
                                {isRunning ? (
                                    <LoaderCircle className="animate-spin" />
                                ) : (
                                    <Play />
                                )}
                                {t(isRunning ? "running-python" : "run-python")}
                            </Button>
                        )}
                        <pre
                            ref={highlightedCodeRef}
                            className={`${className} p-4 font-mono text-sm leading-6 ${
                                editable
                                    ? `overflow-hidden ${editorClassName}`
                                    : "overflow-x-auto"
                            } ${canRun ? "pr-28" : ""}`}
                            style={style}
                            tabIndex={0}
                            role="region"
                            aria-label={t("code-block-region")}
                        >
                            <code>
                                {tokens.map((line, lineIndex) => (
                                    <span
                                        key={lineIndex}
                                        {...getLineProps({ line })}
                                        className="table-row"
                                    >
                                        <span
                                            className="table-cell w-10 pr-3 text-right text-white/40 select-none"
                                            aria-hidden="true"
                                        >
                                            {lineIndex + 1}
                                        </span>
                                        <span className="table-cell">
                                            {line.map((token, tokenIndex) => (
                                                <span
                                                    key={tokenIndex}
                                                    {...getTokenProps({
                                                        token,
                                                    })}
                                                />
                                            ))}
                                        </span>
                                    </span>
                                ))}
                            </code>
                        </pre>
                        {editable && (
                            <textarea
                                className={`absolute inset-0 z-10 h-full w-full resize-none overflow-auto border-0 bg-transparent pt-4 pr-4 pb-4 pl-14 font-mono text-sm leading-6 text-transparent caret-white outline-none selection:bg-primary/40 ${
                                    canRun ? "pr-28" : ""
                                }`}
                                value={code}
                                onChange={(event) =>
                                    changeCode(event.target.value)
                                }
                                onKeyDown={onCodeKeyDown}
                                onScroll={syncCodeScroll}
                                maxLength={maxLength}
                                required={required}
                                spellCheck={false}
                                aria-label={t("source-code")}
                            />
                        )}
                    </div>
                )}
            </Highlight>
            {result !== null && (
                <div className="border-t bg-muted/40 p-3">
                    <p className="mb-1 text-xs font-semibold text-muted-foreground">
                        {t("execution-result")}
                    </p>
                    <pre
                        className="overflow-x-auto font-mono text-sm whitespace-pre-wrap"
                        dir="ltr"
                    >
                        {result}
                    </pre>
                </div>
            )}
        </div>
    )
}
