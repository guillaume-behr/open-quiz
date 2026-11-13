import type { CodeLanguage } from "@/api/types"
import { Button } from "@/components/ui/button"
import {
    describePythonFailure,
    runPython as executePython,
} from "@/components/question-banks/python-runner"
import { LoaderCircle, Play } from "lucide-react"
import { Highlight, themes } from "prism-react-renderer"
import {
    type KeyboardEvent,
    memo,
    type Ref,
    type UIEvent,
    useDeferredValue,
    useEffect,
    useId,
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

/**
 * Read-only code surface sharing the CodeBlock look. CodeBlock itself carries
 * buttons and a textarea, so it cannot be nested inside a clickable label.
 */
export function StaticCodeBlock({
    code,
    language,
}: {
    code: string
    language: CodeLanguage
}) {
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
                    <pre
                        className={`${className} overflow-x-auto p-4 font-mono text-sm leading-6 [font-variant-ligatures:none]`}
                        style={style}
                        dir="ltr"
                    >
                        <code className="table min-w-full" dir="ltr">
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
                                    <span className="table-cell whitespace-pre">
                                        {line.length === 0 ||
                                        (line.length === 1 &&
                                            line[0]?.content === "") ? (
                                            <span>&#8203;</span>
                                        ) : (
                                            line.map((token, tokenIndex) => (
                                                <span
                                                    key={tokenIndex}
                                                    {...getTokenProps({
                                                        token,
                                                    })}
                                                />
                                            ))
                                        )}
                                    </span>
                                </span>
                            ))}
                        </code>
                    </pre>
                )}
            </Highlight>
        </div>
    )
}

/**
 * The highlighted lines under the editor. Memoised so that a render that does
 * not change the code (a deferred keystroke, a sibling's state) skips Prism.
 */
const HighlightedCode = memo(function HighlightedCode({
    code,
    language,
    className: extraClassName,
    label,
    ref,
}: {
    code: string
    language: CodeLanguage
    className: string
    label: string
    ref: Ref<HTMLPreElement>
}) {
    return (
        <Highlight theme={themes.vsDark} code={code} language={language}>
            {({ className, style, tokens, getLineProps, getTokenProps }) => (
                <pre
                    ref={ref}
                    className={`${className} p-4 font-mono text-sm leading-6 [font-variant-ligatures:none] ${extraClassName}`}
                    style={style}
                    tabIndex={0}
                    role="region"
                    aria-label={label}
                >
                    <code className="table min-w-full" dir="ltr">
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
                                <span className="table-cell whitespace-pre">
                                    {line.length === 0 ||
                                    (line.length === 1 &&
                                        line[0]?.content === "") ? (
                                        <span>&#8203;</span>
                                    ) : (
                                        line.map((token, tokenIndex) => (
                                            <span
                                                key={tokenIndex}
                                                {...getTokenProps({ token })}
                                            />
                                        ))
                                    )}
                                </span>
                            </span>
                        ))}
                    </code>
                </pre>
            )}
        </Highlight>
    )
})

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
    const editorHintId = useId()

    useEffect(() => {
        currentCodeRef.current = code
    }, [code])

    useEffect(() => {
        // React Strict Mode runs an extra setup/cleanup cycle in development.
        // Reset the flag during setup so that execution results are not
        // discarded after that development-only cleanup.
        mountedRef.current = true
        return () => {
            mountedRef.current = false
        }
    }, [])

    const canRun = runnable && language === "python"
    // Prism re-tokenises the whole program: the textarea follows each
    // keystroke at once, and the highlighting under it catches up in a render
    // React may interrupt for the next keystroke.
    const highlightedCode = useDeferredValue(code)

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
                    `${t("python-run-error")}\n${describePythonFailure(error, t)}`
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
                            <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                        ) : (
                            <Play />
                        )}
                        {t(isRunning ? "running-python" : "run-python")}
                    </Button>
                )}
                <HighlightedCode
                    ref={highlightedCodeRef}
                    code={highlightedCode}
                    language={language}
                    className={`${
                        editable
                            ? `overflow-hidden ${editorClassName}`
                            : "overflow-x-auto"
                    } ${canRun ? "pr-28" : ""}`}
                    label={t("code-block-region")}
                />
                {editable && (
                    <textarea
                        wrap="off"
                        className={`absolute inset-0 z-10 h-full w-full resize-none overflow-auto border-0 bg-transparent pt-4 pr-4 pb-4 pl-14 font-mono text-sm leading-6 text-transparent caret-white outline-none [font-variant-ligatures:none] selection:bg-primary/40 ${
                            canRun ? "pr-28" : ""
                        }`}
                        value={code}
                        onChange={(event) => changeCode(event.target.value)}
                        onKeyDown={onCodeKeyDown}
                        onScroll={syncCodeScroll}
                        maxLength={maxLength}
                        required={required}
                        spellCheck={false}
                        autoCorrect="off"
                        autoCapitalize="off"
                        aria-label={t("source-code")}
                        aria-describedby={editorHintId}
                    />
                )}
                {editable && (
                    <span id={editorHintId} className="sr-only">
                        {t("code-editor-keyboard-hint")}
                    </span>
                )}
            </div>
            {result !== null && (
                <div
                    className="border-t bg-muted/40 p-3"
                    role="status"
                    aria-live="polite"
                    aria-atomic="true"
                >
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
