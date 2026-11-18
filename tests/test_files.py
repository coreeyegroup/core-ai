"""Parser limits are tested without a running provider or database."""
import io
import zipfile
import pytest
from core_ai.files import extract,check_archive,MAX_TEXT

def test_utf8_binary_and_text_cap():
    assert extract('memo.md',b'# Notes')[0]=='# Notes'
    with pytest.raises(ValueError,match='UTF-8'):extract('memo.txt',b'\xff')
    with pytest.raises(ValueError,match='Binary'):extract('memo.txt',b'a\0b')
    text,truncated=extract('memo.txt',('x'*(MAX_TEXT+1)).encode())
    assert truncated and len(text)==MAX_TEXT

def test_docx_and_spreadsheet_extraction():
    from docx import Document
    from openpyxl import Workbook
    b=io.BytesIO();doc=Document();doc.add_paragraph('Project findings');doc.save(b)
    assert 'Project findings' in extract('report.docx',b.getvalue())[0]
    b=io.BytesIO();wb=Workbook();wb.active.append(['metric','value']);wb.active.append(['requests',12]);wb.save(b)
    assert 'requests | 12' in extract('data.xlsx',b.getvalue())[0]

def test_compressed_document_limit():
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('bomb.xml','x'*2000000)
    with pytest.raises(ValueError,match='compression ratio'):check_archive(b.getvalue())
    with pytest.raises(ValueError,match='valid DOCX'):check_archive(b'bad zip')

def test_image_only_pdf_reports_ocr_unavailable():
    from pypdf import PdfWriter
    b=io.BytesIO();writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.write(b)
    with pytest.raises(ValueError,match='OCR'):extract('scanned.pdf',b.getvalue())
