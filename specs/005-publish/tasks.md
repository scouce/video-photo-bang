# Tasks 005 — Release hygiene and empty-state default

Work in order; `pytest -q` and `ruff check .` before marking a task done.

## H — Hygiene

- [x] T-H1.1 Remove `samples/optional_test.mov` and update the example command in `AGENTS.md`.
- [x] T-H1.2 Extend `.gitignore` (runs, uploads, exports, media, secrets) with an
      exception for `samples/synthetic_test.mov`.
- [x] T-H1.3 Delete the local `out/` tree so the working copy matches a fresh clone.
- [x] T-H1.4 Audit `git ls-files` for binary artefacts; none except the synthetic sample.

## D — Documentation

- [x] T-D1.1 Add a "Primera ejecución" section to `README.md`.
- [x] T-D1.2 Add `LICENSE` (MIT) and `CONTRIBUTING.md`.

## C — CI

- [x] T-C1.1 Add `.github/workflows/ci.yml` (Python 3.11 + 3.14, ruff + pytest).
- [x] T-C1.2 Add the empty-state test to the suite.

## P — Pages (optional)

- [x] T-P1.1 Add `.github/workflows/pages.yml` publishing `docs/` (static copy of the README).

## V — Verification

- [x] T-V1.1 `git status` clean after `pytest -q`.
- [x] T-V1.2 Fresh clone smoke test: empty state renders the uploader, upload a
      synthetic clip, run finishes and the run appears in the selector.
