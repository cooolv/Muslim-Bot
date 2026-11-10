# Contributing

Thank you for considering a contribution to Muslim Apps Assistant. Contributions should improve the current web application on `main` and keep its documentation aligned with the implementation.

## Development setup

For the web application and Cloudflare Worker:

1. Install Node.js 22 and npm.
2. Install dependencies:

   ```bash
   npm ci
   ```

3. To test chat locally, create `.dev.vars` in the repository root and set `GEMINI_API_KEY` to your own Gemini API key. Do not commit this file or expose the key in frontend code.
4. Start the Worker and web app in separate terminals:

   ```bash
   npm run worker:dev
   ```

   ```bash
   npm run dev
   ```

   Set `VITE_CHAT_API_URL` in a local `.env.local` file to the local Worker URL printed by Wrangler.

The legacy Python modules are not part of the current web runtime. Python 3.12 is needed only to run their tests:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Before opening a pull request

Run the checks relevant to your change:

```bash
npm test
npm run typecheck
npm run build
```

If you change or document the legacy Python modules, also run the Python tests. Never use real credentials in tests. Update documentation when behavior, configuration, privacy, or deployment steps change.

## Commit messages

Use a short, imperative commit subject. A Conventional Commit-style prefix is recommended:

```text
docs: clarify local Worker setup
fix: handle empty knowledge results
test: cover Arabic follow-up search
```

Commit-message prefixes are a recommendation, not an automated repository requirement.

## Pull requests

- Open pull requests against `main`.
- Keep each pull request focused and explain the user-visible or maintenance impact.
- Link related issues when applicable.
- Include tests for behavior changes and describe the checks you ran.
- Update relevant documentation and include screenshots only when you have genuine screenshots of the changed UI.
- Do not commit secrets, generated build output, or unrelated formatting changes.

## Suggesting knowledge

Use the [Knowledge suggestion issue form](https://github.com/cooolv/Muslim-Bot/issues/new?template=knowledge_suggestion.yml) to propose source-backed facts. Issues are public; do not include personal or confidential information.

Submitting a suggestion does not add it to the assistant's answers. A maintainer reviews the sources and decides whether to add a record to `public/knowledge.json`. After the approved change is merged into `main`, GitHub Actions automatically deploys the site and Worker, provided the required Cloudflare repository secrets have been configured. This updates the RAG knowledge base; it does not train or fine-tune Gemini. The issue form does not implement a separate admin role or enforce branch review rules; repository permissions control who can edit and merge changes.

## Suggested good first issues

- Suggest a well-sourced knowledge record using the issue form.
- Add test cases for Arabic normalization, search terms, or follow-up queries.
- Improve keyboard navigation or accessible labels in the existing React interface.
- Clarify a setup or privacy detail in the English and Arabic READMEs.
- Provide an actual application screenshot for the preview after coordinating with the project owner.

Please check the existing issues before starting a larger change. For security reports, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
