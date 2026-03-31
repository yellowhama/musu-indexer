import re
from collections import Counter
from typing import List, Dict, Tuple

# 너무 흔해서 검색 품질을 망치는 단어들
STOPWORDS = {
    "이", "그", "저", "것", "수", "등", "좀", "관련", "대해", "대한",
    "어디", "무엇", "어떻게", "왜", "있는", "하는", "되는", "에서", "으로",
    "를", "을", "이랑", "하고", "그리고", "또", "근데", "그럼", "지금",
    "파일", "문서", "코드", "내용", "부분", "처리", "기능", "방식",
    "the", "a", "an", "is", "are", "of", "to", "for", "in", "on",
    "and", "or", "with", "what", "how", "why"
}

# 너무 일반적인 기술 단어들.
WEAK_TERMS = {
    "data", "value", "object", "thing", "system", "method", "class",
    "module", "function", "info", "result", "item", "list"
}

# 간단 동의어/연관어 사전
SYNONYMS: Dict[str, List[str]] = {
    "동전": ["coin", "currency", "mint", "주화"],
    "코인": ["coin", "currency", "token"],
    "로그인": ["login", "auth", "signin", "session"],
    "인증": ["auth", "authentication", "token", "signin"],
    "세션": ["session", "token", "cookie", "auth"],
    "만료": ["expire", "expiry", "expired", "timeout"],
    "결제": ["payment", "billing", "checkout", "invoice"],
    "주문": ["order", "purchase", "checkout"],
    "사용자": ["user", "account", "member"],
    "에러": ["error", "exception", "fail", "failure"],
    "오류": ["error", "exception", "bug", "failure"],
    "버그": ["bug", "issue", "fault", "error"],
    "설정": ["config", "configuration", "env", "option"],
    "환경변수": ["env", "environment", "variable"],
    "게이트웨이": ["gateway", "proxy", "router", "dispatch"],
    "등록": ["register", "registration", "signup", "create"],
    "디스패치": ["dispatch", "route", "routing", "forward"],
    "문서": ["docs", "documentation", "guide", "readme"],
    "테스트": ["test", "testing", "spec", "assert"],
    "빌드": ["build", "compile", "bundle"],
    "검색": ["search", "query", "lookup", "find"],
    "인덱스": ["index", "indexing", "fts", "catalog"],
}

# 아주 단순한 한영 맵.
TRANSLATIONS: Dict[str, str] = {
    "동전": "coin",
    "로그인": "login",
    "인증": "auth",
    "세션": "session",
    "만료": "expiry",
    "결제": "payment",
    "주문": "order",
    "사용자": "user",
    "에러": "error",
    "오류": "error",
    "버그": "bug",
    "설정": "config",
    "환경변수": "env",
    "게이트웨이": "gateway",
    "등록": "register",
    "문서": "docs",
    "테스트": "test",
    "빌드": "build",
    "검색": "search",
    "인덱스": "index",
}

class QueryExpander:
    """AI 없이 작동하는 고속 자연어 질의 확장기"""
    
    @staticmethod
    def normalize_text(text: str) -> str:
        text = text.strip().lower()
        text = re.sub(r"[^\w\s\-/\.가-힣]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def tokenize(text: str) -> List[str]:
        pattern = r"[a-zA-Z_][a-zA-Z0-9_\-\.]*|[가-힣]+|\d+"
        return re.findall(pattern, text)

    @staticmethod
    def split_compound_token(token: str) -> List[str]:
        parts = re.split(r"[_\-.]+", token)
        return [p for p in parts if p and p != token]

    @staticmethod
    def is_good_token(token: str) -> bool:
        if len(token) <= 1:
            return False
        if token in STOPWORDS:
            return False
        if token in WEAK_TERMS:
            return False
        return True

    @staticmethod
    def expand_token(token: str) -> List[str]:
        expanded = []
        if token in SYNONYMS:
            expanded.extend(SYNONYMS[token])
        if token in TRANSLATIONS:
            expanded.append(TRANSLATIONS[token])
        expanded.extend(QueryExpander.split_compound_token(token))
        return expanded

    @staticmethod
    def score_terms(base_tokens: List[str], expanded_tokens: List[str]) -> Counter:
        scores = Counter()
        for tok in base_tokens:
            if QueryExpander.is_good_token(tok):
                scores[tok] += 3
        for tok in expanded_tokens:
            if QueryExpander.is_good_token(tok):
                scores[tok] += 1
                
        for tok in list(scores.keys()):
            if tok in WEAK_TERMS:
                scores[tok] -= 2
                
        for tok in list(scores.keys()):
            if scores[tok] <= 0:
                del scores[tok]
        return scores

    @classmethod
    def expand_query(cls, query: str, max_terms: int = 6) -> List[Tuple[str, int]]:
        normalized = cls.normalize_text(query)
        raw_tokens = cls.tokenize(normalized)
        base_tokens = [t for t in raw_tokens if cls.is_good_token(t)]
        
        expanded_tokens: List[str] = []
        for tok in base_tokens:
            expanded_tokens.extend(cls.expand_token(tok))
            
        scores = cls.score_terms(base_tokens, expanded_tokens)
        ranked = sorted(scores.items(), key=lambda x: (-x[1], -len(x[0]), x[0]))
        return ranked[:max_terms]

    @classmethod
    def build_fts_query(cls, query: str, max_terms: int = 6) -> str:
        """SQLite FTS5용 OR 질의 생성. 결과가 없으면 원본 query를 fallback으로 반환"""
        ranked_terms = cls.expand_query(query, max_terms=max_terms)
        if not ranked_terms:
            # 완전 필터링되어 아무것도 안 남으면 원래 문자열로 폴백 (에러 방지)
            return f'"{query}"'

        terms = [f'"{term}"' for term, _score in ranked_terms]
        return " OR ".join(terms)
