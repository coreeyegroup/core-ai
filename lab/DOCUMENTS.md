# Independent document utilities (first batch)

Pinned anthropics/skills commit e4bb5d960d87126ff3b3a8af1a104b7db67560ba.
The two upstream scripts are Apache-2.0 (see the corresponding skill
LICENSE.txt files). Other repository capabilities have not been qualified.

- pdf-form-check: checks both a plain and a fillable synthetic PDF.
- pptx-text: checks two synthetic slides and their text markers.

On a dedicated test host, review the pinned scripts and the Dockerfile
and dependency versions. The build downloads wheels from PyPI, without
mounting production credentials or source. Versions are pinned; this is
not a hash-locked or vulnerability-audited dependency set. Runtime is
offline, non-root, read-only and resource-bounded. Docker alone is not
complete security isolation.

From the manager checkout:

    python3 lab/document_programs.py list
    docker build -t core-ai-lab-documents:0.1.0 lab/runtime/documents
    IMAGE=$(docker image inspect --format '{{.Id}}' core-ai-lab-documents:0.1.0)
    python3 lab/document_programs.py review pdf-form-check --image "$IMAGE"
    python3 lab/document_programs.py review pptx-text --image "$IMAGE"

After reviewing each plan, copy its actual digest into the corresponding
command (replace PDF_DIGEST and PPTX_DIGEST):

    python3 lab/document_programs.py install pdf-form-check --image "$IMAGE" --approve PDF_DIGEST
    python3 lab/document_programs.py install pptx-text --image "$IMAGE" --approve PPTX_DIGEST

Run against a user-selected readable test document (not production secrets):

    python3 lab/document_programs.py run pdf-form-check --image "$IMAGE" --input /path/to/example.pdf
    python3 lab/document_programs.py run pptx-text --image "$IMAGE" --input /path/to/example.pptx

Each input is individually mounted read-only and limited to 32 MiB in this
initial recipe. No output files are written to the input directory. Output
streams to the operator; logs contain execution metadata, not document content.
The qualification receipt applies to the exact source and image pair.
This does not install LibreOffice, DOCX/XLSX editing or PDF rendering/OCR.
Those are separate capabilities with different dependencies.

Tests: python3 -m unittest discover -s tests -p 'test_independent*.py' -v
