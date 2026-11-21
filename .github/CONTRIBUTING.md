# Contributing to Alma Sync

Thanks for helping make Alma Sync better for Seoul Academy students!

## Report a bug or suggest a feature

Open an [issue](https://github.com/ians0316/alma-sync/issues), or use the email in the README's [Report a bug](../README.md#report-a-bug) section. Please include:

- your computer (macOS or Windows)
- what you expected and what happened instead
- the last lines of `sync.log` (in the `.alma_sync` folder in your home folder)

**Before you paste a log or screenshot, remove anything private:** grades, passwords, tokens, your Notion or Google IDs, and your email.

## Make a change

1. Fork the repo (or ask to be added) and make a new branch from `main`.
2. Set it up as in the README's [Setup](../README.md#setup-and-installation-macos) section, or [WINDOWS_SETUP.md](../WINDOWS_SETUP.md) on Windows.
3. Test without touching your real Notion or calendar first:

   ```sh
   python3 sync.py --dump test.json
   ```

   This reads Alma and writes the assignments to a file only. Then run `python3 sync.py` once and check that Notion, Google Calendar and the Grades sheet look right.
4. Open a pull request that says what you changed and why.

## Rules

- **Never commit private files.** `config.json`, `assignments.json`, Google keys, logs and anything with a password or token stay off GitHub. `.gitignore` already skips them; check `git status` before you commit anyway.
- **Passwords and tokens go in the computer's password store** (macOS Keychain or Windows Credential Manager) through `platform_support.py`, never in code or files.
- **Only read from Alma.** The sync must never submit, change or send anything in Alma.
- **Never delete the student's data.** The sync adds and updates rows in Notion and events in Google Calendar; it doesn't remove them.
- **Keep both computers working.** If you change something that differs between macOS and Windows, update `platform_support.py` and `windows/windows_support.py` together.
- **Change only what you need.** Small pull requests that do one thing are easiest to review.
- **Update the README** if you add a feature, a setting in `config.example.json`, or a new file.

## Where things are

See **Structure** and **Project layout** in the [README](../README.md#structure). Each writer (Notion, Google Calendar, Grades sheet) is its own file, so you can work on one without touching the others.

## License

Alma Sync uses the [MIT License](../LICENSE). By contributing, you agree your changes are shared under it too.
