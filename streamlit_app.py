# main_streamlit.py - ملف Streamlit المعدل
import streamlit as st
import pickle, os
from app import authenticate_gdrive, index_drive_files, embed_texts, search, answer_with_gemini, get_account_info

st.set_page_config(page_title="🔍 نظام البحث الذكي", layout="wide")
st.title("🔍 نظام البحث الذكي باستخدام Gemini + Google Drive")

# -------------------- إدارة الحسابات --------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_account" not in st.session_state:
    st.session_state.current_account = None

if not st.session_state.authenticated:
    # قسم تسجيل الدخول
    st.header("🔐 تسجيل الدخول")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.info("""
        **📌 تعليمات التسجيل:**
        1. اضغط على زر تسجيل الدخول
        2. سيتم فتح نافذة جديدة لاختيار حساب Google
        3. اختر الحساب الذي تريد استخدامه
        4. اسمح للتطبيق بالوصول إلى Google Drive
        """)
    
    with col2:
        if st.button("🚀 تسجيل الدخول", type="primary", use_container_width=True):
            with st.spinner("جاري فتح نافذة تسجيل الدخول..."):
                service = authenticate_gdrive(open_browser=True)
                if service:
                    # الحصول على معلومات الحساب
                    account_info = get_account_info(service)
                    
                    st.session_state.authenticated = True
                    st.session_state.service = service
                    st.session_state.current_account = {
                        'name': account_info['name'],
                        'email': account_info['email']
                    }
                    
                    st.success(f"✅ تم تسجيل الدخول بنجاح! جاري تحميل الملفات...")
                    st.rerun()
                else:
                    st.error("❌ فشل تسجيل الدخول. حاول مرة أخرى.")

else:
    service = st.session_state.service
    current_account = st.session_state.current_account
    
    # عرض معلومات الحساب الحالي
    st.sidebar.header("👤 الحساب الحالي")
    st.sidebar.write(f"**الاسم:** {current_account['name']}")
    st.sidebar.write(f"**البريد الإلكتروني:** {current_account['email']}")
    
    # زر تسجيل الدخول بحساب آخر
    if st.sidebar.button("🔄 تسجيل الدخول بحساب آخر"):
        st.session_state.authenticated = False
        st.session_state.current_account = None
        st.rerun()
    
    # -------------------- فهرسة وإنشاء Embeddings --------------------
    if "documents" not in st.session_state:
        with st.spinner("📂 جاري فهرسة الملفات وإنشاء embeddings..."):
            documents, file_names, file_ids = index_drive_files(service)
            if documents:
                st.session_state.documents = documents
                st.session_state.file_names = file_names
                st.session_state.file_ids = file_ids
                st.session_state.doc_embeddings = embed_texts(documents)
                st.success(f"✅ تم تجهيز النظام! تم فهرسة {len(documents)} ملف")
            else:
                st.error("❌ لم يتم العثور على ملفات نصية للفهرسة")

    # -------------------- إدخال السؤال --------------------
    if "documents" in st.session_state and st.session_state.documents:
        st.header("🔍 البحث في الملفات")
        
        query = st.text_input("📝 اكتب سؤالك هنا:", placeholder="مثال: ما هي أهداف المشروع؟")
        
        if query:
            with st.spinner("🔍 جاري البحث في الملفات..."):
                context, best_files, best_file_ids, best_scores = search(
                    query,
                    st.session_state.documents,
                    st.session_state.file_names,
                    st.session_state.file_ids,
                    st.session_state.doc_embeddings
                )
            
            if best_files:
                # عرض الملفات المستخدمة للإجابة
                st.subheader("📂 الملفات المستخدمة للإجابة:")
                
                for i, (file, score) in enumerate(zip(best_files, best_scores)):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"**{i+1}. {file}**")
                    with col2:
                        st.write(f"**التشابه: {score:.3f}**")
                
                # توليد الإجابة
                with st.spinner("🤖 جاري توليد الإجابة..."):
                    answer = answer_with_gemini(query, context, best_files)
                
                st.subheader("💡 الإجابة:")
                st.write(answer)
            else:
                st.warning("⚠️ لم أجد ملفات ذات صلة بسؤالك")
    
    # زر تسجيل الخروج
    if st.sidebar.button("🚪 تسجيل الخروج", type="secondary"):
        st.session_state.authenticated = False
        st.session_state.current_account = None
        st.session_state.clear()
        st.rerun()