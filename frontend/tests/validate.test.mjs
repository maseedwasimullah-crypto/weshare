import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

import {
  COMMENT_MAX_LENGTH,
  POST_MAX_LENGTH,
  isPasswordStrong,
  validateComment,
  validateContent,
  validatePost,
} from '../src/validate.js'

const here = dirname(fileURLToPath(import.meta.url))
const mainSource = readFileSync(join(here, '..', 'src', 'main.jsx'), 'utf8')

test('the API base is configurable for production deployments', () => {
  assert.match(
    mainSource,
    /import\.meta\.env\.VITE_API_URL\s*\|\|\s*'\/api'/,
    'main.jsx must fall back to the relative /api path when VITE_API_URL is unset',
  )
})

test('empty submissions are rejected', () => {
  assert.match(validatePost(''), /empty/i)
  assert.match(validatePost('   '), /empty/i)
  assert.match(validateComment(''), /empty/i)
  assert.match(validateComment('\t\t'), /empty/i)
})

test('blank lines are rejected', () => {
  assert.match(validatePost('first\n\nsecond'), /blank lines/i)
  assert.match(validatePost('first\n \nsecond'), /blank lines/i)
  assert.match(validatePost('first\r\n\r\nsecond'), /blank lines/i)
  assert.match(validatePost('first\n\t\nsecond'), /blank lines/i)
  assert.match(validateComment('a\n\nb'), /blank lines/i)
})

test('a single newline is allowed', () => {
  assert.equal(validatePost('first\nsecond'), null)
  assert.equal(validatePost('trailing newline\n'), null)
})

test('post length limit is 1000 characters', () => {
  assert.equal(POST_MAX_LENGTH, 1000)
  assert.equal(validatePost('x'.repeat(1000)), null)
  assert.match(validatePost('x'.repeat(1001)), /1000 characters or fewer/)
})

test('comment length limit is 100 characters', () => {
  assert.equal(COMMENT_MAX_LENGTH, 100)
  assert.equal(validateComment('y'.repeat(100)), null)
  assert.match(validateComment('y'.repeat(101)), /100 characters or fewer/)
})

test('validateContent honours the supplied maximum', () => {
  assert.equal(validateContent('abc', 3), null)
  assert.match(validateContent('abcd', 3), /3 characters or fewer/)
})

test('password strength rules match the backend', () => {
  assert.equal(isPasswordStrong('Str0ng!Passw0rd#1'), true)
  assert.equal(isPasswordStrong('short'), false)
  assert.equal(isPasswordStrong('alllowercase!123'), false)
  assert.equal(isPasswordStrong('ALLUPPERCASE!123'), false)
  assert.equal(isPasswordStrong('NoDigitsHere!'), false)
  assert.equal(isPasswordStrong('NoSymbols12345'), false)
})
