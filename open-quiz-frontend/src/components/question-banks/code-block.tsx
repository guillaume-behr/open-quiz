import type { CodeLanguage } from "@/api/api"
import { Highlight, themes } from "prism-react-renderer"

type CodeBlockProps = {
    code: string
    language: CodeLanguage
}

export function CodeBlock({ code, language }: CodeBlockProps) {
    return (
        <Highlight theme={themes.vsDark} code={code} language={language}>
            {({
                className,
                style,
                tokens,
                getLineProps,
                getTokenProps,
            }) => (
                <pre
                    className={`${className} overflow-x-auto rounded-xl border p-4 text-sm leading-6`}
                    style={style}
                    tabIndex={0}
                >
                    <code>
                        {tokens.map((line, lineIndex) => (
                            <span
                                key={lineIndex}
                                {...getLineProps({ line })}
                                className="table-row"
                            >
                                <span
                                    className="table-cell pr-4 text-right text-white/40 select-none"
                                    aria-hidden="true"
                                >
                                    {lineIndex + 1}
                                </span>
                                <span className="table-cell">
                                    {line.map((token, tokenIndex) => (
                                        <span
                                            key={tokenIndex}
                                            {...getTokenProps({ token })}
                                        />
                                    ))}
                                </span>
                            </span>
                        ))}
                    </code>
                </pre>
            )}
        </Highlight>
    )
}
