"""Validated file ingestion. Parsing is performed by the bounded worker, not the API."""
import json
import os
import subprocess
import sys
import hashlib
import io
from pathlib import PurePath
import uuid
import zipfile
from fastapi import APIRouter,Depends,File,Form,HTTPException,UploadFile
from fastapi.responses import Response
from urllib.parse import quote
from . import access,auth,db

router=APIRouter(prefix='/api/v1/files')
MAX_BYTES=10*1024*1024
MAX_TEXT=200000
TEXT={'.txt','.md','.csv','.json','.py','.js','.ts','.tsx','.jsx','.sql','.yaml','.yml','.log','.html','.css','.xml','.toml','.ini','.sh','.ps1','.c','.cpp','.h','.java','.rs','.go','.r','.tex'}
SUPPORTED=TEXT|{'.pdf','.docx','.xlsx'}

def owned(conn,user,ident,lock=False):
    row=conn.execute('SELECT * FROM workspace_files f WHERE id=%s AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.id=f.project_id AND p.deleted_at IS NOT NULL) AND (owner_id=%s OR %s=\'ADMIN\')'+(' FOR UPDATE' if lock else ''),(ident,user['id'],user['role'])).fetchone()
    if not row:raise HTTPException(404,'File not found.')
    return row

@router.get('')
def listing(project_id:uuid.UUID|None=None,user=Depends(auth.session)):
    if project_id is not None:
        with db.connect() as conn: access.project(conn,user,project_id)
    return db.query("""
        SELECT id,owner_id,project_id,name,media_type,size_bytes,sha256,status,error,truncated,document_id,created_at,processed_at
        FROM workspace_files f WHERE NOT EXISTS (SELECT 1 FROM projects p WHERE p.id=f.project_id AND p.deleted_at IS NOT NULL) AND (owner_id=%s OR %s='ADMIN') AND (%s::uuid IS NULL OR project_id=%s)
        ORDER BY created_at DESC LIMIT 200
    """,(user['id'],user['role'],project_id,project_id))


@router.post('',status_code=201)
async def upload(file:UploadFile=File(...),project_id:uuid.UUID|None=Form(default=None),user=Depends(auth.session)):
    access.writer(user)
    name=(file.filename or '').replace('\\','/').split('/')[-1].strip()
    if not name or len(name)>160 or any(ord(c)<32 for c in name) or PurePath(name).suffix.lower() not in SUPPORTED:raise HTTPException(422,'Choose a supported text/code, PDF, DOCX or XLSX file with a filename up to 160 characters.')
    data=await file.read(MAX_BYTES+1)
    await file.close()
    if not data or len(data)>MAX_BYTES:raise HTTPException(413,'Files must contain data and be no larger than 10 MB.')
    ident=uuid.uuid4()
    with db.connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(187875438)')
        if project_id:access.project(conn,user,project_id,True)
        quota=conn.execute('SELECT coalesce(sum(size_bytes),0) AS n FROM workspace_files WHERE owner_id=%s',(user['id'],)).fetchone()['n']
        if quota+len(data)>500*1024*1024:raise HTTPException(409,'Your file library has reached its 500 MB quota. Export or remove unused files.')
        if conn.execute("SELECT count(*) AS n FROM workspace_files WHERE status IN ('QUEUED','PROCESSING')").fetchone()['n']>=20:raise HTTPException(409,'The file-processing queue is full. Try again later.')
        conn.execute("INSERT INTO workspace_files(id,owner_id,project_id,name,media_type,size_bytes,sha256,raw,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'QUEUED')",(ident,user['id'],project_id,name,file.content_type or 'application/octet-stream',len(data),hashlib.sha256(data).hexdigest(),data))
        db.event('file.uploaded',user['id'],{'file_id':str(ident),'bytes':len(data)},conn=conn)
    return {'id':ident,'name':name,'status':'QUEUED'}

@router.get('/{ident}')
def detail(ident:uuid.UUID,user=Depends(auth.session)):
    with db.connect() as conn:
        row=owned(conn,user,ident)
        del row['raw']
        return row

@router.get('/{ident}/download')
def download(ident:uuid.UUID,user=Depends(auth.session)):
    with db.connect() as conn:row=owned(conn,user,ident)
    return Response(bytes(row['raw']),media_type='application/octet-stream',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['name'],safe='')})

@router.delete('/{ident}')
def remove(ident:uuid.UUID,user=Depends(auth.session)):
    access.writer(user)
    with db.connect() as conn:
        row=owned(conn,user,ident,True)
        if row['status']=='PROCESSING':raise HTTPException(409,'Wait for file processing to finish before deleting it.')
        if row['document_id']:
            access.project(conn,user,row['project_id'],True)
            conn.execute('DELETE FROM document_versions WHERE document_id=%s',(row['document_id'],))
            conn.execute('DELETE FROM documents WHERE id=%s',(row['document_id'],))
        conn.execute('DELETE FROM workspace_files WHERE id=%s',(ident,))
        db.event('file.deleted',user['id'],{'file_id':str(ident)},conn=conn)
    return {'ok':True}

def check_archive(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries=archive.infolist()
            if len(entries)>2000 or sum(e.file_size for e in entries)>32*1024*1024:raise ValueError('Archive exceeds document-processing limits.')
            if any(e.file_size>1024*1024 and e.file_size>max(e.compress_size,1)*150 for e in entries):raise ValueError('Document compression ratio exceeds safe processing limits.')
    except zipfile.BadZipFile:raise ValueError('The Office document is not a valid DOCX/XLSX file.') from None

def extract(name,data):
    suffix=PurePath(name).suffix.lower()
    if suffix in TEXT:
        try:text=data.decode('utf-8-sig')
        except UnicodeDecodeError:raise ValueError('Text files must be UTF-8 encoded.') from None
        if '\0' in text:raise ValueError('Binary content is not supported as text.')
    elif suffix=='.pdf':
        from pypdf import PdfReader
        try:
            reader=PdfReader(io.BytesIO(data),strict=False)
            if reader.is_encrypted:raise ValueError('Encrypted PDFs are not supported. Upload an unlocked copy.')
            if len(reader.pages)>100:raise ValueError('PDFs are limited to 100 pages.')
            parts=[];has_text=False
            for i,page in enumerate(reader.pages):
                page_text=page.extract_text() or ''
                has_text=has_text or bool(page_text.strip())
                parts.append(f'--- Page {i+1} ---\n'+page_text)
                if sum(map(len,parts))>MAX_TEXT:break
            text='\n\n'.join(parts)
            if not has_text:raise ValueError('No usable PDF text was found. Scanned PDFs require OCR, which is not configured.')
        except ValueError:raise
        except Exception:raise ValueError('The PDF could not be parsed.') from None
    elif suffix=='.docx':
        check_archive(data)
        from docx import Document
        doc=Document(io.BytesIO(data));parts=[p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:parts.append(' | '.join(cell.text for cell in row.cells))
        text='\n'.join(parts)
    elif suffix=='.xlsx':
        check_archive(data)
        from openpyxl import load_workbook
        workbook=load_workbook(io.BytesIO(data),read_only=True,data_only=True,keep_links=False)
        parts=[];cells=0
        try:
            for sheet in workbook.worksheets[:20]:
                parts.append('# '+sheet.title)
                for row in sheet.iter_rows(max_row=min(sheet.max_row or 1,5000),max_col=min(sheet.max_column or 1,100),values_only=True):
                    cells+=len(row)
                    if cells>100000:raise ValueError('Spreadsheet exceeds the 100,000-cell processing limit.')
                    parts.append(' | '.join('' if v is None else str(v) for v in row))
                    if sum(map(len,parts))>MAX_TEXT:break
                if sum(map(len,parts))>MAX_TEXT:break
            text='\n'.join(parts)
        finally:workbook.close()
    else:raise ValueError('Unsupported file format.')
    return text[:MAX_TEXT],len(text)>MAX_TEXT

def claim():
    with db.connect() as conn:
        conn.execute("UPDATE workspace_files SET status='FAILED',error='Processing interrupted. Upload the file again to retry.',lease_until=NULL,processed_at=now() WHERE status='PROCESSING' AND lease_until<now()")
        row=conn.execute("SELECT * FROM workspace_files WHERE status='QUEUED' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if row:conn.execute("UPDATE workspace_files SET status='PROCESSING',lease_until=now()+interval '30 seconds' WHERE id=%s",(row['id'],))
        return row

def extract_isolated(name, data):
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'core_ai.files', name], input=data,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20, check=True,
            env={'LANG': 'C.UTF-8', 'PYTHONPATH': os.pathsep.join(sys.path)},
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError('File extraction exceeded 20 seconds.') from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError('File extraction failed. Check the file format.') from exc
    payload = json.loads(result.stdout)
    if 'error' in payload:
        raise ValueError(payload['error'])
    return payload['text'], payload['truncated']


def process(row, *, parse=extract):
    try:
        text,truncated=parse(row['name'],bytes(row['raw']))
        if not text.strip():raise ValueError('No readable text was found in this file.')
        with db.connect() as conn:
            user=conn.execute('SELECT id,role FROM users WHERE id=%s AND enabled',(row['owner_id'],)).fetchone()
            if not user:raise ValueError('The uploading account is no longer active.')
            access.writer(user)
            doc_id=None
            if row['project_id']:
                access.project(conn,user,row['project_id'],True)
                doc_id=uuid.uuid4()
                conn.execute('INSERT INTO documents(id,project_id,title,content) VALUES (%s,%s,%s,%s)',(doc_id,row['project_id'],row['name'],text))
                conn.execute('INSERT INTO document_versions(document_id,project_id,version,title,content) VALUES (%s,%s,1,%s,%s)',(doc_id,row['project_id'],row['name'],text))
            conn.execute("UPDATE workspace_files SET status='READY',text_content=%s,truncated=%s,document_id=%s,processed_at=now(),lease_until=NULL WHERE id=%s",(text,truncated,doc_id,row['id']))
            db.event('file.processed',row['owner_id'],{'file_id':str(row['id']),'document_id':str(doc_id) if doc_id else None,'truncated':truncated},conn=conn)
    except Exception as exc:
        message=str(exc) if isinstance(exc,ValueError) else 'File processing failed. Check the format and access permissions.'
        db.query("UPDATE workspace_files SET status='FAILED',error=%s,lease_until=NULL,processed_at=now() WHERE id=%s",(message[:500],row['id']))

if __name__ == '__main__':
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 16))
    try:
        text, truncated = extract(sys.argv[1], sys.stdin.buffer.read())
        print(json.dumps({'text': text, 'truncated': truncated}))
    except ValueError as exc:
        print(json.dumps({'error': str(exc)[:500]}))
