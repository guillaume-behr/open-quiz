import { Fragment, useMemo, type ReactNode } from "react"

import { parseRichText, type RichTextNode } from "@/lib/rich-text"
import { cn } from "@/lib/utils"

function renderNodes(nodes: RichTextNode[]): ReactNode[] {
    return nodes.map((node, index) => {
        switch (node.type) {
            case "text":
                return <Fragment key={index}>{node.text}</Fragment>
            case "code":
                return (
                    <code
                        key={index}
                        className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em] font-normal"
                    >
                        {node.text}
                    </code>
                )
            case "bold":
                return (
                    <strong key={index} className="font-bold">
                        {renderNodes(node.children)}
                    </strong>
                )
            case "italic":
                return (
                    <em key={index} className="italic">
                        {renderNodes(node.children)}
                    </em>
                )
        }
    })
}

type RichTextProps = {
    text: string
    className?: string
}

/**
 * A question prompt with its light formatting: bold, italic, inline code and
 * the line breaks the teacher typed. The text is rendered by React, never as
 * HTML, so a prompt cannot inject markup.
 */
export function RichText({ text, className }: RichTextProps) {
    const content = useMemo(() => renderNodes(parseRichText(text)), [text])
    return (
        <span className={cn("break-words whitespace-pre-wrap", className)}>
            {content}
        </span>
    )
}
