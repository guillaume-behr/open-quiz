/**
 * Values of HTML pattern attributes, mirroring the API's regular expressions
 * (open-quiz-backend/app/schemas.py). Browsers compile them with the v flag,
 * where a literal "-" inside a character class must be escaped.
 */

/** Login identifiers of teachers and students. */
export const USERNAME_PATTERN = String.raw`[a-zA-Z0-9._\-]+`

/** Six-digit two-factor authentication codes. */
export const TWO_FACTOR_CODE_PATTERN = "[0-9]{6}"
