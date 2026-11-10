# Changelog

Notable changes to Open Quiz are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (before 1.0.0, a minor version may
break compatibility).

Each version starts with **Upgrade actions**: what an administrator must do
beyond `sh ./update.sh`. “None” means the update script is enough. Keep a
copy of `open-quiz-backend/.env` and `open-quiz-backend/.env.database` before
any update; since 1.0.0, `update.sh` backs up the database itself (before
1.0.0: back up PostgreSQL by hand).

## [Unreleased]

### Upgrade actions

- In production the API now answers 400 to a request whose `Host` header is
  neither the name in `FRONTEND_ORIGIN` nor an internal one. Check that your
  reverse proxy forwards the name the browser asked for (`proxy_set_header
  Host $host` with Nginx; Caddy does by default). If the API is published
  under another name than the interface (`VITE_API_URL`), list it in
  `TRUSTED_HOSTS` in `open-quiz-backend/.env`.
- The API container is limited to 2 GB of memory and the proxy to 512 MB.
  With several workers, or if large imports fail, raise `OPEN_QUIZ_API_MEMORY`
  in the root `.env` (docs/deployment.md).
- Optional: the Nginx example gained per-address limits and moved its proxy
  headers to the server block. Compare it with your virtual host.
- At startup the backend applies migration 0004, which adds CHECK
  constraints on session statuses, quiz modes and question settings. A
  database holding a value the application never writes makes it fail as a
  whole: the schema stays as it was, and the backend log names the constraint.
- At startup the backend applies migration 0005, which clears the monitoring
  alerts recorded for a copy.

### Added

- Teachers can format question prompts: `**bold**`, `*italic*`, `` `code` ``
  and line breaks, with a toolbar, Ctrl+B / Ctrl+I shortcuts and a live
  preview in the question editor. Formatting shows to students, in results and
  on printed copies; prompts stay plain text, so existing questions and JSON
  imports are unchanged.
- In their results, students see each question's points at the top right of it,
  in a green, orange or red pill for full, partial or no credit.

### Changed

- Copying content during an exam no longer warns the teacher, as pasting
  already did not: the monitoring notice no longer lists it, the API refuses a
  `copy_attempt` event with 422, and alerts already recorded for a copy are
  cleared.
- The grade-level routes moved under the classes: `/api/grade-levels` is now
  `/api/classes/grade-levels`.
- An unknown makeup session action now answers 422 instead of 404.
- PostgreSQL now refuses session statuses, quiz modes, difficulties and answer
  modes outside the values the application uses.
- Listing or exporting results no longer deletes expired exam results: they
  are hidden at once and deleted by the hourly maintenance, which reports them
  in `security.data_retention_enforced`. The `quiz.results_retention_purged`
  audit event is gone.
- The backend runs on uvloop 0.23.0, which no longer calls
  `asyncio.iscoroutinefunction` (removed in Python 3.16), with anyio 4.15.1
  and Starlette 1.7.0.
- The Python runner loads the Pyodide loader from `/pyodide/` with the rest of
  the runtime instead of bundling it, which shrinks its worker to about 1 kB.

### Fixed

- Sending the last answer again after an exam finished (a double click, a
  network retry) no longer resets its grade, which kept the teacher from
  publishing the grades. An answer arriving while the exam is finishing is
  refused instead of being recorded ungraded.
- When the last two students hand in at the same moment, the exam now
  finishes instead of running on until its time is up.
- Pausing or resuming an exam, or a make-up session, at the moment it
  finishes no longer reopens it.
- Make-up sessions no longer fill the teacher's list of running exams with
  one entry per student, which could push the class's own exam out of it.
- A paused make-up session can be finished without resuming it first.
- The class-session routes (`/api/quizzes/sessions/{id}/start`, `pause`,
  `resume`, `cancel`) now refuse a make-up student's session with 409
  `QUIZ_SESSION_IS_MAKEUP`. Cancelling one through them used to keep that
  student from choosing a quiz again.
- Timed exams keep ending on time, and data retention keeps running, after an
  unexpected error: any failed run is logged and retried, instead of only a
  database error. An exam that cannot be finished no longer keeps every
  other due exam from finishing.
- Editing a question no longer changes grades that were already published:
  only finished sessions whose grades are not published yet are regraded.
  The edit response gains `published_sessions_not_regraded`, and the question
  bank tells the teacher how many published sessions kept their grades.
- A question can no longer be edited while an exam or make-up session that
  drew it is waiting, running or paused: the API answers 409
  `QUESTION_IN_ACTIVE_SESSION`. Training attempts do not block an edit.
- Regrading after a question edit rescores only that question's answers, in
  a fixed number of queries, instead of every answer of every session that
  used it.
- Scores, maximum scores and their medians are reported to two decimals in
  the results, the student history and the CSV export: totals such as
  `0.6300000000000001` no longer appear. A mark given by hand is stored to two
  decimals too.

### Security

- Students no longer receive the real ids of answer choices, which follow the
  order the teacher wrote them in and so could reveal the answer behind the
  shuffle. Each participant now sees, sends and loads images for choices
  through opaque tokens of their own (`id`, `selected_choice_ids` and
  `correct_choice_ids` become strings in the student API, and
  `/api/quizzes/student/sessions/{code}/choices/{token}/image`). Teacher
  payloads and stored answers keep the real ids. A page loaded before the
  update has to be reloaded to answer.
- Wrong passwords sent from elsewhere no longer lock an account out of a
  browser it trusts: a browser holding the account's two-factor trust cookie
  has an attempt limit of its own. Before, ten wrong passwords every fifteen
  minutes kept any teacher, or the administrator, from signing in.
- Python snippets can no longer reach `fetch`, `importScripts` or `indexedDB`
  through `WorkerGlobalScope.prototype`, nor `WebSocketStream` and the
  navigator's storage, locks and device APIs.
- Uploaded images are only read by the JPEG, PNG, WebP and GIF decoders,
  whatever type the upload declares.
- One account may hold four live sockets on a feed; a fifth is closed with
  code 1013.
- The API decodes two images and computes four password hashes at a time, and
  a question bank import may decode at most a billion pixels.
- The proxy no longer doubles the security headers the API already sets.

## [1.0.0] — 2026-11-03

First stable version: from here on, a version that breaks compatibility or
the upgrade path changes the major number.

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

[Unreleased]: https://github.com/guillaume-behr/open-quiz/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/guillaume-behr/open-quiz/compare/1518fe7...v1.0.0
[0.4.0]: https://github.com/guillaume-behr/open-quiz/compare/v0.3.5...1518fe7
[0.3.5]: https://github.com/guillaume-behr/open-quiz/compare/v0.3.0...v0.3.5
[0.3.0]: https://github.com/guillaume-behr/open-quiz/releases/tag/v0.3.0
