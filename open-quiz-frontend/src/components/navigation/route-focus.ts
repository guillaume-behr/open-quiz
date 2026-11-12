import { NavigationType } from "react-router"

/**
 * Whether a navigation leads to another screen, where focus moves to the
 * main content. A `replace` or a state-only change (e.g. a dashboard section
 * switch) keeps keyboard users where they are.
 */
export function shouldMoveFocus(
    previousPathname: string,
    pathname: string,
    navigationType: NavigationType
): boolean {
    return (
        previousPathname !== pathname &&
        navigationType !== NavigationType.Replace
    )
}
