# Stage 37 — Licensing decision brief (owner decision; not legal advice)

The repository is public, but it has no `LICENSE` file. Without a licence, nobody else may use, copy or redistribute the program, and a public installer cannot be distributed on clear terms. This brief sets out the choices and what each one requires. The decision belongs to the owner. A lawyer should confirm it before any public or commercial distribution.

The facts about the bundled components come from the build's SBOM and from `docs/STAGE368_BUILD_LOCK.md` §5.

## 1. What decides the question

| Component | Licence | How the program uses it | Consequence |
|---|---|---|---|
| pingouin 0.7.0 | GPL-3.0 | Imported **in the program's own process** (`reliability.py`: Cronbach's α and its Feldt interval) | Distributing the program with it makes the combined work subject to GPL-3.0 |
| Tesseract OCR runtime: tesseract.exe and its DLLs (jbigkit GPL-2.0+; libiconv, libintl, libunistring, libidn2 LGPL; GCC runtime with exception) | Apache-2.0 (Tesseract) plus the GPL/LGPL libraries | A **separate process** the program starts | Ship the licence texts (done) and the corresponding source, or a written offer, for the GPL/LGPL parts with each public release |
| Everything else in the bundle (numpy, scipy, pandas, statsmodels, matplotlib, flet, python-docx, pypdf, pypdfium2, Pillow, cryptography, openpyxl, …) | Permissive: MIT, BSD, Apache-2.0, PSF | In-process | Keep the notices; no copyleft obligation |

## 2. The options

### A. License the program GPL-3.0-or-later
- **Compatibility:** compatible with pingouin and with every other bundled licence. Apache-2.0 is compatible with GPL-3.0.
- **Obligations:**
  - publish or offer the complete corresponding source of each released version (this repository);
  - keep the licence notices;
  - add no further restrictions.
- **What others may do:** use, modify and redistribute the program, also commercially, under the same terms.
- **Code change needed:** none. pingouin stays.

### B. A permissive licence: MIT, Apache-2.0 or BSD-3-Clause
- **What it requires:** that **no GPL code is distributed in-process**.
- **Status:** the Stage 37 research-methods PR contains an **independently written** Cronbach's α, Feldt interval and α-if-item-deleted. They were written from the published formulas, not copied from pingouin, and are validated against pingouin used only as a test oracle and against hand computation. With that commit, pingouin moves to the build/test lock and leaves the installer.
- **Kept as its own commit**, so that the owner can take or drop it.
- **The OCR runtime remains** a separately executed program with its own licences. Its GPL/LGPL parts still need licence texts and a source offer with each release.

### C. Proprietary, or dual licensing
- **Precondition:** the same as B: no GPL code in-process.
- **Additional requirement:** clear ownership of all contributions.
- This option can be combined with B, for example Apache-2.0 for the community plus a commercial licence.

In every option the program keeps its source-available, offline-first design. Signing keys and certificates stay owner-controlled.

## 3. Research instruments: separate from the software licence

The program **must not bundle** the wording of licensed instruments. Researchers import their own authorised copies. The program stores only metadata: name, version, source and licence note. Public tests use invented items only.

| Instrument | What the provided copy states | What this means for the program |
|---|---|---|
| WHO-5 (2024 WHO edition) | © WHO 2024, **CC BY-NC-SA 3.0 IGO**. Non-commercial copying, redistribution and adaptation with citation. No suggestion of WHO endorsement and no WHO logo. Adaptations under the same or an equivalent CC licence. Translations need WHO's disclaimer. Commercial use by request to WHO. | Never ship the items in a commercial product. A researcher's own non-commercial use, with the citation, is theirs to make. Show the licence note when a WHO-5 version is recorded. |
| MSPSS | The provided PDF carries **no licence notice** | Verify the terms with the authors before any bundling or redistribution |
| UCLA Loneliness Scale, SACS | Not provided | Copyrighted by their authors or publishers; verify before use or redistribution |

## 4. Recommendation for the decision
1. Choose A, or choose B/C, before the first public installer.
   - **A** is the smallest change.
   - **B/C** keep more licensing freedom. The independent α implementation of the methods PR, with its oracle tests, makes them possible.
2. Whichever is chosen:
   - add `LICENSE` and a `NOTICE`/third-party file;
   - attach the OCR runtime's corresponding source (or a written offer) to each public release;
   - keep instruments out of the distribution.

