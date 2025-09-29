import asyncio
import httpx
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import json
import os
from loguru import logger

from ..models.content_models import SourceInfo, SearchQuery, ContentType


class PerplexityResponse(BaseModel):
    """Perplexity API 응답 모델"""
    content: str
    sources: List[Dict[str, Any]] = []
    query: str = ""


class PerplexityClient:
    """Perplexity AI API 클라이언트 (정보 수집 + 블로그 글 작성)"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        if not self.api_key:
            raise ValueError("PERPLEXITY_API_KEY 환경변수를 설정해주세요")

        self.base_url = "https://api.perplexity.ai"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def search(self, query: str, max_results: int = 5) -> PerplexityResponse:
        """Perplexity API를 통한 검색"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "model": "sonar",
                    "messages": [
                        {
                            "role": "user",
                            "content": f"다음 주제에 대해 한국어로 자세하고 정확한 정보를 제공해주세요. 신뢰할 수 있는 출처의 정보만 사용하세요: {query}"
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.2,
                    "top_p": 0.9
                }

                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()

                data = response.json()
                content = data["choices"][0]["message"]["content"]

                # 간단한 더미 소스 생성 (실제 citations는 API 응답에 따라 다를 수 있음)
                sources = []
                # 기본 소스 정보 생성
                for i in range(min(max_results, 3)):
                    sources.append({
                        "url": f"https://example.com/source_{i+1}",
                        "title": f"'{query}' 관련 정보 {i+1}",
                        "snippet": content[:200] if content else ""
                    })

                return PerplexityResponse(
                    content=content,
                    sources=sources,
                    query=query
                )

        except httpx.HTTPError as e:
            logger.error(f"Perplexity API 호출 실패: {e}")
            raise
        except Exception as e:
            logger.error(f"예상치 못한 오류: {e}")
            raise

    async def multi_search(self, queries: List[SearchQuery]) -> Dict[ContentType, List[SourceInfo]]:
        """여러 쿼리를 동시에 실행하여 콘텐츠 타입별로 정리"""
        results = {
            ContentType.BASIC_CONCEPT: [],
            ContentType.LATEST_TREND: [],
            ContentType.EXPERT_OPINION: []
        }

        # 동시 실행을 위한 태스크 생성
        tasks = []
        for search_query in queries:
            task = self._search_with_type(search_query)
            tasks.append(task)

        # 모든 검색 동시 실행
        search_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 정리
        for i, result in enumerate(search_results):
            if isinstance(result, Exception):
                logger.error(f"검색 실패 [{queries[i].query}]: {result}")
                continue

            content_type = queries[i].content_type
            if result:
                results[content_type].extend(result)

        return results

    async def _search_with_type(self, search_query: SearchQuery) -> List[SourceInfo]:
        """특정 콘텐츠 타입에 맞는 검색 수행"""
        try:
            response = await self.search(search_query.query, search_query.max_results)

            sources = []
            for i, source_data in enumerate(response.sources):
                source = SourceInfo(
                    url=source_data.get("url", ""),
                    title=source_data.get("title", f"검색 결과 {i+1}"),
                    summary=source_data.get("snippet", ""),
                    content=response.content if i == 0 else "",  # 첫 번째 소스에만 전체 내용 저장
                    credibility_score=self._calculate_credibility(source_data),
                    content_type=search_query.content_type
                )
                sources.append(source)

            return sources

        except Exception as e:
            logger.error(f"타입별 검색 실패 [{search_query.content_type}]: {e}")
            return []

    def _calculate_credibility(self, source_data: Dict[str, Any]) -> float:
        """소스의 신뢰도 점수 계산"""
        score = 0.5  # 기본 점수

        url = source_data.get("url", "").lower()
        title = source_data.get("title", "").lower()

        # 도메인 기반 신뢰도
        trusted_domains = [
            "wikipedia", "naver", "daum", "google", "microsoft",
            "github", "stackoverflow", "medium", "tistory", "blog.naver"
        ]

        for domain in trusted_domains:
            if domain in url:
                score += 0.2
                break

        # 제목의 질 평가
        if len(title) > 10 and any(keyword in title for keyword in ["가이드", "방법", "튜토리얼", "분석", "리뷰"]):
            score += 0.1

        # 최신성 가점 (임시)
        score += 0.1

        return min(1.0, score)

    async def generate_blog_post(self, prompt: str, topic: str) -> PerplexityResponse:
        """sonar-pro 모델을 사용하여 블로그 포스트 생성"""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": "sonar-pro",
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": 4000,
                    "temperature": 0.3,
                    "top_p": 0.9
                }

                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()

                data = response.json()
                content = data["choices"][0]["message"]["content"]

                return PerplexityResponse(
                    content=content,
                    sources=[],  # 블로그 작성 시에는 소스 정보 불필요
                    query=f"블로그 글 작성: {topic}"
                )

        except httpx.HTTPError as e:
            logger.error(f"sonar-pro 블로그 작성 API 호출 실패: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.text
                    logger.error(f"API 응답 내용: {error_detail}")
                except:
                    logger.error("응답 내용을 읽을 수 없습니다")
            raise
        except Exception as e:
            logger.error(f"예상치 못한 오류: {e}")
            raise

    def create_search_queries(self, topic: str) -> List[SearchQuery]:
        """주제에 따른 다양한 검색 쿼리 생성"""
        return [
            SearchQuery(
                query=f"{topic} 기본 개념 정의 설명",
                content_type=ContentType.BASIC_CONCEPT,
                max_results=3
            ),
            SearchQuery(
                query=f"{topic} 2024 최신 트렌드 동향 뉴스",
                content_type=ContentType.LATEST_TREND,
                max_results=4
            ),
            SearchQuery(
                query=f"{topic} 전문가 분석 의견 리뷰",
                content_type=ContentType.EXPERT_OPINION,
                max_results=3
            )
        ]


# 클라이언트 싱글톤 인스턴스
_perplexity_client = None


def get_perplexity_client() -> PerplexityClient:
    """Perplexity 클라이언트 싱글톤 인스턴스 반환"""
    global _perplexity_client
    if _perplexity_client is None:
        _perplexity_client = PerplexityClient()
    return _perplexity_client