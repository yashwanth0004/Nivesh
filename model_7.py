"""
model_7.py  –  Qwen 3:8B AI Brain (always-loaded, highly accurate)
=================================================================
"""

import os
import re
import pdfplumber
from langchain_ollama import OllamaLLM
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.documents import Document

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# ─── LANGUAGE CODE → FULL NAME MAP ────────────────────────────────────────────
LANG_CODE_TO_NAME = {
    "as": "Assamese", "bn": "Bengali", "brx": "Bodo", "doi": "Dogri",
    "gu": "Gujarati", "hi": "Hindi", "kn": "Kannada", "ks": "Kashmiri",
    "kok": "Konkani", "mai": "Maithili", "ml": "Malayalam", "mni": "Manipuri",
    "mr": "Marathi", "ne": "Nepali", "or": "Odia", "pa": "Punjabi",
    "sa": "Sanskrit", "sat": "Santali", "sd": "Sindhi", "ta": "Tamil",
    "te": "Telugu", "ur": "Urdu", "en": "English",
}

# ─── SAFETY REGISTRY ──────────────────────────────────────────────────────────
BANNED_COMPANIES = [
    "nasdaq", "nyse", "nse", "bse",
    "apple", "google", "microsoft", "amazon", "tesla", "meta", "nvidia",
    "aapl", "goog", "tsla", "nvda", "bitcoin", "btc", "ethereum", "eth",
    "reliance", "infosys", "wipro", "tcs", "hdfc", "icici", "sbi",
    "యాపిల్", "గూగుల్", "టెస్లా", "ఎన్విడియా", "రిలయన్స్",
]

# ─── MODULE-LEVEL STATE ────────────────────────────────────────────────────────
llm              = None
vector_db        = None
_initialized     = False
chat_history     = []
_last_language_code = None

DB_DIR   = "./chroma_db"
DOCS_DIR = "./trading_docs"

# ─── BULLETPROOF SYSTEM PROMPT ────────────────────────────────────────────────
CHAT_SYSTEM_PROMPT = """/no_think
You are a highly accurate, strict, and helpful Financial Education AI for Indian users.

CRITICAL LANGUAGE RULE: 
You MUST respond entirely in {language}. Do not use English words unless absolutely necessary, and if you do, transliterate them into {language}.

STRICT RULES:
1. ONLY answer questions about basic financial education (savings, stocks, mutual funds, investing concepts, fraud prevention).
2. IF UNCLEAR / VOICE TYPO: If the user's question contains gibberish, misspelled words (like "నాక్స్టాక్స్" instead of "నాకు స్టాక్స్"), or makes no sense, DO NOT GUESS. Reply exactly with: "I didn't quite catch that. Could you please repeat your question clearly?" (Translated to {language}).
3. OFF-TOPIC: If the question is not about finance, reply in {language}: "I can only answer questions related to financial education."
4. NO ADVICE: Never recommend specific stocks, coins, or companies.
5. FORMAT: Respond in clear, plain {language}. Give a useful, thorough explanation: normally 6-10 short numbered steps or points, define unfamiliar terms, explain practical next steps and common fees/risks where relevant, and end with a simple example. Do not stop after a short summary. Keep unrelated/simple answers proportionate. Never invent current fees, eligibility rules, or guarantees; say when the user should confirm a current detail with their bank, broker, depository participant, or official source.
6. DEMAT ACCOUNT QUESTIONS: Explain what the account holds, how to choose a SEBI-registered depository participant, the usual online/offline opening steps, PAN and KYC/identity/address verification, bank linkage, nominee choice, account activation, delivery instructions, common charges (which vary by provider), account security, and how to verify the provider. Distinguish a demat securities account from D-Mart retail stores. Do not recommend a particular broker or investment.
7. COMPLETION: Finish the final sentence and any numbered point completely. Do not leave a word, list item, or explanation cut off.

Context (if any):
{context}
"""

def _parse_text_and_tables():
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)
        return []
    parsed = []
    for file in os.listdir(DOCS_DIR):
        if file.endswith(".pdf"):
            path = os.path.join(DOCS_DIR, file)
            with pdfplumber.open(path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    tables = page.extract_tables()
                    rows = []
                    for tbl in tables:
                        for row in tbl:
                            r = [str(c).strip() for c in row if c]
                            if r: rows.append(" | ".join(r))
                    content = text + "\n\n" + "\n".join(rows)
                    if content.strip():
                        parsed.append(Document(page_content=content, metadata={"source": file, "page": page_num}))
    return parsed

def _init_knowledge_base(emb):
    if os.path.exists(DB_DIR) and os.listdir(DB_DIR):
        return Chroma(persist_directory=DB_DIR, embedding_function=emb)
    docs = _parse_text_and_tables()
    if not docs: return None
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120)
    chunks = splitter.split_documents(docs)
    return Chroma.from_documents(chunks, emb, persist_directory=DB_DIR)

def initialize():
    global llm, vector_db, _initialized
    print("\n[STEP 1/3] Connecting to Qwen 3:8B via Ollama...")
    # FIXED: repeat_penalty was too high (1.4) which caused the AI to output gibberish.
    # Set to 1.15 to keep grammar correct. Temperature lowered to 0.1 for high accuracy.
    llm = OllamaLLM(
        model="qwen3:8b",
        temperature=0.1,    
        top_p=0.5,
        repeat_penalty=1.15, 
        # Telugu and other Indic scripts often use more tokens per sentence.
        # Leave enough context for the prompt/history and a complete detailed answer.
        num_ctx=8192,
        num_predict=2048,
        keep_alive=-1,
        streaming=True,
    )
    print("\n[STEP 2/3] Loading BGE-M3 embeddings...")
    # Pull the public BGE-M3 weights into the normal Hugging Face cache on first
    # startup instead of shipping multi-gigabyte weights inside this project.
    emb = HuggingFaceEmbeddings(
        model_name="BAAI/bge-m3",
        model_kwargs={"revision": "d5ab3da48ec596cd78a50b27e52c7211b49d870f"},
    )
    print("\n[STEP 3/3] Loading knowledge base...")
    vector_db = _init_knowledge_base(emb)
    _initialized = True
    print("\n[OK] AI model fully loaded and ready.\n")

def _get_language_name(lang_code: str) -> str:
    return LANG_CODE_TO_NAME.get(lang_code.lower().strip(), "English")

def _prepare_chat_language(lang_code: str) -> str:
    """Drop prior-language turns so chat history cannot pull output back to English."""
    global chat_history, _last_language_code
    code = (lang_code or "en").lower().strip()
    if code not in LANG_CODE_TO_NAME:
        code = "en"
    if _last_language_code is not None and code != _last_language_code:
        chat_history = []
    _last_language_code = code
    return code

def _security_check(query_lower: str):
    for company in BANNED_COMPANIES:
        if re.search(rf"\b{company}\b", query_lower):
            return "I am sorry, I cannot discuss specific companies or tickers. I only explain general financial education concepts."
    return None

def _get_context(clean_query: str) -> str:
    global vector_db
    if vector_db:
        results = vector_db.similarity_search(clean_query, k=2)
        if results:
            return "\n\n---\n\n".join([d.page_content for d in results])
    return "No specific document context. Use basic beginner-level financial knowledge. DO NOT mention specific exchange names, market indices, or company names."

def _strip_think_tags(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL)
    return text

def _is_repetition_loop(full_output: str) -> bool:
    if len(full_output) < 180:
        return False
    recent = re.sub(r"\s+", " ", full_output[-1200:]).strip()
    words = re.findall(r"[\w]+", recent, flags=re.UNICODE)
    if len(words) >= 24:
        seen = {}
        for i in range(len(words) - 5):
            gram = " ".join(words[i:i + 6])
            seen[gram] = seen.get(gram, 0) + 1
            if seen[gram] >= 3:
                return True
    # Catch exact repeated phrases in Indic scripts too, while avoiding the old
    # overlapping-character heuristic that could mistake normal Telugu for a loop.
    return bool(re.search(r"(.{32,100}?)\1{2,}", recent, flags=re.DOTALL))


def _clarify_query(user_query: str, lang_code: str):
    """Correct a common Telugu speech-to-text spelling of demat account."""
    query = (user_query or "").strip()
    if lang_code != "te":
        return query, False
    # Include the short-vowel spelling used in the reported Telugu prompt
    # (డిమార్ట్), as well as డీమార్ట్ / డీమాట్ / డీమ్యాట్.
    demat_word = re.compile(r"డ[ీి]?మా?ర్ట్|డ[ీి]?మా?ట్|డీ?మ్యాట్", re.IGNORECASE)
    account_context = re.search(r"అకౌంట్|ఖాతా|స్టార్ట్|తెరవ|ప్రారంభ|కావలసిన|వివరించ|ఎక్స్ప్లెయిన్", query)
    if account_context and demat_word.search(query):
        return demat_word.sub("డీమ్యాట్ (demat)", query), True
    return query, False


def _context_for_query(clean_query: str, is_demat_question: bool) -> str:
    if is_demat_question:
        return (
            "Intent clarification: This Telugu question asks how to open a demat (dematerialized securities) account "
            "and what documents and steps are needed. The phrase was misrecognized as D-Mart. It is not asking about "
            "the D-Mart retail company. Explain general account-opening steps, typical KYC documents, nominee choice, "
            "variable charges, account security, and verifying a SEBI-registered provider. Do not claim one fixed fee."
        )
    return _get_context(clean_query)

def stream_sentences(user_query: str, lang_code: str = "en"):
    global chat_history
    if not _initialized: raise RuntimeError("Call model_7.initialize() first.")

    lang_code = _prepare_chat_language(lang_code)
    language_name = _get_language_name(lang_code)
    clean_query, is_demat_question = _clarify_query(user_query, lang_code)
    query_lower   = clean_query.lower()

    rejection = _security_check(query_lower)
    if rejection:
        print(f"\nAI: {rejection}\n")
        yield rejection
        return

    context_str = _context_for_query(clean_query, is_demat_question)
    system_str  = CHAT_SYSTEM_PROMPT.replace("{language}", language_name)
    chain = ChatPromptTemplate.from_messages([
        ("system", system_str),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{user_query}")
    ]) | llm

    print("\nListening....", flush=True)
    print("AI: ", end="", flush=True)

    full_output = ""
    sentence_buf = ""
    SENT_END = re.compile(r"(?<=[^\d])[.!?।॥]+\s*|\n+")

    try:
        for raw_chunk in chain.stream({
            "user_query": clean_query,
            "chat_history": chat_history[-2:], # Keep history short to prevent drift
            "context": context_str,
        }):
            chunk = _strip_think_tags(raw_chunk)
            if not chunk: continue

            full_output += chunk
            sentence_buf += chunk
            print(chunk, end="", flush=True)

            if _is_repetition_loop(full_output):
                print("\n[Output trimmed: repetition detected.]")
                break

            while True:
                m = SENT_END.search(sentence_buf)
                if not m: break
                sentence = sentence_buf[: m.end()].strip()
                sentence_buf = sentence_buf[m.end():].strip()
                if len(sentence) >= 5:
                    yield sentence

    except KeyboardInterrupt:
        print("\n[Generation cancelled.]")
    except Exception as e:
        print(f"\n[Generation error: {e}]")
        yield "An error occurred during generation."
        return

    remainder = sentence_buf.strip()
    if len(remainder) >= 2:
        yield remainder

    print("\n")
    chat_history.append(HumanMessage(content=clean_query))
    chat_history.append(AIMessage(content=full_output.strip()))

def stream_response_chunks(user_query: str, lang_code: str = "en", cancel_event=None):
    """Yield Qwen's text chunks and control events for the live browser chat."""
    global chat_history
    if not _initialized:
        raise RuntimeError("Call model_7.initialize() first.")

    clean_query = user_query.strip()
    if not clean_query:
        return
    lang_code = _prepare_chat_language(lang_code)
    clean_query, is_demat_question = _clarify_query(clean_query, lang_code)
    rejection = _security_check(clean_query.lower())
    if rejection:
        yield rejection
        return

    language_name = _get_language_name(lang_code)
    context_str = _context_for_query(clean_query, is_demat_question)
    system_str = CHAT_SYSTEM_PROMPT.replace("{language}", language_name)
    full_output = ""
    print("\nAI: ", end="", flush=True)
    if cancel_event is not None and cancel_event.is_set():
        yield {"type": "stopped"}
        return
    chain = ChatPromptTemplate.from_messages([
        ("system", system_str),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{user_query}")
    ]) | llm
    loop_detected = False
    for raw_chunk in chain.stream({
        "user_query": clean_query,
        "chat_history": chat_history[-2:],
        "context": context_str,
    }):
        if cancel_event is not None and cancel_event.is_set():
            break
        chunk = _strip_think_tags(raw_chunk)
        if not chunk:
            continue
        if _is_repetition_loop(full_output + chunk):
            loop_detected = True
            break
        full_output += chunk
        print(chunk, end="", flush=True)
        yield chunk

    if cancel_event is not None and cancel_event.is_set():
        if full_output.strip():
            chat_history.extend((HumanMessage(content=clean_query), AIMessage(content=full_output.strip())))
        yield {"type": "stopped"}
        print("\n[Generation stopped by user.]", flush=True)
        return
    if loop_detected:
        print("\n[Repeated output detected; keeping the useful partial answer and stopping.]", flush=True)
        if full_output.strip():
            chat_history.extend((HumanMessage(content=clean_query), AIMessage(content=full_output.strip())))
        yield {"type": "loop_stopped"}
        return

    print("\n")
    if full_output.strip():
        chat_history.extend((HumanMessage(content=clean_query), AIMessage(content=full_output.strip())))

def chat_with_bot_stream(user_query: str, lang_code: str = "en") -> str:
    parts = []
    for sentence in stream_sentences(user_query, lang_code=lang_code):
        parts.append(sentence)
    return " ".join(parts)
