<h1><img src=".github/assets/open-quiz-wordmark.svg" alt="Open Quiz" width="230"></h1>

[![CI](https://github.com/guillaume-behr/open-quiz/actions/workflows/ci.yml/badge.svg)](https://github.com/guillaume-behr/open-quiz/actions/workflows/ci.yml)
[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[Français](README.md) · **English**

A free, self-hostable platform to create quizzes, run exams in class and offer
practice sessions to students.

Open Quiz brings three spaces together in one application: the administrator
manages teachers, teachers prepare content and sessions, and students take
their exams or practise from their dashboard.

> [!NOTE]
> This page is the English entry point. The deployment guide, the contributing
> guide and the component READMEs are written in French; the
> [changelog](CHANGELOG.md) is in English.

## 📖 Contents

- [Features](#-features)
- [Installation](#-installation)
- [First steps](#-first-steps)
- [Development](#-development)
- [Documentation](#-documentation)

## ✨ Features

Open Quiz assumes no particular subject. Whatever the subject, a session always
follows the same course:

1. the administrator creates teacher accounts;
2. the teacher creates students, classes and question banks;
3. they prepare an exam, or open banks for practice;
4. students sign in and join their activity;
5. the teacher grades written answers, then publishes or exports the grades.

### Question banks

- single choice, multiple choice and written answers;
- prompts illustrated with images, formatted code snippets, and answers
  expected in a given programming language;
- questions spread over three difficulty levels, from which each quiz draws
  according to the scale you set;
- points set choice by choice, with optional negative points;
- JSON import and export of a whole bank, images included, in a single
  transaction: nothing is created if one line is invalid.

### Exams

- waiting room, timer, pause and resume for the whole class;
- the same draw for everyone, or an individual paper drawn per student;
- optional review of the paper before final hand-in;
- the teacher is warned when a student leaves full screen, switches tabs,
  copies or starts printing: these alerts are informative and never trigger an
  automatic penalty;
- make-up sessions: let chosen students retake a selection of past exams;
- named A4 paper copies with a deterministic draw: a student always gets the
  same paper;
- enlarged display of the session code and timer, to project to the class.

### Grading

- automatic grading of choice questions, manual grading of written answers;
- students see their correction provisionally, and publishing freezes the
  grade;
- CSV export of results, and immediate deletion of a result by the teacher.

### Practice and student experience

- banks opened for practice class by class, with the number of questions of
  your choice, restartable at will;
- immediate correction and progress history;
- a personal account and a dedicated dashboard;
- light or dark interface, available in eight languages;
- translation of the quiz on the student’s device, when their browser supports
  it;
- short Python snippets run in the browser, with Pyodide.

### Hosting and personal data

- self-contained deployment with Docker Compose, Caddy and PostgreSQL;
- Argon2 passwords, TOTP for privileged accounts, HttpOnly cookies and rate
  limits;
- no IP address processed, no third-party service called, no audience
  measurement or advertising;
- retention periods enforced automatically, and legal pages filled in per
  instance.

## 📦 Installation

Docker Compose is the recommended way to install and run Open Quiz. This
section covers the first start. The
[deployment and operations guide](docs/deployment.md) (in French) details
production setup, backups, secret rotation and troubleshooting.

### Requirements

- Docker with the Compose plugin;
- Git and a POSIX-compatible shell (Linux, macOS or WSL on Windows);
- a valid domain name, and an HTTPS reverse proxy to make the instance public.

### 1. Get the project

```shell
git clone https://github.com/guillaume-behr/open-quiz.git
cd open-quiz
```

### 2. Run the guided installation

```shell
sh ./install.sh
```

The script asks for the domain name, without `https://` or a trailing `/`. It
generates the secrets and the administrator password, writes
`open-quiz-backend/.env`, then builds and starts the containers. Pass
`--domain quiz.example.com` for a non-interactive installation, and `--help`
for the other options.

> [!IMPORTANT]
> The administrator password is shown only once. Save it before closing the
> terminal.

On an existing deployment, the installation refuses to overwrite the
configuration: use `sh ./update.sh` instead.

### 3. Publish the instance over HTTPS

The installation configures Open Quiz, but not DNS, the TLS certificate or the
machine’s reverse proxy. The frontend only listens on `127.0.0.1:7800`: put an
HTTPS reverse proxy in front of that port, for instance with Caddy.

```caddyfile
quiz.example.com {
    reverse_proxy 127.0.0.1:7800
}
```

An [Nginx configuration example](docs/nginx.conf) is also provided; replace
its domain and certificate paths before enabling it. The proxy must forward
WebSocket upgrades, which live updates rely on.

### 4. Check the instance

```shell
curl --fail --show-error https://quiz.example.com/api/health
```

The expected answer is `{"status":"ok"}`.

### Updates

```shell
sh ./update.sh
```

The script pulls the new revision, rebuilds the images and restarts the
containers; the backend applies pending database migrations by itself at
startup. `--no-pull` rebuilds without fetching a new revision. Before each
update, read the **Upgrade actions** of the new version in the
[changelog](CHANGELOG.md).

> [!CAUTION]
> Back up PostgreSQL and `open-quiz-backend/.env` before each update. The
> [deployment guide](docs/deployment.md#-sauvegarder-les-données) describes
> backup, restore and secret rotation.

## 🚀 First steps

The instance starts empty: a single administrator account exists, nothing
else. The four steps below lead from there to the first exam.

Paths are appended to the domain configured during installation. In local
development, use `http://localhost:5173`.

| Space          | Path               | Who signs in                              |
| -------------- | ------------------ | ----------------------------------------- |
| Administration | `/admin/dashboard` | the account created by the installation   |
| Teacher        | `/teacher/login`   | the accounts created by the administrator |
| Student        | `/student/login`   | the accounts created by a teacher         |

### 1. Sign in as administrator

Go to `/admin/dashboard` with the credentials shown during installation, then
set up two-factor authentication right away: it is mandatory for privileged
accounts.

The administrator creates neither content nor students. They manage teacher
accounts and problem reports.

### 2. Fill in the privacy and legal notices

The `/privacy`, `/legal-notice` and `/accessibility` pages ship no text
specific to your organisation: they show what you declare here. While a value
stays empty, the page shows “Not provided” in red, and the instance publishes a
privacy policy without an identifiable controller.

These variables are not secrets, but they go in the same file as the rest of
the configuration:

```shell
$EDITOR open-quiz-backend/.env
sh ./update.sh
```

Identity of the host, required for the legal notice:

| Variable             | What it publishes       |
| -------------------- | ----------------------- |
| `LEGAL_HOST_NAME`    | the host’s company name |
| `LEGAL_HOST_ADDRESS` | its postal address      |
| `LEGAL_HOST_PHONE`   | its phone number        |

Data controller and exercise of rights, required by articles 13 and 14 of the
GDPR:

| Variable                     | What it publishes                        |
| ---------------------------- | ---------------------------------------- |
| `PRIVACY_CONTROLLER_NAME`    | the organisation controlling the data    |
| `PRIVACY_CONTROLLER_CONTACT` | the address where users exercise rights  |
| `PRIVACY_LEGAL_BASIS`        | the legal basis, spelled out             |
| `PRIVACY_RECIPIENTS`         | who accesses the data, the host included |

These are the seven values without which the public pages stay incomplete.
Retention periods applied by the purge already have defaults and are displayed
automatically. At startup, the API lists the values it considers mandatory
under the `security.public_information_incomplete` event.

### 3. Create a teacher account

From the administration dashboard, create the account and hand its
credentials to the teacher. On their first sign-in at `/teacher/login`, they
set up their own two-factor authentication.

### 4. Prepare and start an activity

The teacher then works from their own space: they create classes and student
accounts, fill question banks, then start an exam or open banks for practice.
Students sign in at `/student/login` with the credentials the teacher gives
them.

> [!CAUTION]
> Self-hosting is neither an approval nor automatic compliance. Before opening
> the instance to students, have the legal basis, retention periods,
> processors and user information validated by your organisation or its data
> protection officer.

## 🛠️ Development

To install an instance for use, follow [Installation](#-installation). To work
on the code, a script prepares development secrets and starts PostgreSQL:

```shell
sh ./install-dev.sh
```

Then start the API with `uv run fastapi dev main.py` from `open-quiz-backend`,
and the interface with `pnpm dev` from `open-quiz-frontend`. The
[contributing guide](CONTRIBUTING.md) (in French) details the requirements and
the checks to run before a pull request. Issues and pull requests in English
are welcome.

## 📚 Documentation

| Resource                                                             | Content                                       | Language        |
| -------------------------------------------------------------------- | --------------------------------------------- | --------------- |
| [Changelog](CHANGELOG.md)                                            | changes and upgrade actions per version       | English         |
| [Deployment and operations](docs/deployment.md)                      | production, backups, updates, troubleshooting | French          |
| [Backend documentation](open-quiz-backend/README.md)                 | API, security, storage and operations         | French          |
| [Frontend documentation](open-quiz-frontend/README.md)               | interface, routes, translation, browser tests | French          |
| [Contributing guide](CONTRIBUTING.md)                                | environment, conventions and checks           | French          |
| [Security policy](SECURITY.md#-reporting-a-vulnerability-in-english) | private reporting procedure                   | English section |

## ⚖️ License

Open Quiz is distributed under the [MIT license](LICENSE).
