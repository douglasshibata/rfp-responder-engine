import json
import logging
import re
import time
from typing import List, Dict, Any, Optional
from config import settings

logger = logging.getLogger(__name__)

class RFPLLMFactory:
    """
    Multi-Provider LLM Factory routing tasks based on model strengths & privacy requirements:
    1. DeepInfra (Llama 3): High-volume, low-cost document parsing & question extraction.
    2. Ollama: Local privacy-first vector embedding & knowledge base retrieval.
    3. OpenAI (GPT-4o): Complex reasoning & persuasive answer synthesis.
    """

    @classmethod
    def get_extraction_llm(cls):
        """Routes document question extraction to DeepInfra (OpenAI-compatible Llama 3 endpoint)."""
        if settings.DEEPINFRA_API_KEY and settings.DEEPINFRA_API_KEY != "mock_deepinfra_key":
            try:
                from langchain_community.chat_models import ChatOpenAI
                return ChatOpenAI(
                    model_name=settings.DEEPINFRA_MODEL,
                    openai_api_key=settings.DEEPINFRA_API_KEY,
                    openai_api_base=settings.DEEPINFRA_BASE_URL,
                    temperature=0.1
                )
            except Exception as e:
                logger.warning(f"Could not initialize DeepInfra LLM client: {e}. Falling back.")
        return None

    @classmethod
    def get_reasoning_llm(cls):
        """Routes persuasive answer synthesis to OpenAI GPT-4o."""
        if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "mock_openai_key":
            try:
                from langchain_community.chat_models import ChatOpenAI
                return ChatOpenAI(
                    model_name=settings.OPENAI_MODEL,
                    openai_api_key=settings.OPENAI_API_KEY,
                    temperature=0.3
                )
            except Exception as e:
                logger.warning(f"Could not initialize OpenAI reasoning client: {e}. Falling back.")
        return None

    @classmethod
    def extract_questions(cls, document_text: str) -> List[str]:
        """
        Extracts individual questions from an RFP document text using DeepInfra.
        Includes a robust rule-based fallback for offline/test execution.
        """
        llm = cls.get_extraction_llm()
        if llm:
            try:
                prompt = (
                    "Extract all distinct RFP / Tender questions from the following text.\n"
                    "Return ONLY a valid JSON array of string questions, e.g. [\"Q1 text\", \"Q2 text\"].\n\n"
                    f"RFP DOCUMENT:\n{document_text}"
                )
                response = llm.invoke(prompt)
                content = response.content.strip()
                if "[" in content and "]" in content:
                    start = content.find("[")
                    end = content.rfind("]") + 1
                    json_str = content[start:end]
                    questions = json.loads(json_str)
                    if isinstance(questions, list) and len(questions) > 0:
                        return [str(q).strip() for q in questions if str(q).strip()]
            except Exception as e:
                logger.error(f"DeepInfra question extraction failed: {e}. Using fallback extractor.")

        # Fallback question extractor using regex and line splitting
        lines = [line.strip() for line in document_text.splitlines() if line.strip()]
        questions = []
        for line in lines:
            if line.endswith("?") or re.match(r"^(Q\d+|\d+|[\d\.\)]+|\-)\s*", line, re.IGNORECASE):
                # Clean prefix labels e.g. "Q1.", "1)", "1."
                cleaned = re.sub(r"^(Q\d+|\d+)\s*[\.\:\-\)]*\s*", "", line, flags=re.IGNORECASE).strip()
                if cleaned and cleaned not in questions:
                    questions.append(cleaned)

        if not questions and document_text.strip():
            paragraphs = [p.strip() for p in document_text.split("\n\n") if len(p.strip()) > 15]
            questions = paragraphs[:10] if paragraphs else [document_text[:150]]

        return questions

    @classmethod
    def embed_and_retrieve_context(cls, question: str, knowledge_base: Optional[str]) -> str:
        """
        Retrieves relevant context from internal company knowledge base using Ollama local embeddings
        or local keyword semantic search to maintain strict corporate data privacy.
        """
        if not knowledge_base or not knowledge_base.strip():
            return "No company knowledge base provided."

        paragraphs = [p.strip() for p in knowledge_base.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [p.strip() for p in knowledge_base.splitlines() if p.strip()]

        try:
            try:
                from langchain_ollama import OllamaEmbeddings
            except ImportError:
                from langchain_community.embeddings import OllamaEmbeddings

            embeddings = OllamaEmbeddings(
                base_url=settings.OLLAMA_BASE_URL,
                model=settings.OLLAMA_EMBED_MODEL
            )
            q_vec = embeddings.embed_query(question)
            p_vecs = [embeddings.embed_query(p) for p in paragraphs[:20]]

            scores = []
            for idx, p_vec in enumerate(p_vecs):
                similarity = sum(a * b for a, b in zip(q_vec, p_vec))
                scores.append((similarity, paragraphs[idx]))

            scores.sort(key=lambda x: x[0], reverse=True)
            top_context = "\n---\n".join([item[1] for item in scores[:2]])
            return top_context
        except Exception:
            logger.debug("Ollama embeddings unavailable. Using local term-frequency semantic matcher.")

        q_words = set(re.findall(r"\w+", question.lower()))
        matched = []
        for p in paragraphs:
            p_words = set(re.findall(r"\w+", p.lower()))
            overlap = len(q_words.intersection(p_words))
            matched.append((overlap, p))

        matched.sort(key=lambda x: x[0], reverse=True)
        top_paragraphs = [item[1] for item in matched[:2] if item[0] > 0]
        if not top_paragraphs:
            top_paragraphs = paragraphs[:2]

        return "\n---\n".join(top_paragraphs)

    @classmethod
    def synthesize_persuasive_answer(cls, question: str, context: str) -> Dict[str, Any]:
        """
        Synthesizes a highly persuasive, nuanced RFP response using OpenAI GPT-4o
        leveraging extracted question and retrieved local context.
        """
        start_time = time.time()
        llm = cls.get_reasoning_llm()

        if llm:
            try:
                prompt = (
                    "You are an expert RFP & B2B Proposal Writer.\n"
                    "Write a compelling, professional, and compliant response for the RFP question below "
                    "using the provided company knowledge base context.\n\n"
                    f"QUESTION:\n{question}\n\n"
                    f"COMPANY KNOWLEDGE BASE CONTEXT:\n{context}\n\n"
                    "RESPONSE:"
                )
                response = llm.invoke(prompt)
                answer_text = response.content.strip()
                latency = round(time.time() - start_time, 3)
                return {
                    "answer": answer_text,
                    "provider": "openai",
                    "latency_seconds": latency
                }
            except Exception as e:
                logger.error(f"OpenAI answer synthesis failed: {e}. Using fallback synthesizer.")

        latency = round(time.time() - start_time, 3)
        fallback_answer = (
            f"Regarding '{question}': Our organization adheres strictly to enterprise standards and industry best practices. "
            f"Based on internal capabilities ({context[:120]}...), we deliver scalable, secure, and fully compliant solutions "
            f"tailored to meet client specifications."
        )
        return {
            "answer": fallback_answer,
            "provider": "fallback_writer",
            "latency_seconds": latency
        }
