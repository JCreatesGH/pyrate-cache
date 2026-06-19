# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [0.3.0]

### Added
- **`@cache(key=…)`** — an optional key callable to cache by a subset of the arguments (or
  normalize them, e.g. ignore a `self`/session arg). Defaults to keying on all args as before.
- **`TokenBucket.remaining()` / `SlidingWindowLimiter.remaining()`** — whole calls available
  right now; with the existing `time_until()` this is everything you need to emit
  `X-RateLimit-Remaining` / `X-RateLimit-Reset` headers from the decorator's attached limiter.

## [0.2.0]

### Added
- `SlidingWindowLimiter` — a sliding-window-log rate limiter that never allows
  more than `calls` in any trailing `period` (stricter than a token bucket, no
  bursts). Usable standalone or via the decorator.
- `rate_limit(..., strategy="token-bucket" | "sliding-window")` to choose the
  limiting algorithm.
- `rate_limit(..., key=callable)` for per-key limiting — each distinct key
  (per user / IP / tenant) gets its own independent limiter. The registry is
  exposed as `.limiters`; the single-limiter case still exposes `.bucket`.

## [0.1.0]

### Added
- `@cache` decorator with TTL expiry, LRU `maxsize` eviction, `.cache_info()` /
  `.cache_clear()`, correct caching of `None` results, and pluggable backends
  (any object with `get`/`set`/`clear`).
- `@rate_limit` decorator backed by a token bucket, blocking or non-blocking
  (`RateLimitExceeded`).
- Full `async def` support for both decorators.
