import streamlit as st
import pandas as pd
from docx import Document
from fpdf import FPDF
import io
from PyPDF2 import PdfReader
import time
from groq import Groq
import os
import re

# --- 1. CONFIGURATION & STYLING ---
st.set_page_config(
    page_title="German Biography Generator",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    /* Main Layout */
    .main {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #2c3e50 0%, #34495e 100%);
    }
    [data-testid="stSidebar"] * {
        color: white !important;
    }
    
    /* Header */
    .header-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 40px;
        border-radius: 20px;
        text-align: center;
        margin-bottom: 30px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        color: white;
    }
    .header-title {
        font-size: 3em; 
        font-weight: 800; 
        margin: 0;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
    }
    .header-subtitle {
        font-size: 1.2em; 
        margin-top: 10px; 
        opacity: 0.9;
    }

    /* Buttons */
    .stButton>button {
        background: linear-gradient(to right, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 12px 24px;
        font-weight: 600;
        transition: all 0.3s ease;
        width: 100%;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
    }

    /* Text Areas & Inputs */
    .stTextArea textarea {
        border-radius: 10px;
        border: 2px solid #e0e0e0;
        font-family: 'Courier New', monospace;
    }
    
    /* Status Containers */
    [data-testid="stStatusWidget"] {
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        background: white;
    }

    /* Hide Default Streamlit Elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- 2. HELPER FUNCTIONS ---

def simple_sent_tokenize(text):
    """Simple sentence tokenizer without NLTK"""
    if not text: return []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

def simple_word_tokenize(text):
    """Simple word tokenizer without NLTK"""
    if not text: return []
    return re.findall(r'\b\w+\b', text)

def read_csv(file):
    """Robust CSV reader handling different separators"""
    try:
        # Try tab separator first (common for transcripts)
        df = pd.read_csv(file, sep='\t')
        if df.shape[1] < 2: # If only 1 column, retry with comma
            file.seek(0)
            df = pd.read_csv(file, sep=',')
            
        if 'Transkript' in df.columns:
            df['Transkript'] = df['Transkript'].fillna('').astype(str)
            return "\n".join(df['Transkript'].tolist())
        else:
            # Concatenate all columns if 'Transkript' header not found
            return "\n".join(df.astype(str).apply(' '.join, axis=1).tolist())
    except Exception as e:
        raise ValueError(f"CSV format error: {str(e)}")

def read_docx(file):
    try:
        doc = Document(io.BytesIO(file.read()))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip() != '']
        return "\n".join(paragraphs)
    except Exception as e:
        raise ValueError(f"DOCX error: {str(e)}")

def read_pdf(file):
    try:
        reader = PdfReader(io.BytesIO(file.read()))
        text = []
        for page in reader.pages:
            extract = page.extract_text()
            if extract:
                text.append(extract)
        return "\n".join(text)
    except Exception as e:
        raise ValueError(f"PDF error: {str(e)}")

def divide_into_chunks(text, max_words_per_chunk):
    sentences = simple_sent_tokenize(text)
    chunks = []
    current_chunk = []
    current_word_count = 0

    for sentence in sentences:
        words_in_sentence = len(simple_word_tokenize(sentence))
        if current_word_count + words_in_sentence > max_words_per_chunk:
            chunks.append(' '.join(current_chunk))
            current_chunk = [sentence]
            current_word_count = words_in_sentence
        else:
            current_chunk.append(sentence)
            current_word_count += words_in_sentence

    if current_chunk:
        chunks.append(' '.join(current_chunk))

    return chunks

def save_text_to_pdf(text):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font('Arial', size=12)
    
    # Handle German characters for FPDF (Latin-1 encoding)
    replacements = {
        '–': '-', '—': '-', '“': '"', '”': '"', '’': "'", '‘': "'"
    }
    
    for line in text.split('\n'):
        clean_line = line
        for char, repl in replacements.items():
            clean_line = clean_line.replace(char, repl)
            
        try:
            clean_line = clean_line.encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 10, clean_line)
        except Exception:
            pdf.multi_cell(0, 10, "Error rendering line.")
            
    return pdf.output(dest='S').encode('latin-1')

# --- 3. AI SUMMARIZER CLASS ---

class Summarizer:
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.3-70b-versatile" 

    def invoke_with_retry(self, full_input, retries=3):
        for attempt in range(retries):
            try:
                chat_completion = self.client.chat.completions.create(
                    messages=[{"role": "user", "content": full_input}],
                    model=self.model,
                    temperature=0.1,
                    max_tokens=7000, 
                    top_p=1,
                )
                return chat_completion.choices[0].message.content
            except Exception as e:
                error_msg = str(e).lower()
                
                if "429" in error_msg or "rate limit" in error_msg:
                    time.sleep(10)
                elif "413" in error_msg:
                    raise ValueError("Request too large. Please report this.")
                
                # Fallback strategy
                if "model_decommissioned" in error_msg or "deprecated" in error_msg:
                    alternatives = ["llama-3.1-70b-versatile", "mixtral-8x7b-32768", "llama3-70b-8192"]
                    for alt in alternatives:
                        if alt == self.model: continue
                        try:
                            self.model = alt
                            return self.invoke_with_retry(full_input, retries=1)
                        except: continue
                
                if attempt < retries - 1:
                    time.sleep(3)
                else:
                    raise e

    def extract_key_facts(self, input_text):
        """
        Step 1: Extract pure facts without worrying about word count yet.
        """
        prompt = """
        Analyze this transcript section and extract a dense list of biographical facts in German.
        
        CRITICAL INSTRUCTION:
        1. Capture ALL specific dates (Day, Month, Year) mentioned.
        2. Capture ALL specific names (People, Companies, Schools, Places).
        3. Capture specific "Edge Case" details: unusual events, accidents, specific awards, unique failures or successes.
        4. Do NOT write a story yet. Just output dense, factual notes.
        
        Transcript Section:
        """
        
        # Max 2500 words per chunk to stay under API limits
        chunks = divide_into_chunks(input_text, max_words_per_chunk=2500)
        fact_sheets = []
        
        with st.status("🔍 Analyzing transcript for specific details...", expanded=True) as status:
            for i, chunk in enumerate(chunks):
                status.update(label=f"Extracting facts from part {i+1} of {len(chunks)}...", state="running")
                full_input = chunk + prompt
                output_facts = self.invoke_with_retry(full_input)
                fact_sheets.append(output_facts.strip())
                
                if i < len(chunks) - 1:
                    time.sleep(5) # Rate limit safety
            
            status.update(label="Fact extraction complete!", state="complete")
            
        return " ".join(fact_sheets)

    def condense_and_polish(self, all_facts):
        """
        Step 2: Synthesize facts into a strict <800 word narrative.
        """
        prompt = f"""
        Using the factual notes provided below, write a professional biography in German.
        
        STRICT CONSTRAINTS:
        1. MAXIMUM LENGTH: 800 Words. Be concise.
        2. Do NOT lose the specific "edge case" info (dates, specific names, unique events).
        3. Narrative Style: Third-person, chronological, professional.
        4. Structure:
           - Early Life & Family
           - Education
           - Professional Career
           - Personal Life & Key Milestones
        
        Notes to synthesize:
        {all_facts}
        """
        
        # We process this in one go as the input is now just "Facts" (smaller than transcript)
        # If facts are still huge, we chunk them, but usually facts are compressed enough.
        chunks = divide_into_chunks(all_facts, max_words_per_chunk=6000)
        
        final_bio_parts = []
        
        with st.status("✨ Synthesizing final biography (<800 words)...", expanded=True) as status:
            for i, chunk in enumerate(chunks):
                full_input = chunk + prompt
                output = self.invoke_with_retry(full_input)
                final_bio_parts.append(output)
                if i < len(chunks) - 1: time.sleep(5)
            
            status.update(label="Synthesis complete!", state="complete")

        full_text = " ".join(final_bio_parts)
        return self.remove_incomplete_sentence(full_text)

    def remove_incomplete_sentence(self, text):
        if not text: return ""
        if text.strip().endswith('.'): return text
        last_dot = text.rfind('.')
        return text[:last_dot + 1] if last_dot != -1 else text

# --- 4. MAIN APPLICATION ---

def main():
    # Header
    st.markdown("""
        <div class="header-container">
            <h1 class="header-title">📝 German Biography Generator</h1>
            <p class="header-subtitle">Professional Compact Biographies (Max 800 Words)</p>
        </div>
    """, unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        api_key = st.text_input("Groq API Key", type="password", help="Get from console.groq.com")
        if api_key:
            st.success("✅ Key loaded")
        else:
            st.warning("⚠️ Key required")
        
        st.markdown("---")
        st.info("💡 **Mode:** Compact Biography. \nGenerates a dense summary (<800 words) while preserving specific dates and unique life events.")

    # File Upload
    uploaded_files = st.file_uploader(
        "Upload Interview Files (PDF, DOCX, CSV)", 
        type=['pdf', 'docx', 'csv'], 
        accept_multiple_files=True
    )

    # Stats
    if uploaded_files:
        col1, col2 = st.columns(2)
        col1.metric("Files Selected", len(uploaded_files))
        total_size_mb = sum([f.size for f in uploaded_files]) / (1024*1024)
        col2.metric("Total Size", f"{total_size_mb:.2f} MB")

    # Action Button
    st.markdown("---")
    if uploaded_files and api_key:
        if st.button("🚀 Generate Compact Biographies", type="primary", use_container_width=True):
            process_files(uploaded_files, api_key)
    elif uploaded_files and not api_key:
        st.error("Please enter your API Key in the sidebar.")
    elif not uploaded_files:
        st.info("👆 Upload files to begin.")

def process_files(uploaded_files, api_key):
    summarizer = Summarizer(api_key)
    
    for idx, file in enumerate(uploaded_files):
        st.subheader(f"📄 Processing: {file.name}")
        
        # Create a container for each file
        with st.container():
            try:
                # 1. Read File
                transcript_text = ""
                with st.spinner("📖 Extracting text..."):
                    if file.name.endswith('.csv'): transcript_text = read_csv(file)
                    elif file.name.endswith('.docx'): transcript_text = read_docx(file)
                    elif file.name.endswith('.pdf'): transcript_text = read_pdf(file)
                
                if not transcript_text or len(transcript_text.strip()) < 50:
                    st.error(f"❌ Could not extract sufficient text from {file.name}")
                    continue

                word_count = len(simple_word_tokenize(transcript_text))
                st.caption(f"Original Word count: {word_count}")

                # 2. Extract Facts (Pass 1)
                facts = summarizer.extract_key_facts(transcript_text)
                
                # 3. Synthesize Compact Bio (Pass 2)
                final_bio = summarizer.condense_and_polish(facts)
                
                # 4. Result Area
                st.success("✅ Biography Generated!")
                
                # Show final word count
                final_wc = len(simple_word_tokenize(final_bio))
                st.metric("Final Word Count", final_wc)

                # Preview
                with st.expander("👁️ Preview Text"):
                    st.text_area("Content", final_bio, height=300, disabled=True)
                
                # PDF Download
                pdf_bytes = save_text_to_pdf(final_bio)
                out_name = os.path.splitext(file.name)[0] + "_bio.pdf"
                
                st.download_button(
                    label=f"📥 Download PDF ({out_name})",
                    data=pdf_bytes,
                    file_name=out_name,
                    mime="application/pdf",
                    key=f"dl_{idx}",
                    use_container_width=True
                )

            except Exception as e:
                st.error(f"❌ Error processing {file.name}")
                with st.expander("Error Details"):
                    st.code(str(e))
        
        st.divider()
    
    if uploaded_files:
        st.balloons()
        st.success("🎉 All tasks completed!")

if __name__ == "__main__":
    main()