# Changelog

Notable changes to Open Quiz are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (before 1.0.0, a minor version may
break compatibility).

Each version starts with **Upgrade actions**: what an administrator must do
beyond `sh ./update.sh`. “None” means the update script is enough. Back up
PostgreSQL and `open-quiz-backend/.env` before any update.

## [Unreleased]

### Upgrade actions

- None. At its first start, the backend adopts the existing database into
  Alembic migrations by itself, then applies the pending ones. Keep the backup
  taken before the update until the instance has restarted cleanly.

### Added

- The database schema is managed by Alembic migrations, applied at startup
  under a lock so that a single backend migrates.
- Every API error carries a stable `code`, and the interface translates errors
  from that code into all eight languages.
- Playwright browser tests run on every pull request, and backend tests
  enforce 100% coverage.

### Changed

- The API is split into one router per domain, with the session lifecycle,
  grading, question draws and result summaries moved to `app/services`.
- Docker base images are pinned, and Dependabot proposes their updates.

### Fixed

- Saving a student account clears its sign-in lockout, so a teacher can undo
  a lockout caused by a classmate guessing the identifier.
- Selecting a make-up quiz discards the student’s running practice sessions
  on its banks, which could otherwise reveal the expected answers.
- Student access tokens last `STUDENT_ACCESS_TOKEN_HOURS` (2 by default, 2 to 12) instead of a fixed 12 hours, and signing out revokes them server-side.
- Make-up sessions accept students who were absent from the original exam,
  and quizzes are regraded when their question bank changes.
- A quiz translation is no longer erased by a late reset.

### Security

- Dependencies upgraded past reported advisories: minimatch, dnspython,
  filelock, msgpack, urllib3 and i18next-http-backend.

## [0.4.0] — 2026-09-29

### Upgrade actions

- None.

### Changed

- Grades are read on a single scale, with the points one hover away.
- Sign-in rate-limit buckets are wider, and known accounts get through an
  exhausted authentication budget.
- The database container drops its Linux capabilities, like the other
  containers.

### Fixed

- Join codes are reclaimed, and live sockets keep talking through idle
  periods.
- A paste is no longer reported as an exam monitoring alert.
- Negative points no longer pay for selecting more choices.
- A student keeps an unsent answer when stepping back a question.

### Security

- httpx upgraded past three advisories.

## [0.3.5] — 2026-09-11

### Upgrade actions

- Fill in the privacy and legal notice variables (`LEGAL_HOST_*`,
  `PRIVACY_*`) in `open-quiz-backend/.env`: the public pages show “Not
  provided” until they are set. See [README.en.md](README.en.md#-first-steps).

### Added

- Every record has a retention period and a way to be erased, and the
  privacy pages state what is monitored, kept and stored.
- Students see a provisional correction before grades are published.
- Students can review their answers before hand-in, and teachers get an
  enlarged session display to project.

### Changed

- Partial-credit grades use a red-to-green gradient instead of solid red.
- Code views and editors disable font ligatures.

### Fixed

- Tab indents in the student code editor.
- A concurrent duplicate of a participant’s last answer is accepted.
- The class label of the API and of the interface match when the name is
  empty.
- The secret backup written by the rotation script is created unreadable by
  other accounts.

## [0.3.0] — 2026-08-29

First tagged version.

[Unreleased]: https://github.com/guillaume-behr/open-quiz/compare/1518fe7...HEAD
[0.4.0]: https://github.com/guillaume-behr/open-quiz/compare/v0.3.5...1518fe7
[0.3.5]: https://github.com/guillaume-behr/open-quiz/compare/v0.3.0...v0.3.5
[0.3.0]: https://github.com/guillaume-behr/open-quiz/releases/tag/v0.3.0
