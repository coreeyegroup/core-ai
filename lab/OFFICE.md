# Independent DOCX and XLSX utilities

Adds two original Apache-2.0 scripts from the existing pinned
anthropics/skills source. The original PDF/PPTX recipes and their receipt
digests remain unchanged. This separate runtime does not replace any
existing image.

- docx-merge-runs: merge adjacent equally formatted text runs while
  retaining displayed text and distinct bold formatting. Fixture uses
  python-docx and validates both the original and result.
- xlsx-recalc: recalculate a workbook using upstream recalc.py and
  LibreOffice Calc. Fixture asserts the original formula remains and
  the computed cached result is 42, with zero reported formula errors.

Review the source and runtime definitions on a dedicated test host. The
base image digest and Python package versions are pinned. Debian packages
are resolved from the image's configured repositories at build time;
they are not version- or hash-locked. Record the resulting image ID.
No host LibreOffice or production Python change is required.

    docker build -t core-ai-lab-office:0.1.0 lab/runtime/office
    IMAGE=$(docker image inspect --format '{{.Id}}' core-ai-lab-office:0.1.0)
    python3 lab/document_programs.py review docx-merge-runs --image "$IMAGE"
    python3 lab/document_programs.py review xlsx-recalc --image "$IMAGE"

After reviewing each plan, copy its actual digest:

    python3 lab/document_programs.py install docx-merge-runs --image "$IMAGE" --approve DOCX_DIGEST
    python3 lab/document_programs.py install xlsx-recalc --image "$IMAGE" --approve XLSX_DIGEST

User-selected input and a new output path are required for editing:

    python3 lab/document_programs.py run docx-merge-runs --image "$IMAGE" --input /path/to/input.docx --output /path/to/new.docx
    python3 lab/document_programs.py run xlsx-recalc --image "$IMAGE" --input /path/to/input.xlsx --output /path/to/new.xlsx

Input is read-only and execution is offline, non-root, resource bounded.
The program operates on scratch data and sends the result through stdout.
The host checks size and expected ZIP structure before exclusive
publication. Existing outputs are never overwritten. Input/output limit
is 32 MiB. The input must be readable by the container user. The wrapper
withholds XLSX output when recalculation reports errors or uncomputed
cells. This release supports .docx and .xlsx only, not macro-enabled
formats, linked-workbook workflows, full Office editing, or visual
rendering checks. The test verifies synthetic fixtures, not all real
documents. Inspect real output before using it.

Tests: python3 -m unittest discover -s tests -p 'test_independent*.py' -v
