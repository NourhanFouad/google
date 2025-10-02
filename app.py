# app.py - الملف الرئيسي للتطبيق
import io, os, pickle, warnings
import pdfplumber
from docx import Document
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.generativeai as genai
import numpy as np

warnings.filterwarnings('ignore')
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# -------------------- المصادقة --------------------
def authenticate_gdrive(open_browser=True):
    creds = None
    token_file = "token.pickle"
    
    try:
        if os.path.exists(token_file):
            with open(token_file, "rb") as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    r"D:\google\client_secret_2_368639615599-s553j8nei3iolbq4as35abevl4ba6m61.apps.googleusercontent.com.json",
                    SCOPES
                )
                # يسمح للمستخدم باختيار الحساب مباشرة من نافذة Google
                creds = flow.run_local_server(
                    port=0, 
                    open_browser=open_browser,
                    prompt='consent'  # يطلب اختيار الحساب كل مرة
                )   

            with open(token_file, "wb") as token:
                pickle.dump(creds, token)

        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"❌ خطأ في المصادقة: {e}")
        return None

# -------------------- الحصول على معلومات الحساب --------------------
def get_account_info(service):
    try:
        about = service.about().get(fields="user").execute()
        user_info = about.get('user', {})
        return {
            'email': user_info.get('emailAddress', 'غير معروف'),
            'name': user_info.get('displayName', 'غير معروف')
        }
    except Exception as e:
        print(f"❌ خطأ في الحصول على معلومات الحساب: {e}")
        return {'email': 'غير معروف', 'name': 'غير معروف'}

# -------------------- قراءة الملفات --------------------
def read_file(file_id, mime_type, service):
    text = ""
    try:
        if mime_type.startswith("application/vnd.google-apps"):
            request = service.files().export_media(fileId=file_id, mimeType="text/plain")
        else:
            request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        if mime_type == "application/pdf":
            with pdfplumber.open(fh) as pdf:
                for page in pdf.pages:
                    if page.extract_text():
                        text += page.extract_text() + "\n"
        elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            temp_path = f"temp_{file_id}.docx"
            with open(temp_path, "wb") as f:
                f.write(fh.getvalue())
            doc = Document(temp_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
            os.remove(temp_path)
        else:
            text = fh.read().decode("utf-8", errors='ignore')
    except:
        text = ""
    return text.strip()

# -------------------- فهرسة الملفات --------------------
def index_drive_files(service):
    results = service.files().list(
        pageSize=100, fields="files(id, name, mimeType)", q="trashed=false"
    ).execute()
    items = results.get("files", [])
    documents, file_names, file_ids = [], [], []
    allowed_types = [
        'application/vnd.google-apps.document',
        'application/vnd.google-apps.spreadsheet',
        'application/vnd.google-apps.presentation',
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain'
    ]
    for item in items:
        if item["mimeType"] in allowed_types:
            text = read_file(item["id"], item["mimeType"], service)
            if len(text) > 20:
                documents.append(text)
                file_names.append(item["name"])
                file_ids.append(item["id"])
    return documents, file_names, file_ids

# -------------------- إنشاء Embeddings --------------------
def embed_texts(texts):
    genai.configure(api_key="AIzaSyAqH8V7huw-3R8CF7beqiwjUYk6PpNUc3E")
    embeddings = []
    for t in texts:
        try:
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=t,
                task_type="retrieval_document"
            )
            embeddings.append(np.array(result['embedding']))
        except:
            embeddings.append(np.zeros(768))
    return embeddings

# -------------------- البحث --------------------
def search(query, documents, file_names, file_ids, doc_embeddings, top_k=3):
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=query,
            task_type="retrieval_query"
        )
        query_emb = np.array(result['embedding'])
    except:
        return "", [], [], []
    sims = []
    for doc_emb in doc_embeddings:
        if np.linalg.norm(query_emb) > 0 and np.linalg.norm(doc_emb) > 0:
            sim = np.dot(query_emb, doc_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(doc_emb))
            sims.append(sim)
        else:
            sims.append(0.0)
    top_idx = np.argsort(sims)[-top_k:][::-1]
    context = "\n\n".join([documents[i] for i in top_idx])
    best_files = [file_names[i] for i in top_idx]
    best_file_ids = [file_ids[i] for i in top_idx]
    best_scores = [sims[i] for i in top_idx]
    return context, best_files, best_file_ids, best_scores

# -------------------- توليد الإجابة --------------------
def answer_with_gemini(query, context, source_files):
    model = genai.GenerativeModel("gemini-2.0-flash-exp")
    
    prompt = f"""
بناءً على السياق التالي، أجب على السؤال بدقة ووضوح.
إذا لم تجد الإجابة في السياق، قل بصراحة أن المعلومات غير متوفرة.

السياق:
{context[:8000]}

السؤال: {query}

بعد الإجابة، أذكر المصادر التي استخدمتها من القائمة التالية:
{source_files}
"""
    try:
        resp = model.generate_content(prompt)
        if hasattr(resp, "text") and resp.text:
            return resp.text
    except:
        return "⚠️ لم أستطع توليد إجابة"