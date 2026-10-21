export const POST_MAX_LENGTH = 1000
export const COMMENT_MAX_LENGTH = 100

/**
 * Mirrors the server side rules in backend/app/moderation.py so the browser
 * can reject invalid input before a request is sent. The server remains the
 * authority; these helpers only improve the feedback loop.
 */
export function validateContent(text, maximum) {
  if (typeof text !== 'string' || text.length === 0) {
    return 'Text cannot be empty.'
  }
  if (!text.trim()) {
    return 'Text cannot be empty.'
  }
  if (text.length > maximum) {
    return `Text must be ${maximum} characters or fewer.`
  }
  const normalised = text.replace(/\r\n/g, '\n')
  if (/\n[ \t]*\n/.test(normalised)) {
    return 'Blank lines and multiple paragraphs are not allowed.'
  }
  const lines = normalised.split('\n')
  if (lines.length > 1 && lines[lines.length - 1] === '') {
    lines.pop()
  }
  if (lines.some((line) => line.trim() === '')) {
    return 'Empty lines are not allowed.'
  }
  return null
}

export function validatePost(text) {
  return validateContent(text, POST_MAX_LENGTH)
}

export function validateComment(text) {
  return validateContent(text, COMMENT_MAX_LENGTH)
}

export function isPasswordStrong(password) {
  if (typeof password !== 'string' || password.length < 12) return false
  return (
    /[a-z]/.test(password) &&
    /[A-Z]/.test(password) &&
    /\d/.test(password) &&
    /[^A-Za-z0-9]/.test(password)
  )
}
