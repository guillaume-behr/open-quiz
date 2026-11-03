# Changelog

Notable changes to Open Quiz are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (before 1.0.0, a minor version may
break compatibility).

Each version starts with **Upgrade actions**: what an administrator must do
beyond `sh ./update.sh`. “None” means the update script is enough. Keep a
copy of `open-quiz-backend/.env` before any update; from the next release on,
`update.sh` backs up the database itself (earlier versions: back up
PostgreSQL by hand).

## [Unreleased]

### Upgrade actions

- At its first start, the backend adopts the existing database into Alembic
  migrations by itself, then applies the pending ones, including the move of
  question images into `stored_images`. Keep the backup taken before the
  update until the instance has restarted cleanly.
- **From 0.4.x, back up by hand before the first `sh ./update.sh`**: the
  0.4 script that fetches this version applies the migrations without taking
  a backup, so the backups `update.sh` takes afterwards already hold the new
  schema. From the deployment directory:
  `docker compose exec -T open-quiz-database pg_dump --username=open_quiz --dbname=open_quiz --format=custom > open-quiz-before-1.0.0.dump`.
  Should the update go wrong, `sh ./restore.sh open-quiz-before-1.0.0.dump`
  brings that data back, and the API migrates it again at startup.
- The API now connects to PostgreSQL with its own unprivileged role,
  `open_quiz_app`, and the database container no longer receives the
  application's secrets. `update.sh` migrates the deployment by itself: it moves
  `POSTGRES_PASSWORD` into the new `open-quiz-backend/.env.database`, adds
  `DATABASE_PASSWORD` to `.env`, points `DATABASE_URL` at the new role, creates
  the role and hands it the database. The `update.sh` that fetches this
  version still runs the previous script, which leaves the instance running as
  before: **run `sh ./update.sh` a second time** to apply the migration. Back up
  `.env.database` alongside `.env` from now on. Docker Compose 2.24 or later is
  required.
- Student sessions now last 2 hours by default instead of 12. Set
  `STUDENT_ACCESS_TOKEN_HOURS` (2 to 12) in `open-quiz-backend/.env` to keep
  longer sessions.

### Added

- A browser that completed two-factor authentication skips the code until
  midnight, device time (24 hours at most): the password alone signs in again.
  A password change, a new TOTP enrollment, a disabled account or the
  "clear data from this device" button end it; `TWO_FACTOR_BROWSER_TRUST=false`
  turns it off.
- The database schema is managed by Alembic migrations, applied at startup
  under a lock so that a single backend migrates.
- Every API error carries a stable `code`, and the interface translates errors
  from that code into all eight languages.
- Playwright browser tests run on every pull request, and backend tests
  enforce 100% coverage. mypy checks the backend types and Vitest runs the
  frontend unit tests.
- `backup.sh` and `restore.sh` back up and restore the database, and
  `update.sh` takes a backup before rebuilding (`--no-backup` skips it).
- Several API workers can serve one instance (`OPEN_QUIZ_API_WORKERS`): live
  updates reach every worker through PostgreSQL `LISTEN/NOTIFY`.
- Running sessions end when their timer runs out, even when nobody has them
  open.
- The API logs every request as one JSON line, with the route template and no
  IP address or identifier.
- `README.en.md`, an English README, and this changelog.

### Changed

- The API is split into one router per domain, with the session lifecycle,
  grading, question draws and result summaries moved to `app/services`.
- Docker base images are pinned, and Dependabot proposes their updates.
- Question images are stored once per distinct content in `stored_images`,
  and listing questions no longer reads them.
- The Compose subnet follows `OPEN_QUIZ_SUBNET_PREFIX`, and the proxy
  addresses the API trusts follow it.
- A malformed setting fails at startup with the variable's name and the
  expected type.
- Pyodide is copied from its npm package at build time instead of being
  committed.

### Removed

- The former `question_bank_ids` format for a class's practice banks: the
  interface sends `question_banks` with a question count for each bank, and
  the old format is now rejected instead of read as an empty selection.
- Unused interface translations and code paths kept for timestamps without a
  time zone, which PostgreSQL never returns for these columns.

### Fixed

- A student who leaves the waiting room and rejoins after the quiz started
  now gets the first question, instead of a page with no question that
  counted them as finished.
- Search boxes match `%` and `_` literally instead of as wildcards.
- Pressing Tab on a selection of whole lines in the code editor no longer
  indents the line after the selection.
- Saving a student account clears its sign-in lockout, so a teacher can undo
  a lockout caused by a classmate guessing the identifier.
- Selecting a make-up quiz discards the student’s running practice sessions
  on its banks, which could otherwise reveal the expected answers.
- Student access tokens last `STUDENT_ACCESS_TOKEN_HOURS` (2 by default, 2 to 12) instead of a fixed 12 hours, and signing out revokes them server-side.
- Make-up sessions accept students who were absent from the original exam,
  and quizzes are regraded when their question bank changes.
- A quiz translation is no longer erased by a late reset.
- Removing unused question images no longer aborts the data-retention run
  when a teacher reuses one of those images at the same moment.
- Hourly data retention keeps running after a database error instead of
  stopping until the backend restarts.

### Security

- Dependencies upgraded past reported advisories: minimatch, dnspython,
  filelock, msgpack, urllib3 and i18next-http-backend.
- The API's PostgreSQL role is no longer a superuser and the database
  container holds only its own password: a SQL injection could no longer read
  server files or run programs, and a compromised database no longer exposes
  `JWT_SECRET` or the student credential key.
- Two-factor codes are capped per account and per day
  (`TWO_FACTOR_DAILY_ATTEMPTS`, 30 by default) on top of the 15-minute window,
  which still allowed about a thousand guesses a day to someone holding the
  password. A successful login does not reset the daily cap; an administrator's
  credential reset and `scripts.reset_two_factor` do.

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
