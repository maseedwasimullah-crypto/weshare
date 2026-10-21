import React, { useCallback, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'

import './style.css'
import {
  COMMENT_MAX_LENGTH,
  POST_MAX_LENGTH,
  isPasswordStrong,
  validateComment,
  validatePost,
} from './validate.js'

// In development the Vite dev server proxies /api to the FastAPI backend
// (see vite.config.js). In production set VITE_API_URL to the deployed
// backend origin, for example https://weshare-api.onrender.com.
const API = import.meta.env.VITE_API_URL || '/api'
const TOKEN_KEY = 'ws_token'

const getToken = () => localStorage.getItem(TOKEN_KEY)
const setToken = (token) => localStorage.setItem(TOKEN_KEY, token)
const clearToken = () => localStorage.removeItem(TOKEN_KEY)

function describeDetail(detail) {
  if (!detail) return null
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === 'string' ? item : item && item.msg))
      .filter(Boolean)
      .join(' ')
  }
  return JSON.stringify(detail)
}

async function call(path, options = {}) {
  const token = getToken()
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  }
  const response = await fetch(API + path, {
    ...options,
    headers,
    credentials: 'include',
  })
  let payload = null
  if (response.status !== 204) {
    const raw = await response.text()
    if (raw) {
      try {
        payload = JSON.parse(raw)
      } catch {
        payload = { detail: raw }
      }
    }
  }
  if (!response.ok) {
    if (response.status === 401 && token) {
      clearToken()
    }
    throw new Error(describeDetail(payload && payload.detail) || `Request failed (${response.status}).`)
  }
  return payload
}

function Robot() {
  return <span className="robot" aria-hidden="true">R</span>
}

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString()
}

function App() {
  const [user, setUser] = useState(null)
  const [posts, setPosts] = useState([])
  const [page, setPage] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [mode, setMode] = useState('feed')
  const [content, setContent] = useState('')
  const [adminData, setAdminData] = useState(null)
  const [adminSearch, setAdminSearch] = useState('')
  const [verificationToken, setVerificationToken] = useState('')

  const load = useCallback(
    async (targetPage) => {
      setLoading(true)
      try {
        const data = await call(`/feed?limit=20&offset=${targetPage * 20}`)
        setPosts((current) => (targetPage === 0 ? data.items : current.concat(data.items)))
        setHasMore(Boolean(data.has_more))
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token')
    if (!token) return
    call('/auth/verify', { method: 'POST', body: JSON.stringify({ token }) })
      .then((data) => {
        setNotice(data.message)
        window.history.replaceState({}, '', window.location.pathname)
      })
      .catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    load(page)
  }, [page, load])

  useEffect(() => {
    if (!getToken()) return
    call('/auth/me')
      .then(setUser)
      .catch(() => {
        clearToken()
        setUser(null)
      })
  }, [])

  async function submit(event) {
    event.preventDefault()
    setError('')
    setNotice('')
    const problem = validatePost(content)
    if (problem) {
      setError(problem)
      return
    }
    try {
      const post = await call('/posts', {
        method: 'POST',
        body: JSON.stringify({ content }),
      })
      setPosts((current) => [post, ...current])
      setContent('')
    } catch (err) {
      setError(err.message)
    }
  }

  async function auth(event) {
    event.preventDefault()
    setError('')
    setNotice('')
    const form = new FormData(event.currentTarget)
    const email = String(form.get('email') || '').trim()
    const password = String(form.get('password') || '')
    try {
      if (mode === 'register') {
        const confirm = String(form.get('confirm') || '')
        if (!isPasswordStrong(password)) {
          setError('Password must be at least 12 characters and include uppercase, lowercase, number, and symbol.')
          return
        }
        if (password !== confirm) {
          setError('Passwords do not match.')
          return
        }
        const data = await call('/auth/register', {
          method: 'POST',
          body: JSON.stringify({ email, password, confirm_password: confirm }),
        })
        setNotice(data.message)
        if (data.verification_token) {
          setVerificationToken(data.verification_token)
        }
        event.currentTarget.reset()
        return
      }
      const data = await call('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
      setToken(data.access_token)
      setUser(data.user)
      setMode('feed')
      setPage(0)
    } catch (err) {
      setError(err.message)
    }
  }

  async function verifyAccount(token) {
    setError('')
    setNotice('')
    try {
      const data = await call('/auth/verify', {
        method: 'POST',
        body: JSON.stringify({ token: token || verificationToken }),
      })
      setNotice(data.message)
      setVerificationToken('')
      if (user) setUser({ ...user, email_verified: true })
    } catch (err) {
      setError(err.message)
    }
  }

  async function comment(postId, text, setText) {
    setError('')
    const problem = validateComment(text)
    if (problem) {
      setError(problem)
      return
    }
    try {
      const created = await call(`/posts/${postId}/comments`, {
        method: 'POST',
        body: JSON.stringify({ content: text }),
      })
      setText('')
      setPosts((current) =>
        current.map((post) =>
          post.id === postId
            ? {
                ...post,
                comment_count: post.comment_count + 1,
                comments: [...post.comments, created],
              }
            : post,
        ),
      )
    } catch (err) {
      setError(err.message)
    }
  }

  function logout() {
    call('/auth/logout', { method: 'POST' }).catch(() => {})
    clearToken()
    setUser(null)
    setMode('feed')
    setPage(0)
    setAdminData(null)
  }

  const loadAdmin = useCallback(async (search = '') => {
    setError('')
    try {
      const [stats, users, contentData, moderation] = await Promise.all([
        call('/admin/stats'),
        call(`/admin/users?search=${encodeURIComponent(search)}`),
        call('/admin/content'),
        call('/admin/moderation'),
      ])
      setAdminData({ stats, users, ...contentData, moderation })
      setMode('admin')
    } catch (err) {
      setError(err.message)
    }
  }, [])

  async function adminAction(path, options, confirmation) {
    setError('')
    if (confirmation && !window.confirm(confirmation)) return
    try {
      await call(path, options)
      await loadAdmin(adminSearch)
    } catch (err) {
      setError(err.message)
    }
  }

  const postProblem = validatePost(content)
  const commentButtonsDisabled = (text) => Boolean(validateComment(text))

  return (
    <div className="shell">
      <header>
        <a
          className="brand"
          href="#"
          onClick={(event) => {
            event.preventDefault()
            setMode('feed')
            setPage(0)
            setError('')
            setNotice('')
          }}
        >
          WeShare<span>!</span>
        </a>
        <nav>
          {user ? (
            <>
              <span className="who">
                <Robot /> {user.username}
              </span>
              {user.role === 'admin' && (
                <button className="link" onClick={() => loadAdmin('')}>
                  Admin
                </button>
              )}
              <button className="link" onClick={logout}>
                Log out
              </button>
            </>
          ) : (
            <>
              <button className="link" onClick={() => setMode('login')}>
                Log in
              </button>
              <button className="small" onClick={() => setMode('register')}>
                Create account
              </button>
            </>
          )}
        </nav>
      </header>

      {mode === 'login' || mode === 'register' ? (
        <section className="auth">
          <h1>{mode === 'login' ? 'Log in' : 'Create account'}</h1>
          <form onSubmit={auth}>
            <label>
              Email address
              <input name="email" type="email" required autoComplete="email" />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                required
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              />
            </label>
            {mode === 'register' && (
              <>
                <label>
                  Confirm password
                  <input name="confirm" type="password" required autoComplete="new-password" />
                </label>
                <small>12+ characters, with uppercase, lowercase, number, and symbol.</small>
              </>
            )}
            <button>{mode === 'login' ? 'Log in' : 'Create account'}</button>
          </form>
          <p>
            {mode === 'login' ? 'New here? ' : 'Already registered? '}
            <button
              className="link"
              onClick={() => {
                setMode(mode === 'login' ? 'register' : 'login')
                setError('')
                setNotice('')
              }}
            >
              {mode === 'login' ? 'Create an account' : 'Log in'}
            </button>
          </p>
          {verificationToken && (
            <p>
              <small>No mail server is configured, so use this token to activate the account.</small>
              <br />
              <button onClick={() => verifyAccount(verificationToken)}>Verify this account</button>
            </p>
          )}
          {notice && <p className="notice">{notice}</p>}
          {error && <p className="error">{error}</p>}
        </section>
      ) : mode === 'admin' ? (
        <main>
          <h2>Administration</h2>
          {adminData && (
            <>
              <p>
                Users {adminData.stats.users} | Active {adminData.stats.active_users} | Posts{' '}
                {adminData.stats.posts} | Comments {adminData.stats.comments}
              </p>

              <h3>Accounts</h3>
              <input
                aria-label="Search accounts"
                placeholder="Search by email or username"
                value={adminSearch}
                onChange={(event) => setAdminSearch(event.target.value)}
              />
              <button onClick={() => loadAdmin(adminSearch)}>Search</button>
              {adminData.users.map((account) => (
                <article className="card" key={account.id}>
                  {account.username} | {account.email} | {account.is_active ? 'Active' : 'Inactive'} |{' '}
                  {account.role}
                  <button
                    disabled={account.id === user.id}
                    onClick={() =>
                      adminAction(
                        `/admin/users/${account.id}`,
                        { method: 'PATCH', body: JSON.stringify({ is_active: !account.is_active }) },
                      )
                    }
                  >
                    {account.is_active ? 'Deactivate' : 'Reactivate'}
                  </button>
                  <button
                    disabled={account.id === user.id || account.role === 'admin'}
                    onClick={() =>
                      adminAction(
                        `/admin/users/${account.id}`,
                        { method: 'DELETE' },
                        'Permanently delete this user and their posts/comments?',
                      )
                    }
                  >
                    Delete
                  </button>
                </article>
              ))}

              <h3>Recent posts</h3>
              {adminData.posts.map((post) => (
                <article className="card" key={post.id}>
                  {post.username}: {post.content}
                  <button
                    onClick={() =>
                      adminAction(
                        `/admin/posts/${post.id}`,
                        { method: 'DELETE' },
                        'Delete this post and its comments?',
                      )
                    }
                  >
                    Remove
                  </button>
                </article>
              ))}

              <h3>Recent comments</h3>
              {adminData.comments.map((item) => (
                <article className="card" key={item.id}>
                  {item.username}: {item.content}
                  <button
                    onClick={() =>
                      adminAction(
                        `/admin/comments/${item.id}`,
                        { method: 'DELETE' },
                        'Delete this comment?',
                      )
                    }
                  >
                    Remove
                  </button>
                </article>
              ))}

              <h3>Moderation log</h3>
              {adminData.moderation.map((row) => (
                <article className="card" key={row.id}>
                  {row.content_type} | {row.decision} | {row.reason} | {row.content_excerpt}
                </article>
              ))}
            </>
          )}
          {error && <p className="error">{error}</p>}
          <button className="more" onClick={() => setMode('feed')}>
            Back to the feed
          </button>
        </main>
      ) : (
        <main>
          <div className="intro">
            <h1>News and notes from the community.</h1>
            <p>Read what people are sharing across the region.</p>
          </div>

          {notice && <p className="notice">{notice}</p>}
          {error && <p className="error">{error}</p>}

          {user && !user.email_verified && (
            <div className="signin-note">
              Your email address is not verified yet, so you cannot post or comment.
              {verificationToken && (
                <button onClick={() => verifyAccount(verificationToken)}>Verify my account</button>
              )}
            </div>
          )}

          {user && user.email_verified && (
            <form className="compose" onSubmit={submit}>
              <label htmlFor="post">Share an update</label>
              <textarea
                id="post"
                maxLength={POST_MAX_LENGTH}
                value={content}
                onChange={(event) => setContent(event.target.value)}
                placeholder="What's happening?"
              />
              <div className="row">
                <small>
                  {content.length}/{POST_MAX_LENGTH}
                  {postProblem ? ` - ${postProblem}` : ''}
                </small>
                <button disabled={Boolean(postProblem)}>Post</button>
              </div>
            </form>
          )}

          {!user && (
            <div className="signin-note">
              You can read the feed without an account.{' '}
              <button className="link" onClick={() => setMode('login')}>
                Log in
              </button>{' '}
              to post or comment.
            </div>
          )}

          {posts.map((post) => (
            <PostCard key={post.id} post={post} user={user} onComment={comment} />
          ))}

          {loading && <p className="more">Loading…</p>}
          {hasMore && posts.length > 0 && (
            <button className="more" onClick={() => setPage((current) => current + 1)}>
              Load more
            </button>
          )}
        </main>
      )}

      <footer>WeShare! | A text-only community</footer>
    </div>
  )
}

function PostCard({ post, user, onComment }) {
  const [text, setText] = useState('')
  const problem = validateComment(text)

  return (
    <article className="card">
      <div className="meta">
        <Robot />
        <b>{post.username}</b>
        <time>{formatDate(post.created_at)}</time>
      </div>
      <p className="post-text">{post.content}</p>
      <div className="comment-count">{post.comment_count} comments</div>
      <div className="comments">
        {post.comments.map((comment, index) => (
          <div className="comment" key={comment.id || index}>
            <b>
              <Robot /> {comment.username}
            </b>
            <time>{formatDate(comment.created_at)}</time>
            <p>{comment.content}</p>
          </div>
        ))}
      </div>
      {user && user.email_verified && (
        <form
          className="comment-form"
          onSubmit={(event) => {
            event.preventDefault()
            onComment(post.id, text, setText)
          }}
        >
          <input
            aria-label="Write a comment"
            maxLength={COMMENT_MAX_LENGTH}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Write a comment"
          />
          <small>
            {text.length}/{COMMENT_MAX_LENGTH}
            {problem ? ` - ${problem}` : ''}
          </small>
          <button disabled={commentButtonsDisabled(text)}>Comment</button>
        </form>
      )}
    </article>
  )
}

createRoot(document.getElementById('root')).render(<App />)
