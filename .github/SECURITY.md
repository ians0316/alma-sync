# Security

## Supported versions

Only the newest version on `main` gets fixes.

## Report a security problem

If you find something that could expose a student's password, tokens, grades or Google and Notion data, **don't open a public issue.** Email the address in the README's [Report a bug](../README.md#report-a-bug) section instead, with "Security" in the subject.

Please include:

- what the problem is and what someone could do with it
- the steps to make it happen
- your computer (macOS or Windows)

Don't send real passwords, tokens or keys in your report. You'll get a reply as soon as possible.

## What Alma Sync does to keep you safe

- Your Alma password and Notion token live in your computer's password store (macOS Keychain or Windows Credential Manager), never in files or in this repo.
- The Google key lives in the `.alma_sync` folder in your home folder.
- `config.json`, exported data and logs are kept out of the repo by `.gitignore`.
- It only reads from Alma. It never submits or changes anything there.
- Your data goes only to your own Notion, Google Calendar and Google Sheets.
