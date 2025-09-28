import os
from typing import Optional, Dict, Any, List
import google.generativeai as genai
from loguru import logger
import json
import asyncio

from ..models.content_models import CollectedContent, BlogArticle, BlogSection, ContentType


class LLMClient:
    """LLM API 클라이언트 (Google Gemini만 지원)"""

    def __init__(self, provider: str = "gemini"):
        self.provider = "gemini"  # 고정

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY 환경변수를 설정해주세요")

        genai.configure(api_key=api_key)
        # 최신 방식으로 모델 초기화 시도
        try:
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        except:
            try:
                self.model = genai.GenerativeModel('gemini-pro')
            except:
                # 가장 기본적인 모델명으로 시도
                self.model = genai.GenerativeModel('models/gemini-pro')

    async def generate_blog_article(
        self,
        collected_content: CollectedContent,
        topic: str,
        tone: str = "친근하고 정보성",
        target_audience: str = "일반"
    ) -> BlogArticle:
        """수집된 정보를 바탕으로 블로그 글 생성"""

        try:
            # 시스템 프롬프트 구성
            system_prompt = self._create_blog_writing_system_prompt(tone, target_audience)

            # 사용자 프롬프트 구성
            user_prompt = self._create_blog_writing_user_prompt(collected_content, topic)

            # LLM 호출 (Google Gemini만 사용)
            response = await self._call_gemini(system_prompt, user_prompt)

            # 응답 파싱 및 BlogArticle 객체 생성
            article = self._parse_blog_response(response, topic)

            logger.info(f"블로그 글 생성 완료: {len(article.content)}자")
            return article

        except Exception as e:
            logger.error(f"블로그 글 생성 실패: {e}")
            raise

    async def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        """Google Gemini API 비동기 호출 (네이티브 방식)"""
        # Gemini는 system prompt를 별도로 받지 않으므로 user prompt에 합침
        combined_prompt = f"{system_prompt}\n\n{user_prompt}"

        # 네이티브 비동기 메소드 사용
        response = await self.model.generate_content_async(
            combined_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=4000,
                # JSON 응답을 보장하는 옵션 추가
                response_mime_type="application/json",
            )
        )
        return response.text

    def _create_blog_writing_system_prompt(self, tone: str, target_audience: str) -> str:
        """블로그 글 작성용 시스템 프롬프트 생성"""
        return f"""당신은 전문적인 블로그 작가입니다. 다음 조건에 맞춰 고품질의 블로그 글을 작성해주세요:

**글의 톤앤매너**: {tone}
**타겟 독자**: {target_audience}

**글 작성 원칙**:
1. 수집된 정보를 바탕으로 하되, 단순 복사가 아닌 창작적 글쓰기
2. 논리적이고 읽기 쉬운 구조로 구성
3. 독자의 관심을 끌고 끝까지 읽을 수 있도록 흥미롭게 작성
4. 정확한 정보 전달과 실용적인 가치 제공
5. SEO를 고려한 키워드 자연스러운 배치

**응답 형식**:
JSON 형태로 다음 구조에 맞춰 응답해주세요:
{{
    "title": "매력적인 블로그 제목",
    "subtitle": "부제목 (선택사항)",
    "sections": [
        {{
            "title": "섹션 제목",
            "content": "섹션 내용 (마크다운 형식)",
            "section_type": "intro|concept|trend|case|opinion|conclusion",
            "image_placeholder": "[이미지: 설명]"
        }}
    ],
    "meta_tags": ["태그1", "태그2", "태그3"],
    "keywords": ["키워드1", "키워드2", "키워드3"],
    "category": "카테고리명"
}}"""

    def _create_blog_writing_user_prompt(self, collected_content: CollectedContent, topic: str) -> str:
        """블로그 글 작성용 사용자 프롬프트 생성"""

        # 수집된 정보 요약
        content_summary = f"**주제**: {topic}\n\n"

        if collected_content.basic_concepts:
            content_summary += "**기본 개념 정보**:\n"
            for source in collected_content.basic_concepts[:3]:
                content_summary += f"- {source.title}: {source.summary}\n"
            content_summary += "\n"

        if collected_content.latest_trends:
            content_summary += "**최신 트렌드**:\n"
            for source in collected_content.latest_trends[:3]:
                content_summary += f"- {source.title}: {source.summary}\n"
            content_summary += "\n"

        if collected_content.practical_cases:
            content_summary += "**실무 활용 사례**:\n"
            for source in collected_content.practical_cases[:3]:
                content_summary += f"- {source.title}: {source.summary}\n"
            content_summary += "\n"

        if collected_content.expert_opinions:
            content_summary += "**전문가 의견**:\n"
            for source in collected_content.expert_opinions[:3]:
                content_summary += f"- {source.title}: {source.summary}\n"
            content_summary += "\n"

        return f"""{content_summary}

위 정보를 바탕으로 '{topic}'에 대한 포괄적이고 유익한 블로그 글을 작성해주세요.

**요구사항**:
1. 2000-3000자 분량의 완성된 글
2. 명확한 구조: 서론 → 개념설명 → 트렌드분석 → 활용방안 → 결론
3. 각 섹션마다 적절한 이미지 삽입 위치 표시
4. 읽기 쉽고 실용적인 내용
5. 출처 정보 자연스럽게 언급 (직접 링크 X)

JSON 형식으로 응답해주세요."""

    def _parse_blog_response(self, response: str, topic: str) -> BlogArticle:
        """LLM 응답을 BlogArticle 객체로 파싱"""
        try:
            # JSON 파싱
            data = json.loads(response)

            # 섹션 객체 생성
            sections = []
            full_content = ""
            image_placeholders = []

            for section_data in data.get("sections", []):
                section = BlogSection(
                    title=section_data["title"],
                    content=section_data["content"],
                    section_type=section_data.get("section_type", "general"),
                    image_placeholder=section_data.get("image_placeholder")
                )
                sections.append(section)

                # 전체 콘텐츠 구성
                full_content += f"\n\n## {section.title}\n\n{section.content}"

                # 이미지 플레이스홀더 수집
                if section.image_placeholder:
                    image_placeholders.append(section.image_placeholder)

            # BlogArticle 객체 생성
            article = BlogArticle(
                title=data.get("title", f"{topic}에 대한 완전 가이드"),
                subtitle=data.get("subtitle"),
                content=full_content.strip(),
                sections=sections,
                meta_tags=data.get("meta_tags", [topic]),
                keywords=data.get("keywords", [topic]),
                category=data.get("category", "일반"),
                image_placeholders=image_placeholders
            )

            # 단어 수 및 읽기 시간 계산
            article.calculate_word_count()
            article.estimate_read_time()

            return article

        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {e}")
            # 파싱 실패 시 기본 구조로 폴백
            return self._create_fallback_article(response, topic)

        except Exception as e:
            logger.error(f"블로그 응답 파싱 실패: {e}")
            raise

    def _create_fallback_article(self, content: str, topic: str) -> BlogArticle:
        """JSON 파싱 실패 시 폴백 아티클 생성"""
        sections = [
            BlogSection(
                title="개요",
                content=content[:1000] if len(content) > 1000 else content,
                section_type="intro"
            )
        ]

        article = BlogArticle(
            title=f"{topic}에 대한 종합 가이드",
            content=content,
            sections=sections,
            meta_tags=[topic],
            keywords=[topic],
            category="일반"
        )

        article.calculate_word_count()
        article.estimate_read_time()

        return article


# 클라이언트 싱글톤 인스턴스
_llm_client = None


def get_llm_client(provider: str = "gemini") -> LLMClient:
    """LLM 클라이언트 싱글톤 인스턴스 반환"""
    global _llm_client
    if _llm_client is None or _llm_client.provider != provider.lower():
        _llm_client = LLMClient(provider)
    return _llm_client